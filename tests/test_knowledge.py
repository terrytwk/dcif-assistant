from datetime import UTC, datetime

from backend.dcif.io import write_jsonl
from backend.dcif.knowledge import build_knowledge_artifacts
from backend.dcif.models import NormalizedDocument, NormalizedSection, StructuredRecord


def normalized_doc(
    source_url: str,
    source_title: str,
    sections: list[NormalizedSection],
    *,
    document_type: str = "pdf",
) -> NormalizedDocument:
    return NormalizedDocument(
        source_url=source_url,
        source_title=source_title,
        document_type=document_type,  # type: ignore[arg-type]
        crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source_hash=f"hash-{source_title}",
        sections=sections,
    )


def structured_record(
    record_id: str,
    record_type: str,
    category: str,
    name: str,
    text: str,
    fields: dict[str, str] | None = None,
) -> StructuredRecord:
    return StructuredRecord(
        record_id=record_id,
        record_type=record_type,  # type: ignore[arg-type]
        category=category,
        name=name,
        text=text,
        source_url="https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
        source_title="DCIF",
        section_heading=category,
        crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source_hash="overview-hash",
        fields=fields or {},
    )


def test_builds_instrument_document_resource_and_rule_hierarchy(tmp_path) -> None:
    normalized_dir = tmp_path / "normalized"
    records_path = tmp_path / "structured" / "records.jsonl"
    normalized_dir.mkdir()

    overview = normalized_doc(
        "https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
        "DCIF",
        [NormalizedSection(heading="Mass Spectrometry (MS)", text="GC/MS The GCMS is available.")],
        document_type="html",
    )
    guide = normalized_doc(
        "https://example.com/gcms.pdf",
        "Quick start guide - GCMS",
        [
            NormalizedSection(
                heading="GCMS page 1",
                page=1,
                text=(
                    "Sample preparation: All samples must be completely dissolved in an organic solvent. "
                    "Avoid using water and acid containing samples, which will damage the column."
                ),
            )
        ],
    )
    (normalized_dir / "overview.json").write_text(overview.model_dump_json(), encoding="utf-8")
    (normalized_dir / "gcms.json").write_text(guide.model_dump_json(), encoding="utf-8")

    write_jsonl(
        records_path,
        [
            structured_record(
                "gcms",
                "instrument",
                "Mass Spectrometry",
                "GC/MS",
                "DCIF instrument inventory. Instrument: GC/MS.",
            ),
            structured_record(
                "gcms-guide",
                "guide",
                "Mass Spectrometry (MS)",
                "Quick start guide - GCMS",
                "DCIF linked guide or application note. Title: Quick start guide - GCMS.",
                {"guide_title": "Quick start guide - GCMS"},
            ),
        ],
    )

    artifacts = build_knowledge_artifacts(normalized_dir=normalized_dir, records_path=records_path)

    gcms = next(item for item in artifacts.instruments if item.instrument_id == "gcms")
    assert gcms.related_document_ids
    assert gcms.related_resource_ids
    assert any(resource.document_id in gcms.related_document_ids for resource in artifacts.resources)
    assert any(rule.instrument_id == "gcms" and rule.condition == "aqueous_or_acid_sample" for rule in artifacts.rules)
    assert any(section.section_type == "sample_preparation" for section in artifacts.sections)
