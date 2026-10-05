from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from backend.dcif.models import ChatAnswer, ChatCitation, RetrievalResult
from backend.dcif.prompts import DCIF_CHAT_SYSTEM_PROMPT

TOutput = TypeVar("TOutput", bound=BaseModel)


class LLMUserContext(BaseModel):
    user_id: str = "anonymous"
    tenant_id: str | None = None
    locale: str = "en-US"
    safety_identifier: str = "anonymous"


class LLMRequestMetadata(BaseModel):
    feature: str
    prompt_version: str
    trace_content: bool = False


class LLMClient(Protocol):
    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        metadata: LLMRequestMetadata,
        user: LLMUserContext,
    ) -> str:
        ...

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_model: type[TOutput],
        json_schema: dict[str, Any],
        metadata: LLMRequestMetadata,
        user: LLMUserContext,
    ) -> TOutput:
        ...


class AzureApiKeyProvider:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def headers(self) -> dict[str, str]:
        return {"api-key": self._api_key}


class AzureBearerTokenProvider:
    def __init__(self, scope: str = "https://ai.azure.com/.default") -> None:
        from azure.identity.aio import DefaultAzureCredential

        self._scope = scope
        self._credential = DefaultAzureCredential()

    async def headers(self) -> dict[str, str]:
        token = await self._credential.get_token(self._scope)
        return {"Authorization": f"Bearer {token.token}"}

    async def close(self) -> None:
        await self._credential.close()


class AzureResponsesClient:
    def __init__(
        self,
        *,
        responses_url: str,
        model: str,
        auth_headers: Callable[[], Awaitable[dict[str, str]]],
        timeout_seconds: float = 20,
        temperature: float = 0.2,
        max_output_tokens: int = 1200,
    ) -> None:
        self._responses_url = responses_url
        self._model = model
        self._auth_headers = auth_headers
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_model: type[TOutput],
        json_schema: dict[str, Any],
        metadata: LLMRequestMetadata,
        user: LLMUserContext,
    ) -> TOutput:
        request_body = self._request_body(system_prompt, user_payload, metadata, user)
        request_body["text"] = {
            "format": {
                "type": "json_schema",
                "name": output_model.__name__,
                "strict": True,
                "schema": json_schema,
            }
        }
        raw = await self._post(request_body)
        text = self._extract_output_text(raw)
        if not text:
            raise ValueError("Azure Responses API response did not include output text")
        try:
            return output_model.model_validate_json(text)
        except ValidationError:
            raise
        except ValueError as exc:
            raise ValueError("Azure Responses API response was not valid JSON") from exc

    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        metadata: LLMRequestMetadata,
        user: LLMUserContext,
    ) -> str:
        raw = await self._post(self._request_body(system_prompt, user_payload, metadata, user))
        text = self._extract_output_text(raw)
        if not text:
            raise ValueError("Azure Responses API response did not include output text")
        return text.strip()

    def _request_body(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        metadata: LLMRequestMetadata,
        user: LLMUserContext,
    ) -> dict[str, Any]:
        body = {
            "model": self._model,
            "input": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, separators=(",", ":")),
                },
            ],
            "temperature": self._temperature,
            "max_output_tokens": self._max_output_tokens,
            "safety_identifier": user.safety_identifier,
            "prompt_cache_key": metadata.prompt_version,
            "metadata": {
                "feature": metadata.feature,
                "prompt_version": metadata.prompt_version,
                "tenant_id": user.tenant_id,
            },
        }
        return body

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            **await self._auth_headers(),
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(self._responses_url, headers=headers, json=body)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _extract_output_text(body: dict[str, Any]) -> str | None:
        output_text = body.get("output_text")
        if isinstance(output_text, str):
            return output_text

        output = body.get("output")
        if not isinstance(output, list):
            return None
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    return part["text"]
        return None


CHAT_ANSWER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "citations", "confidence"],
    "properties": {
        "answer": {"type": "string", "minLength": 1, "maxLength": 4000},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "citations": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["chunk_id", "source_url", "source_title", "section_heading", "page"],
                "properties": {
                    "chunk_id": {"type": "string"},
                    "source_url": {"type": "string"},
                    "source_title": {"type": "string"},
                    "section_heading": {"type": "string"},
                    "page": {"type": ["integer", "null"]},
                },
            },
        },
    },
}


class LLMSettings(BaseModel):
    enabled: bool = False
    provider: str = "azure_foundry"
    feature_mode: str = "responses"
    azure_endpoint: str | None = None
    azure_responses_url: str | None = None
    azure_model: str | None = None
    auth_mode: str = "managed_identity"
    azure_scope: str = "https://ai.azure.com/.default"
    azure_api_key: str | None = None
    timeout_seconds: float = 20
    max_output_tokens: int = 1200
    temperature: float = 0.2
    prompt_version: str = "dcif-chat-v1"

    @classmethod
    def from_env(cls) -> "LLMSettings":
        load_dotenv()
        endpoint = os.getenv("LLM_AZURE_ENDPOINT")
        return cls(
            enabled=os.getenv("LLM_ENABLED", "false").lower() == "true",
            provider=os.getenv("LLM_PROVIDER", "azure_foundry"),
            feature_mode=os.getenv("LLM_FEATURE_MODE", "responses"),
            azure_endpoint=endpoint,
            azure_responses_url=os.getenv("LLM_AZURE_RESPONSES_URL"),
            azure_model=os.getenv("LLM_AZURE_MODEL"),
            auth_mode=os.getenv("LLM_AUTH_MODE", "managed_identity"),
            azure_scope=os.getenv("LLM_AZURE_SCOPE", "https://ai.azure.com/.default"),
            azure_api_key=os.getenv("LLM_AZURE_API_KEY"),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
            max_output_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1200")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            prompt_version=os.getenv("LLM_PROMPT_VERSION", "dcif-chat-v1"),
        )

    @property
    def responses_url(self) -> str:
        if self.azure_responses_url:
            return self.azure_responses_url
        if not self.azure_endpoint:
            raise ValueError("LLM_AZURE_ENDPOINT is required")
        parsed = urlparse(self.azure_endpoint)
        if parsed.path.rstrip("/") == "/openai/v1/responses":
            return self.azure_endpoint.rstrip("/")
        return f"{self.azure_endpoint.rstrip('/')}/openai/v1/responses"

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "feature_mode": self.feature_mode,
            "auth_mode": self.auth_mode,
            "has_azure_endpoint": bool(self.azure_endpoint or self.azure_responses_url),
            "has_azure_model": bool(self.azure_model),
            "has_api_key": bool(self.azure_api_key),
            "prompt_version": self.prompt_version,
        }


def build_llm_client(settings: LLMSettings | None = None) -> LLMClient | None:
    settings = settings or LLMSettings.from_env()
    if not settings.enabled:
        return None
    if settings.provider != "azure_foundry" or settings.feature_mode != "responses":
        raise ValueError("Only azure_foundry responses mode is implemented")
    if not settings.azure_model:
        raise ValueError("LLM_AZURE_MODEL is required")

    if settings.auth_mode == "api_key":
        if not settings.azure_api_key:
            raise ValueError("LLM_AZURE_API_KEY is required for api_key auth")
        auth_provider = AzureApiKeyProvider(settings.azure_api_key)
    elif settings.auth_mode == "managed_identity":
        auth_provider = AzureBearerTokenProvider(settings.azure_scope)
    else:
        raise ValueError("LLM_AUTH_MODE must be api_key or managed_identity")

    return AzureResponsesClient(
        responses_url=settings.responses_url,
        model=settings.azure_model,
        auth_headers=auth_provider.headers,
        timeout_seconds=settings.timeout_seconds,
        temperature=settings.temperature,
        max_output_tokens=settings.max_output_tokens,
    )


def context_payload(results: list[RetrievalResult]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": item.chunk_id,
            "source_url": item.source_url,
            "source_title": item.source_title,
            "document_type": item.document_type,
            "section_heading": item.section_heading,
            "page": item.page,
            "crawl_timestamp": item.crawl_timestamp.isoformat(),
            "source_hash": item.source_hash,
            "text": item.text,
        }
        for item in results
    ]


def validate_citations(answer: ChatAnswer, results: list[RetrievalResult]) -> ChatAnswer:
    allowed = {item.chunk_id for item in results}
    answer.citations = [citation for citation in answer.citations if citation.chunk_id in allowed]
    if not answer.citations and results:
        item = results[0]
        answer.citations = [
            ChatCitation(
                chunk_id=item.chunk_id,
                source_url=item.source_url,
                source_title=item.source_title,
                section_heading=item.section_heading,
                page=item.page,
            )
        ]
        answer.confidence = "low"
    return answer


async def synthesize_answer(
    *,
    question: str,
    results: list[RetrievalResult],
    client: LLMClient,
    settings: LLMSettings | None = None,
) -> ChatAnswer:
    settings = settings or LLMSettings.from_env()
    answer = await client.generate_json(
        system_prompt=DCIF_CHAT_SYSTEM_PROMPT,
        user_payload={"question": question, "sources": context_payload(results)},
        output_model=ChatAnswer,
        json_schema=CHAT_ANSWER_SCHEMA,
        metadata=LLMRequestMetadata(feature="dcif_chat", prompt_version=settings.prompt_version),
        user=LLMUserContext(safety_identifier="dcif-chat:anonymous"),
    )
    return validate_citations(answer, results)


def extractive_answer(question: str, results: list[RetrievalResult]) -> ChatAnswer:
    if not results:
        return ChatAnswer(
            answer="I could not find DCIF source passages that answer that question.",
            citations=[],
            confidence="low",
        )

    lead = results[0]
    citations = [
        ChatCitation(
            chunk_id=item.chunk_id,
            source_url=item.source_url,
            source_title=item.source_title,
            section_heading=item.section_heading,
            page=item.page,
        )
        for item in results[:3]
    ]
    return ChatAnswer(
        answer=(
            "LLM synthesis is disabled, so here is the most relevant retrieved passage: "
            f"{lead.text}"
        ),
        citations=citations,
        confidence="medium",
    )
