"""Meaningful differences between two payloads of the same format."""
from __future__ import annotations

import csv
import difflib
import io
from dataclasses import dataclass

from lxml import etree

from .engine import BOM, detect
from .parsers import edifact as edifact_parser
from .parsers import x12 as x12_parser


@dataclass
class Change:
    kind: str  # added | removed | changed
    location: str
    old: str | None = None
    new: str | None = None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "location": self.location, "old": self.old, "new": self.new}


def _text(data: bytes) -> str:
    return (data[3:] if data.startswith(BOM) else data).decode("utf-8", errors="replace")


def _segment_diff(a: list[list[str]], b: list[list[str]], tags_a: list[str], tags_b: list[str], sep: str) -> list[Change]:
    """a/b are segments as lists of elements; elements may be strings or joined components."""
    out: list[Change] = []
    sa, sb = [sep.join(s) for s in a], [sep.join(s) for s in b]
    sm = difflib.SequenceMatcher(a=sa, b=sb, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if op == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                ea, eb = a[i1 + k], b[j1 + k]
                if tags_a[i1 + k] != tags_b[j1 + k]:
                    out.append(Change("changed", f"segment {j1 + k + 1}", sa[i1 + k], sb[j1 + k]))
                    continue
                for n in range(1, max(len(ea), len(eb))):
                    va = ea[n] if n < len(ea) else None
                    vb = eb[n] if n < len(eb) else None
                    if va != vb:
                        out.append(Change("changed", f"segment {j1 + k + 1} {tags_b[j1 + k]}{n:02d}", va, vb))
            continue
        for k in range(i1, i2):
            out.append(Change("removed", f"segment {k + 1} ({tags_a[k]})", sa[k], None))
        for k in range(j1, j2):
            out.append(Change("added", f"segment {k + 1} ({tags_b[k]})", None, sb[k]))
    return out


def _flatten_xml(data: bytes) -> dict[str, str]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=True)
    root = etree.fromstring(data[3:] if data.startswith(BOM) else data, parser)
    flat: dict[str, str] = {}

    def walk(el, path: str):
        counts: dict[str, int] = {}
        for attr, value in sorted(el.attrib.items()):
            flat[f"{path}/@{etree.QName(attr).localname}"] = value
        text = (el.text or "").strip()
        if text:
            flat[path] = text
        for child in el:
            if not isinstance(child.tag, str):
                continue
            name = etree.QName(child).localname
            counts[name] = counts.get(name, 0) + 1
            walk(child, f"{path}/{name}[{counts[name]}]")

    walk(root, "/" + etree.QName(root).localname)
    return flat


def _dict_diff(a: dict[str, str], b: dict[str, str]) -> list[Change]:
    out = []
    for key in sorted(set(a) | set(b)):
        if key not in b:
            out.append(Change("removed", key, a[key], None))
        elif key not in a:
            out.append(Change("added", key, None, b[key]))
        elif a[key] != b[key]:
            out.append(Change("changed", key, a[key], b[key]))
    return out


def _csv_diff(ta: str, tb: str) -> list[Change]:
    ra, rb = list(csv.reader(io.StringIO(ta))), list(csv.reader(io.StringIO(tb)))
    out: list[Change] = []
    ha, hb = (ra[0] if ra else []), (rb[0] if rb else [])
    if ha != hb:
        out.append(Change("changed", "header", ",".join(ha), ",".join(hb)))
    for n in range(1, max(len(ra), len(rb))):
        a = ra[n] if n < len(ra) else None
        b = rb[n] if n < len(rb) else None
        if a == b:
            continue
        if a is None:
            out.append(Change("added", f"line {n + 1}", None, ",".join(b)))
        elif b is None:
            out.append(Change("removed", f"line {n + 1}", ",".join(a), None))
        else:
            for i in range(max(len(a), len(b))):
                va = a[i] if i < len(a) else None
                vb = b[i] if i < len(b) else None
                if va != vb:
                    col = hb[i] if i < len(hb) else f"column {i + 1}"
                    out.append(Change("changed", f"line {n + 1}, {col}", va, vb))
    return out


def diff(a: bytes, b: bytes) -> tuple[str, list[Change]]:
    fa, fb = detect(a), detect(b)
    if fa != fb:
        return f"{fa} vs {fb}", [Change("changed", "format", fa, fb)]
    if fa == "x12":
        ia, ib = x12_parser.parse(_text(a)), x12_parser.parse(_text(b))
        return "x12", _segment_diff([s.elements for s in ia.segments], [s.elements for s in ib.segments],
                                    [s.tag for s in ia.segments], [s.tag for s in ib.segments], "*")
    if fa == "edifact":
        ia, ib = edifact_parser.parse(_text(a)), edifact_parser.parse(_text(b))
        ea = [[":".join(c) for c in s.elements] for s in ia.segments]
        eb = [[":".join(c) for c in s.elements] for s in ib.segments]
        return "edifact", _segment_diff(ea, eb, [s.tag for s in ia.segments], [s.tag for s in ib.segments], "+")
    if fa == "xml":
        return "xml", _dict_diff(_flatten_xml(a), _flatten_xml(b))
    if fa == "csv":
        return "csv", _csv_diff(_text(a), _text(b))
    lines = difflib.unified_diff(_text(a).splitlines(), _text(b).splitlines(), lineterm="", n=0)
    return "text", [Change("changed", "text", None, line) for line in lines if not line.startswith(("---", "+++"))]
