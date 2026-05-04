# path: omnisource/main.py
from __future__ import annotations

import asyncio
import sys
from typing import Optional, List

import typer
from rich.table import Table
from rich.console import Console

from omnisource.core.orchestrator import SearchOrchestrator

app = typer.Typer()
console = Console()


def parse_sources(sources: Optional[str]) -> Optional[List[str]]:
    if not sources:
        return None
    return [s.strip() for s in sources.split(",") if s.strip()]


def print_table(results):
    table = Table(title="OmniSource Results")

    table.add_column("Score", justify="right")
    table.add_column("URL")
    table.add_column("Sources")
    table.add_column("Reasons")

    for r in results:
        table.add_row(
            f"{r.score:.2f}",
            r.normalized.url,
            ", ".join(r.contributing_sources),
            "; ".join(r.reasons[:2]),
        )

    console.print(table)


@app.command()
def search(
    image: str = typer.Option(..., "--image", help="Path or URL of image"),
    sources: Optional[str] = typer.Option(None, "--sources"),
    min_confidence: float = typer.Option(30.0, "--min-confidence"),
    format: str = typer.Option("table", "--format"),
    debug: bool = typer.Option(False, "--debug"),
    no_cache: bool = typer.Option(False, "--no-cache"),
):
    """
    OmniSource CLI
    """

    try:
        parsed_sources = parse_sources(sources)

        orch = SearchOrchestrator()

        result = asyncio.run(
            orch.search(
                image_path=image,
                sources=parsed_sources,
                use_cache=not no_cache,
            )
        )

        filtered = [
            r for r in result.results if r.score >= min_confidence
        ]

        if format == "json":
            import json
            console.print_json(data=result.model_dump())

        elif format == "csv":
            import csv

            writer = csv.writer(sys.stdout)
            writer.writerow(["score", "url", "sources"])

            for r in filtered:
                writer.writerow([
                    r.score,
                    r.normalized.url,
                    "|".join(r.contributing_sources),
                ])

        else:
            print_table(filtered)

        # Exit codes
        success_rate = (
            len(result.sources_succeeded) / len(result.sources_attempted)
            if result.sources_attempted else 0
        )

        if success_rate < 0.4:
            sys.exit(3)

        sys.exit(0)

    except typer.BadParameter:
        console.print("[red]Invalid input[/red]")
        sys.exit(1)

    except Exception as e:
        console.print(f"[red]System error:[/red] {e}")
        sys.exit(2)


if __name__ == "__main__":
    app()