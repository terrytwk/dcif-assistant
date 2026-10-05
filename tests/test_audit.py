from datetime import UTC, datetime

from backend.dcif.audit import audit_retrieval_artifacts
from backend.dcif.io import write_json, write_jsonl
from backend.dcif.models import (
    Chunk,
    InstrumentProfile,
    KnowledgeDocument,
    KnowledgeRule,
    ResourceRecord,
    SourceSnapshot,
    StructuredRecord,
)


def make_record(record_type: str, category: str, name: str) -> StructuredRecord:
    return StructuredRecord(
        record_id=f"{record_type}-{category}-{name}",
        record_type=record_type,  # type: ignore[arg-type]
        category=category,
        name=name,
        text=f"{record_type} {category} {name}",
        source_url="https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
        source_title="DCIF",
        section_heading=category,
        crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source_hash="hash",
    )


def test_audit_fails_when_structured_inventory_is_missing(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    chunks_path = tmp_path / "chunks" / "chunks.jsonl"
    records_path = tmp_path / "structured" / "records.jsonl"
    documents_path = tmp_path / "structured" / "documents.jsonl"
    instruments_path = tmp_path / "structured" / "instruments.jsonl"
    resources_path = tmp_path / "structured" / "resources.jsonl"
    rules_path = tmp_path / "structured" / "rules.jsonl"
    write_json(
        raw_dir / "overview.meta.json",
        SourceSnapshot(
            url="https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
            document_type="html",
            raw_path=str(raw_dir / "overview.html"),
            source_hash="hash",
        ),
    )
    write_jsonl(chunks_path, [])
    write_jsonl(records_path, [])

    report = audit_retrieval_artifacts(
        raw_dir=raw_dir,
        chunks_path=chunks_path,
        records_path=records_path,
        min_pdf_snapshots=0,
        min_chunks=1,
        min_structured_records=1,
    )

    assert not report.ok
    assert any("structured records" in error for error in report.errors)


def test_audit_passes_with_expected_artifacts(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    chunks_path = tmp_path / "chunks" / "chunks.jsonl"
    records_path = tmp_path / "structured" / "records.jsonl"
    documents_path = tmp_path / "structured" / "documents.jsonl"
    instruments_path = tmp_path / "structured" / "instruments.jsonl"
    resources_path = tmp_path / "structured" / "resources.jsonl"
    rules_path = tmp_path / "structured" / "rules.jsonl"
    write_json(
        raw_dir / "overview.meta.json",
        SourceSnapshot(
            url="https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
            document_type="html",
            raw_path=str(raw_dir / "overview.html"),
            source_hash="hash",
        ),
    )
    write_json(
        raw_dir / "guide.meta.json",
        SourceSnapshot(
            url="https://example.com/guide.pdf",
            document_type="pdf",
            raw_path=str(raw_dir / "guide.pdf"),
            source_hash="hash",
        ),
    )
    records = [
        make_record("instrument", "Mass Spectrometry", "Mass Spectrometry instruments"),
        make_record("instrument", "NMR Spectroscopy", "NMR Spectroscopy instruments"),
        make_record("instrument", "Other Instruments", "Other Instruments instruments"),
        make_record("fee", "Mass Spectrometers", "LCMS"),
        make_record("guide", "Mass Spectrometry (MS)", "Quick start guide - LCMS"),
        make_record("overview_section", "Training Requests", "Training Requests"),
    ]
    chunks = [
        Chunk(
            chunk_id=record.record_id,
            source_url=record.source_url,
            source_title=record.source_title,
            document_type="structured",
            section_heading=record.section_heading,
            crawl_timestamp=record.crawl_timestamp,
            source_hash=record.source_hash,
            text=record.text,
        )
        for record in records
    ]
    write_jsonl(records_path, records)
    write_jsonl(chunks_path, chunks)
    write_jsonl(
        documents_path,
        [
            KnowledgeDocument(
                document_id="overview",
                source_url="https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
                source_title="DCIF",
                document_type="html",
                knowledge_type="overview",
                source_hash="hash",
                crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
    )
    write_jsonl(
        instruments_path,
        [
            InstrumentProfile(instrument_id="gcms", name="GCMS", category="Mass Spectrometry"),
        ],
    )
    write_jsonl(
        resources_path,
        [
            ResourceRecord(
                resource_id="gcms-guide",
                title="Quick start guide - GCMS",
                resource_type="quick_start",
                category="Mass Spectrometry (MS)",
                source_url="https://example.com/guide.pdf",
                source_title="Quick start guide - GCMS",
                related_instrument_ids=["gcms"],
            )
        ],
    )
    write_jsonl(
        rules_path,
        [
            KnowledgeRule(
                rule_id="gcms-water",
                instrument_id="gcms",
                instrument_name="GCMS",
                severity="hard_constraint",
                condition="aqueous_sample",
                statement="Avoid aqueous samples.",
                source_url="https://example.com/guide.pdf",
                source_title="Quick start guide - GCMS",
                section_id="section",
                source_hash="hash",
                crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
    )

    report = audit_retrieval_artifacts(
        raw_dir=raw_dir,
        chunks_path=chunks_path,
        records_path=records_path,
        documents_path=documents_path,
        instruments_path=instruments_path,
        resources_path=resources_path,
        rules_path=rules_path,
        min_pdf_snapshots=1,
        min_chunks=1,
        min_structured_records=1,
        min_knowledge_documents=1,
        min_instrument_profiles=1,
        min_resources=1,
        min_rules=1,
    )

    assert report.ok
