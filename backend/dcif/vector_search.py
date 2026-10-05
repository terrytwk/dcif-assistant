from __future__ import annotations

import json
import shutil
from pathlib import Path

from backend.dcif.embed import HashingEmbeddingFunction
from backend.dcif.io import read_chunks
from backend.dcif.models import Chunk, RetrievalResult
from backend.dcif.paths import data_path


class VectorSearch:
    def __init__(
        self,
        persist_dir: Path = data_path("indexes", "chroma"),
        collection_name: str = "dcif_chunks",
    ) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_fn = HashingEmbeddingFunction()

    def _client(self):
        import chromadb
        from chromadb.config import Settings

        self.persist_dir.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

    def rebuild(self, chunks: list[Chunk]) -> None:
        if self.persist_dir.exists():
            shutil.rmtree(self.persist_dir)
        client = self._client()
        collection = client.get_or_create_collection(
            self.collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        if not chunks:
            return
        collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[{"chunk": chunk.model_dump_json()} for chunk in chunks],
        )

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        if not self.persist_dir.exists() or not query.strip():
            return []
        client = self._client()
        collection = client.get_or_create_collection(
            self.collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        result = collection.query(query_texts=[query], n_results=top_k)
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        results: list[RetrievalResult] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] or {}
            raw_chunk = metadata.get("chunk")
            if not raw_chunk:
                continue
            chunk = Chunk.model_validate(json.loads(raw_chunk))
            distance = float(distances[index]) if index < len(distances) else 1.0
            results.append(
                RetrievalResult(
                    **chunk.model_dump(),
                    score=max(0.0, 1.0 - distance),
                    rank=index + 1,
                )
            )
        return results


def rebuild_vector_index(
    *,
    chunks_path: Path = data_path("chunks", "chunks.jsonl"),
    persist_dir: Path = data_path("indexes", "chroma"),
) -> None:
    VectorSearch(persist_dir).rebuild(read_chunks(chunks_path))
