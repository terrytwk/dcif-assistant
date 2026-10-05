from __future__ import annotations

from pathlib import Path

import pymupdf

from backend.dcif.models import NormalizedSection


def parse_pdf_sections(path: Path) -> tuple[str, list[NormalizedSection]]:
    doc = pymupdf.open(path)
    metadata_title = (doc.metadata or {}).get("title") or path.stem
    sections: list[NormalizedSection] = []
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        text = page.get_text("text").strip()
        if text:
            sections.append(
                NormalizedSection(
                    heading=f"{metadata_title} page {page_index + 1}",
                    text=text,
                    page=page_index + 1,
                )
            )
    return metadata_title, sections
