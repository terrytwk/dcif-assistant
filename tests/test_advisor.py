from datetime import UTC, datetime
import asyncio
import json

from backend.dcif.advisor import (
    advisory_payload,
    build_dcif_catalog,
    build_advisory_context,
    classify_query,
    extract_instrument,
    extractive_advisory_answer,
    extractive_catalog_answer,
    is_advisory_intent,
    profile_query,
    synthesize_advice,
)
from backend.dcif.hybrid_search import HybridSearch
from backend.dcif.io import write_jsonl
from backend.dcif.models import ChatAnswer, Chunk, KnowledgeRule, StructuredRecord


class BadConstraintLLMClient:
    async def generate_json(self, **kwargs):
        return ChatAnswer(answer="Yes, you can use GC-MS for brewed coffee.", citations=[], confidence="high")

    async def generate_text(self, **kwargs):
        return "Yes, you can use GC-MS for brewed coffee."


def record(
    record_id: str,
    category: str,
    name: str,
    text: str,
    *,
    record_type: str = "instrument",
    fields: dict[str, str] | None = None,
) -> StructuredRecord:
    return StructuredRecord(
        record_id=record_id,
        record_type=record_type,
        category=category,
        name=name,
        text=text,
        source_url="https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
        source_title="DCIF",
        section_heading="instrument",
        crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source_hash="hash",
        fields=fields or {},
    )


def test_classify_recommendation_question() -> None:
    intent = classify_query("Which tool should I use for coffee?")

    assert intent == "instrument_recommendation"
    assert is_advisory_intent(intent)


def test_classify_inventory_question_is_not_advisory() -> None:
    intent = classify_query("What mass spectrometry instruments do you have?")

    assert intent == "inventory_lookup"
    assert is_advisory_intent(intent)


def test_classify_instrument_sample_question_is_advisory() -> None:
    intent = classify_query("Can I put raw coffee into GC-MS?")

    assert intent == "instrument_procedure"
    assert is_advisory_intent(intent)
    assert extract_instrument("Can I put raw coffee into GC-MS?") == "GC/MS"


def test_profile_query_recognizes_coffee() -> None:
    profile = profile_query("Which instrument should I use for coffee?")

    assert profile.sample == "coffee"
    assert any("volatile aroma" in goal for goal in profile.likely_goals)
    assert "LCMS" in profile.search_terms


def test_build_advisory_context_includes_candidate_records_and_evidence(tmp_path) -> None:
    records_path = tmp_path / "structured" / "records.jsonl"
    records = [
        record(
            "ms-summary",
            "Mass Spectrometry",
            "Mass Spectrometry instruments",
            "DCIF instrument inventory summary. Available instruments: LCMS, GC/MS, ICP-MS.",
        ),
        record(
            "other-summary",
            "Other Instruments",
            "Other Instruments instruments",
            "DCIF instrument inventory summary. Available instruments: HPLC, FTIR.",
        ),
    ]
    write_jsonl(records_path, records)

    chunks = [
        Chunk(
            chunk_id="lcms-guide",
            source_url="https://example.com/lcms.pdf",
            source_title="Quick start guide - LCMS",
            document_type="pdf",
            section_heading="LCMS guide",
            crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_hash="hash",
            text="LCMS supports small molecule analysis with chromatography and mass detection.",
        ),
        Chunk(
            chunk_id="gcms-guide",
            source_url="https://example.com/gcms.pdf",
            source_title="Quick start guide - GCMS",
            document_type="pdf",
            section_heading="GCMS guide",
            crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_hash="hash",
            text="GC/MS is useful for volatile compound analysis.",
        ),
    ]
    searcher = HybridSearch(
        keyword_db_path=tmp_path / "keyword.sqlite",
        vector_dir=tmp_path / "chroma",
    )
    searcher.rebuild(chunks)

    context = build_advisory_context(
        "Which tool should I use for coffee?",
        searcher=searcher,
        records_path=records_path,
        evidence_limit=6,
    )

    assert context.intent == "instrument_recommendation"
    assert [candidate.name for candidate in context.candidate_records] == [
        "Mass Spectrometry instruments",
        "Other Instruments instruments",
    ]
    assert {item.chunk_id for item in context.evidence} >= {"ms-summary", "other-summary"}


def test_instrument_procedure_context_prioritizes_matching_guide_chunk(tmp_path) -> None:
    records_path = tmp_path / "structured" / "records.jsonl"
    chunks_path = tmp_path / "chunks" / "chunks.jsonl"
    records = [
        record(
            "gcms-instrument",
            "Mass Spectrometry",
            "GC/MS",
            "DCIF instrument inventory. Instrument: GC/MS.",
        ),
        record(
            "gcms-guide-record",
            "Mass Spectrometry (MS)",
            "Quick start guide - GCMS",
            "DCIF linked guide or application note. Title: Quick start guide - GCMS.",
            record_type="guide",
            fields={"guide_title": "Quick start guide - GCMS"},
        ),
    ]
    write_jsonl(records_path, records)

    chunks = [
        Chunk(
            chunk_id="gcms-prep",
            source_url="https://example.com/gcms.pdf",
            source_title="Quick start guide - GCMS",
            document_type="pdf",
            section_heading="GCMS page 1",
            crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_hash="hash",
            text=(
                "Sample preparation: All samples must be completely dissolved in an organic "
                "solvent. Avoid using water and acid containing samples because they will "
                "damage the column."
            ),
        ),
        Chunk(
            chunk_id="nmr-diffusion",
            source_url="https://example.com/nmr.pdf",
            source_title="Diffusion Experiments",
            document_type="pdf",
            section_heading="Diffusion spectroscopy",
            crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_hash="hash",
            text="Coffee samples can be studied with unrelated NMR diffusion workflows.",
        ),
    ]
    write_jsonl(chunks_path, chunks)
    searcher = HybridSearch(
        keyword_db_path=tmp_path / "keyword.sqlite",
        vector_dir=tmp_path / "chroma",
    )
    searcher.rebuild(chunks)

    context = build_advisory_context(
        "Can I put raw coffee into GC-MS?",
        searcher=searcher,
        records_path=records_path,
        chunks_path=chunks_path,
        evidence_limit=6,
    )

    assert context.intent == "instrument_procedure"
    assert context.evidence[0].chunk_id == "gcms-prep"
    assert "water" in context.evidence[0].text
    assert "nmr-diffusion" not in {item.chunk_id for item in context.evidence[:3]}


def test_instrument_procedure_context_prioritizes_matching_knowledge_rule(tmp_path) -> None:
    records_path = tmp_path / "structured" / "records.jsonl"
    chunks_path = tmp_path / "chunks" / "chunks.jsonl"
    rules_path = tmp_path / "structured" / "rules.jsonl"
    records = [
        record(
            "gcms-instrument",
            "Mass Spectrometry",
            "GC/MS",
            "DCIF instrument inventory. Instrument: GC/MS.",
        )
    ]
    write_jsonl(records_path, records)
    write_jsonl(
        rules_path,
        [
            KnowledgeRule(
                rule_id="gcms-water-rule",
                instrument_id="gcms",
                instrument_name="GC/MS",
                severity="hard_constraint",
                condition="aqueous_sample",
                statement="Avoid using water and acid containing samples because they will damage the column.",
                recommendation="Do not use GC/MS for aqueous samples unless DCIF staff approve an alternate workflow.",
                source_url="https://example.com/gcms.pdf",
                source_title="Quick start guide - GCMS",
                section_id="gcms-section",
                page=1,
                source_hash="hash",
                crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
    )
    chunks = [
        Chunk(
            chunk_id="generic-gcms",
            source_url="https://example.com/gcms.pdf",
            source_title="Quick start guide - GCMS",
            document_type="pdf",
            section_heading="GCMS page 1",
            crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_hash="hash",
            text="GC/MS is useful for volatile compound analysis.",
        )
    ]
    write_jsonl(chunks_path, chunks)
    searcher = HybridSearch(
        keyword_db_path=tmp_path / "keyword.sqlite",
        vector_dir=tmp_path / "chroma",
    )
    searcher.rebuild(chunks)

    context = build_advisory_context(
        "Can I put raw coffee into GC-MS?",
        searcher=searcher,
        records_path=records_path,
        chunks_path=chunks_path,
        rules_path=rules_path,
        evidence_limit=6,
    )

    assert context.evidence[0].chunk_id == "gcms-water-rule"
    assert context.rules[0].severity == "hard_constraint"
    assert "water" in context.evidence[0].text


def test_advisory_payload_with_rules_is_json_serializable(tmp_path) -> None:
    records_path = tmp_path / "structured" / "records.jsonl"
    chunks_path = tmp_path / "chunks" / "chunks.jsonl"
    rules_path = tmp_path / "structured" / "rules.jsonl"
    write_jsonl(
        records_path,
        [
            record(
                "gcms-instrument",
                "Mass Spectrometry",
                "GC/MS",
                "DCIF instrument inventory. Instrument: GC/MS.",
            )
        ],
    )
    write_jsonl(chunks_path, [])
    write_jsonl(
        rules_path,
        [
            KnowledgeRule(
                rule_id="gcms-water-rule",
                instrument_id="gcms",
                instrument_name="GC/MS",
                severity="hard_constraint",
                condition="aqueous_sample",
                statement="Avoid using water and acid containing samples because they will damage the column.",
                recommendation="Do not use GC/MS for aqueous samples unless DCIF staff approve an alternate workflow.",
                source_url="https://example.com/gcms.pdf",
                source_title="Quick start guide - GCMS",
                section_id="gcms-section",
                page=1,
                source_hash="hash",
                crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
    )
    searcher = HybridSearch(
        keyword_db_path=tmp_path / "keyword.sqlite",
        vector_dir=tmp_path / "chroma",
    )
    searcher.rebuild([])

    context = build_advisory_context(
        "Can I use GC-MS for analyzing brewed coffee?",
        searcher=searcher,
        records_path=records_path,
        chunks_path=chunks_path,
        rules_path=rules_path,
    )
    payload = advisory_payload(context.question, context)

    json.dumps(payload)


def test_extractive_advisory_answer_uses_gcms_aqueous_rule(tmp_path) -> None:
    records_path = tmp_path / "structured" / "records.jsonl"
    rules_path = tmp_path / "structured" / "rules.jsonl"
    write_jsonl(
        records_path,
        [
            record(
                "gcms-instrument",
                "Mass Spectrometry",
                "GC/MS",
                "DCIF instrument inventory. Instrument: GC/MS.",
            )
        ],
    )
    write_jsonl(
        rules_path,
        [
            KnowledgeRule(
                rule_id="gcms-water-rule",
                instrument_id="gcms",
                instrument_name="GC/MS",
                severity="hard_constraint",
                condition="aqueous_sample",
                statement="Avoid using water and acid containing samples because they will damage the column.",
                recommendation="Do not use GC/MS for aqueous samples unless DCIF staff approve an alternate workflow.",
                source_url="https://example.com/gcms.pdf",
                source_title="Quick start guide - GCMS",
                section_id="gcms-section",
                page=1,
                source_hash="hash",
                crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
    )
    searcher = HybridSearch(
        keyword_db_path=tmp_path / "keyword.sqlite",
        vector_dir=tmp_path / "chroma",
    )
    searcher.rebuild([])

    context = build_advisory_context(
        "Can I use GC-MS for analyzing brewed coffee?",
        searcher=searcher,
        records_path=records_path,
        rules_path=rules_path,
    )
    answer = extractive_advisory_answer(context)

    assert "Brewed coffee" in answer.answer
    assert "aqueous" in answer.answer
    assert "Do not use GC/MS" in answer.answer


def test_synthesize_advice_falls_back_when_llm_conflicts_with_hard_constraint(tmp_path) -> None:
    records_path = tmp_path / "structured" / "records.jsonl"
    rules_path = tmp_path / "structured" / "rules.jsonl"
    write_jsonl(
        records_path,
        [
            record(
                "gcms-instrument",
                "Mass Spectrometry",
                "GC/MS",
                "DCIF instrument inventory. Instrument: GC/MS.",
            )
        ],
    )
    write_jsonl(
        rules_path,
        [
            KnowledgeRule(
                rule_id="gcms-water-rule",
                instrument_id="gcms",
                instrument_name="GC/MS",
                severity="hard_constraint",
                condition="aqueous_sample",
                statement="Avoid using water and acid containing samples because they will damage the column.",
                recommendation="Do not use GC/MS for aqueous samples unless DCIF staff approve an alternate workflow.",
                source_url="https://example.com/gcms.pdf",
                source_title="Quick start guide - GCMS",
                section_id="gcms-section",
                page=1,
                source_hash="hash",
                crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
    )
    searcher = HybridSearch(
        keyword_db_path=tmp_path / "keyword.sqlite",
        vector_dir=tmp_path / "chroma",
    )
    searcher.rebuild([])
    context = build_advisory_context(
        "Can I use GC-MS for analyzing brewed coffee?",
        searcher=searcher,
        records_path=records_path,
        rules_path=rules_path,
    )

    answer = asyncio.run(
        synthesize_advice(
            question=context.question,
            context=context,
            client=BadConstraintLLMClient(),
        )
    )

    assert "Probably not directly" in answer.answer
    assert "Do not use GC/MS" in answer.answer


def test_catalog_merges_inventory_and_fee_table_records() -> None:
    records = [
        record(
            "ms-summary",
            "Mass Spectrometry",
            "Mass Spectrometry instruments",
            "DCIF instrument inventory summary. Available instruments: LCMS.",
        ),
        record(
            "lcms",
            "Mass Spectrometry",
            "LCMS",
            "Instrument description for LCMS.",
        ),
        record(
            "gcms-fee",
            "Mass Spectrometers",
            "GCMS",
            "Fee row for GCMS.",
            record_type="fee",
            fields={
                "mit_rate": "$23.00",
                "nonprofit_rate": "$37.26",
                "commercial_rate": "$157.09",
                "unit": "per hour",
            },
        ),
    ]

    catalog = build_dcif_catalog(records)

    mass_spec = catalog["instruments_by_category"][0]
    assert mass_spec["category"] == "Mass Spectrometry"
    by_name = {item["name"]: item for item in mass_spec["instruments"]}
    assert by_name["LCMS"]["seen_in"] == ["instrument inventory"]
    assert by_name["GCMS"]["seen_in"] == ["fee table"]
    assert by_name["GCMS"]["fee"]["mit_rate"] == "$23.00"


def test_inventory_context_uses_catalog_without_rules(tmp_path) -> None:
    records_path = tmp_path / "structured" / "records.jsonl"
    rules_path = tmp_path / "structured" / "rules.jsonl"
    records = [
        record(
            "ms-summary",
            "Mass Spectrometry",
            "Mass Spectrometry instruments",
            "DCIF instrument inventory summary. Available instruments: LCMS.",
        ),
        record("lcms", "Mass Spectrometry", "LCMS", "Instrument description for LCMS."),
        record("gcms-fee", "Mass Spectrometers", "GCMS", "Fee row for GCMS.", record_type="fee"),
    ]
    write_jsonl(records_path, records)
    write_jsonl(
        rules_path,
        [
            KnowledgeRule(
                rule_id="unrelated-rule",
                instrument_id="gcms",
                instrument_name="GC/MS",
                severity="hard_constraint",
                condition="aqueous_sample",
                statement="Avoid water.",
                source_url="https://example.com/gcms.pdf",
                source_title="Quick start guide - GCMS",
                section_id="section",
                source_hash="hash",
                crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
    )
    searcher = HybridSearch(
        keyword_db_path=tmp_path / "keyword.sqlite",
        vector_dir=tmp_path / "chroma",
    )
    searcher.rebuild([])

    context = build_advisory_context(
        "What mass spectrometry instruments do you have?",
        searcher=searcher,
        records_path=records_path,
        rules_path=rules_path,
    )
    answer = extractive_catalog_answer(context)

    assert context.rules == []
    assert all(not item.section_heading.startswith("rule:") for item in context.evidence)
    assert "LCMS" in answer.answer
    assert "GCMS (fee table)" in answer.answer
    assert {citation.chunk_id for citation in answer.citations} >= {"lcms", "gcms-fee"}
