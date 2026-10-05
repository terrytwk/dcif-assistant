from datetime import UTC, datetime

from backend.dcif.hybrid_search import HybridSearch
from backend.dcif.models import Chunk


def test_hybrid_retrieval_returns_keyword_match(tmp_path) -> None:
    chunks = [
        Chunk(
            chunk_id="one",
            source_url="https://dcif.mit.edu/nmr",
            source_title="NMR",
            document_type="html",
            section_heading="Instruments",
            crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_hash="hash1",
            text="NMR spectrometers are available for trained DCIF users.",
        ),
        Chunk(
            chunk_id="two",
            source_url="https://dcif.mit.edu/ms",
            source_title="Mass Spectrometry",
            document_type="html",
            section_heading="Overview",
            crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_hash="hash2",
            text="Mass spectrometry services support molecular characterization.",
        ),
    ]
    search = HybridSearch(
        keyword_db_path=tmp_path / "keyword.sqlite",
        vector_dir=tmp_path / "chroma",
    )
    search.rebuild(chunks)

    results = search.retrieve("NMR spectrometers", top_k=1)

    assert results
    assert results[0].chunk_id == "one"


def test_hybrid_retrieval_prefers_dcif_ms_inventory_for_instrument_question(tmp_path) -> None:
    chunks = [
        Chunk(
            chunk_id="inventory",
            source_url="https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
            source_title="DCIF",
            document_type="html",
            section_heading="Mass Spectrometry (MS)",
            crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_hash="hash1",
            text="GC/MS LCMS AccuTOF-DART Maldi-TOF Q-TOF QQQ ICP-MS are available.",
        ),
        Chunk(
            chunk_id="lecture",
            source_url="https://www.dropbox.com/s/example/Intro_MS.pdf?dl=1",
            source_title="Introduction to Mass Spectrometry",
            document_type="pdf",
            section_heading="Mass Spectrometry page 1",
            crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            source_hash="hash2",
            text="Mass spectrometry measures mass to charge ratio with many instruments.",
        ),
    ]
    search = HybridSearch(
        keyword_db_path=tmp_path / "keyword.sqlite",
        vector_dir=tmp_path / "chroma",
    )
    search.rebuild(chunks)

    results = search.retrieve("what mass spectrometry instruments do you have?", top_k=1)

    assert results
    assert results[0].chunk_id == "inventory"
