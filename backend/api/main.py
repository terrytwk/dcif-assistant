from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.dcif.advisor import (
    build_advisory_context,
    classify_query,
    extractive_catalog_answer,
    extractive_advisory_answer,
    is_advisory_intent,
    synthesize_advice,
    synthesize_inventory_answer,
)
from backend.dcif.hybrid_search import HybridSearch
from backend.dcif.io import read_structured_records
from backend.dcif.llm import LLMSettings, build_llm_client, extractive_answer, synthesize_answer
from backend.dcif.models import ChatAnswer, RetrievalResult
from backend.dcif.paths import data_path


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievalResponse(BaseModel):
    results: list[RetrievalResult]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class ChatResponse(BaseModel):
    answer: ChatAnswer
    retrieved: list[RetrievalResult]
    llm_enabled: bool


app = FastAPI(title="MIT DCIF Retrieval API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache
def searcher() -> HybridSearch:
    return HybridSearch()


@lru_cache
def llm_settings() -> LLMSettings:
    return LLMSettings.from_env()


@lru_cache
def llm_client():
    return build_llm_client(llm_settings())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/llm/status")
def llm_status() -> dict:
    settings = llm_settings()
    return settings.status()


@app.get("/debug/runtime")
def debug_runtime(
    query: str = "What mass spectrometry instruments do you have?",
) -> dict:
    records_path = data_path("structured", "records.jsonl")
    records = read_structured_records(records_path)
    context = build_advisory_context(query, searcher=searcher())
    return {
        "cwd": str(Path.cwd()),
        "api_module": __file__,
        "query": query,
        "intent": context.intent,
        "is_advisory_intent": is_advisory_intent(context.intent),
        "records_path": str(records_path),
        "records_exists": records_path.exists(),
        "structured_records": len(records),
        "catalog_categories": [
            {
                "category": category["category"],
                "instrument_names": [item["name"] for item in category["instruments"]],
            }
            for category in context.catalog.get("instruments_by_category", [])
        ],
        "rule_evidence_count": len(context.rules),
        "top_evidence": [
            {
                "chunk_id": item.chunk_id,
                "source_title": item.source_title,
                "section_heading": item.section_heading,
            }
            for item in context.evidence[:5]
        ],
        "llm": llm_settings().status(),
    }


@app.post("/retrieve", response_model=RetrievalResponse)
def retrieve_endpoint(request: RetrievalRequest) -> RetrievalResponse:
    results = searcher().retrieve(request.query, top_k=request.top_k)
    return RetrievalResponse(results=results)


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    intent = classify_query(request.message)
    if is_advisory_intent(intent):
        advisory_context = build_advisory_context(request.message, searcher=searcher())
        if intent == "inventory_lookup":
            client = llm_client()
            if client is not None:
                try:
                    answer = await synthesize_inventory_answer(
                        question=request.message,
                        context=advisory_context,
                        client=client,
                        settings=llm_settings(),
                    )
                except Exception:
                    answer = extractive_catalog_answer(advisory_context)
                return ChatResponse(answer=answer, retrieved=advisory_context.evidence, llm_enabled=True)
            return ChatResponse(
                answer=extractive_catalog_answer(advisory_context),
                retrieved=advisory_context.evidence,
                llm_enabled=False,
            )
        client = llm_client()
        if client is None:
            return ChatResponse(
                answer=extractive_answer(request.message, advisory_context.evidence),
                retrieved=advisory_context.evidence,
                llm_enabled=False,
            )
        try:
            answer = await synthesize_advice(
                question=request.message,
                context=advisory_context,
                client=client,
                settings=llm_settings(),
            )
        except Exception:
            answer = extractive_advisory_answer(advisory_context)
        return ChatResponse(answer=answer, retrieved=advisory_context.evidence, llm_enabled=True)

    results = searcher().retrieve(request.message, top_k=request.top_k)
    client = llm_client()
    if client is None:
        return ChatResponse(
            answer=extractive_answer(request.message, results),
            retrieved=results,
            llm_enabled=False,
        )

    try:
        answer = await synthesize_answer(
            question=request.message,
            results=results,
            client=client,
            settings=llm_settings(),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="LLM synthesis failed") from exc

    return ChatResponse(answer=answer, retrieved=results, llm_enabled=True)
