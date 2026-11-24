"""Command-line interface: pdoc check | trace | diff | as2 | rules."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from . import __version__
from .as2check import check_cert, check_mdn
from .diff import diff as diff_payloads
from .engine import check_file
from .report import print_diff, print_result, print_rules, print_trace, rules_markdown
from .rules import all_rules
from .trace import summarise, trace as trace_txn

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Payload Doctor: explains why a B2B file (X12, EDIFACT, EPCIS XML, CSV) failed, in plain English.")
console = Console(highlight=False)

PAYLOAD_SUFFIXES = {".edi", ".x12", ".txt", ".xml", ".csv", ".edifact", ".dat", ".850", ".856", ".997"}


def _version(value: bool):
    if value:
        console.print(f"payload-doctor {__version__}")
        raise typer.Exit()


@app.callback()
def main(version: bool = typer.Option(False, "--version", callback=_version, is_eager=True,
                                      help="Show the version and exit.")):
    pass


def _collect(paths: List[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix.lower() in PAYLOAD_SUFFIXES)
        elif p.exists():
            files.append(p)
        else:
            console.print(f"[red]No such file or folder:[/red] {p}")
            raise typer.Exit(3)
    return files


@app.command()
def check(paths: List[Path] = typer.Argument(..., help="Files or folders to check."),
          as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
          brief: bool = typer.Option(False, "--brief", "-b", help="Hide the why / cause / fix text."),
          schemas: Optional[Path] = typer.Option(None, "--schemas", help="Folder with EPCIS 1.2 XSD files.")):
    """Detect each file's format and run every rule for it."""
    results = [check_file(f, schemas) for f in _collect(paths)]
    if as_json:
        payload = [r.to_dict() for r in results]
        sys.stdout.write(json.dumps(payload[0] if len(payload) == 1 else payload, indent=2) + "\n")
    else:
        for r in results:
            print_result(console, r, verbose=not brief)
        if len(results) > 1:
            bad = sum(1 for r in results if r.errors)
            console.print(f"[bold]{len(results)} file(s) checked, {bad} with errors[/bold]")
    codes = [r.exit_code for r in results] or [0]
    raise typer.Exit(1 if 1 in codes else max(codes))


@app.command()
def trace(txn_id: str = typer.Argument(..., help="Transaction ID to follow, e.g. TXN-2026-000182."),
          paths: List[Path] = typer.Argument(..., help="Log files or folders."),
          as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON.")):
    """Build one transaction's timeline across log files (JSON lines or plain text)."""
    events = trace_txn(txn_id, paths)
    summary = summarise(events)
    if as_json:
        sys.stdout.write(json.dumps({"transaction": txn_id, "summary": summary, "timeline": [
            {"time": e.raw_time, "level": e.level, "message": e.message, "source": e.source, **e.fields}
            for e in events]}, indent=2, default=str) + "\n")
    else:
        print_trace(console, txn_id, events, summary)
    raise typer.Exit(1 if summary["status"] in ("FAILED", "NOT FOUND") else 0)


@app.command()
def diff(good: Path = typer.Argument(..., help="Known-good payload."),
         bad: Path = typer.Argument(..., help="Payload to compare."),
         as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON.")):
    """Show meaningful differences between two payloads (segment, element or XML path level)."""
    fmt, changes = diff_payloads(good.read_bytes(), bad.read_bytes())
    if as_json:
        sys.stdout.write(json.dumps({"format": fmt, "changes": [c.to_dict() for c in changes]}, indent=2) + "\n")
    else:
        print_diff(console, fmt, changes)
    raise typer.Exit(1 if changes else 0)


@app.command()
def as2(cert: Optional[Path] = typer.Argument(None, help="Partner or own certificate (PEM or DER)."),
        mdn: Optional[Path] = typer.Option(None, "--mdn", help="An MDN (receipt) file to read."),
        brief: bool = typer.Option(False, "--brief", "-b", help="Hide the why / cause / fix text."),
        as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON.")):
    """Check an AS2 certificate (expiry, key size, signature) and/or read an MDN receipt."""
    if not cert and not mdn:
        console.print("Give a certificate file, --mdn FILE, or both.")
        raise typer.Exit(3)
    results = []
    if cert:
        results.append(check_cert(cert))
    if mdn:
        results.append(check_mdn(mdn))
    if as_json:
        sys.stdout.write(json.dumps([r.to_dict() for r in results], indent=2) + "\n")
    else:
        for r in results:
            print_result(console, r, verbose=not brief)
    codes = [r.exit_code for r in results]
    raise typer.Exit(1 if 1 in codes else max(codes))


@app.command()
def rules(fmt: Optional[str] = typer.Option(None, "--format", "-f",
                                            help="Only rules for one format: x12, edifact, epcis, xml, csv, as2, any."),
          markdown: bool = typer.Option(False, "--markdown", help="Print the catalogue as Markdown.")):
    """List every diagnostic rule."""
    selected = [r for r in all_rules() if fmt is None or r.fmt == fmt.lower()]
    if markdown:
        sys.stdout.write(rules_markdown(selected) + "\n")
    else:
        print_rules(console, selected)
        console.print(f"{len(selected)} rule(s)")


if __name__ == "__main__":
    app()
