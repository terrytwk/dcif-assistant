from __future__ import annotations

import re
import hashlib
from pathlib import Path

from backend.dcif.io import load_normalized, normalized_doc_paths, write_jsonl
from backend.dcif.models import Chunk, NormalizedDocument, NormalizedSection, StructuredRecord
from backend.dcif.paths import data_path


OVERVIEW_URL_MARKER = "/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/"

INSTRUMENT_SECTION_CATEGORIES = {
    "Mass Spectrometry (MS)": "Mass Spectrometry",
    "Nuclear Magnetic Resonance (NMR)": "NMR Spectroscopy",
    "Other Instruments": "Other Instruments",
}

FEE_CATEGORIES = {"Mass Spectrometers", "NMR Spectrometers", "Other Instruments"}

GUIDE_SECTIONS = {
    "Instrument Training Guides",
    "Application Notes",
    "Batch NMR automation",
    "Nuclear Magnetic Resonance (NMR)",
    "Mass Spectrometry (MS)",
    "Other",
    "DCIF Seminar series",
    "Guest lectures in Chemistry",
    "Advanced topics",
}

STAFF_NAME_RE = re.compile(r"^([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})\s+(.+)$")


def is_overview_doc(doc: NormalizedDocument) -> bool:
    return doc.document_type == "html" and OVERVIEW_URL_MARKER in doc.source_url


def source_fields(doc: NormalizedDocument, section: NormalizedSection) -> dict:
    return {
        "source_url": doc.source_url,
        "source_title": doc.source_title,
        "section_heading": section.heading,
        "page": section.page,
        "crawl_timestamp": doc.crawl_timestamp,
        "source_hash": doc.source_hash,
    }


def record_id_for(doc: NormalizedDocument, record_type: str, category: str, name: str, text: str) -> str:
    raw = "|".join(("structured", doc.source_url, doc.source_hash, record_type, category, name, text))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def infer_instrument_name(line: str) -> str:
    normalized = " ".join(line.split())
    for marker in (" The ", " is ", " lab has ", " owns "):
        if marker in normalized:
            candidate = normalized.split(marker, 1)[0].strip()
            if 1 <= len(candidate.split()) <= 4:
                return candidate
    return " ".join(normalized.split()[:4])


def is_instrument_description_line(line: str) -> bool:
    if line.lower().startswith(("please note", "click here")):
        return False
    return any(marker in line for marker in (" The ", " is ", " lab has ", " owns "))


def extract_instrument_records(doc: NormalizedDocument, section: NormalizedSection) -> list[StructuredRecord]:
    category = INSTRUMENT_SECTION_CATEGORIES.get(section.heading)
    if not category:
        return []

    records: list[StructuredRecord] = []
    instruments: list[str] = []
    descriptions: list[str] = []
    for line in section.text.splitlines():
        description = " ".join(line.split())
        if len(description) < 30 or not is_instrument_description_line(description):
            continue
        name = infer_instrument_name(description)
        instruments.append(name)
        descriptions.append(description)
        text = (
            f"DCIF instrument inventory. Category: {category}. "
            f"Instrument: {name}. Description: {description}"
        )
        records.append(
            StructuredRecord(
                record_id=record_id_for(doc, "instrument", category, name, description),
                record_type="instrument",
                category=category,
                name=name,
                text=text,
                fields={"instrument": name, "category": category},
                **source_fields(doc, section),
            )
        )
    if instruments:
        summary = (
            f"DCIF instrument inventory summary. Category: {category}. "
            f"Available instruments: {', '.join(instruments)}. "
            f"Instrument details: {' '.join(descriptions)}"
        )
        records.insert(
            0,
            StructuredRecord(
                record_id=record_id_for(doc, "instrument", category, f"{category} instruments", summary),
                record_type="instrument",
                category=category,
                name=f"{category} instruments",
                text=summary,
                fields={"instruments": ", ".join(instruments), "category": category},
                **source_fields(doc, section),
            ),
        )
    return records


def extract_fee_records(doc: NormalizedDocument, section: NormalizedSection) -> list[StructuredRecord]:
    if section.heading != "Fees":
        return []

    lines = [line.strip() for line in section.text.splitlines() if line.strip()]
    records: list[StructuredRecord] = []
    category = ""
    index = 0
    while index < len(lines):
        line = lines[index]
        if line in {"Instrument", "MIT", "Non-Profit", "Commercial", "Unit"}:
            index += 1
            continue
        if line in FEE_CATEGORIES:
            category = line
            index += 1
            continue
        if category and index + 4 < len(lines):
            name, mit, nonprofit, commercial, unit = lines[index : index + 5]
            if mit.startswith("$") and nonprofit and unit in {"per hour", "each"}:
                text = (
                    f"DCIF fee schedule. Category: {category}. Instrument or service: {name}. "
                    f"MIT rate: {mit} {unit}. Non-profit rate: {nonprofit} {unit}. "
                    f"Commercial rate: {commercial} {unit}."
                )
                records.append(
                    StructuredRecord(
                        record_id=record_id_for(doc, "fee", category, name, text),
                        record_type="fee",
                        category=category,
                        name=name,
                        text=text,
                        fields={
                            "instrument": name,
                            "category": category,
                            "mit_rate": mit,
                            "nonprofit_rate": nonprofit,
                            "commercial_rate": commercial,
                            "unit": unit,
                        },
                        **source_fields(doc, section),
                    )
                )
                index += 5
                continue
        index += 1
    return records


def extract_staff_records(doc: NormalizedDocument, section: NormalizedSection) -> list[StructuredRecord]:
    if section.heading != "Staff":
        return []

    records: list[StructuredRecord] = []
    for line in section.text.splitlines():
        description = " ".join(line.split())
        if len(description) < 40:
            continue
        match = STAFF_NAME_RE.match(description)
        if not match:
            continue
        name = match.group(1)
        text = f"DCIF staff record. Staff member: {name}. Details: {description}"
        records.append(
            StructuredRecord(
                record_id=record_id_for(doc, "staff", "Staff", name, description),
                record_type="staff",
                category="Staff",
                name=name,
                text=text,
                fields={"staff_member": name},
                **source_fields(doc, section),
            )
        )
    return records


def extract_guide_records(doc: NormalizedDocument, section: NormalizedSection) -> list[StructuredRecord]:
    if section.heading not in GUIDE_SECTIONS:
        return []

    records: list[StructuredRecord] = []
    for line in section.text.splitlines():
        title = " ".join(line.split())
        if not title or len(title) < 3:
            continue
        if section.heading in INSTRUMENT_SECTION_CATEGORIES and any(
            marker in title for marker in (" The ", " is ", " lab has ", " owns ")
        ):
            continue
        if len(title) > 180 and not any(word in title.lower() for word in {"guide", "note", "lecture", "seminar"}):
            continue
        text = f"DCIF linked guide or application note. Category: {section.heading}. Title: {title}."
        records.append(
            StructuredRecord(
                record_id=record_id_for(doc, "guide", section.heading, title, text),
                record_type="guide",
                category=section.heading,
                name=title,
                text=text,
                fields={"guide_title": title, "category": section.heading},
                **source_fields(doc, section),
            )
        )
    return records


def extract_overview_section_records(doc: NormalizedDocument, section: NormalizedSection) -> list[StructuredRecord]:
    if section.heading not in {"General Information", "Training Requests", "Instrument Reservations", "Software"}:
        return []
    text = f"DCIF overview section. Topic: {section.heading}. Details: {section.text}"
    return [
        StructuredRecord(
            record_id=record_id_for(doc, "overview_section", section.heading, section.heading, section.text),
            record_type="overview_section",
            category=section.heading,
            name=section.heading,
            text=text,
            fields={"topic": section.heading},
            **source_fields(doc, section),
        )
    ]


def extract_records_from_document(doc: NormalizedDocument) -> list[StructuredRecord]:
    if not is_overview_doc(doc):
        return []

    records: list[StructuredRecord] = []
    for section in doc.sections:
        records.extend(extract_instrument_records(doc, section))
        records.extend(extract_fee_records(doc, section))
        records.extend(extract_staff_records(doc, section))
        records.extend(extract_guide_records(doc, section))
        records.extend(extract_overview_section_records(doc, section))
    return records


def records_to_chunks(records: list[StructuredRecord]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for record in records:
        chunks.append(
            Chunk(
                chunk_id=record.record_id,
                source_url=record.source_url,
                source_title=record.source_title,
                document_type="structured",
                section_heading=f"{record.record_type}: {record.category}",
                page=record.page,
                crawl_timestamp=record.crawl_timestamp,
                source_hash=record.source_hash,
                text=record.text,
            )
        )
    return chunks


def extract_structured_records(
    *,
    normalized_dir: Path = data_path("normalized"),
    records_path: Path = data_path("structured", "records.jsonl"),
) -> list[StructuredRecord]:
    records: list[StructuredRecord] = []
    for path in normalized_doc_paths(normalized_dir):
        records.extend(extract_records_from_document(load_normalized(path)))
    write_jsonl(records_path, records)
    return records
