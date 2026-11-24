"""Render terminal screenshots (SVG) of Payload Doctor for the README.

Run: python scripts/render_demo.py
"""
from pathlib import Path

from rich.console import Console

from pdoc.diff import diff
from pdoc.engine import check_file
from pdoc.report import print_diff, print_result, print_trace
from pdoc.trace import summarise, trace

ROOT = Path(__file__).resolve().parent.parent
S = Path("samples")  # relative, so screenshots show short paths (run from the repo root)
DOCS = ROOT / "docs"


def shot(name: str, title: str, draw) -> None:
    console = Console(record=True, width=104, force_terminal=True, color_system="truecolor", highlight=False, file=open("/dev/null", "w"))
    draw(console)
    console.save_svg(str(DOCS / f"{name}.svg"), title=title)


def main() -> None:
    DOCS.mkdir(exist_ok=True)

    def check(console):
        console.print("[dim]$[/dim] pdoc check samples/bad/850_missing_shipto.edi")
        print_result(console, check_file(S / "bad" / "850_missing_shipto.edi"))
        console.print("[dim]$[/dim] pdoc check samples/bad/epcis_duplicate_serial.xml")
        print_result(console, check_file(S / "bad" / "epcis_duplicate_serial.xml"))

    def tracer(console):
        console.print("[dim]$[/dim] pdoc trace TXN-2026-000182 samples/logs")
        events = trace("TXN-2026-000182", [S / "logs"])
        print_trace(console, "TXN-2026-000182", events, summarise(events))

    def differ(console):
        console.print("[dim]$[/dim] pdoc diff samples/good/po_850.edi samples/bad/850_negative_qty.edi")
        print_diff(console, *diff((S / "good" / "po_850.edi").read_bytes(), (S / "bad" / "850_negative_qty.edi").read_bytes()))

    shot("demo-check", "pdoc check", check)
    shot("demo-trace", "pdoc trace", tracer)
    shot("demo-diff", "pdoc diff", differ)
    print("SVGs written to docs/")


if __name__ == "__main__":
    main()
