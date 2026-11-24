"""GS1 helpers: check digits and EPC URN parsing (SGTIN, SSCC)."""
from __future__ import annotations

import re
from dataclasses import dataclass


def check_digit(digits: str) -> int:
    """GS1 mod-10 check digit for the given digits (without the check digit)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10


def gtin_valid(gtin: str) -> bool:
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", gtin):
        return False
    return check_digit(gtin[:-1]) == int(gtin[-1])


@dataclass
class Epc:
    kind: str  # sgtin | sscc | other
    urn: str
    gtin: str | None = None
    serial: str | None = None
    error: str | None = None


SGTIN_RE = re.compile(r"^urn:epc:id:sgtin:([^.]+)\.([^.]+)\.(.+)$")
SSCC_RE = re.compile(r"^urn:epc:id:sscc:([^.]+)\.([^.]+)$")


def parse_epc(urn: str) -> Epc:
    urn = urn.strip()
    m = SGTIN_RE.match(urn)
    if m:
        prefix, item_ref, serial = m.groups()
        if not (prefix.isdigit() and item_ref.isdigit()):
            return Epc("sgtin", urn, error="company prefix and item reference must be digits only")
        if len(prefix) + len(item_ref) != 13:
            return Epc("sgtin", urn, error=f"company prefix + item reference is {len(prefix) + len(item_ref)} digits; "
                                           "it must be 13 so a GTIN-14 can be rebuilt")
        if not 6 <= len(prefix) <= 12:
            return Epc("sgtin", urn, error=f"company prefix has {len(prefix)} digits; GS1 prefixes are 6-12 digits")
        if len(serial) > 20:
            return Epc("sgtin", urn, error=f"serial number is {len(serial)} characters; the maximum is 20")
        body = item_ref[0] + prefix + item_ref[1:]
        return Epc("sgtin", urn, gtin=body + str(check_digit(body)), serial=serial)
    m = SSCC_RE.match(urn)
    if m:
        prefix, ref = m.groups()
        if not (prefix.isdigit() and ref.isdigit()) or len(prefix) + len(ref) != 17:
            return Epc("sscc", urn, error="SSCC company prefix + serial reference must be 17 digits")
        return Epc("sscc", urn, serial=prefix + ref)
    if urn.startswith("urn:epc:id:"):
        return Epc("other", urn)
    return Epc("other", urn, error="not an EPC URN (expected urn:epc:id:...)")
