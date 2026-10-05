# DCIF Assistant Documentation

This folder is the canonical project documentation. The old `plans/` folder has been retired; active
architecture, operations, and implementation guidance should live here.

## Start Here

- [Scraping Architecture](scraping-architecture.md): how the DCIF overview page and linked PDFs are
  fetched, normalized, structured, chunked, indexed, and audited.
- [Retrieval Architecture](retrieval-architecture.md): how runtime question answering uses
  hierarchical retrieval, catalog/rule evidence, hybrid search, and optional LLM synthesis.
- [Knowledge Organization](knowledge-organization.md): what each generated knowledge artifact in
  `data/structured/` means and how the advisor uses it.
- [DCIF Source Catalog](dcif-source-catalog.md): the exact overview page, PDFs, structured records,
  and resource groups currently represented in local data artifacts.
- [Reproducibility And Website Drift](reproducibility.md): rebuild commands, audit checks,
  maintenance rules, regression queries, and future hardening work.
- [Azure Foundry LLM](azure-foundry-llm.md): provider-boundary guidance for Azure AI Foundry,
  Responses API configuration, structured outputs, safety, observability, and rollout.

## Current System Shape

```text
DCIF overview page + directly linked PDFs
  -> dcif crawl
  -> data/raw
  -> dcif parse
  -> data/normalized
  -> dcif extract-structured / dcif build-knowledge
  -> data/structured
  -> dcif chunk
  -> data/chunks
  -> dcif index
  -> data/indexes
  -> FastAPI retrieval/chat API
  -> Next.js chatbot demo
```

The chatbot is a demonstration layer. The reusable core is the reproducible DCIF knowledge and
retrieval pipeline.

## Core Principles

- The DCIF overview page, linked PDFs, and local source snapshots are the source of truth.
- Search indexes are disposable and must be rebuildable from `data/raw`, `data/normalized`, and
  `data/structured`.
- Ingestion is deterministic; do not use an LLM while crawling, parsing, extracting, or chunking.
- Structured knowledge comes before vector search for inventory, recommendations, sample
  compatibility, fees, and procedure questions.
- Explicit hard constraints, such as GC/MS aqueous-sample restrictions, override broad semantic
  similarity.
- Every answer should preserve provenance back to a source URL, page/section when available, source
  hash, and crawl timestamp.

## Common Workflows

Rebuild everything:

```bash
dcif ingest
dcif audit
```

Run the app locally:

```bash
uvicorn backend.api.main:app --reload
cd frontend && npm run dev
```

Run tests:

```bash
pytest -q
```

Inspect runtime state:

```bash
curl 'http://127.0.0.1:8000/debug/runtime?query=What%20mass%20spectrometry%20instruments%20do%20you%20have%3F'
```

## Where To Put New Documentation

- Add source coverage and data-inventory updates to `dcif-source-catalog.md`.
- Add crawl/parser/indexing changes to `scraping-architecture.md`.
- Add runtime routing, retrieval, advisor, or prompting changes to `retrieval-architecture.md`.
- Add generated artifact schema and maintenance notes to `knowledge-organization.md`.
- Add rebuild, audit, drift, and evaluation guidance to `reproducibility.md`.
- Add Azure/provider-boundary implementation notes to `azure-foundry-llm.md`.
