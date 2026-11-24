"""Rules for UN/EDIFACT interchanges (envelope + ORDERS, DESADV, CONTRL)."""
from __future__ import annotations

from ..models import Finding
from ..parsers.edifact import MESSAGE_NAMES, Interchange, Segment
from . import define, hit

define("EDI-001", "edifact", "error", "UNB/UNZ interchange references do not match",
       "The interchange control reference is how duplicates and losses are detected; mismatches are rejected.",
       "Envelope built by a custom script or two interchanges merged.",
       "Make UNZ02 equal UNB05 and resend.")
define("EDI-002", "edifact", "error", "UNZ message count is wrong",
       "UNZ01 must equal the number of UNH messages (or UNG groups) in the interchange.",
       "Messages added or removed without updating the trailer, or a truncated transfer.",
       "Recount UNH segments and correct UNZ01.")
define("EDI-003", "edifact", "error", "UNH/UNT message references do not match",
       "The receiver cannot pair the message header with its trailer.",
       "Template that hard-codes one of the two references.",
       "Make UNT02 equal UNH01.")
define("EDI-004", "edifact", "error", "UNT segment count is wrong",
       "UNT01 counts every segment from UNH to UNT inclusive; a mismatch means segments were lost or added.",
       "Map changed without recalculating the count.",
       "Recalculate UNT01 (UNH..UNT inclusive).")
define("EDI-005", "edifact", "error", "Envelope segment missing",
       "Without UNZ/UNT the receiver cannot confirm the interchange arrived complete.",
       "Truncated transfer or an export that stopped early.",
       "Compare file sizes with the sender and request a full resend.")
define("EDI-006", "edifact", "warning", "Message type not covered by Payload Doctor",
       "Only envelope checks were run for this message.",
       "Message type other than ORDERS, DESADV or CONTRL.",
       "Validate the business content manually or add rules for this message type.")
define("EDI-007", "edifact", "error", "ORDERS has no delivery party (NAD+DP or NAD+ST)",
       "Without a delivery party the order cannot be routed to the right site.",
       "Address block skipped in the partner's map.",
       "Add NAD+DP (or NAD+ST) with a GLN or address and resend.")
define("EDI-008", "edifact", "error", "Message has no line items (LIN)",
       "An order or despatch advice without lines carries no products.",
       "Lines filtered out by the export.",
       "Re-export including LIN/QTY segment groups.")
define("EDI-009", "edifact", "warning", "DESADV has no despatch date (DTM+11)",
       "Receiving teams plan the dock schedule from the despatch date.",
       "Date not set when the DESADV was generated.",
       "Add DTM+11 with the actual despatch date/time.")
define("EDI-010", "edifact", "error", "QTY value is not a positive number",
       "Quantities must be numeric for allocation and receiving.",
       "Decimal mark mismatch (comma vs point) or text in a numeric field.",
       "Send QTY as a plain number using the decimal mark declared in UNA.")
define("EDI-011", "edifact", "error", "CONTRL reports the interchange or a message was rejected",
       "The partner's system refused the original interchange; it was not processed.",
       "Syntax error in the original file (see UCS/UCD segments for the exact place).",
       "Read UCS/UCD to locate the error, fix the original interchange and resend.")
define("EDI-012", "edifact", "error", "Segment outside a message",
       "Business segments must sit between UNH and UNT.",
       "Missing UNH, or two interchanges merged.",
       "Check the segment order around the reported position.")


def _at(seg: Segment) -> str:
    return f"segment {seg.index} ({seg.tag})"


def describe(ic: Interchange) -> str:
    unb = ic.segments[0]
    types = [s.el(2, 0) for s in ic.find("UNH")]
    names = ", ".join(f"EDIFACT {t} ({MESSAGE_NAMES.get(t, 'unknown')})" for t in dict.fromkeys(types))
    return f"{names or 'EDIFACT interchange'}, sender {unb.el(2)} -> receiver {unb.el(3)}"


def check(ic: Interchange) -> list[Finding]:
    out: list[Finding] = []
    unb = ic.segments[0]
    unz = ic.find("UNZ")
    n_unh = len(ic.find("UNH"))
    if not unz:
        out.append(hit("EDI-005", "UNZ (interchange trailer) is missing"))
    else:
        if unz[-1].el(2) != unb.el(5):
            out.append(hit("EDI-001", f"UNB05 is {unb.el(5)!r} but UNZ02 is {unz[-1].el(2)!r}", _at(unz[-1])))
        n_ung = len(ic.find("UNG"))
        expected = n_ung or n_unh
        if unz[-1].el(1) != str(expected):
            out.append(hit("EDI-002", f"UNZ01 says {unz[-1].el(1)} but the interchange has {expected}", _at(unz[-1])))

    unh: Segment | None = None
    body: list[Segment] = []
    for seg in ic.segments[1:]:
        if seg.tag == "UNH":
            unh, body = seg, [seg]
        elif seg.tag == "UNT":
            if unh is None:
                out.append(hit("EDI-012", "UNT without a matching UNH", _at(seg)))
                continue
            body.append(seg)
            if seg.el(2) != unh.el(1):
                out.append(hit("EDI-003", f"UNH01 is {unh.el(1)!r} but UNT02 is {seg.el(2)!r}", _at(seg)))
            if seg.el(1) != str(len(body)):
                out.append(hit("EDI-004", f"UNT01 says {seg.el(1)} but UNH..UNT contains {len(body)}", _at(seg)))
            out.extend(_check_message(unh.el(2, 0), body))
            unh, body = None, []
        elif seg.tag in ("UNZ", "UNG", "UNE"):
            continue
        elif unh is None:
            out.append(hit("EDI-012", f"{seg.tag} appears outside a UNH..UNT message", _at(seg)))
        else:
            body.append(seg)
    if unh is not None:
        out.append(hit("EDI-005", f"message {unh.el(1)} has no UNT trailer", _at(unh)))
    return out


def _check_message(mtype: str, body: list[Segment]) -> list[Finding]:
    out: list[Finding] = []
    if mtype not in ("ORDERS", "DESADV", "CONTRL"):
        return [hit("EDI-006", f"{mtype} ({MESSAGE_NAMES.get(mtype, 'unknown')}) only had envelope checks", _at(body[0]))]
    if mtype == "CONTRL":
        for seg in body:
            if seg.tag in ("UCI", "UCM") and seg.el(4 if seg.tag == "UCI" else 3) == "4":
                out.append(hit("EDI-011", f"{seg.tag} action code 4 = rejected", _at(seg)))
        return out
    if mtype == "ORDERS" and not any(s.tag == "NAD" and s.el(1) in ("DP", "ST") for s in body):
        out.append(hit("EDI-007", "no NAD+DP or NAD+ST segment in this order", _at(body[0])))
    if not any(s.tag == "LIN" for s in body):
        out.append(hit("EDI-008", f"{mtype} message has no LIN segments", _at(body[0])))
    if mtype == "DESADV" and not any(s.tag == "DTM" and s.el(1, 0) == "11" for s in body):
        out.append(hit("EDI-009", "no DTM+11 (despatch date) segment", _at(body[0])))
    for qty in (s for s in body if s.tag == "QTY"):
        value = qty.el(1, 1)
        try:
            ok = float(value) > 0
        except ValueError:
            ok = False
        if not ok:
            out.append(hit("EDI-010", f"QTY+{qty.el(1, 0)} value {value!r}", _at(qty)))
    return out
