from __future__ import annotations

from pathlib import Path

import typer

from backend.dcif.audit import audit_retrieval_artifacts
from backend.dcif.chunk import chunk_all
from backend.dcif.crawl import CrawlFetchError, crawl_sources
from backend.dcif.hybrid_search import HybridSearch
from backend.dcif.io import read_chunks
from backend.dcif.knowledge import write_knowledge_artifacts
from backend.dcif.normalize import normalize_all
from backend.dcif.paths import config_path, data_path
from backend.dcif.structured_extract import extract_structured_records

app = typer.Typer(help="MIT DCIF deterministic ingestion and retrieval CLI")


@app.command()
def crawl(
    config: Path = config_path("sources.yaml"),
    raw_dir: Path = data_path("raw"),
    db_path: Path = data_path("crawl.db"),
) -> None:
    try:
        snapshots = crawl_sources(config_path=config, raw_dir=raw_dir, db_path=db_path)
    except CrawlFetchError as exc:
        raise typer.BadParameter(str(exc), param_hint="config.root_urls") from exc
    typer.echo(f"Crawled {len(snapshots)} source snapshots")


@app.command("parse")
def parse_command(
    raw_dir: Path = data_path("raw"),
    normalized_dir: Path = data_path("normalized"),
) -> None:
    docs = normalize_all(raw_dir=raw_dir, normalized_dir=normalized_dir)
    typer.echo(f"Normalized {len(docs)} documents")


@app.command("chunk")
def chunk_command(
    normalized_dir: Path = data_path("normalized"),
    chunks_path: Path = data_path("chunks", "chunks.jsonl"),
    records_path: Path = data_path("structured", "records.jsonl"),
    max_words: int = 180,
    overlap_words: int = 35,
) -> None:
    chunks = chunk_all(
        normalized_dir=normalized_dir,
        chunks_path=chunks_path,
        records_path=records_path,
        max_words=max_words,
        overlap_words=overlap_words,
    )
    typer.echo(f"Wrote {len(chunks)} chunks")


@app.command("extract-structured")
def extract_structured_command(
    normalized_dir: Path = data_path("normalized"),
    records_path: Path = data_path("structured", "records.jsonl"),
) -> None:
    records = extract_structured_records(normalized_dir=normalized_dir, records_path=records_path)
    typer.echo(f"Wrote {len(records)} structured records")


@app.command("build-knowledge")
def build_knowledge_command(
    normalized_dir: Path = data_path("normalized"),
    records_path: Path = data_path("structured", "records.jsonl"),
    output_dir: Path = data_path("structured"),
) -> None:
    artifacts = write_knowledge_artifacts(
        output_dir=output_dir,
        normalized_dir=normalized_dir,
        records_path=records_path,
    )
    typer.echo(
        "Wrote knowledge artifacts: "
        f"{len(artifacts.documents)} documents, "
        f"{len(artifacts.sections)} sections, "
        f"{len(artifacts.instruments)} instruments, "
        f"{len(artifacts.resources)} resources, "
        f"{len(artifacts.rules)} rules"
    )


@app.command("index")
def index_command(
    chunks_path: Path = data_path("chunks", "chunks.jsonl"),
    keyword_db_path: Path = data_path("indexes", "keyword.sqlite"),
    vector_dir: Path = data_path("indexes", "chroma"),
) -> None:
    chunks = read_chunks(chunks_path)
    HybridSearch(keyword_db_path=keyword_db_path, vector_dir=vector_dir).rebuild(chunks)
    typer.echo(f"Indexed {len(chunks)} chunks")


@app.command()
def ingest() -> None:
    snapshots = crawl_sources()
    docs = normalize_all()
    chunks = chunk_all()
    artifacts = write_knowledge_artifacts()
    HybridSearch().rebuild(chunks)
    typer.echo(
        f"Ingest complete: {len(snapshots)} snapshots, {len(docs)} documents, "
        f"{len(chunks)} chunks, {len(artifacts.instruments)} instruments, "
        f"{len(artifacts.rules)} rules"
    )


@app.command()
def retrieve(query: str, top_k: int = 5) -> None:
    results = HybridSearch().retrieve(query, top_k=top_k)
    for result in results:
        page = f", page {result.page}" if result.page else ""
        typer.echo(f"[{result.rank}] {result.source_title} ({result.source_url}{page})")
        typer.echo(result.text[:700])
        typer.echo("")


@app.command()
def audit(
    raw_dir: Path = data_path("raw"),
    chunks_path: Path = data_path("chunks", "chunks.jsonl"),
    records_path: Path = data_path("structured", "records.jsonl"),
) -> None:
    report = audit_retrieval_artifacts(
        raw_dir=raw_dir,
        chunks_path=chunks_path,
        records_path=records_path,
    )
    typer.echo(report.render())
    if not report.ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
