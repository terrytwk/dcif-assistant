from __future__ import annotations

from pathlib import Path

from backend.dcif.embed import tokenize
from backend.dcif.io import read_chunks
from backend.dcif.keyword_search import KeywordSearch
from backend.dcif.models import Chunk, RetrievalResult
from backend.dcif.paths import data_path
from backend.dcif.vector_search import VectorSearch


DOMAIN_EXPANSIONS = {
    "mass spectrometry": ["ms", "gcms", "lcms", "accutof", "maldi", "q-tof", "qqq", "icp-ms"],
    "mass spectrometer": ["ms", "gcms", "lcms", "accutof", "maldi", "q-tof", "qqq", "icp-ms"],
    "instrument": ["instruments", "spectrometer", "spectrometers"],
    "instruments": ["instrument", "spectrometer", "spectrometers"],
}

INVENTORY_TERMS = {
    "available",
    "availability",
    "have",
    "instrument",
    "instruments",
    "list",
    "offer",
    "available",
}

MS_INSTRUMENT_TERMS = {"gc/ms", "gcms", "lcms", "accutof", "maldi", "q-tof", "qtof", "qqq", "icp-ms"}


def expand_query(query: str) -> str:
    lowered = query.lower()
    additions: list[str] = []
    for phrase, terms in DOMAIN_EXPANSIONS.items():
        if phrase in lowered:
            additions.extend(terms)
    if {"mass", "spectrometry"}.issubset(set(tokenize(query))):
        additions.extend(DOMAIN_EXPANSIONS["mass spectrometry"])
    if not additions:
        return query
    return f"{query} {' '.join(dict.fromkeys(additions))}"


def inventory_boost(query: str, item: RetrievalResult) -> float:
    query_tokens = set(tokenize(query))
    heading = item.section_heading.lower()
    text = item.text.lower()
    source_url = item.source_url.lower()
    boost = 0.0

    asks_for_inventory = bool(query_tokens & INVENTORY_TERMS)
    asks_for_ms = "mass spectrometry" in query.lower() or "ms" in query_tokens
    if asks_for_inventory and asks_for_ms and "mass spectrometry" in heading:
        boost += 0.08
    if asks_for_inventory and asks_for_ms and item.document_type == "structured" and heading == "instrument: mass spectrometry":
        boost += 0.12
    if asks_for_inventory and asks_for_ms and "available instruments:" in text:
        boost += 0.08
    if asks_for_inventory and asks_for_ms and source_url.startswith("https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/"):
        boost += 0.03
    if asks_for_inventory and asks_for_ms and any(term in text for term in MS_INSTRUMENT_TERMS):
        boost += 0.03
    return boost


class HybridSearch:
    def __init__(
        self,
        *,
        keyword_db_path: Path = data_path("indexes", "keyword.sqlite"),
        vector_dir: Path = data_path("indexes", "chroma"),
    ) -> None:
        self.keyword = KeywordSearch(keyword_db_path)
        self.vector = VectorSearch(vector_dir)

    def rebuild(self, chunks: list[Chunk]) -> None:
        self.keyword.rebuild(chunks)
        self.vector.rebuild(chunks)

    def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        expanded_query = expand_query(query)
        candidate_count = max(top_k * 8, 30)
        keyword_results = self.keyword.search(expanded_query, top_k=candidate_count)
        try:
            vector_results = self.vector.search(expanded_query, top_k=candidate_count)
        except Exception:
            vector_results = []

        merged: dict[str, RetrievalResult] = {}
        scores: dict[str, float] = {}

        for source_weight, results in ((0.58, keyword_results), (0.42, vector_results)):
            for item in results:
                reciprocal_rank = 1.0 / (60 + item.rank)
                normalized = reciprocal_rank + max(item.score, 0.0) * 0.01
                scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + source_weight * normalized
                merged[item.chunk_id] = item

        for chunk_id, item in merged.items():
            scores[chunk_id] = scores.get(chunk_id, 0.0) + inventory_boost(query, item)

        ranked = sorted(merged.values(), key=lambda item: scores[item.chunk_id], reverse=True)
        return [
            RetrievalResult(**item.model_dump(exclude={"score", "rank"}), score=scores[item.chunk_id], rank=rank)
            for rank, item in enumerate(ranked[:top_k], start=1)
        ]


def retrieve(query: str, top_k: int = 5) -> list[RetrievalResult]:
    return HybridSearch().retrieve(query, top_k=top_k)


def rebuild_indexes(
    *,
    chunks_path: Path = data_path("chunks", "chunks.jsonl"),
    keyword_db_path: Path = data_path("indexes", "keyword.sqlite"),
    vector_dir: Path = data_path("indexes", "chroma"),
) -> None:
    HybridSearch(keyword_db_path=keyword_db_path, vector_dir=vector_dir).rebuild(read_chunks(chunks_path))
