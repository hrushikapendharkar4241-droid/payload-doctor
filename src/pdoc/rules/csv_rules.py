"""Rules for CSV files. Columns are recognised by name, so any partner layout gets useful checks."""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from ..gs1 import gtin_valid
from ..models import Finding
from . import define, hit

define("CSV-001", "csv", "error", "Header row missing or has duplicate/blank column names",
       "Receivers map columns by header name; without a clean header every value lands in the wrong field.",
       "File exported without headers, or a spreadsheet with merged/blank header cells.",
       "Export with one header row and unique, non-blank column names.")
define("CSV-002", "csv", "error", "Row has the wrong number of columns",
       "Shifted columns put values into the wrong fields (a quantity read as a date, for example).",
       "Unquoted comma inside a value (e.g. a company name), or a truncated line.",
       "Quote values that contain the delimiter, or remove the stray delimiter, and resend.")
define("CSV-003", "csv", "error", "Required value is empty",
       "Identifier, quantity, lot and date columns are needed to process each row.",
       "Blank cells in the source spreadsheet or a mapping gap.",
       "Fill the empty cells in the source data and re-export.")
define("CSV-004", "csv", "error", "Date is not in ISO format (YYYY-MM-DD)",
       "Dates like 03/04/2026 are ambiguous (3 April or 4 March?) and break sorting and comparisons.",
       "Spreadsheet locale formatting applied on export.",
       "Format date columns as YYYY-MM-DD before exporting.")
define("CSV-005", "csv", "error", "GTIN check digit is wrong",
       "A GTIN with a wrong check digit matches no product, so the row is rejected.",
       "Typo, a leading zero removed by Excel, or a digit transposed.",
       "Correct the GTIN (keep leading zeros by formatting the column as text) and resend.")
define("CSV-006", "csv", "error", "Quantity is not a positive number",
       "Quantities must be numeric for stock and order updates.",
       "Text such as '10 boxes', a decimal comma, or a negative adjustment in the wrong file.",
       "Send plain numbers (e.g. 10 or 10.5) in quantity columns.")
define("CSV-007", "csv", "warning", "Delimiter is not a comma",
       "The receiver may expect commas and read the whole row as one column.",
       "Spreadsheet saved with a European locale (semicolon) or as tab-separated.",
       "Confirm the agreed delimiter with the partner, or re-export as comma-separated.")
define("CSV-008", "csv", "warning", "Duplicate rows",
       "Duplicate lines double-count stock or create duplicate orders.",
       "Export run twice into the same file, or a copy-paste error.",
       "Remove duplicate lines, or confirm with the partner that they are intended.")

ID_COLS = re.compile(r"(^|_)(id|gtin|sku|po|order|lot|batch)(_|$|number|no)", re.I)
QTY_COLS = re.compile(r"(qty|quantity)", re.I)
DATE_COLS = re.compile(r"(date|expiry|expiration)", re.I)
GTIN_COLS = re.compile(r"gtin", re.I)


def sniff(text: str) -> str:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def describe(text: str) -> str:
    delim = sniff(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    header = rows[0] if rows else []
    return f"CSV file: {max(len(rows) - 1, 0)} data row(s), {len(header)} column(s): {', '.join(header[:8])}"


def check(text: str) -> list[Finding]:
    out: list[Finding] = []
    delim = sniff(text)
    if delim != ",":
        out.append(hit("CSV-007", f"delimiter looks like {delim!r}"))
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return out
    header = [h.strip() for h in rows[0]]
    dupes = {h for h in header if header.count(h) > 1}
    looks_like_data = header and all(re.fullmatch(r"[\d.\-/]+", h or "0") for h in header)
    if "" in header or dupes or looks_like_data:
        problem = ("first row looks like data, not column names" if looks_like_data else
                   f"duplicate column(s): {', '.join(sorted(dupes))}" if dupes else "blank column name")
        out.append(hit("CSV-001", problem, "line 1"))
        if looks_like_data:
            return out

    seen: dict[tuple, int] = {}
    for n, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        if len(row) != len(header):
            out.append(hit("CSV-002", f"expected {len(header)} columns, found {len(row)}", f"line {n}"))
            continue
        key = tuple(row)
        if key in seen:
            out.append(hit("CSV-008", f"same as line {seen[key]}", f"line {n}"))
        else:
            seen[key] = n
        for col, value in zip(header, row):
            v = value.strip()
            loc = f"line {n}, column {col!r}"
            required = ID_COLS.search(col) or QTY_COLS.search(col) or DATE_COLS.search(col)
            if not v:
                if required:
                    out.append(hit("CSV-003", f"{col} is empty", loc))
                continue
            if GTIN_COLS.search(col) and not gtin_valid(v):
                out.append(hit("CSV-005", f"GTIN {v!r} fails the GS1 check digit (or has the wrong length)", loc))
            elif QTY_COLS.search(col):
                try:
                    ok = float(v) > 0
                except ValueError:
                    ok = False
                if not ok:
                    out.append(hit("CSV-006", f"quantity is {v!r}", loc))
            elif DATE_COLS.search(col):
                try:
                    date.fromisoformat(v[:10])
                    if len(v) > 10 and v[10] not in "T ":
                        raise ValueError
                except ValueError:
                    out.append(hit("CSV-004", f"{col} is {v!r}", loc))
    return out
