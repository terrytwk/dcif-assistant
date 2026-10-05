from datetime import UTC, datetime

from backend.dcif.chunk import chunk_document
from backend.dcif.models import NormalizedDocument, NormalizedSection
from backend.dcif.structured_extract import extract_records_from_document, records_to_chunks


def overview_doc(sections: list[NormalizedSection]) -> NormalizedDocument:
    return NormalizedDocument(
        source_url="https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
        source_title="DCIF",
        document_type="html",
        crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source_hash="hash",
        sections=sections,
    )


def test_extracts_instrument_records_from_overview_sections() -> None:
    doc = overview_doc(
        [
            NormalizedSection(
                heading="Mass Spectrometry (MS)",
                text=(
                    "GC/MS The GCMS is a nominal mass Agilent 5977B mass spectrometer.\n"
                    "Q-TOF The QTOF is a high-resolution Agilent 6545 mass spectrometer."
                ),
            )
        ]
    )

    records = extract_records_from_document(doc)

    assert [record.name for record in records] == ["Mass Spectrometry instruments", "GC/MS", "Q-TOF"]
    assert all(record.record_type == "instrument" for record in records)
    assert all(record.category == "Mass Spectrometry" for record in records)
    assert "Available instruments: GC/MS, Q-TOF" in records[0].text


def test_guide_list_is_not_treated_as_instrument_inventory() -> None:
    doc = overview_doc(
        [
            NormalizedSection(
                heading="Mass Spectrometry (MS)",
                text="How to choose the best instrument\nQuick start guide - LCMS",
            )
        ]
    )

    records = extract_records_from_document(doc)

    assert all(record.record_type == "guide" for record in records)


def test_instrument_extraction_ignores_non_instrument_notes() -> None:
    doc = overview_doc(
        [
            NormalizedSection(
                heading="Other Instruments",
                text=(
                    "HPLC The lab has an analytical scale Agilent Infinity 1260 II HPLC.\n"
                    "Please note that once this form is submitted, your advisor is automatically billed."
                ),
            )
        ]
    )

    records = extract_records_from_document(doc)

    assert all("Please note" not in record.name for record in records)
    assert [record.name for record in records if record.record_type == "instrument"] == [
        "Other Instruments instruments",
        "HPLC",
    ]


def test_extracts_fee_records_from_fee_table_text() -> None:
    doc = overview_doc(
        [
            NormalizedSection(
                heading="Fees",
                text=(
                    "Instrument\nMIT\nNon-Profit\nCommercial\nUnit\n"
                    "Mass Spectrometers\nLCMS\n$23.00\n$37.26\n$157.09\nper hour"
                ),
            )
        ]
    )

    records = extract_records_from_document(doc)

    assert len(records) == 1
    assert records[0].record_type == "fee"
    assert records[0].fields["instrument"] == "LCMS"
    assert records[0].fields["mit_rate"] == "$23.00"


def test_structured_records_become_searchable_chunks() -> None:
    doc = overview_doc(
        [
            NormalizedSection(
                heading="Other Instruments",
                text="HPLC The lab has an analytical scale Agilent Infinity 1260 II HPLC.",
            )
        ]
    )

    records = extract_records_from_document(doc)
    chunks = records_to_chunks(records)

    assert chunks[0].document_type == "structured"
    assert "DCIF instrument inventory" in chunks[0].text
    assert chunks[0].section_heading == "instrument: Other Instruments"
