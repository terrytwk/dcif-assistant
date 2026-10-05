from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from backend.dcif.io import (
    read_chunks,
    read_instrument_profiles,
    read_knowledge_documents,
    read_knowledge_rules,
    read_resource_records,
    read_structured_records,
    snapshot_meta_paths,
)
from backend.dcif.models import StructuredRecord
from backend.dcif.paths import data_path


EXPECTED_RECORD_TYPES = {"instrument", "fee", "guide", "overview_section"}
EXPECTED_INSTRUMENT_CATEGORIES = {"Mass Spectrometry", "NMR Spectroscopy", "Other Instruments"}


@dataclass
class AuditReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, int | str] = field(default_factory=dict)

    def render(self) -> str:
        lines = ["DCIF retrieval audit", f"status: {'ok' if self.ok else 'failed'}"]
        if self.metrics:
            lines.append("")
            lines.append("metrics:")
            for key, value in self.metrics.items():
                lines.append(f"  {key}: {value}")
        if self.errors:
            lines.append("")
            lines.append("errors:")
            lines.extend(f"  - {error}" for error in self.errors)
        if self.warnings:
            lines.append("")
            lines.append("warnings:")
            lines.extend(f"  - {warning}" for warning in self.warnings)
        return "\n".join(lines)


def aggregate_instrument_categories(records: list[StructuredRecord]) -> set[str]:
    return {
        record.category
        for record in records
        if record.record_type == "instrument" and record.name.endswith(" instruments")
    }


def audit_retrieval_artifacts(
    *,
    raw_dir: Path = data_path("raw"),
    chunks_path: Path = data_path("chunks", "chunks.jsonl"),
    records_path: Path = data_path("structured", "records.jsonl"),
    documents_path: Path = data_path("structured", "documents.jsonl"),
    instruments_path: Path = data_path("structured", "instruments.jsonl"),
    resources_path: Path = data_path("structured", "resources.jsonl"),
    rules_path: Path = data_path("structured", "rules.jsonl"),
    min_pdf_snapshots: int = 20,
    min_chunks: int = 100,
    min_structured_records: int = 20,
    min_knowledge_documents: int = 20,
    min_instrument_profiles: int = 10,
    min_resources: int = 20,
    min_rules: int = 1,
) -> AuditReport:
    errors: list[str] = []
    warnings: list[str] = []

    snapshot_paths = snapshot_meta_paths(raw_dir)
    chunks = read_chunks(chunks_path)
    records = read_structured_records(records_path)
    documents = read_knowledge_documents(documents_path)
    instruments = read_instrument_profiles(instruments_path)
    resources = read_resource_records(resources_path)
    rules = read_knowledge_rules(rules_path)

    doc_type_counts = Counter()
    for path in snapshot_paths:
        try:
            import json

            doc_type_counts[json.loads(path.read_text(encoding="utf-8"))["document_type"]] += 1
        except Exception as exc:
            errors.append(f"Could not read snapshot metadata {path}: {exc}")

    record_type_counts = Counter(record.record_type for record in records)
    instrument_categories = aggregate_instrument_categories(records)
    records_by_category = defaultdict(int)
    for record in records:
        records_by_category[record.category] += 1

    metrics: dict[str, int | str] = {
        "snapshots": len(snapshot_paths),
        "html_snapshots": doc_type_counts.get("html", 0),
        "pdf_snapshots": doc_type_counts.get("pdf", 0),
        "chunks": len(chunks),
        "structured_records": len(records),
        "knowledge_documents": len(documents),
        "instrument_profiles": len(instruments),
        "resources": len(resources),
        "rules": len(rules),
        "instrument_records": record_type_counts.get("instrument", 0),
        "fee_records": record_type_counts.get("fee", 0),
        "guide_records": record_type_counts.get("guide", 0),
        "overview_section_records": record_type_counts.get("overview_section", 0),
        "instrument_categories": ", ".join(sorted(instrument_categories)) or "none",
    }

    if doc_type_counts.get("html", 0) != 1:
        errors.append("Expected exactly one HTML source snapshot: the DCIF overview page.")
    if doc_type_counts.get("pdf", 0) < min_pdf_snapshots:
        errors.append(f"Expected at least {min_pdf_snapshots} linked PDF snapshots.")
    if len(chunks) < min_chunks:
        errors.append(f"Expected at least {min_chunks} retrieval chunks.")
    if len(records) < min_structured_records:
        errors.append(f"Expected at least {min_structured_records} structured records.")
    if len(documents) < min_knowledge_documents:
        errors.append(f"Expected at least {min_knowledge_documents} knowledge documents.")
    if len(instruments) < min_instrument_profiles:
        errors.append(f"Expected at least {min_instrument_profiles} instrument profiles.")
    if len(resources) < min_resources:
        errors.append(f"Expected at least {min_resources} resource records.")
    if len(rules) < min_rules:
        errors.append(f"Expected at least {min_rules} knowledge rules.")

    missing_record_types = EXPECTED_RECORD_TYPES - set(record_type_counts)
    if missing_record_types:
        errors.append(f"Missing structured record types: {', '.join(sorted(missing_record_types))}.")

    missing_categories = EXPECTED_INSTRUMENT_CATEGORIES - instrument_categories
    if missing_categories:
        errors.append(f"Missing aggregate instrument categories: {', '.join(sorted(missing_categories))}.")

    if record_type_counts.get("staff", 0) == 0:
        warnings.append("No staff records were extracted.")
    if records_by_category.get("Mass Spectrometry", 0) < 3:
        warnings.append("Mass Spectrometry structured coverage is unexpectedly small.")
    if not any(rule.instrument_id == "gcms" and rule.condition in {"aqueous_sample", "aqueous_or_acid_sample"} for rule in rules):
        warnings.append("No explicit GC/MS aqueous-sample constraint was extracted.")

    return AuditReport(ok=not errors, errors=errors, warnings=warnings, metrics=metrics)
