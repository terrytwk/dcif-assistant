from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.dcif.embed import tokenize
from backend.dcif.io import read_chunks
from backend.dcif.models import Chunk, RetrievalResult
from backend.dcif.paths import data_path


class KeywordSearch:
    def __init__(self, db_path: Path = data_path("indexes", "keyword.sqlite")) -> None:
        self.db_path = db_path

    def rebuild(self, chunks: list[Chunk]) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DROP TABLE IF EXISTS chunks_fts")
            conn.execute(
                """
                CREATE VIRTUAL TABLE chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    content,
                    metadata UNINDEXED
                )
                """
            )
            conn.executemany(
                "INSERT INTO chunks_fts(chunk_id, content, metadata) VALUES (?, ?, ?)",
                [
                    (
                        chunk.chunk_id,
                        f"{chunk.source_title}\n{chunk.section_heading}\n{chunk.text}",
                        chunk.model_dump_json(),
                    )
                    for chunk in chunks
                ],
            )

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        if not self.db_path.exists():
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        safe_query = " OR ".join(f'"{token}"' for token in tokens[:16])

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT metadata, bm25(chunks_fts) AS rank_score
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                ORDER BY rank_score
                LIMIT ?
                """,
                (safe_query, top_k),
            ).fetchall()

        results: list[RetrievalResult] = []
        for rank, (metadata, rank_score) in enumerate(rows, start=1):
            chunk = Chunk.model_validate(json.loads(metadata))
            results.append(
                RetrievalResult(**chunk.model_dump(), score=float(-rank_score), rank=rank)
            )
        return results


def rebuild_keyword_index(
    *,
    chunks_path: Path = data_path("chunks", "chunks.jsonl"),
    db_path: Path = data_path("indexes", "keyword.sqlite"),
) -> None:
    KeywordSearch(db_path).rebuild(read_chunks(chunks_path))
