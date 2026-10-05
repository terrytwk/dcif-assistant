# Retrieval Architecture

The chatbot is a demonstration layer over a reusable DCIF retrieval system. Retrieval should be
hierarchical and provenance-aware: find the right entity or document first, then retrieve the
supporting sections or chunks inside that scope.

## Core Principle

Do not treat the vector database as the knowledge source.

```text
canonical knowledge
  -> instruments, resources, rules, documents, sections
  -> chunks
  -> keyword + vector indexes
  -> retrieved evidence
  -> optional LLM synthesis
```

The canonical knowledge lives in `data/raw`, `data/normalized`, and `data/structured`. The indexes in
`data/indexes` are disposable and can be rebuilt.

## Retrieval Layers

The system uses several levels of evidence rather than one flat RAG search.

| Layer | Artifact | Best for |
| --- | --- | --- |
| Instrument catalog | `data/structured/instruments.jsonl` | Inventory, candidate instruments, fees, related guides |
| Resource map | `data/structured/resources.jsonl` | Finding the right quick start, training guide, application note, or safety document |
| Explicit rules | `data/structured/rules.jsonl` | Sample compatibility, solvent restrictions, safety/operation constraints |
| Documents/sections | `data/structured/documents.jsonl`, `data/structured/sections.jsonl` | Parent-child retrieval and whole-guide workflows |
| Legacy records | `data/structured/records.jsonl` | Backward-compatible overview-derived instrument, fee, guide, staff, and overview records |
| Chunks/indexes | `data/chunks/chunks.jsonl`, `data/indexes/` | Fine-grained supporting passages and fallback search |

Structured knowledge should be consulted before semantic chunks for catalog, recommendation,
compatibility, and procedure questions.

## Offline Flow

```text
DCIF overview page + linked PDFs
  -> crawl source snapshots
  -> parse into normalized documents
  -> extract overview records
  -> build hierarchical knowledge
  -> chunk normalized text + structured records
  -> build keyword/vector indexes
```

`dcif ingest` runs the full path. `dcif build-knowledge` can rebuild only the hierarchical knowledge
files from `data/normalized` and `data/structured/records.jsonl`.

## Online Flow

At runtime, `/chat` uses a small server-owned workflow rather than autonomous tool calling.

```text
user question
  -> classify intent
  -> resolve instrument/sample hints
  -> load catalog/resources/rules
  -> choose retrieval policy
  -> collect evidence
  -> optional Azure Foundry synthesis
  -> answer with citations
```

This keeps retrieval deterministic, debuggable, and provider-portable. The LLM receives a prepared
payload; it does not decide which tools to call or scrape the website.

## Query Routing

Current routing lives in `backend/dcif/advisor.py`.

Important intents:

- `inventory_lookup`: list instruments/resources from catalog records.
- `instrument_recommendation`: compare candidate instruments from the instrument catalog, then
  support with targeted retrieval.
- `instrument_procedure`: resolve the named instrument, promote explicit rules, then retrieve from
  the matching quick-start guide or related document.
- `fee_lookup`, `guide_lookup`, `training_access`, `procedure_help`, and `chat`: currently fall back
  mostly to normal retrieval, with room to route more specifically later.

Target behavior:

| User need | First source | Then |
| --- | --- | --- |
| "What instruments do you have?" | Instrument profiles/catalog | cite overview-derived records |
| "What should I use for this sample?" | Instrument profiles + rules | retrieve candidate guide sections |
| "Can I put water/raw sample into GC-MS?" | Matching `rules.jsonl` constraints | retrieve GC/MS sample-preparation guide text |
| "How do I run LCMS?" | LCMS quick-start resource/document | retrieve sections or load fuller guide context |
| "How much does Q-TOF cost?" | Fee fields on instrument/profile records | cite fee table record |
| "How do I get trained?" | Overview training record/resources | retrieve training guide if needed |

## Parent-Child Retrieval

Flat nearest-neighbor retrieval is a fallback, not the default mental model.

For document questions:

```text
question
  -> resolve instrument or resource
  -> select parent document
  -> select relevant sections
  -> include chunks/passages from those sections
```

Example:

```text
"Can I put raw coffee into GC-MS?"
  -> instrument = GC/MS
  -> resource = Quick start guide – GCMS
  -> section_type = sample_preparation
  -> rule = aqueous_or_acid_sample hard constraint
  -> answer from rule + GC/MS guide evidence
```

For broad workflow questions, the system should prefer loading more of the matched document over
mixing unrelated top-k chunks from many PDFs.

## Rules Before Similarity

Hard constraints are promoted before ordinary chunk search because scientific-facility advice should
not depend on embeddings finding a warning sentence by chance.

Examples of rule conditions:

- `aqueous_or_acid_sample`
- `high_boiling_solvent`
- `nonvolatile_buffer`
- `particulate_sample`
- `sample_concentration`
- `sample_or_operation`

If an applicable `hard_constraint` conflicts with a general capability passage, the answer should
follow the hard constraint and cite it.

## Synthesis Policy

The LLM prompt should stay narrow:

- answer only from supplied catalog, resources, rules, and passages;
- treat explicit rules as authoritative constraints;
- use instrument profiles for inventory and recommendations;
- use quick-start guides for procedure/sample-preparation details;
- say what is missing when context is insufficient;
- cite only supplied source IDs.

The prompt should not compensate for missing context. If an answer is poor because the right evidence
was not supplied, fix retrieval, parsing, or structured extraction.

## Provenance

Every fact used for an answer should remain traceable:

```text
claim
  -> rule/profile/resource/section/chunk
  -> document
  -> source URL
  -> source hash
  -> crawl timestamp
```

This lets answers distinguish official DCIF documentation, deterministic derived records, extracted
rules, and LLM inference.

## Extension Points

Good next improvements:

- add section-level retrieval over `sections.jsonl`, not only chunk retrieval;
- add whole-document loading for "walk me through the whole process" questions;
- add an admin-reviewed `rules.jsonl` overlay for staff expertise that is not scraped from PDFs;
- expand routing for fees, training, reservations, safety, and staff contact questions;
- add retrieval evals that assert expected rules/documents for common user questions;
- add semantic diff/review reports when source hashes change.
