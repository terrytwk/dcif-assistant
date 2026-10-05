from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from backend.dcif.models import (
    Chunk,
    InstrumentProfile,
    KnowledgeDocument,
    KnowledgeRule,
    KnowledgeSection,
    NormalizedDocument,
    ResourceRecord,
    SourceSnapshot,
    StructuredRecord,
    ensure_parent,
)

T = TypeVar("T", bound=BaseModel)


def write_json(path: Path, model: BaseModel) -> None:
    ensure_parent(path)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def read_json(path: Path, model_type: type[T]) -> T:
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[BaseModel]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(row.model_dump_json())
            handle.write("\n")


def read_chunks(path: Path) -> list[Chunk]:
    if not path.exists():
        return []
    chunks: list[Chunk] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                chunks.append(Chunk.model_validate_json(line))
    return chunks


def read_structured_records(path: Path) -> list[StructuredRecord]:
    if not path.exists():
        return []
    records: list[StructuredRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(StructuredRecord.model_validate_json(line))
    return records


def read_knowledge_documents(path: Path) -> list[KnowledgeDocument]:
    return read_jsonl_model(path, KnowledgeDocument)


def read_knowledge_sections(path: Path) -> list[KnowledgeSection]:
    return read_jsonl_model(path, KnowledgeSection)


def read_instrument_profiles(path: Path) -> list[InstrumentProfile]:
    return read_jsonl_model(path, InstrumentProfile)


def read_resource_records(path: Path) -> list[ResourceRecord]:
    return read_jsonl_model(path, ResourceRecord)


def read_knowledge_rules(path: Path) -> list[KnowledgeRule]:
    return read_jsonl_model(path, KnowledgeRule)


def read_jsonl_model(path: Path, model_type: type[T]) -> list[T]:
    if not path.exists():
        return []
    rows: list[T] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(model_type.model_validate_json(line))
    return rows


def snapshot_meta_paths(raw_dir: Path) -> list[Path]:
    return sorted(raw_dir.glob("*.meta.json"))


def normalized_doc_paths(normalized_dir: Path) -> list[Path]:
    return sorted(normalized_dir.glob("*.json"))


def load_snapshot(meta_path: Path) -> SourceSnapshot:
    return read_json(meta_path, SourceSnapshot)


def load_normalized(path: Path) -> NormalizedDocument:
    return read_json(path, NormalizedDocument)


def dump_json(path: Path, payload: dict) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
