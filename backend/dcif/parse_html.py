from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from backend.dcif.models import NormalizedSection


NOISE_SELECTORS = ["script", "style", "noscript", "svg", "form", "nav", "footer"]


def parse_html_sections(content: bytes) -> tuple[str, list[NormalizedSection]]:
    soup = BeautifulSoup(content, "html.parser")
    for selector in NOISE_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    title = "Untitled page"
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.split())
    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        h1_text = h1.get_text(" ", strip=True)
        if h1_text:
            title = h1_text

    root = soup.body or soup
    sections: list[NormalizedSection] = []
    current_heading = title
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_parts
        text = "\n".join(part for part in current_parts if part).strip()
        if text:
            sections.append(NormalizedSection(heading=current_heading, text=text))
        current_parts = []

    for node in root.descendants:
        if not isinstance(node, Tag):
            continue
        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            flush()
            heading = node.get_text(" ", strip=True)
            if heading:
                current_heading = heading
            continue
        if node.name in {"p", "li", "td", "th"}:
            text = node.get_text(" ", strip=True)
            if text:
                current_parts.append(text)

    flush()
    if not sections:
        fallback = root.get_text("\n", strip=True)
        if fallback:
            sections.append(NormalizedSection(heading=title, text=fallback))
    return title, sections
