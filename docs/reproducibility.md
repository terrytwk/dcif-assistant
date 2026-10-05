# Reproducibility and Website Drift

This project treats the DCIF overview page and directly linked source files as the knowledge source.
Generated indexes are disposable and should be rebuilt from snapshots.

## Current Crawl Contract

The crawler is intentionally scoped to:

- the DCIF overview page configured in `config/sources.yaml`;
- directly linked files from that page whose path ends with one of `linked_file_extensions`;
- Dropbox PDF links converted from `dl=0` to `dl=1` so they are downloaded as files.

It does not recursively crawl unrelated MIT Chemistry pages.

```yaml
root_urls:
  - https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/
follow_html_links: false
fetch_linked_files: true
linked_file_extensions:
  - .pdf
```

## Rebuild Procedure

Use a fresh rebuild when DCIF content changes:

```bash
source .venv/bin/activate
dcif crawl
dcif parse
dcif chunk
dcif build-knowledge
dcif index
dcif audit
```

`dcif ingest` runs the same major pipeline in one command.

## Drift Detection

Run:

```bash
dcif audit
```

The audit checks for:

- exactly one HTML source snapshot;
- a reasonable number of linked PDF snapshots;
- retrieval chunks;
- structured records;
- hierarchical knowledge documents, instrument profiles, resources, and rules;
- expected structured record types;
- aggregate instrument categories for Mass Spectrometry, NMR Spectroscopy, and Other Instruments.

If this fails after a site update, inspect:

- `data/raw/*.meta.json` for the fetched URL list;
- `data/normalized/*.json` for parsed section headings;
- `data/structured/records.jsonl` for extracted records.

## What to Update When the Website Changes

If the DCIF page URL changes:

1. Update `config/sources.yaml`.
2. Update `OVERVIEW_URL_MARKER` in `backend/dcif/structured_extract.py`.
3. Run `dcif ingest && dcif audit`.

If section headings change:

1. Update `INSTRUMENT_SECTION_CATEGORIES`, `GUIDE_SECTIONS`, or overview section names in
   `backend/dcif/structured_extract.py`.
2. Add or update tests in `tests/test_structured_extract.py`.
3. Run `pytest -q && dcif ingest && dcif audit`.

If the page no longer contains line-oriented instrument descriptions:

1. Prefer improving `parse_html.py` to preserve more DOM/table/list structure.
2. Update structured extraction rules after inspecting `data/normalized`.
3. Keep extraction deterministic; do not use an LLM during ingestion.

## Regression Queries

After every meaningful ingestion or extraction change, check broad and specific queries:

```bash
dcif retrieve "what mass spectrometry instruments do you have?" --top-k 5
dcif retrieve "what NMR instruments are available?" --top-k 5
dcif retrieve "how much does LCMS cost?" --top-k 5
dcif retrieve "how do I get trained?" --top-k 5
dcif retrieve "LCMS quick start guide" --top-k 5
```

The first result for broad inventory questions should usually be a `structured` chunk.

## Future Hardening

Useful next improvements:

- Add retrieval evaluation fixtures in `evals/retrieval.yaml` with expected source IDs, structured
  record categories, rules, or documents.
- Add a `dcif eval` command that runs those fixtures against the local index.
- Preserve HTML tables as tables during normalization, especially for fees.
- Store structured records in SQLite with typed columns for exact lookups.
- Expand the advisor workflow to route fee lookup, training, reservation, safety, and staff-contact
  intents as specifically as inventory and instrument-procedure intents.
- Add CI steps for `pytest -q`, `dcif ingest`, `dcif audit`, and selected retrieval evals.
