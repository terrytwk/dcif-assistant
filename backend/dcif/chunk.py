from __future__ import annotations

import hashlib
from pathlib import Path

from backend.dcif.io import load_normalized, normalized_doc_paths, write_jsonl
from backend.dcif.models import Chunk, NormalizedDocument, NormalizedSection
from backend.dcif.paths import data_path
from backend.dcif.structured_extract import extract_structured_records, records_to_chunks


def chunk_id_for(*parts: object) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def word_windows(text: str, *, max_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]

    step = max(1, max_words - overlap_words)
    windows: list[str] = []
    for start in range(0, len(words), step):
        window = words[start : start + max_words]
        if window:
            windows.append(" ".join(window))
        if start + max_words >= len(words):
            break
    return windows


def chunk_section(
    doc: NormalizedDocument,
    section: NormalizedSection,
    *,
    max_words: int,
    overlap_words: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for index, text in enumerate(
        word_windows(section.text, max_words=max_words, overlap_words=overlap_words)
    ):
        chunk_id = chunk_id_for(doc.source_url, doc.source_hash, section.heading, section.page, index, text)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                source_url=doc.source_url,
                source_title=doc.source_title,
                document_type=doc.document_type,
                section_heading=section.heading,
                page=section.page,
                crawl_timestamp=doc.crawl_timestamp,
                source_hash=doc.source_hash,
                text=text,
            )
        )
    return chunks


def chunk_document(
    doc: NormalizedDocument,
    *,
    max_words: int = 180,
    overlap_words: int = 35,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in doc.sections:
        chunks.extend(
            chunk_section(doc, section, max_words=max_words, overlap_words=overlap_words)
        )
    return chunks


def chunk_all(
    *,
    normalized_dir: Path = data_path("normalized"),
    chunks_path: Path = data_path("chunks", "chunks.jsonl"),
    records_path: Path = data_path("structured", "records.jsonl"),
    max_words: int = 180,
    overlap_words: int = 35,
    include_structured_records: bool = True,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in normalized_doc_paths(normalized_dir):
        chunks.extend(
            chunk_document(
                load_normalized(path),
                max_words=max_words,
                overlap_words=overlap_words,
            )
        )
    if include_structured_records:
        records = extract_structured_records(normalized_dir=normalized_dir, records_path=records_path)
        chunks.extend(records_to_chunks(records))
    write_jsonl(chunks_path, chunks)
    return chunks
