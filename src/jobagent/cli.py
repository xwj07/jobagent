"""Command-line entry points.

Examples
--------
    jobagent init-db
    jobagent ingest data/samples/jds.jsonl --provider mock
    jobagent stats --top 15
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import settings
from .db import get_session_factory, init_db
from .extract import ingest_many
from .llm import get_provider
from .schemas import RawPosting
from .stats import corpus_summary, skill_frequency

app = typer.Typer(help="Job-agent stage 1: turn raw JDs into skill intelligence.")
console = Console()


def _load_jsonl(path: Path) -> list[RawPosting]:
    postings: list[RawPosting] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                postings.append(RawPosting.model_validate(json.loads(line)))
            except Exception as exc:
                console.print(f"[yellow]skip line {line_no}: invalid input ({exc})[/yellow]")
    return postings


@app.command("init-db")
def init_db_cmd() -> None:
    """Create tables in the configured database."""
    init_db()
    console.print(f"[green]database ready[/green] url={settings.database_url}")


@app.command()
def ingest(
    file: Path = typer.Argument(..., exists=True, dir_okay=False, help="JSONL file"),
    provider: str | None = typer.Option(None, help="mock | openai (default: from env)"),
) -> None:
    """Import a JSONL file of postings and extract structured fields."""
    postings = _load_jsonl(file)
    if not postings:
        console.print("[yellow]no valid postings found[/yellow]")
        raise typer.Exit(code=1)

    prov = get_provider(provider)
    init_db()
    result = ingest_many(get_session_factory(), postings, prov)

    console.print(
        f"[green]inserted={result.inserted}[/green] skipped={result.skipped} "
        f"failed={len(result.failed)}"
    )
    for failure in result.failed[:5]:
        console.print(f"  [red]line {failure['index']}: {failure['error']}[/red]")


@app.command()
def stats(
    top: int = typer.Option(20, help="how many skills to show"),
    as_json: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """Show the most demanded skills across stored postings."""
    init_db()
    factory = get_session_factory()
    with factory() as session:
        summary = corpus_summary(session)
        rows = skill_frequency(session, top=top)

    if as_json:
        typer.echo(json.dumps({"summary": summary, "skills": rows}, ensure_ascii=False, indent=2))
        return

    console.print(
        f"postings={summary['postings']}  distinct_skills={summary['distinct_skills']}  "
        f"median_monthly_k={summary['median_monthly_k']}"
    )
    table = Table(title="Top skills")
    table.add_column("#", justify="right")
    table.add_column("skill")
    table.add_column("postings", justify="right")
    table.add_column("required", justify="right")
    table.add_column("share", justify="right")
    for i, row in enumerate(rows, start=1):
        table.add_row(
            str(i),
            row["skill"],
            str(row["postings"]),
            str(row["required"]),
            f"{row['share']:.0%}",
        )
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
