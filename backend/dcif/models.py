from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


DocumentType = Literal["html", "pdf", "text", "structured"]
RecordType = Literal["instrument", "fee", "staff", "guide", "overview_section"]
KnowledgeRuleSeverity = Literal["hard_constraint", "guidance"]


def utc_now() -> datetime:
    return datetime.now(UTC)


class CrawlConfig(BaseModel):
    allowed_domains: list[str]
    root_urls: list[HttpUrl]
    follow_html_links: bool = False
    fetch_linked_files: bool = True
    linked_file_extensions: list[str] = Field(default_factory=lambda: [".pdf"])
    max_pages: int = Field(default=80, ge=1)
    request_timeout_seconds: float = Field(default=20, gt=0)
    user_agent: str = "dcif-assistant/0.1"


class SourceSnapshot(BaseModel):
    url: str
    title: str | None = None
    document_type: DocumentType
    raw_path: str
    content_type: str | None = None
    crawl_timestamp: datetime = Field(default_factory=utc_now)
    source_hash: str


class NormalizedSection(BaseModel):
    heading: str
    text: str
    page: int | None = None


class NormalizedDocument(BaseModel):
    source_url: str
    source_title: str
    document_type: DocumentType
    crawl_timestamp: datetime
    source_hash: str
    sections: list[NormalizedSection]


class Chunk(BaseModel):
    chunk_id: str
    source_url: str
    source_title: str
    document_type: DocumentType
    section_heading: str
    page: int | None = None
    crawl_timestamp: datetime
    source_hash: str
    text: str


class RetrievalResult(Chunk):
    score: float
    rank: int


class StructuredRecord(BaseModel):
    record_id: str
    record_type: RecordType
    category: str
    name: str
    text: str
    source_url: str
    source_title: str
    section_heading: str
    page: int | None = None
    crawl_timestamp: datetime
    source_hash: str
    fields: dict[str, str] = Field(default_factory=dict)


class KnowledgeDocument(BaseModel):
    document_id: str
    source_url: str
    source_title: str
    document_type: DocumentType
    knowledge_type: str
    related_instrument_ids: list[str] = Field(default_factory=list)
    source_hash: str
    crawl_timestamp: datetime


class KnowledgeSection(BaseModel):
    section_id: str
    document_id: str
    source_url: str
    source_title: str
    heading: str
    section_type: str
    text: str
    page: int | None = None
    related_instrument_ids: list[str] = Field(default_factory=list)
    source_hash: str
    crawl_timestamp: datetime


class InstrumentProfile(BaseModel):
    instrument_id: str
    name: str
    category: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    related_document_ids: list[str] = Field(default_factory=list)
    related_resource_ids: list[str] = Field(default_factory=list)
    fee: dict[str, str] | None = None
    source_record_ids: list[str] = Field(default_factory=list)
    source_url: str | None = None
    source_title: str | None = None


class ResourceRecord(BaseModel):
    resource_id: str
    title: str
    resource_type: str
    category: str
    document_id: str | None = None
    source_url: str
    source_title: str
    related_instrument_ids: list[str] = Field(default_factory=list)
    source_record_id: str | None = None


class KnowledgeRule(BaseModel):
    rule_id: str
    rule_type: str = "instrument_constraint"
    instrument_id: str | None = None
    instrument_name: str | None = None
    severity: KnowledgeRuleSeverity
    condition: str
    statement: str
    recommendation: str | None = None
    source_url: str
    source_title: str
    section_id: str
    page: int | None = None
    source_hash: str
    crawl_timestamp: datetime


class ChatCitation(BaseModel):
    chunk_id: str
    source_url: str
    source_title: str
    section_heading: str
    page: int | None = None


class ChatAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    citations: list[ChatCitation] = Field(default_factory=list, max_length=8)
    confidence: Literal["low", "medium", "high"] = "low"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
