from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from backend.dcif.io import (
    load_normalized,
    normalized_doc_paths,
    read_structured_records,
    write_jsonl,
)
from backend.dcif.models import (
    InstrumentProfile,
    KnowledgeDocument,
    KnowledgeRule,
    KnowledgeSection,
    NormalizedDocument,
    NormalizedSection,
    ResourceRecord,
    StructuredRecord,
)
from backend.dcif.paths import data_path


INSTRUMENT_ALIASES: dict[str, list[str]] = {
    "GC/MS": ["gc/ms", "gc-ms", "gcms", "gc ms", "agilent gc/ms"],
    "LCMS": ["lcms", "lc/ms", "lc-ms", "lc ms", "single q lcms", "single quadrupole lcms"],
    "AccuTOF-DART": ["accutof-dart", "accutof dart", "accutof", "accu-tof", "dart"],
    "Maldi-TOF": ["maldi-tof", "maldi tof", "malditof", "maldi", "autoflex"],
    "Q-TOF": ["q-tof", "qtof", "q tof", "qtof-hr", "qtof hr"],
    "QQQ": ["qqq", "qqq lcms", "triple quadrupole", "triple-quadrupole", "ultivo"],
    "ICP-MS": ["icp-ms", "icpms", "icp ms"],
    "Avance401": ["avance401", "avance 401", "aviii 401"],
    "Neo402": ["neo402", "neo 402"],
    "Neo500": ["neo500", "neo 500"],
    "Neo501": ["neo501", "neo 501", "bruker501", "bruker 501"],
    "JEOL502": ["jeol502", "jeol 502", "jeol"],
    "Neo600": ["neo600", "neo 600"],
    "Time-Domain NMR": ["time-domain nmr", "time domain nmr", "td-nmr", "tdspec"],
    "FTIR": ["ftir", "alpha ii"],
    "Polarimeter": ["polarimeter", "polarimetry", "jasco"],
    "HPLC": ["hplc", "infinity 1260"],
    "EPR": ["epr"],
}

INSTRUMENT_ID_ALIASES = {
    "GC/MS": "gcms",
    "LCMS": "lcms",
    "AccuTOF-DART": "accutof_dart",
    "Maldi-TOF": "maldi_tof",
    "Q-TOF": "qtof",
    "QQQ": "qqq",
    "ICP-MS": "icp_ms",
    "Avance401": "avance401",
    "Neo402": "neo402",
    "Neo500": "neo500",
    "Neo501": "neo501",
    "JEOL502": "jeol502",
    "Neo600": "neo600",
    "Time-Domain NMR": "time_domain_nmr",
    "FTIR": "ftir",
    "Polarimeter": "polarimeter",
    "HPLC": "hplc",
    "EPR": "epr",
}

FEE_CATEGORY_ALIASES = {
    "Mass Spectrometers": "Mass Spectrometry",
    "NMR Spectrometers": "NMR Spectroscopy",
}


@dataclass
class KnowledgeArtifacts:
    documents: list[KnowledgeDocument]
    sections: list[KnowledgeSection]
    instruments: list[InstrumentProfile]
    resources: list[ResourceRecord]
    rules: list[KnowledgeRule]


def stable_id(*parts: object, length: int = 24) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def instrument_id_for(name: str) -> str:
    if name in INSTRUMENT_ID_ALIASES:
        return INSTRUMENT_ID_ALIASES[name]
    return normalized_key(name)


def display_category(category: str) -> str:
    return FEE_CATEGORY_ALIASES.get(category, category)


def add_unique(items: list[str], value: str | None) -> None:
    if value and value not in items:
        items.append(value)


def alias_in_text(alias: str, text: str) -> bool:
    lowered_alias = alias.lower()
    lowered_text = text.lower()
    if not lowered_alias:
        return False
    if re.fullmatch(r"[a-z0-9]+", lowered_alias) and len(lowered_alias) <= 3:
        return re.search(rf"\b{re.escape(lowered_alias)}\b", lowered_text) is not None
    return lowered_alias in lowered_text


def text_matches_alias(text: str, canonical_name: str) -> bool:
    key = normalized_key(text)
    aliases = [canonical_name, *INSTRUMENT_ALIASES.get(canonical_name, [])]
    for alias in aliases:
        alias_key = normalized_key(alias)
        if alias_in_text(alias, text) or (len(alias_key) >= 4 and alias_key in key):
            return True
    return False


def related_instrument_ids_for(text: str, *, require_alias: bool = True) -> list[str]:
    related: list[str] = []
    for name in INSTRUMENT_ALIASES:
        if text_matches_alias(text, name):
            add_unique(related, instrument_id_for(name))
    if not related and not require_alias and "nmr" in text.lower():
        add_unique(related, "nmr_general")
    return related


def classify_document(doc: NormalizedDocument) -> str:
    title = doc.source_title.lower()
    url = doc.source_url.lower()
    if doc.document_type == "html":
        return "overview"
    if "quick start" in title or "quick guide" in title or "user guide" in title:
        return "quick_start"
    if "training" in title:
        return "training_guide"
    if "application note" in title or "diffusion" in title or "selective" in title or "measurement" in title:
        return "application_note"
    if "safety" in title:
        return "safety"
    if "reservation" in title or "res1p" in title:
        return "reservation"
    if "seminar" in title or "lecture" in title or "introduction" in title or "course" in title:
        return "seminar_or_lecture"
    if "manual" in title or "reference" in title or "manual" in url:
        return "manual"
    return "resource"


def classify_resource(title: str, category: str) -> str:
    lowered = f"{title} {category}".lower()
    if "quick start" in lowered or "quick guide" in lowered or "user guide" in lowered:
        return "quick_start"
    if "training" in lowered:
        return "training_guide"
    if "application note" in lowered or "application notes" in lowered:
        return "application_note"
    if "safety" in lowered:
        return "safety"
    if "reservation" in lowered or "res1p" in lowered:
        return "reservation"
    if "seminar" in lowered or "lecture" in lowered or "course" in lowered:
        return "seminar_or_lecture"
    if "spreadsheet" in lowered:
        return "spreadsheet"
    return "resource"


def classify_section(section: NormalizedSection) -> str:
    text = f"{section.heading}\n{section.text[:1200]}".lower()
    if "sample preparation" in text:
        return "sample_preparation"
    if "compatible solvents" in text or "solvent" in text[:500]:
        return "compatible_solvents"
    if "operating procedure" in text or "acquisition" in text:
        return "operating_procedure"
    if "shutdown" in text:
        return "shutdown"
    if "data processing" in text or "process" in text:
        return "data_processing"
    if "troubleshoot" in text or "error" in text or "fail" in text:
        return "troubleshooting"
    if "safety" in text or "hazard" in text:
        return "safety"
    if "fee" in text or "rate" in text:
        return "fees"
    return "content"


def sentence_candidates(text: str) -> list[str]:
    clean = " ".join(text.split())
    clean = re.sub(
        r"\b(Sample preparation|Operating procedure|Compatible solvents|Data processing|Shutdown):",
        r". \1:",
        clean,
        flags=re.IGNORECASE,
    ).lstrip(". ")
    pieces = re.split(r"(?<=[.!?])\s+|(?<=\.)\s*(?=[A-Z][a-z]+:)", clean)
    return [piece.strip() for piece in pieces if len(piece.strip()) >= 25]


def rule_condition(sentence: str) -> str:
    lowered = sentence.lower()
    if "water" in lowered or "aqueous" in lowered:
        if "acid" in lowered:
            return "aqueous_or_acid_sample"
        return "aqueous_sample"
    if "acid" in lowered:
        return "acidic_sample"
    if "high boiling" in lowered:
        return "high_boiling_solvent"
    if "nonvolatile buffer" in lowered or "phosphate" in lowered or "tris" in lowered:
        return "nonvolatile_buffer"
    if "cloudy" in lowered or "floating particles" in lowered or "filter" in lowered:
        return "particulate_sample"
    if "concentration" in lowered or "ppm" in lowered or "mg/ml" in lowered:
        return "sample_concentration"
    return "sample_or_operation"


def rule_severity(sentence: str) -> str:
    lowered = sentence.lower()
    hard_markers = ("not allowed", "avoid", "must", "will damage", "no exceptions", "should not")
    return "hard_constraint" if any(marker in lowered for marker in hard_markers) else "guidance"


def should_extract_rule(sentence: str) -> bool:
    lowered = sentence.lower()
    if not any(
        marker in lowered
        for marker in (
            "not allowed",
            "avoid",
            "must",
            "should",
            "will damage",
            "need help",
            "ask for help",
            "sample preparation",
            "compatible solvents",
        )
    ):
        return False
    return any(
        domain_term in lowered
        for domain_term in (
            "sample",
            "solvent",
            "water",
            "aqueous",
            "acid",
            "buffer",
            "filter",
            "column",
            "source",
            "concentration",
            "training",
        )
    )


def create_documents_and_sections(docs: list[NormalizedDocument]) -> tuple[list[KnowledgeDocument], list[KnowledgeSection]]:
    documents: list[KnowledgeDocument] = []
    sections: list[KnowledgeSection] = []
    for doc in docs:
        document_id = stable_id("document", doc.source_url, doc.source_hash)
        related = related_instrument_ids_for(f"{doc.source_title} {doc.source_url}", require_alias=False)
        documents.append(
            KnowledgeDocument(
                document_id=document_id,
                source_url=doc.source_url,
                source_title=doc.source_title,
                document_type=doc.document_type,
                knowledge_type=classify_document(doc),
                related_instrument_ids=related,
                source_hash=doc.source_hash,
                crawl_timestamp=doc.crawl_timestamp,
            )
        )
        for index, section in enumerate(doc.sections):
            section_text = f"{doc.source_title} {section.heading} {section.text[:1000]}"
            section_related = related_instrument_ids_for(section_text, require_alias=False) or related
            sections.append(
                KnowledgeSection(
                    section_id=stable_id("section", document_id, section.heading, section.page, index),
                    document_id=document_id,
                    source_url=doc.source_url,
                    source_title=doc.source_title,
                    heading=section.heading,
                    section_type=classify_section(section),
                    text=section.text,
                    page=section.page,
                    related_instrument_ids=section_related,
                    source_hash=doc.source_hash,
                    crawl_timestamp=doc.crawl_timestamp,
                )
            )
    return documents, sections


def document_lookup(documents: list[KnowledgeDocument]) -> dict[str, KnowledgeDocument]:
    return {document.document_id: document for document in documents}


def match_document_for_resource(title: str, documents: list[KnowledgeDocument]) -> KnowledgeDocument | None:
    title_key = normalized_key(title)
    if not title_key:
        return None
    best: KnowledgeDocument | None = None
    best_score = 0
    for document in documents:
        doc_key = normalized_key(document.source_title)
        if not doc_key:
            continue
        score = 0
        if title_key in doc_key or doc_key in title_key:
            score += min(len(title_key), len(doc_key))
        for instrument_id in document.related_instrument_ids:
            if instrument_id and instrument_id in normalized_key(title):
                score += 6
        if score > best_score:
            best = document
            best_score = score
    return best if best_score >= 6 else None


def build_resources(records: list[StructuredRecord], documents: list[KnowledgeDocument]) -> list[ResourceRecord]:
    resources: list[ResourceRecord] = []
    seen: set[str] = set()
    matched_document_ids: set[str] = set()

    for record in records:
        if record.record_type != "guide":
            continue
        title = record.fields.get("guide_title") or record.name
        matched_doc = match_document_for_resource(title, documents)
        if matched_doc:
            matched_document_ids.add(matched_doc.document_id)
        related = list(matched_doc.related_instrument_ids) if matched_doc else related_instrument_ids_for(title)
        resource_id = stable_id("resource", title, record.category, matched_doc.document_id if matched_doc else record.record_id)
        seen.add(resource_id)
        resources.append(
            ResourceRecord(
                resource_id=resource_id,
                title=title,
                resource_type=classify_resource(title, record.category),
                category=record.category,
                document_id=matched_doc.document_id if matched_doc else None,
                source_url=matched_doc.source_url if matched_doc else record.source_url,
                source_title=matched_doc.source_title if matched_doc else record.source_title,
                related_instrument_ids=related,
                source_record_id=record.record_id,
            )
        )

    for document in documents:
        if document.knowledge_type == "overview" or document.document_id in matched_document_ids:
            continue
        resource_id = stable_id("resource", document.source_title, document.document_id)
        if resource_id in seen:
            continue
        resources.append(
            ResourceRecord(
                resource_id=resource_id,
                title=document.source_title,
                resource_type=document.knowledge_type,
                category=document.knowledge_type,
                document_id=document.document_id,
                source_url=document.source_url,
                source_title=document.source_title,
                related_instrument_ids=document.related_instrument_ids,
            )
        )
    return sorted(resources, key=lambda item: (item.category.lower(), item.title.lower()))


def build_instruments(
    records: list[StructuredRecord],
    documents: list[KnowledgeDocument],
    resources: list[ResourceRecord],
) -> list[InstrumentProfile]:
    profiles: dict[str, InstrumentProfile] = {}

    def bucket(name: str, category: str) -> InstrumentProfile:
        instrument_id = instrument_id_for(name)
        profile = profiles.get(instrument_id)
        if profile is None:
            aliases = [alias for alias in INSTRUMENT_ALIASES.get(name, []) if alias != name.lower()]
            profile = InstrumentProfile(
                instrument_id=instrument_id,
                name=name,
                category=display_category(category),
                aliases=aliases,
            )
            profiles[instrument_id] = profile
        if profile.category != display_category(category) and profile.category in {"Mass Spectrometers", "NMR Spectrometers"}:
            profile.category = display_category(category)
        return profile

    for record in records:
        if record.record_type == "instrument" and not record.name.endswith(" instruments"):
            profile = bucket(record.name, record.category)
            profile.description = record.text
            add_unique(profile.source_record_ids, record.record_id)
            profile.source_url = record.source_url
            profile.source_title = record.source_title
        elif record.record_type == "fee":
            profile = bucket(record.name, record.category)
            profile.fee = {
                key: value
                for key, value in record.fields.items()
                if key in {"mit_rate", "nonprofit_rate", "commercial_rate", "unit"} and value
            }
            add_unique(profile.source_record_ids, record.record_id)
            profile.source_url = profile.source_url or record.source_url
            profile.source_title = profile.source_title or record.source_title

    for document in documents:
        for instrument_id in document.related_instrument_ids:
            if instrument_id in profiles:
                add_unique(profiles[instrument_id].related_document_ids, document.document_id)

    for resource in resources:
        for instrument_id in resource.related_instrument_ids:
            if instrument_id in profiles:
                add_unique(profiles[instrument_id].related_resource_ids, resource.resource_id)

    return sorted(profiles.values(), key=lambda item: (item.category.lower(), item.name.lower()))


def build_rules(sections: list[KnowledgeSection], instruments: list[InstrumentProfile]) -> list[KnowledgeRule]:
    known_instruments = {instrument.instrument_id: instrument for instrument in instruments}
    rules: list[KnowledgeRule] = []
    seen: set[str] = set()
    for section in sections:
        if section.section_type not in {
            "sample_preparation",
            "compatible_solvents",
            "operating_procedure",
            "safety",
            "troubleshooting",
        }:
            continue
        for sentence in sentence_candidates(section.text):
            if not should_extract_rule(sentence):
                continue
            related = [instrument_id for instrument_id in section.related_instrument_ids if instrument_id in known_instruments]
            if not related:
                continue
            for instrument_id in related:
                rule_id = stable_id("rule", instrument_id, section.section_id, sentence)
                if rule_id in seen:
                    continue
                seen.add(rule_id)
                severity = rule_severity(sentence)
                recommendation = None
                if severity == "hard_constraint" and ("water" in sentence.lower() or "aqueous" in sentence.lower()):
                    recommendation = "Do not use this instrument for aqueous samples unless DCIF staff explicitly approve an alternate workflow."
                rules.append(
                    KnowledgeRule(
                        rule_id=rule_id,
                        instrument_id=instrument_id,
                        instrument_name=known_instruments[instrument_id].name,
                        severity=severity,  # type: ignore[arg-type]
                        condition=rule_condition(sentence),
                        statement=sentence,
                        recommendation=recommendation,
                        source_url=section.source_url,
                        source_title=section.source_title,
                        section_id=section.section_id,
                        page=section.page,
                        source_hash=section.source_hash,
                        crawl_timestamp=section.crawl_timestamp,
                    )
                )
    return sorted(rules, key=lambda item: (item.instrument_id or "", item.severity, item.condition, item.statement))


def build_knowledge_artifacts(
    *,
    normalized_dir: Path = data_path("normalized"),
    records_path: Path = data_path("structured", "records.jsonl"),
) -> KnowledgeArtifacts:
    docs = [load_normalized(path) for path in normalized_doc_paths(normalized_dir)]
    records = read_structured_records(records_path)
    documents, sections = create_documents_and_sections(docs)
    resources = build_resources(records, documents)
    instruments = build_instruments(records, documents, resources)
    rules = build_rules(sections, instruments)
    return KnowledgeArtifacts(
        documents=documents,
        sections=sections,
        instruments=instruments,
        resources=resources,
        rules=rules,
    )


def write_knowledge_artifacts(
    *,
    output_dir: Path = data_path("structured"),
    normalized_dir: Path = data_path("normalized"),
    records_path: Path = data_path("structured", "records.jsonl"),
) -> KnowledgeArtifacts:
    artifacts = build_knowledge_artifacts(normalized_dir=normalized_dir, records_path=records_path)
    write_jsonl(output_dir / "documents.jsonl", artifacts.documents)
    write_jsonl(output_dir / "sections.jsonl", artifacts.sections)
    write_jsonl(output_dir / "instruments.jsonl", artifacts.instruments)
    write_jsonl(output_dir / "resources.jsonl", artifacts.resources)
    write_jsonl(output_dir / "rules.jsonl", artifacts.rules)
    return artifacts
