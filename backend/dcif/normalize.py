from __future__ import annotations

import re
from pathlib import Path

from backend.dcif.io import load_snapshot, snapshot_meta_paths, write_json
from backend.dcif.models import NormalizedDocument, NormalizedSection, SourceSnapshot
from backend.dcif.paths import data_path
from backend.dcif.parse_html import parse_html_sections
from backend.dcif.parse_pdf import parse_pdf_sections


WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean_text(value: str) -> str:
    value = WHITESPACE_RE.sub(" ", value)
    value = BLANK_LINES_RE.sub("\n\n", value)
    return value.strip()


def normalize_sections(sections: list[NormalizedSection]) -> list[NormalizedSection]:
    normalized: list[NormalizedSection] = []
    for section in sections:
        text = clean_text(section.text)
        heading = clean_text(section.heading) or "Untitled section"
        if text:
            normalized.append(
                NormalizedSection(heading=heading, text=text, page=section.page)
            )
    return normalized


def normalize_snapshot(snapshot: SourceSnapshot) -> NormalizedDocument:
    raw_path = Path(snapshot.raw_path)
    if snapshot.document_type == "pdf":
        title, sections = parse_pdf_sections(raw_path)
    elif snapshot.document_type == "html":
        title, sections = parse_html_sections(raw_path.read_bytes())
    else:
        title = snapshot.title or raw_path.stem
        sections = [NormalizedSection(heading=title, text=raw_path.read_text(encoding="utf-8", errors="ignore"))]

    return NormalizedDocument(
        source_url=snapshot.url,
        source_title=snapshot.title or title,
        document_type=snapshot.document_type,
        crawl_timestamp=snapshot.crawl_timestamp,
        source_hash=snapshot.source_hash,
        sections=normalize_sections(sections),
    )


def normalize_all(
    *,
    raw_dir: Path = data_path("raw"),
    normalized_dir: Path = data_path("normalized"),
) -> list[NormalizedDocument]:
    normalized_dir.mkdir(parents=True, exist_ok=True)
    docs: list[NormalizedDocument] = []
    for meta_path in snapshot_meta_paths(raw_dir):
        snapshot = load_snapshot(meta_path)
        doc = normalize_snapshot(snapshot)
        output_path = normalized_dir / f"{meta_path.stem.removesuffix('.meta')}.json"
        write_json(output_path, doc)
        docs.append(doc)
    return docs
