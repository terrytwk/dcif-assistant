# DCIF Scraping Architecture

This document describes how the project scrapes the MIT DCIF website and turns the fetched sources
into reproducible local data artifacts. The scraping pipeline is intentionally narrow: the DCIF
overview page is the only HTML page fetched, and directly linked PDF files from that page are fetched
as source documents.

## Goals

- Keep the source scope auditable and reproducible.
- Avoid crawling unrelated MIT Chemistry pages.
- Preserve raw source snapshots before parsing or chunking.
- Extract important DCIF facts deterministically, without using an LLM during ingestion.
- Produce artifacts that can be rebuilt from the same configured source page.

## High-Level Flow

```text
config/sources.yaml
  -> dcif crawl
  -> data/raw/*.html, *.pdf, *.meta.json
  -> dcif parse
  -> data/normalized/*.json
  -> dcif extract-structured
  -> data/structured/records.jsonl
  -> dcif build-knowledge
  -> data/structured/{documents,sections,instruments,resources,rules}.jsonl
  -> dcif chunk
  -> data/chunks/chunks.jsonl
  -> dcif index
  -> data/indexes/keyword.sqlite + data/indexes/chroma/
```

`dcif ingest` runs the same major stages in one command:

```text
crawl -> normalize -> chunk, including structured extraction -> build hierarchical knowledge -> rebuild indexes
```

## Source Scope

The crawl contract lives in `config/sources.yaml`.

Current settings:

- `root_urls` contains only the DCIF overview page.
- `allowed_domains` contains `chemistry.mit.edu`.
- `follow_html_links` is `false`, so normal web pages linked from the overview are not recursively
  fetched.
- `fetch_linked_files` is `true`.
- `linked_file_extensions` contains `.pdf`, so direct PDF links from the overview page are fetched.
- Dropbox links are normalized to `dl=1` so linked PDFs are downloaded as files.

This means the crawler currently fetches:

- the configured DCIF overview HTML page;
- PDF files linked from that overview page, including Dropbox-hosted PDF links.

It does not fetch:

- linked non-PDF pages;
- arbitrary MIT Chemistry pages;
- external resources that are not direct linked files selected by the configured extension list.

## CLI Entry Points

The ingestion CLI is defined in `backend/cli.py`.

| Command | Implementation | Output |
| --- | --- | --- |
| `dcif crawl` | `backend.dcif.crawl.crawl_sources` | Raw snapshots, metadata, and crawl DB records |
| `dcif parse` | `backend.dcif.normalize.normalize_all` | Normalized documents |
| `dcif extract-structured` | `backend.dcif.structured_extract.extract_structured_records` | Structured JSONL records |
| `dcif build-knowledge` | `backend.dcif.knowledge.write_knowledge_artifacts` | Documents, sections, instrument profiles, resources, and rules |
| `dcif chunk` | `backend.dcif.chunk.chunk_all` | Retrieval chunks, including structured chunks |
| `dcif index` | `backend.dcif.hybrid_search.HybridSearch.rebuild` | Keyword and vector indexes |
| `dcif ingest` | Combined crawl, normalize, chunk, index flow | Full rebuild |
| `dcif audit` | `backend.dcif.audit.audit_retrieval_artifacts` | Coverage and drift report |

## Crawl Stage

The crawler is implemented in `backend/dcif/crawl.py`.

Core behavior:

1. Load `CrawlConfig` from `config/sources.yaml`.
2. Initialize `data/crawl.db` with a `crawl_records` table.
3. Start a queue with the configured root URL.
4. Fetch each allowed URL with `httpx.Client`.
5. Detect document type using URL extension, content type, and PDF magic bytes.
6. Store the raw response body in `data/raw`.
7. Store sidecar metadata in `data/raw/*.meta.json`.
8. Store/update the crawl record in `data/crawl.db`.
9. If the fetched document is the root HTML page, extract links from its anchors.
10. Queue direct linked PDFs, applying Dropbox direct-download normalization.

Important implementation details:

- `canonical_url` removes fragments, lowercases scheme/host, and sorts query params for root URL
  comparison.
- `should_fetch_url` allows only root URLs and configured linked files.
- `extract_links` uses BeautifulSoup and records both absolute URLs and anchor text.
- Anchor text is kept as a candidate source title for linked PDFs.
- `stable_id(url)` produces the local filename stem, so files are deterministic for a URL.
- `source_hash` is a SHA-256 hash of the fetched bytes and is carried through later artifacts.

## Raw Artifacts

`data/raw` contains the source snapshots and metadata.

For each fetched source, the crawler writes:

- the raw file itself, such as `<stable-id>.html` or `<stable-id>.pdf`;
- `<stable-id>.meta.json`.

Each metadata file is a `SourceSnapshot` with:

- `url`;
- optional `title`;
- `document_type`;
- `raw_path`;
- optional `content_type`;
- `crawl_timestamp`;
- `source_hash`.

The SQLite crawl DB mirrors this metadata for quick crawl-record inspection, but the pipeline mainly
uses the metadata JSON files when rebuilding later stages.

## Normalization Stage

Normalization is implemented in `backend/dcif/normalize.py`.

For every `data/raw/*.meta.json` file:

1. Load the `SourceSnapshot`.
2. Dispatch by document type:
   - HTML uses `backend/dcif/parse_html.py`.
   - PDF uses `backend/dcif/parse_pdf.py`.
   - text falls back to reading the file as UTF-8 with ignored errors.
3. Clean repeated whitespace and blank lines.
4. Write one `NormalizedDocument` JSON file to `data/normalized`.

HTML parsing:

- Uses BeautifulSoup.
- Removes noisy nodes: `script`, `style`, `noscript`, `svg`, `form`, `nav`, and `footer`.
- Uses the page `<h1>` as the title when available.
- Splits content into sections at heading tags.
- Collects text from paragraphs, list items, and table cells.

PDF parsing:

- Uses PyMuPDF.
- Reads the PDF metadata title when available.
- Creates one `NormalizedSection` per page with extracted text.
- Preserves page numbers for citations and retrieval results.

## Normalized Artifacts

`data/normalized/*.json` files are `NormalizedDocument` objects with:

- `source_url`;
- `source_title`;
- `document_type`;
- `crawl_timestamp`;
- `source_hash`;
- `sections`.

Each section has:

- `heading`;
- `text`;
- optional `page`.

This layer is the main boundary between source parsing and downstream retrieval logic.

## Structured Extraction Stage

Structured extraction is implemented in `backend/dcif/structured_extract.py`.

Only the DCIF overview HTML page is used for structured extraction. The helper `is_overview_doc`
checks for the configured DCIF overview URL marker and ignores PDFs.

The extractor creates deterministic `StructuredRecord` rows for:

- instrument inventory;
- fee table entries;
- staff records;
- linked guide/application-note/resource titles;
- key overview sections such as general information, training requests, reservations, and software.

Structured records are written to `data/structured/records.jsonl`.

Instrument records:

- Read overview sections named `Mass Spectrometry (MS)`, `Nuclear Magnetic Resonance (NMR)`, and
  `Other Instruments`.
- Infer instrument names from description lines.
- Create one record per instrument.
- Create one aggregate summary record per instrument category so broad inventory questions have a
  compact authoritative source.

Fee records:

- Parse the overview `Fees` section as table-like text.
- Preserve MIT, non-profit, commercial, and unit fields.

Guide records:

- Read configured guide/resource sections such as `Instrument Training Guides`, `Application Notes`,
  `Mass Spectrometry (MS)`, `Other`, `DCIF Seminar series`, `Guest lectures in Chemistry`, and
  `Advanced topics`.
- Store guide titles as structured records so linked resources remain discoverable even when the
  linked PDF content is sparse or difficult to rank.

The structured extraction code is intentionally heuristic but deterministic. If the website layout
changes, update the section names and parsing rules there rather than adding LLM-based ingestion.

## Hierarchical Knowledge Stage

Hierarchical knowledge building is implemented in `backend/dcif/knowledge.py`.

It reads `data/normalized/*.json` and `data/structured/records.jsonl`, then writes:

- `data/structured/documents.jsonl`;
- `data/structured/sections.jsonl`;
- `data/structured/instruments.jsonl`;
- `data/structured/resources.jsonl`;
- `data/structured/rules.jsonl`.

This stage organizes the scraped corpus into document, section, instrument, resource, and explicit
rule records. It is still deterministic and does not call an LLM.

## Chunking And Indexing

Chunking is implemented in `backend/dcif/chunk.py`.

Text chunks:

- Every normalized section is split into word windows.
- Default window size is `180` words.
- Default overlap is `35` words.
- Chunk IDs include source URL, source hash, section heading, page, chunk index, and text.

Structured chunks:

- `chunk_all` calls `extract_structured_records` by default.
- Structured records are converted into chunks with `document_type = "structured"`.
- These chunks are appended to normal text chunks in `data/chunks/chunks.jsonl`.

Indexing:

- `dcif index` reads `data/chunks/chunks.jsonl`.
- `HybridSearch().rebuild` writes the keyword index and vector index.
- Current index artifacts live under `data/indexes`.

## Audit And Drift Checks

`dcif audit` is implemented in `backend/dcif/audit.py`.

It checks:

- exactly one HTML snapshot;
- a minimum number of PDF snapshots;
- a minimum number of chunks;
- a minimum number of structured records;
- a minimum number of hierarchical knowledge documents, instrument profiles, resources, and rules;
- expected structured record types;
- expected aggregate instrument categories;
- warning-level staff and mass spectrometry coverage checks.

Use it after ingestion changes:

```bash
dcif ingest
dcif audit
```

The source catalog in `docs/dcif-source-catalog.md` is a human-readable inventory of the exact
resources currently present in the local data artifacts.

## Tests Covering Scraping Behavior

The scraping and extraction behavior is covered by focused tests:

- `tests/test_crawl.py` checks crawl scope, Dropbox direct-download normalization, PDF type
  detection, and link extraction.
- `tests/test_parser.py` checks HTML parsing and noise removal.
- `tests/test_structured_extract.py` checks overview-derived instrument, guide, fee, and structured
  chunk behavior.
- `tests/test_audit.py` checks audit behavior.

## How To Update When DCIF Changes

If the DCIF overview URL changes:

1. Update `config/sources.yaml`.
2. Update `OVERVIEW_URL_MARKER` in `backend/dcif/structured_extract.py`.
3. Run `dcif ingest`.
4. Run `dcif audit`.
5. Refresh `docs/dcif-source-catalog.md` if the source list changed.

If the overview page structure changes:

1. Run `dcif crawl` and `dcif parse`.
2. Inspect the relevant file in `data/normalized`.
3. Update deterministic extraction rules in `backend/dcif/structured_extract.py`.
4. Add or update focused tests.
5. Run `pytest -q`, `dcif ingest`, and `dcif audit`.

If new source file types should be fetched:

1. Add the extension to `linked_file_extensions` in `config/sources.yaml`.
2. Add parser support if the new type is not already handled.
3. Add tests for type detection, parsing, and expected extraction behavior.

## Design Tradeoffs

This scraper favors precision over breadth. That is why it starts from one overview page and fetches
only directly linked PDFs. This keeps the assistant focused on DCIF-owned or DCIF-linked materials
and prevents irrelevant site-wide pages from polluting retrieval.

The main limitation is that overview-only non-PDF links are not fetched as standalone sources. They
can still appear as structured guide/resource records if they are listed on the overview page, but
their target content is not downloaded unless the crawl contract is expanded.
