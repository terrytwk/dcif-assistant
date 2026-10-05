from __future__ import annotations

import hashlib
import sqlite3
from collections import deque
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse, urldefrag

import httpx
from bs4 import BeautifulSoup

from backend.dcif.config import load_crawl_config
from backend.dcif.io import write_json
from backend.dcif.models import CrawlConfig, DocumentType, SourceSnapshot
from backend.dcif.paths import config_path as default_config_path
from backend.dcif.paths import data_path


class CrawlFetchError(RuntimeError):
    def __init__(self, url: str, message: str) -> None:
        super().__init__(f"Failed to fetch {url}: {message}")
        self.url = url


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def document_type_for(url: str, content_type: str | None, content: bytes | None = None) -> DocumentType:
    lower_url = url.lower()
    lower_path = urlparse(url).path.lower()
    lower_type = (content_type or "").lower()
    if lower_path.endswith(".pdf") or "application/pdf" in lower_type or (content or b"").startswith(b"%PDF"):
        return "pdf"
    if "html" in lower_type or lower_url.endswith(("/", ".html", ".htm")):
        return "html"
    return "text"


def is_allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = parsed.hostname or ""
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)


def canonical_url(url: str) -> str:
    parsed = urlparse(urldefrag(url)[0])
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{hostname}{port}"
    path = parsed.path or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunparse((scheme, netloc, path, "", query, ""))


def is_root_url(url: str, root_urls: set[str]) -> bool:
    return canonical_url(url) in root_urls


def looks_like_linked_file(url: str, extensions: list[str]) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(extension.lower()) for extension in extensions)


def normalize_download_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname.endswith("dropbox.com"):
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        params["dl"] = "1"
        return urlunparse(parsed._replace(query=urlencode(params)))
    return url


def should_fetch_url(url: str, *, root_urls: set[str], config: CrawlConfig) -> bool:
    if is_root_url(url, root_urls):
        return True
    if config.fetch_linked_files and looks_like_linked_file(url, config.linked_file_extensions):
        return True
    return False


def extract_links(base_url: str, content: bytes) -> list[tuple[str, str]]:
    soup = BeautifulSoup(content, "html.parser")
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urldefrag(urljoin(base_url, href))[0]
        label = " ".join(anchor.get_text(" ", strip=True).split())
        links.append((absolute, label))
    return links


def init_crawl_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_records (
                url TEXT PRIMARY KEY,
                title TEXT,
                document_type TEXT NOT NULL,
                raw_path TEXT NOT NULL,
                content_type TEXT,
                crawl_timestamp TEXT NOT NULL,
                source_hash TEXT NOT NULL
            )
            """
        )


def save_record(db_path: Path, snapshot: SourceSnapshot) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO crawl_records (
                url, title, document_type, raw_path, content_type, crawl_timestamp, source_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                document_type=excluded.document_type,
                raw_path=excluded.raw_path,
                content_type=excluded.content_type,
                crawl_timestamp=excluded.crawl_timestamp,
                source_hash=excluded.source_hash
            """,
            (
                snapshot.url,
                snapshot.title,
                snapshot.document_type,
                snapshot.raw_path,
                snapshot.content_type,
                snapshot.crawl_timestamp.isoformat(),
                snapshot.source_hash,
            ),
        )


def crawl_sources(
    *,
    config: CrawlConfig | None = None,
    config_path: Path = default_config_path("sources.yaml"),
    raw_dir: Path = data_path("raw"),
    db_path: Path = data_path("crawl.db"),
) -> list[SourceSnapshot]:
    cfg = config or load_crawl_config(config_path)
    root_urls = {canonical_url(str(url)) for url in cfg.root_urls}
    init_crawl_db(db_path)
    raw_dir.mkdir(parents=True, exist_ok=True)

    queue: deque[str] = deque(str(url) for url in cfg.root_urls)
    seen: set[str] = set()
    link_titles: dict[str, str] = {}
    snapshots: list[SourceSnapshot] = []

    headers = {"User-Agent": cfg.user_agent}
    with httpx.Client(headers=headers, follow_redirects=True, timeout=cfg.request_timeout_seconds) as client:
        while queue and len(seen) < cfg.max_pages:
            url = queue.popleft()
            url = normalize_download_url(urldefrag(url)[0])
            if url in seen or not should_fetch_url(url, root_urls=root_urls, config=cfg):
                continue
            if is_root_url(url, root_urls) and not is_allowed_domain(url, cfg.allowed_domains):
                continue
            seen.add(url)

            try:
                response = client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                if not snapshots and not queue:
                    raise CrawlFetchError(url, str(exc)) from exc
                continue
            final_url = str(response.url)
            if is_root_url(url, root_urls) and not is_allowed_domain(final_url, cfg.allowed_domains):
                continue
            content = response.content
            content_type = response.headers.get("content-type")
            doc_type = document_type_for(url, content_type, content)
            source_hash = hash_bytes(content)
            suffix = ".pdf" if doc_type == "pdf" else ".html" if doc_type == "html" else ".txt"
            base = stable_id(url)
            raw_path = raw_dir / f"{base}{suffix}"
            raw_path.write_bytes(content)

            title = None
            if doc_type == "html":
                soup = BeautifulSoup(content, "html.parser")
                if soup.title and soup.title.string:
                    title = " ".join(soup.title.string.split())
                for link, label in extract_links(str(response.url), content):
                    normalized_link = normalize_download_url(link)
                    if is_root_url(url, root_urls):
                        if cfg.follow_html_links and is_allowed_domain(normalized_link, cfg.allowed_domains):
                            if label:
                                link_titles[normalized_link] = label
                            queue.append(normalized_link)
                        elif cfg.fetch_linked_files and looks_like_linked_file(
                            normalized_link, cfg.linked_file_extensions
                        ):
                            if label:
                                link_titles[normalized_link] = label
                            queue.append(normalized_link)
            else:
                title = link_titles.get(url)

            snapshot = SourceSnapshot(
                url=url,
                title=title,
                document_type=doc_type,
                raw_path=str(raw_path),
                content_type=content_type,
                source_hash=source_hash,
            )
            write_json(raw_dir / f"{base}.meta.json", snapshot)
            save_record(db_path, snapshot)
            snapshots.append(snapshot)

    return snapshots
