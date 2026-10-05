# DCIF Knowledge Organization

This project stores DCIF knowledge in layers. Raw scraped files are preserved, parsed into normalized
documents, organized into structured knowledge artifacts, then indexed for retrieval. The structured
knowledge files are the canonical application-facing layer; chunks and vector indexes are derived
search artifacts.

## Layered Model

```text
data/raw/
  -> original HTML/PDF snapshots and source metadata

data/normalized/
  -> parsed documents with sections/pages

data/structured/records.jsonl
  -> deterministic overview-derived legacy records

data/structured/{documents,sections,instruments,resources,rules}.jsonl
  -> hierarchical knowledge layer

data/chunks/ + data/indexes/
  -> retrieval indexes derived from normalized + structured knowledge
```

The intent is:

- **raw** answers "what did we fetch?"
- **normalized** answers "what text did we parse?"
- **structured** answers "what entities, resources, and constraints do we know?"
- **chunks/indexes** answer "how do we search it quickly?"

## Knowledge Artifacts

The hierarchy is built by `backend/dcif/knowledge.py` and written by:

```bash
dcif build-knowledge
```

`dcif ingest` also runs this step after chunk generation.

### `documents.jsonl`

One row per scraped source document.

Important fields:

- `document_id`: stable ID derived from source URL and hash.
- `source_url`, `source_title`, `document_type`.
- `knowledge_type`: coarse type such as `overview`, `quick_start`, `training_guide`,
  `application_note`, `safety`, `reservation`, `seminar_or_lecture`, `manual`, or `resource`.
- `related_instrument_ids`: instruments inferred from title/URL aliases.
- `source_hash`, `crawl_timestamp`.

Use this when deciding which full document should be read for a question.

### `sections.jsonl`

One row per normalized section or PDF page.

Important fields:

- `section_id`.
- `document_id`.
- `heading`.
- `section_type`: inferred type such as `sample_preparation`, `compatible_solvents`,
  `operating_procedure`, `shutdown`, `data_processing`, `troubleshooting`, `safety`, `fees`, or
  `content`.
- `text`.
- optional `page`.
- `related_instrument_ids`.

Use this for parent-child retrieval: resolve the document first, then search or load relevant
sections inside that document.

### `instruments.jsonl`

One row per known instrument/profile.

Important fields:

- `instrument_id`: canonical machine-readable ID, such as `gcms`, `qtof`, `qqq`, or `hplc`.
- `name`, `category`, `aliases`.
- `description`: overview-derived inventory text when available.
- `related_document_ids`: guides or docs associated with the instrument.
- `related_resource_ids`: resource records associated with the instrument.
- `fee`: MIT, non-profit, commercial, and unit values when present.
- `source_record_ids`, `source_url`, `source_title`.

Use this as the first source for inventory and recommendation questions.

### `resources.jsonl`

One row per guide/resource.

Important fields:

- `resource_id`.
- `title`.
- `resource_type`: quick start, training guide, application note, seminar/lecture, spreadsheet,
  safety, reservation, manual, or generic resource.
- `category`: original overview category when available.
- optional `document_id`: linked parsed document, if the resource corresponds to a crawled PDF.
- `related_instrument_ids`.
- optional `source_record_id`: legacy guide record from `records.jsonl`.

Use this to answer "what guide should I read?" and to route procedure questions to the right PDF.

### `rules.jsonl`

One row per extracted constraint or important operational guidance.

Important fields:

- `rule_id`.
- `instrument_id`, `instrument_name`.
- `severity`: `hard_constraint` or `guidance`.
- `condition`: normalized condition such as `aqueous_or_acid_sample`, `high_boiling_solvent`,
  `nonvolatile_buffer`, `particulate_sample`, `sample_concentration`, or `sample_or_operation`.
- `statement`: source-backed sentence or sentence-like rule text.
- optional `recommendation`.
- source provenance: URL, title, section ID, page, hash, timestamp.

Use this before general RAG results for compatibility/safety/procedure questions. For example,
GC/MS aqueous-sample questions should surface the GC/MS hard constraint from the quick-start guide
before generic GC/MS capability text.

## Build Logic

The builder is deterministic and does not use an LLM.

It performs:

- document classification from source title/URL;
- section classification from headings and early section text;
- instrument matching with canonical aliases;
- guide/resource matching to parsed documents;
- instrument profile assembly from inventory, fee, guide, and document relationships;
- conservative rule extraction from sample-preparation, solvent, operation, safety, and
  troubleshooting sections.

Short aliases such as `EPR` are matched with word-boundary checks to avoid false matches inside
words like "preparation."

## Runtime Use

The advisor uses the hierarchy in this order:

1. Classify the user query.
2. Resolve an instrument when the query names one.
3. Load instrument profiles, resources, and rules from `data/structured`.
4. Promote applicable rules into evidence for instrument-specific sample, solvent, safety, or
   operation questions.
5. Use hybrid retrieval over chunks for supporting passages.
6. Ask the LLM to synthesize only from supplied catalog, rules, resources, and passages.

This means a question like "can I put raw coffee into GC-MS?" is routed to GC/MS, the GC/MS
quick-start-derived hard constraint about water/acid-containing samples is promoted first, and only
then are ordinary retrieved passages considered.

## Maintenance

After changing crawl, parsing, or extraction behavior, rebuild and audit:

```bash
dcif ingest
dcif audit
pytest -q
```

The audit checks the original retrieval artifacts plus the new knowledge layer:

- knowledge documents;
- instrument profiles;
- resources;
- rules;
- expected instrument categories;
- minimum source/chunk/record counts.

If DCIF changes page structure, prefer updating deterministic parsers and extraction rules over
adding LLM-based ingestion. The knowledge files should remain reproducible from the same raw
snapshot.
