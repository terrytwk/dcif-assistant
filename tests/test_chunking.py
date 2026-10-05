from datetime import UTC, datetime

from backend.dcif.chunk import chunk_document
from backend.dcif.models import NormalizedDocument, NormalizedSection


def test_chunk_document_is_deterministic_and_preserves_provenance() -> None:
    doc = NormalizedDocument(
        source_url="https://dcif.mit.edu/example",
        source_title="Example",
        document_type="html",
        crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source_hash="abc123",
        sections=[NormalizedSection(heading="Access", text="one two three four five six seven eight nine ten")],
    )

    first = chunk_document(doc, max_words=4, overlap_words=1)
    second = chunk_document(doc, max_words=4, overlap_words=1)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert len(first) == 3
    assert first[0].source_url == "https://dcif.mit.edu/example"
    assert first[0].section_heading == "Access"
