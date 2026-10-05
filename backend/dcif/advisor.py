from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel

from backend.dcif.embed import tokenize
from backend.dcif.hybrid_search import HybridSearch
from backend.dcif.io import (
    read_chunks,
    read_instrument_profiles,
    read_knowledge_rules,
    read_resource_records,
    read_structured_records,
)
from backend.dcif.llm import (
    CHAT_ANSWER_SCHEMA,
    LLMClient,
    LLMRequestMetadata,
    LLMSettings,
    LLMUserContext,
    context_payload,
)
from backend.dcif.models import (
    ChatAnswer,
    ChatCitation,
    InstrumentProfile,
    KnowledgeRule,
    ResourceRecord,
    RetrievalResult,
    StructuredRecord,
)
from backend.dcif.paths import data_path
from backend.dcif.prompts import DCIF_ADVISOR_SYSTEM_PROMPT, DCIF_INFORMATION_MAP


QueryIntent = Literal[
    "chat",
    "instrument_procedure",
    "instrument_recommendation",
    "inventory_lookup",
    "fee_lookup",
    "guide_lookup",
    "training_access",
    "procedure_help",
]


RECOMMENDATION_TERMS = {
    "recommend",
    "recommendation",
    "which",
    "what",
    "best",
    "choose",
    "use",
    "tool",
    "instrument",
    "method",
    "analyze",
    "analysis",
    "measure",
}

FEE_TERMS = {"cost", "fee", "fees", "price", "rate", "rates", "charge", "charges"}
TRAINING_TERMS = {"training", "trained", "access", "reserve", "reservation", "reservations"}
GUIDE_TERMS = {"guide", "quick", "manual", "instructions", "application", "note", "notes"}
PROCEDURE_TERMS = {"how", "run", "operate", "prepare", "sample", "submit", "acquire"}
INVENTORY_TERMS = {"have", "available", "list", "instruments", "instrument", "tools"}
SAMPLE_COMPATIBILITY_TERMS = {
    "acid",
    "acids",
    "aqueous",
    "compatible",
    "compatibility",
    "damage",
    "dissolve",
    "dissolved",
    "inject",
    "injection",
    "into",
    "prepare",
    "preparation",
    "put",
    "raw",
    "sample",
    "samples",
    "soluble",
    "solvent",
    "solvents",
    "vial",
    "volume",
    "water",
}

INSTRUMENT_ALIASES = {
    "GC/MS": ["gc/ms", "gc-ms", "gcms", "gc ms"],
    "LCMS": ["lcms", "lc/ms", "lc-ms", "lc ms"],
    "AccuTOF-DART": ["accutof-dart", "accutof dart", "accutof", "dart"],
    "Maldi-TOF": ["maldi-tof", "maldi tof", "malditof", "maldi"],
    "Q-TOF": ["q-tof", "qtof", "q tof"],
    "QQQ": ["qqq", "triple quadrupole", "triple-quadrupole"],
    "ICP-MS": ["icp-ms", "icpms", "icp ms"],
    "HPLC": ["hplc"],
    "FTIR": ["ftir"],
    "Polarimeter": ["polarimeter", "polarimetry"],
    "Time-Domain NMR": ["time-domain nmr", "time domain nmr", "tdspec", "td-nmr"],
}

GUIDE_QUERY_TERMS = {
    "sample",
    "sample preparation",
    "compatible solvents",
    "solvent",
    "solvents",
    "dissolved",
    "aqueous",
    "water",
    "acid",
    "damage",
    "column",
    "vial",
    "volume",
    "concentration",
    "inject",
    "injection",
}

SAMPLE_PROFILES = {
    "coffee": {
        "sample": "coffee",
        "likely_goals": [
            "quantify caffeine or small organic molecules",
            "identify volatile aroma compounds",
            "identify unknown small molecules by accurate mass",
            "measure elements or metals",
        ],
        "search_terms": [
            "coffee",
            "caffeine",
            "small molecule",
            "volatile",
            "aroma",
            "food extract",
            "chromatography",
            "LCMS",
            "HPLC",
            "GC/MS",
            "Q-TOF",
            "QQQ",
            "ICP-MS",
        ],
        "clarifying_question": "Are you trying to quantify caffeine, identify aroma compounds, identify unknowns, or measure elements/metals?",
    },
    "polymer": {
        "sample": "polymer",
        "likely_goals": ["molecular characterization", "functional group analysis", "diffusion or relaxation measurements"],
        "search_terms": ["polymer", "Maldi-TOF", "NMR", "FTIR", "diffusion"],
        "clarifying_question": "Are you trying to identify composition, measure molecular weight, or characterize functional groups?",
    },
    "protein": {
        "sample": "protein",
        "likely_goals": ["biomolecule mass analysis", "peptide/protein sequencing", "labeling experiments"],
        "search_terms": ["protein", "peptide", "MALDI", "Q-TOF", "biomolecule", "NMR"],
        "clarifying_question": "Are you measuring intact mass, peptide fragments, or solution structure/interactions?",
    },
}


class QueryProfile(BaseModel):
    sample: str | None = None
    likely_goals: list[str] = []
    search_terms: list[str] = []
    clarifying_question: str | None = None


@dataclass
class AdvisoryContext:
    question: str
    intent: QueryIntent
    profile: QueryProfile
    candidate_records: list[StructuredRecord]
    citation_records: list[StructuredRecord]
    catalog: dict
    instrument_profiles: list[InstrumentProfile]
    resources: list[ResourceRecord]
    rules: list[KnowledgeRule]
    evidence: list[RetrievalResult]


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def alias_in_text(alias: str, text: str) -> bool:
    lowered_alias = alias.lower()
    lowered_text = text.lower()
    if not lowered_alias:
        return False
    if re.fullmatch(r"[a-z0-9]+", lowered_alias) and len(lowered_alias) <= 3:
        return re.search(rf"\b{re.escape(lowered_alias)}\b", lowered_text) is not None
    return lowered_alias in lowered_text


def extract_instrument(query: str) -> str | None:
    lowered = query.lower()
    key = normalized_key(query)
    for canonical, aliases in INSTRUMENT_ALIASES.items():
        for alias in aliases:
            alias_key = normalized_key(alias)
            if alias_in_text(alias, lowered) or (len(alias_key) >= 4 and alias_key in key):
                return canonical
    return None


def asks_instrument_procedure(query: str) -> bool:
    tokens = set(tokenize(query))
    lowered = query.lower()
    if not extract_instrument(query):
        return False
    if tokens & SAMPLE_COMPATIBILITY_TERMS:
        return True
    return any(phrase in lowered for phrase in ("can i", "can we", "is it ok", "is it okay"))


def classify_query(query: str) -> QueryIntent:
    tokens = set(tokenize(query))
    lowered = query.lower()

    if tokens & FEE_TERMS:
        return "fee_lookup"
    if tokens & TRAINING_TERMS:
        return "training_access"
    if asks_instrument_procedure(query):
        return "instrument_procedure"
    if tokens & GUIDE_TERMS:
        return "guide_lookup"
    if (tokens & PROCEDURE_TERMS) and any(term in lowered for term in ("lcms", "gcms", "nmr", "hplc", "sample")):
        return "procedure_help"
    if (tokens & INVENTORY_TERMS) and any(term in lowered for term in ("instrument", "tool", "spectrometry", "nmr", "dcif")):
        return "inventory_lookup"
    if (tokens & RECOMMENDATION_TERMS) and any(term in lowered for term in (" use ", " for ", "best", "recommend", "tool", "instrument", "analyze")):
        return "instrument_recommendation"
    return "chat"


def is_advisory_intent(intent: QueryIntent) -> bool:
    return intent in {"instrument_procedure", "instrument_recommendation", "inventory_lookup"}


def profile_query(query: str) -> QueryProfile:
    lowered = query.lower()
    for keyword, profile in SAMPLE_PROFILES.items():
        if keyword in lowered:
            return QueryProfile.model_validate(profile)
    return QueryProfile()


def record_to_result(record: StructuredRecord, *, rank: int, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=record.record_id,
        source_url=record.source_url,
        source_title=record.source_title,
        document_type="structured",
        section_heading=f"{record.record_type}: {record.category}",
        page=record.page,
        crawl_timestamp=record.crawl_timestamp,
        source_hash=record.source_hash,
        text=record.text,
        rank=rank,
        score=score,
    )


def rule_to_result(rule: KnowledgeRule, *, rank: int, score: float) -> RetrievalResult:
    instrument = f" Instrument: {rule.instrument_name}." if rule.instrument_name else ""
    recommendation = f" Recommendation: {rule.recommendation}" if rule.recommendation else ""
    return RetrievalResult(
        chunk_id=rule.rule_id,
        source_url=rule.source_url,
        source_title=rule.source_title,
        document_type="structured",
        section_heading=f"rule: {rule.condition}",
        page=rule.page,
        crawl_timestamp=rule.crawl_timestamp,
        source_hash=rule.source_hash,
        text=(
            f"DCIF knowledge rule. Severity: {rule.severity}.{instrument} "
            f"Condition: {rule.condition}. Statement: {rule.statement}.{recommendation}"
        ),
        rank=rank,
        score=score,
    )


def rule_matches_query(rule: KnowledgeRule, query: str, instrument: str | None = None) -> bool:
    lowered = query.lower()
    if instrument and rule.instrument_name and not text_matches_instrument_name(rule.instrument_name, instrument):
        return False
    text = f"{rule.condition} {rule.statement} {rule.recommendation or ''}".lower()
    query_tokens = set(tokenize(query))
    if any(term in lowered for term in ("water", "aqueous", "coffee", "raw")) and any(
        term in text for term in ("water", "aqueous", "solvent", "sample")
    ):
        return True
    return bool(query_tokens & set(tokenize(text)))


def score_rule_for_query(rule: KnowledgeRule, query: str) -> float:
    lowered = query.lower()
    text = f"{rule.condition} {rule.statement} {rule.recommendation or ''}".lower()
    score = 0.0
    if rule.severity == "hard_constraint":
        score += 10.0
    if any(term in lowered for term in ("water", "aqueous", "coffee", "raw")) and any(
        term in text for term in ("aqueous", "water", "acid", "solvent", "sample")
    ):
        score += 6.0
    query_tokens = set(tokenize(query))
    score += min(2.0, len(query_tokens & set(tokenize(text))) * 0.25)
    return score


def text_matches_instrument_name(candidate_name: str, instrument: str) -> bool:
    if normalized_key(candidate_name) == normalized_key(instrument):
        return True
    candidate_key = normalized_key(candidate_name)
    aliases = [instrument, *INSTRUMENT_ALIASES.get(instrument, [])]
    return any(
        alias_in_text(alias, candidate_name)
        or (len(normalized_key(alias)) >= 4 and normalized_key(alias) in candidate_key)
        for alias in aliases
    )


def instrument_candidates(records: list[StructuredRecord]) -> list[StructuredRecord]:
    aggregate = [
        record
        for record in records
        if record.record_type == "instrument" and record.name.endswith(" instruments")
    ]
    individual = [
        record
        for record in records
        if record.record_type == "instrument" and not record.name.endswith(" instruments")
    ]
    return aggregate + individual


def catalog_key(name: str) -> str:
    return normalized_key(name)


def display_category(record: StructuredRecord) -> str:
    category_aliases = {
        "Mass Spectrometers": "Mass Spectrometry",
        "NMR Spectrometers": "NMR Spectroscopy",
    }
    return category_aliases.get(record.category, record.category)


def add_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def record_reference(record: StructuredRecord) -> dict:
    return {
        "chunk_id": record.record_id,
        "source_title": record.source_title,
        "section_heading": record.section_heading,
        "page": record.page,
    }


def build_dcif_catalog(records: list[StructuredRecord]) -> dict:
    instruments_by_key: dict[str, dict] = {}
    category_order: list[str] = []
    overview_records: dict[str, list[dict]] = {}

    def category_bucket(category: str) -> None:
        if category not in category_order:
            category_order.append(category)

    def instrument_bucket(record: StructuredRecord) -> dict:
        category = display_category(record)
        category_bucket(category)
        key = f"{catalog_key(category)}:{catalog_key(record.name)}"
        item = instruments_by_key.setdefault(
            key,
            {
                "name": record.name,
                "category": category,
                "seen_in": [],
                "chunk_ids": [],
                "fee": None,
                "guide_titles": [],
                "source_notes": [],
            },
        )
        add_unique(item["chunk_ids"], record.record_id)
        return item

    for record in records:
        if record.record_type == "instrument" and record.name.endswith(" instruments"):
            category = display_category(record)
            category_bucket(category)
            overview_records.setdefault(category, []).append(record_reference(record))

    for record in records:
        if record.record_type != "instrument" or record.name.endswith(" instruments"):
            continue
        item = instrument_bucket(record)
        add_unique(item["seen_in"], "instrument inventory")
        add_unique(item["source_notes"], record.text[:500])

    for record in records:
        if record.record_type != "fee":
            continue
        item = instrument_bucket(record)
        if item["seen_in"] == []:
            item["name"] = record.name
        add_unique(item["seen_in"], "fee table")
        item["fee"] = {
            "mit_rate": record.fields.get("mit_rate"),
            "nonprofit_rate": record.fields.get("nonprofit_rate"),
            "commercial_rate": record.fields.get("commercial_rate"),
            "unit": record.fields.get("unit"),
        }

    for record in records:
        if record.record_type != "guide":
            continue
        guide_title = record.fields.get("guide_title") or record.name
        guide_key = catalog_key(guide_title)
        for item in instruments_by_key.values():
            item_key = catalog_key(item["name"])
            if item_key and item_key in guide_key:
                add_unique(item["guide_titles"], guide_title)
                add_unique(item["chunk_ids"], record.record_id)
                add_unique(item["seen_in"], "linked guide")

    instruments_by_category = []
    for category in category_order:
        instruments = [
            item
            for item in instruments_by_key.values()
            if item["category"] == category
        ]
        instruments.sort(key=lambda item: item["name"].lower())
        instruments_by_category.append(
            {
                "category": category,
                "overview_sources": overview_records.get(category, []),
                "instruments": instruments,
            }
        )

    resources_by_category: dict[str, list[dict]] = {}
    for record in records:
        if record.record_type != "guide":
            continue
        resources_by_category.setdefault(record.category, []).append(
            {
                "title": record.fields.get("guide_title") or record.name,
                "chunk_id": record.record_id,
            }
        )

    return {
        "catalog_source": "data/structured/records.jsonl",
        "record_counts": {
            record_type: sum(1 for record in records if record.record_type == record_type)
            for record_type in ("instrument", "fee", "guide", "staff", "overview_section")
        },
        "instruments_by_category": instruments_by_category,
        "resources_by_category": [
            {"category": category, "resources": resources}
            for category, resources in sorted(resources_by_category.items())
        ],
    }


def catalog_records_for_context(records: list[StructuredRecord], intent: QueryIntent) -> list[StructuredRecord]:
    if intent == "inventory_lookup":
        return [
            record
            for record in records
            if record.record_type in {"instrument", "fee", "guide"}
        ]
    if intent == "instrument_procedure":
        return [
            record
            for record in records
            if record.record_type in {"instrument", "guide"}
        ]
    return [
        record
        for record in records
        if record.record_type in {"instrument", "fee"}
    ]


def record_matches_instrument(record: StructuredRecord, instrument: str) -> bool:
    record_text = " ".join([record.name, record.text, record.fields.get("instrument", ""), record.fields.get("guide_title", "")])
    record_key = normalized_key(record_text)
    aliases = [instrument, *INSTRUMENT_ALIASES.get(instrument, [])]
    return any(
        alias_in_text(alias, record_text)
        or (len(normalized_key(alias)) >= 4 and normalized_key(alias) in record_key)
        for alias in aliases
    )


def chunk_matches_instrument_guide(chunk: RetrievalResult | object, instrument: str) -> bool:
    title = getattr(chunk, "source_title", "")
    heading = getattr(chunk, "section_heading", "")
    text = getattr(chunk, "text", "")
    haystack_key = normalized_key(" ".join([title, heading, text[:300]]))
    aliases = [instrument, *INSTRUMENT_ALIASES.get(instrument, [])]
    haystack = " ".join([title, heading, text[:300]])
    return any(
        alias_in_text(alias, haystack)
        or (len(normalized_key(alias)) >= 4 and normalized_key(alias) in haystack_key)
        for alias in aliases
    )


def instrument_procedure_query(query: str, instrument: str) -> str:
    guide_terms = " ".join(GUIDE_QUERY_TERMS)
    aliases = " ".join(INSTRUMENT_ALIASES.get(instrument, []))
    return f"{query} {instrument} {aliases} quick start guide {guide_terms}"


def score_instrument_guide_chunk(query: str, instrument: str, chunk: object) -> float:
    title = getattr(chunk, "source_title", "").lower()
    heading = getattr(chunk, "section_heading", "").lower()
    text = getattr(chunk, "text", "").lower()
    query_tokens = set(tokenize(query))
    text_tokens = set(tokenize(text))
    score = 0.0

    if not chunk_matches_instrument_guide(chunk, instrument):
        return 0.0
    if "quick start guide" in title:
        score += 2.0
    if any(normalized_key(alias) in normalized_key(title) for alias in [instrument, *INSTRUMENT_ALIASES.get(instrument, [])]):
        score += 2.0
    if "sample preparation" in text or ("sample" in text and "preparation" in text):
        score += 2.5
    if query_tokens & text_tokens:
        score += min(1.0, len(query_tokens & text_tokens) * 0.08)
    for term in GUIDE_QUERY_TERMS:
        if term in text or term in heading:
            score += 0.18
    return score


def instrument_procedure_results(
    query: str,
    *,
    instrument: str,
    searcher: HybridSearch,
    records: list[StructuredRecord],
    chunks_path: Path,
    limit: int,
) -> list[RetrievalResult]:
    focused_records = [
        record
        for record in records
        if record.record_type in {"instrument", "guide"} and record_matches_instrument(record, instrument)
    ]
    seed_results = [
        record_to_result(record, rank=index + 1, score=1.2 - index * 0.02)
        for index, record in enumerate(focused_records)
    ]

    guide_chunks = []
    for chunk in read_chunks(chunks_path):
        score = score_instrument_guide_chunk(query, instrument, chunk)
        if score > 0:
            guide_chunks.append(RetrievalResult(**chunk.model_dump(), rank=1, score=score))
    guide_chunks.sort(key=lambda item: item.score, reverse=True)

    broad_results = searcher.retrieve(instrument_procedure_query(query, instrument), top_k=8)
    demoted_broad_results = [
        RetrievalResult(**item.model_dump(exclude={"score"}), score=item.score * 0.5)
        for item in broad_results
        if chunk_matches_instrument_guide(item, instrument) or item.document_type == "structured"
    ]

    return merge_results([*guide_chunks[:8], *seed_results, *demoted_broad_results], limit=limit)


def targeted_queries(query: str, profile: QueryProfile, candidates: list[StructuredRecord]) -> list[str]:
    queries = [query]
    if profile.search_terms:
        queries.append(f"{query} {' '.join(profile.search_terms)}")

    for candidate in candidates[:12]:
        terms = [candidate.name, candidate.category]
        if profile.search_terms:
            terms.extend(profile.search_terms[:6])
        queries.append(" ".join([query, *terms]))
    return queries


def merge_results(results: list[RetrievalResult], *, limit: int) -> list[RetrievalResult]:
    merged: dict[str, RetrievalResult] = {}
    for item in results:
        existing = merged.get(item.chunk_id)
        if existing is None or item.score > existing.score:
            merged[item.chunk_id] = item
    ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
    return [
        RetrievalResult(**item.model_dump(exclude={"rank"}), rank=rank)
        for rank, item in enumerate(ranked[:limit], start=1)
    ]


def build_advisory_context(
    query: str,
    *,
    searcher: HybridSearch,
    records_path: Path = data_path("structured", "records.jsonl"),
    chunks_path: Path = data_path("chunks", "chunks.jsonl"),
    instruments_path: Path | None = None,
    resources_path: Path | None = None,
    rules_path: Path | None = None,
    evidence_limit: int = 24,
) -> AdvisoryContext:
    intent = classify_query(query)
    profile = profile_query(query)
    structured_dir = records_path.parent
    instruments_path = instruments_path or structured_dir / "instruments.jsonl"
    resources_path = resources_path or structured_dir / "resources.jsonl"
    rules_path = rules_path or structured_dir / "rules.jsonl"
    records = read_structured_records(records_path)
    instrument_profiles = read_instrument_profiles(instruments_path)
    resources = read_resource_records(resources_path)
    rules = read_knowledge_rules(rules_path)
    candidates = instrument_candidates(records)
    citation_records = catalog_records_for_context(records, intent)
    catalog = build_dcif_catalog(records)
    instrument = extract_instrument(query)
    applicable_rules = []
    if intent in {"instrument_procedure", "instrument_recommendation"}:
        applicable_rules = sorted(
            [rule for rule in rules if rule_matches_query(rule, query, instrument)],
            key=lambda rule: score_rule_for_query(rule, query),
            reverse=True,
        )
    rule_results = [
        rule_to_result(rule, rank=index + 1, score=10.0 + score_rule_for_query(rule, query) - index * 0.03)
        for index, rule in enumerate(applicable_rules)
    ]

    if intent == "instrument_procedure" and instrument:
        evidence = instrument_procedure_results(
            query,
            instrument=instrument,
            searcher=searcher,
            records=records,
            chunks_path=chunks_path,
            limit=evidence_limit,
        )
        evidence = merge_results([*rule_results, *evidence], limit=evidence_limit)
        return AdvisoryContext(
            question=query,
            intent=intent,
            profile=profile,
            candidate_records=[record for record in candidates if record_matches_instrument(record, instrument)],
            citation_records=[
                record
                for record in citation_records
                if record_matches_instrument(record, instrument)
            ],
            catalog=catalog,
            instrument_profiles=[
                profile
                for profile in instrument_profiles
                if text_matches_instrument_name(profile.name, instrument)
            ],
            resources=[
                resource
                for resource in resources
                if any(
                    profile.instrument_id in resource.related_instrument_ids
                    for profile in instrument_profiles
                    if text_matches_instrument_name(profile.name, instrument)
                )
            ],
            rules=applicable_rules,
            evidence=evidence,
        )

    seed_results = [
        record_to_result(record, rank=index + 1, score=max(0.001, 0.03 - index * 0.001))
        for index, record in enumerate(citation_records)
    ]

    gathered: list[RetrievalResult] = [*rule_results, *seed_results]
    for targeted_query in targeted_queries(query, profile, candidates):
        gathered.extend(searcher.retrieve(targeted_query, top_k=5))

    return AdvisoryContext(
        question=query,
        intent=intent,
        profile=profile,
        candidate_records=candidates,
        citation_records=citation_records,
        catalog=catalog,
        instrument_profiles=instrument_profiles,
        resources=resources,
        rules=applicable_rules,
        evidence=merge_results(gathered, limit=evidence_limit),
    )


def advisory_payload(question: str, context: AdvisoryContext) -> dict:
    return {
        "question": question,
        "intent": context.intent,
        "detected_instrument": extract_instrument(question),
        "query_profile": context.profile.model_dump(),
        "available_information": DCIF_INFORMATION_MAP,
        "catalog": context.catalog,
        "instrument_profiles": [
            profile.model_dump(mode="json")
            for profile in context.instrument_profiles
        ],
        "applicable_rules": [
            rule.model_dump(mode="json")
            for rule in context.rules
        ],
        "related_resources": [
            resource.model_dump(mode="json")
            for resource in context.resources[:20]
        ],
        "candidate_instruments": [
            {
                "name": record.name,
                "category": record.category,
                "record_type": record.record_type,
                "summary": record.text[:1200],
                "chunk_id": record.record_id,
            }
            for record in context.candidate_records
        ],
        "sources": context_payload(context.evidence),
    }


def advisory_citation_map(context: AdvisoryContext) -> dict[str, ChatCitation]:
    citation_map = {
        item.chunk_id: ChatCitation(
            chunk_id=item.chunk_id,
            source_url=item.source_url,
            source_title=item.source_title,
            section_heading=item.section_heading,
            page=item.page,
        )
        for item in context.evidence
    }
    for record in context.citation_records:
        citation_map.setdefault(
            record.record_id,
            ChatCitation(
                chunk_id=record.record_id,
                source_url=record.source_url,
                source_title=record.source_title,
                section_heading=record.section_heading,
                page=record.page,
            ),
        )
    return citation_map


def validate_advisory_citations(answer: ChatAnswer, context: AdvisoryContext) -> ChatAnswer:
    citation_map = advisory_citation_map(context)
    answer.citations = [
        citation_map[citation.chunk_id]
        for citation in answer.citations
        if citation.chunk_id in citation_map
    ]
    if not answer.citations and citation_map:
        answer.citations = [next(iter(citation_map.values()))]
        answer.confidence = "low"
    return answer


def extractive_catalog_answer(context: AdvisoryContext) -> ChatAnswer:
    if context.intent != "inventory_lookup" or not context.catalog.get("instruments_by_category"):
        from backend.dcif.llm import extractive_answer

        return extractive_answer("", context.evidence)

    lines = ["DCIF lists the following instruments:"]
    citations = []
    cited: set[str] = set()
    citation_map = advisory_citation_map(context)

    lowered_question = context.question.lower()
    category_terms = {
        "Mass Spectrometry": ("mass", "ms", "spectrometry", "spectrometer"),
        "NMR Spectroscopy": ("nmr", "nuclear magnetic resonance"),
        "Other Instruments": ("other", "hplc", "ftir", "polarimeter", "epr"),
    }
    selected_categories = []
    for category in context.catalog["instruments_by_category"]:
        terms = category_terms.get(category["category"], ())
        if not terms or any(term in lowered_question for term in terms):
            selected_categories.append(category)
    if not selected_categories:
        selected_categories = context.catalog["instruments_by_category"]

    for category in selected_categories:
        names = []
        for item in category["instruments"]:
            label = item["name"]
            if item["seen_in"] == ["fee table"]:
                label = f"{label} (fee table)"
            names.append(label)
            for chunk_id in item["chunk_ids"]:
                if chunk_id in citation_map and chunk_id not in cited and len(citations) < 8:
                    citations.append(citation_map[chunk_id].model_dump())
                    cited.add(chunk_id)
        if names:
            lines.append(f"- {category['category']}: {', '.join(names)}")

    return ChatAnswer.model_validate(
        {
            "answer": "\n".join(lines),
            "citations": citations,
            "confidence": "medium",
        }
    )


def extractive_advisory_answer(context: AdvisoryContext) -> ChatAnswer:
    citation_map = advisory_citation_map(context)
    citations = [
        citation_map[item.chunk_id]
        for item in context.evidence
        if item.chunk_id in citation_map
    ][:3]

    if context.rules:
        hard_rules = [rule for rule in context.rules if rule.severity == "hard_constraint"]
        rules_to_show = hard_rules or context.rules
        instrument = extract_instrument(context.question) or rules_to_show[0].instrument_name or "that instrument"
        lines: list[str] = []
        lowered = context.question.lower()
        if context.profile.sample == "coffee" and "brew" in lowered:
            lines.append(
                f"Probably not directly. Brewed coffee is likely aqueous, and the DCIF guidance for {instrument} flags aqueous or acid-containing samples as a problem."
            )
        else:
            lines.append(f"Based on the DCIF guidance for {instrument}, check these constraints before using it.")
        for rule in rules_to_show[:3]:
            detail = rule.statement
            if rule.recommendation:
                detail = f"{detail} {rule.recommendation}"
            lines.append(f"- {detail}")
        if context.profile.clarifying_question:
            lines.append(context.profile.clarifying_question)
        return ChatAnswer(answer="\n".join(lines), citations=citations, confidence="high" if hard_rules else "medium")

    if context.evidence:
        lead = context.evidence[0]
        return ChatAnswer(
            answer=f"Based on the most relevant DCIF passage: {lead.text}",
            citations=citations,
            confidence="medium",
        )

    return ChatAnswer(
        answer="I could not find DCIF source passages that answer that question.",
        citations=[],
        confidence="low",
    )


def expected_inventory_names(context: AdvisoryContext) -> list[str]:
    lowered_question = context.question.lower()
    category_terms = {
        "Mass Spectrometry": ("mass", "ms", "spectrometry", "spectrometer"),
        "NMR Spectroscopy": ("nmr", "nuclear magnetic resonance"),
        "Other Instruments": ("other", "hplc", "ftir", "polarimeter", "epr"),
    }
    names: list[str] = []
    for category in context.catalog.get("instruments_by_category", []):
        terms = category_terms.get(category["category"], ())
        if terms and not any(term in lowered_question for term in terms):
            continue
        for item in category["instruments"]:
            if item.get("seen_in") != ["fee table"]:
                add_unique(names, item["name"])
    if names:
        return names
    for category in context.catalog.get("instruments_by_category", []):
        for item in category["instruments"]:
            if item.get("seen_in") != ["fee table"]:
                add_unique(names, item["name"])
    return names


def inventory_answer_is_valid(answer: ChatAnswer, context: AdvisoryContext) -> bool:
    text = normalized_key(answer.answer)
    if not text:
        return False
    invalid_phrases = (
        "doesnotlist",
        "donotlist",
        "couldnotfind",
        "nospecificinformation",
        "notcontainspecificinformation",
    )
    if any(phrase in text for phrase in invalid_phrases):
        return False
    expected = expected_inventory_names(context)
    if not expected:
        return False
    present = [name for name in expected if normalized_key(name) in text]
    return len(present) >= max(1, min(3, len(expected)))


def answer_conflicts_with_hard_constraints(answer: ChatAnswer, context: AdvisoryContext) -> bool:
    lowered_question = context.question.lower()
    lowered_answer = answer.answer.lower().lstrip()
    direct_aqueous_question = any(
        term in lowered_question
        for term in ("aqueous", "water", "coffee", "brewed", "raw")
    )
    if not direct_aqueous_question:
        return False
    has_aqueous_hard_constraint = any(
        rule.severity == "hard_constraint"
        and any(term in f"{rule.condition} {rule.statement}".lower() for term in ("aqueous", "water"))
        for rule in context.rules
    )
    if not has_aqueous_hard_constraint:
        return False
    starts_with_yes = lowered_answer.startswith(("yes", "yes,", "yes."))
    has_clear_limit = any(phrase in lowered_answer for phrase in ("not directly", "do not use", "cannot directly"))
    return starts_with_yes and not has_clear_limit


async def synthesize_inventory_answer(
    *,
    question: str,
    context: AdvisoryContext,
    client: LLMClient,
    settings: LLMSettings | None = None,
) -> ChatAnswer:
    deterministic = extractive_catalog_answer(context)
    settings = settings or LLMSettings.from_env()
    answer = await client.generate_json(
        system_prompt=DCIF_ADVISOR_SYSTEM_PROMPT,
        user_payload={
            **advisory_payload(question, context),
            "deterministic_catalog_answer": deterministic.answer,
            "instruction": (
                "Rewrite the deterministic catalog answer in a concise, helpful way. "
                "Do not omit listed instruments. If the catalog lists instruments, never say none are listed."
            ),
        },
        output_model=ChatAnswer,
        json_schema=CHAT_ANSWER_SCHEMA,
        metadata=LLMRequestMetadata(feature="dcif_inventory", prompt_version=f"{settings.prompt_version}-inventory-v1"),
        user=LLMUserContext(safety_identifier="dcif-inventory:anonymous"),
    )
    answer = validate_advisory_citations(answer, context)
    if not inventory_answer_is_valid(answer, context):
        return deterministic
    return answer


async def synthesize_advice(
    *,
    question: str,
    context: AdvisoryContext,
    client: LLMClient,
    settings: LLMSettings | None = None,
) -> ChatAnswer:
    settings = settings or LLMSettings.from_env()
    deterministic = extractive_advisory_answer(context)
    answer = await client.generate_json(
        system_prompt=DCIF_ADVISOR_SYSTEM_PROMPT,
        user_payload={
            **advisory_payload(question, context),
            "deterministic_constraint_answer": deterministic.answer,
            "instruction": (
                "Use the deterministic constraint answer as a safety floor. "
                "If a hard constraint applies to the user's sample, lead with it and avoid an unconditional yes."
            ),
        },
        output_model=ChatAnswer,
        json_schema=CHAT_ANSWER_SCHEMA,
        metadata=LLMRequestMetadata(feature="dcif_advisor", prompt_version=f"{settings.prompt_version}-advisor-v1"),
        user=LLMUserContext(safety_identifier="dcif-advisor:anonymous"),
    )
    answer = validate_advisory_citations(answer, context)
    if answer_conflicts_with_hard_constraints(answer, context):
        return deterministic
    return answer
