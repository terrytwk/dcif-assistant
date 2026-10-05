from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import main
from backend.dcif.models import ChatAnswer, StructuredRecord


class ExplodingLLMClient:
    async def generate_json(self, **kwargs):
        raise AssertionError("LLM failed while polishing inventory")

    async def generate_text(self, **kwargs):
        raise AssertionError("LLM failed while polishing inventory")


class BadInventoryLLMClient:
    async def generate_json(self, **kwargs):
        return ChatAnswer(
            answer="The current inventory does not list any mass spectrometry instruments.",
            citations=[],
            confidence="medium",
        )

    async def generate_text(self, **kwargs):
        return "The current inventory does not list any mass spectrometry instruments."


class EmptySearcher:
    def retrieve(self, query: str, top_k: int = 5):
        return []


def record(record_id: str, name: str, text: str) -> StructuredRecord:
    return StructuredRecord(
        record_id=record_id,
        record_type="instrument",
        category="Mass Spectrometry",
        name=name,
        text=text,
        source_url="https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
        source_title="DCIF",
        section_heading="Mass Spectrometry (MS)",
        crawl_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source_hash="hash",
    )


@pytest.fixture(autouse=True)
def clear_api_caches():
    main.searcher.cache_clear()
    main.llm_client.cache_clear()
    main.llm_settings.cache_clear()
    yield
    main.app.dependency_overrides.clear()
    for cached in (main.searcher, main.llm_client, main.llm_settings):
        if hasattr(cached, "cache_clear"):
            cached.cache_clear()


def write_inventory_records(records_path) -> None:
    records_path.parent.mkdir(parents=True)
    records_path.write_text(
        "\n".join(
            [
                record(
                    "ms-summary",
                    "Mass Spectrometry instruments",
                    "DCIF instrument inventory summary. Available instruments: GC/MS, LCMS.",
                ).model_dump_json(),
                record("gcms", "GC/MS", "DCIF instrument inventory. Instrument: GC/MS.").model_dump_json(),
                record("lcms", "LCMS", "DCIF instrument inventory. Instrument: LCMS.").model_dump_json(),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def patch_inventory_context(monkeypatch, records_path) -> None:
    original_build_advisory_context = main.build_advisory_context

    def fake_context(query, *, searcher, **kwargs):
        return original_build_advisory_context(
            query,
            searcher=searcher,
            records_path=records_path,
            evidence_limit=8,
        )

    monkeypatch.setattr(main, "build_advisory_context", fake_context)
    monkeypatch.setattr(main, "searcher", lambda: EmptySearcher())


def test_chat_inventory_lookup_falls_back_when_llm_fails(monkeypatch, tmp_path) -> None:
    records_path = tmp_path / "structured" / "records.jsonl"
    write_inventory_records(records_path)
    patch_inventory_context(monkeypatch, records_path)
    monkeypatch.setattr(main, "llm_client", lambda: ExplodingLLMClient())

    response = TestClient(main.app).post(
        "/chat",
        json={"message": "What mass spectrometry instruments do you have?", "top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_enabled"] is True
    assert "GC/MS" in payload["answer"]["answer"]
    assert "LCMS" in payload["answer"]["answer"]
    assert "does not list" not in payload["answer"]["answer"].lower()


def test_chat_inventory_lookup_rejects_bad_llm_inventory_answer(monkeypatch, tmp_path) -> None:
    records_path = tmp_path / "structured" / "records.jsonl"
    write_inventory_records(records_path)
    patch_inventory_context(monkeypatch, records_path)
    monkeypatch.setattr(main, "llm_client", lambda: BadInventoryLLMClient())

    response = TestClient(main.app).post(
        "/chat",
        json={"message": "What mass spectrometry instruments do you have?", "top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm_enabled"] is True
    assert "GC/MS" in payload["answer"]["answer"]
    assert "LCMS" in payload["answer"]["answer"]
    assert "does not list" not in payload["answer"]["answer"].lower()


def test_debug_runtime_uses_project_root_paths_from_backend_cwd(monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project_root / "backend")
    main.searcher.cache_clear()

    payload = main.debug_runtime()

    assert payload["records_exists"] is True
    assert payload["structured_records"] >= 20
    assert "Mass Spectrometry" in {
        category["category"] for category in payload["catalog_categories"]
    }
