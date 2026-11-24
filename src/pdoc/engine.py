"""Format detection and the check pipeline used by the CLI (and by IntegrX as a library)."""
from __future__ import annotations

import os
from pathlib import Path

from lxml import etree

from .models import CheckResult
from .parsers import edifact as edifact_parser
from .parsers import x12 as x12_parser
from .rules import all_rules, hit
from .rules import csv_rules, edifact_rules, epcis_rules, x12_rules

all_rules()  # register every rule

BOM = b"\xef\xbb\xbf"
# Put the official GS1 EPCIS 1.2 XSD files here (or point PDOC_SCHEMA_DIR at them) to enable XSD validation.
SCHEMA_DIR = Path(os.environ.get("PDOC_SCHEMA_DIR",
                                 Path(__file__).resolve().parent.parent.parent / "schemas" / "epcis"))


def detect(data: bytes) -> str:
    """Return one of: x12, edifact, xml, csv, unknown, empty."""
    body = data[3:] if data.startswith(BOM) else data
    head = body.lstrip()[:16]
    if not head:
        return "empty"
    if head.startswith(b"ISA"):
        return "x12"
    if head.startswith(b"UNA") or head.startswith(b"UNB"):
        return "edifact"
    if head.startswith(b"<"):
        return "xml"
    try:
        text = body[:4096].decode("utf-8")
    except UnicodeDecodeError:
        text = body[:4096].decode("latin-1")
    first = text.splitlines()[0] if text.splitlines() else ""
    if any(d in first for d in (",", ";", "\t", "|")) and "\x00" not in text:
        return "csv"
    return "unknown"


def check_bytes(data: bytes, name: str = "<stdin>", schema_dir: Path | None = None) -> CheckResult:
    fmt = detect(data)
    result = CheckResult(name, fmt)
    if fmt == "empty":
        result.findings.append(hit("GEN-003", "file has no content"))
        return result
    if data.startswith(BOM):
        result.findings.append(hit("GEN-001", "file starts with bytes EF BB BF", "byte 0"))
    body = data[3:] if data.startswith(BOM) else data

    if fmt == "unknown":
        result.findings.append(hit("GEN-002", "file is not X12, EDIFACT, XML or CSV"))
        return result

    if fmt == "xml":
        try:
            root = epcis_rules.parse(body)
        except etree.XMLSyntaxError as e:
            result.fmt = "xml"
            result.findings.append(hit("XML-001", str(e.msg), f"line {e.lineno}, column {e.offset}"))
            return result
        result.fmt = "epcis-xml"
        result.summary = epcis_rules.describe(root)
        result.findings.extend(epcis_rules.validate_xsd(body, schema_dir or SCHEMA_DIR))
        result.findings.extend(epcis_rules.check(root))
        return result

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        result.findings.append(hit("GEN-004", f"invalid UTF-8 byte 0x{body[e.start]:02X}", f"byte {e.start + (len(data) - len(body))}"))
        text = body.decode("latin-1")

    if fmt == "x12":
        try:
            ic = x12_parser.parse(text)
        except x12_parser.X12ParseError as e:
            result.findings.append(hit("X12-001", str(e), "segment 1 (ISA)"))
            return result
        result.summary = x12_rules.describe(ic)
        result.findings.extend(x12_rules.check(ic))
    elif fmt == "edifact":
        try:
            ic = edifact_parser.parse(text)
        except edifact_parser.EdifactParseError as e:
            result.findings.append(hit("EDI-005", str(e)))
            return result
        result.summary = edifact_rules.describe(ic)
        result.findings.extend(edifact_rules.check(ic))
    elif fmt == "csv":
        result.summary = csv_rules.describe(text)
        result.findings.extend(csv_rules.check(text))
    return result


def check_file(path: Path, schema_dir: Path | None = None) -> CheckResult:
    return check_bytes(path.read_bytes(), str(path), schema_dir)
