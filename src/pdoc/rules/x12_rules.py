"""Rules for ANSI X12 interchanges (envelope + 850, 856, 997)."""
from __future__ import annotations

import re
from datetime import datetime

from ..models import Finding
from ..parsers.x12 import TRANSACTION_NAMES, Interchange, Segment
from . import define, hit

# --- envelope -----------------------------------------------------------------------------
define("X12-001", "x12", "error", "ISA header malformed",
       "The receiver reads the delimiters from fixed positions in ISA; if ISA is wrong nothing else can be parsed.",
       "ISA fields not padded to their fixed widths, or the file was edited by hand.",
       "Regenerate the interchange from the EDI translator; ISA must be exactly 106 characters.")
define("X12-002", "x12", "error", "ISA/IEA control numbers do not match",
       "Translators use the control number to detect lost or duplicate interchanges, and reject mismatches.",
       "Envelope built by a custom script, or two interchanges concatenated.",
       "Make IEA02 equal ISA13 and resend.")
define("X12-003", "x12", "error", "IEA group count is wrong",
       "IEA01 must equal the number of GS groups; a mismatch suggests the file was truncated or merged.",
       "Partial transfer, or groups added without updating the trailer.",
       "Recount GS/GE groups, fix IEA01 and resend; check the transfer log for a cut-off upload.")
define("X12-004", "x12", "error", "GS/GE control numbers do not match",
       "The functional group cannot be acknowledged (997) when its header and trailer disagree.",
       "Envelope generation bug in the sender's translator.",
       "Make GE02 equal GS06 and resend.")
define("X12-005", "x12", "error", "GE transaction count is wrong",
       "GE01 must equal the number of ST/SE sets in the group; otherwise the group is rejected.",
       "Transaction sets added or removed without updating GE01.",
       "Recount the ST segments in the group and correct GE01.")
define("X12-006", "x12", "error", "ST/SE control numbers do not match",
       "The transaction set cannot be matched to its trailer, so the whole set is rejected.",
       "Template or mapping bug that hard-codes one of the two numbers.",
       "Make SE02 equal ST02.")
define("X12-007", "x12", "error", "SE segment count is wrong",
       "SE01 counts every segment from ST to SE inclusive; receivers use it to detect missing segments.",
       "Segments added or dropped by the map without recalculating SE01.",
       "Recalculate SE01 (count ST..SE inclusive) in the map.")
define("X12-008", "x12", "warning", "Transaction set not covered by Payload Doctor",
       "Only envelope checks were run; business rules for this transaction type were skipped.",
       "The interchange contains a transaction set other than 850, 856 or 997.",
       "Validate the business content manually or add rules for this transaction set.")
define("X12-009", "x12", "warning", "Line breaks inside segments (wrapped file)",
       "Many translators treat a line break as data, so elements split across lines are read wrongly or the ISA header is rejected.",
       "File wrapped at a fixed width (often 80 characters) by a mainframe, mail gateway or FTP ASCII-mode transfer.",
       "Unwrap the file (tr -d '\\r\\n' < in > out) and ask the partner to send it unwrapped in binary mode.")
define("X12-010", "x12", "error", "Envelope segment missing",
       "Without the trailer segments the receiver cannot tell whether the file arrived complete.",
       "Truncated transfer or an export that stopped mid-file.",
       "Compare file size with the sender's copy; ask for a full resend.")
define("X12-011", "x12", "error", "Segment outside a transaction set",
       "Business segments must sit between ST and SE; anything else is ignored or rejected.",
       "Two interchanges merged, or a missing ST segment.",
       "Check the segment order around the reported position and regenerate the file.")
define("X12-012", "x12", "warning", "Interchange is flagged as TEST (ISA15 = T)",
       "Production systems usually discard test interchanges, so the partner thinks it was sent but nothing is processed.",
       "Partner forgot to switch the trading-partner profile from test to production.",
       "Ask the partner to set ISA15 to P for production traffic and resend.")
# --- 850 purchase order ------------------------------------------------------------------
define("X12-014", "x12", "error", "850 has no ship-to party (N1*ST)",
       "Without a ship-to party the receiver cannot route the order to a warehouse or customer site.",
       "The partner's ERP mapping skipped the address block, or the location is missing in master data.",
       "Add an N1*ST segment (with N3/N4 address or an ID in N103/N104) and resend; ask partner to check the map.")
define("X12-015", "x12", "error", "850 BEG segment missing or PO number empty",
       "The PO number is the key every later document (855, 856, 810) refers to.",
       "Order created without a PO number, or BEG mapped to the wrong field.",
       "Populate BEG03 with the purchase order number.")
define("X12-016", "x12", "error", "850 has no line items (PO1)",
       "An order without lines cannot be fulfilled.",
       "Lines filtered out by the export, or an order header sent on its own.",
       "Check the source order in the ERP and re-export including lines.")
define("X12-017", "x12", "warning", "CTT line count does not match PO1 lines",
       "Receivers use CTT01 as a checksum; a mismatch suggests lost lines.",
       "Lines removed after the count was calculated.",
       "Recalculate CTT01 as the number of PO1 segments.")
define("X12-018", "x12", "error", "PO1 quantity is not a positive number",
       "An order line with zero, negative or non-numeric quantity cannot be allocated.",
       "Unit-of-measure conversion bug, or a text value in a numeric field.",
       "Fix PO102 in the source order and resend.")
define("X12-019", "x12", "error", "Invalid date (expected CCYYMMDD)",
       "Dates that do not parse break scheduling and ageing reports downstream.",
       "Date sent as YYMMDD, DD-MM-YYYY or with separators.",
       "Send dates as 8 digits, for example 20261124.")
# --- 856 ship notice -----------------------------------------------------------------------
define("X12-020", "x12", "error", "856 BSN missing or shipment ID empty",
       "The shipment ID links the ASN to the physical delivery at receiving.",
       "Shipment created without an ID in the warehouse system.",
       "Populate BSN02 with the shipment identifier.")
define("X12-021", "x12", "error", "856 HL hierarchy broken",
       "Each HL points to its parent; a broken link means items cannot be placed in their packs or shipment.",
       "HL parent IDs (HL02) generated out of order or after lines were removed.",
       "Regenerate the HL loop so every HL02 refers to an earlier HL01.")
define("X12-022", "x12", "error", "856 has no item-level HL (HL03 = I)",
       "The receiver cannot see what products are in the shipment.",
       "Only shipment/order levels were mapped.",
       "Add item-level HL loops with LIN/SN1 for each product.")
define("X12-023", "x12", "warning", "856 has no ship date (DTM*011)",
       "Receiving teams plan dock schedules from the ship date.",
       "Date not available at the time the ASN was generated.",
       "Add DTM*011 with the actual ship date.")
# --- 997 acknowledgment --------------------------------------------------------------------
define("X12-025", "x12", "error", "997 reports a rejected transaction or group",
       "The partner's system refused the original document, so it was NOT processed on their side.",
       "The original file failed the partner's validation (see AK3/AK4 for the exact segment).",
       "Read the AK3/AK4 segments to find the failing segment, fix the original document and resend it.")
define("X12-026", "x12", "warning", "997 reports accepted with errors",
       "The document was processed, but some data was ignored.",
       "Optional elements the partner does not support or invalid code values.",
       "Review the AK3/AK4 details with the partner and correct the map.")

DATE_RE = re.compile(r"^\d{8}$")


def _valid_date(value: str) -> bool:
    if not DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def _at(seg: Segment) -> str:
    return f"segment {seg.index} ({seg.tag})"


def describe(ic: Interchange) -> str:
    isa = ic.segments[0]
    sender, receiver = isa.get(6).strip(), isa.get(8).strip()
    sets = [s.get(1) for s in ic.find("ST")]
    names = ", ".join(f"X12 {c} ({TRANSACTION_NAMES.get(c, 'unknown')})" for c in dict.fromkeys(sets))
    return f"{names or 'X12 interchange'}, sender {sender} -> receiver {receiver}"


def check(ic: Interchange) -> list[Finding]:
    out: list[Finding] = []
    segs = ic.segments
    if ic.wrapped:
        out.append(hit("X12-009", "line breaks found inside segments; the file looks wrapped at a fixed width"))

    isa = segs[0]
    if len(isa.elements) != 17:
        out.append(hit("X12-001", f"ISA has {len(isa.elements) - 1} elements, expected 16", _at(isa)))
        return out
    if isa.get(15).strip() == "T":
        out.append(hit("X12-012", "ISA15 is 'T' (test); production files use 'P'", _at(isa)))

    iea = [s for s in segs if s.tag == "IEA"]
    if not iea:
        out.append(hit("X12-010", "IEA (interchange trailer) is missing; the file may be truncated"))
    else:
        if iea[-1].get(2).strip() != isa.get(13).strip():
            out.append(hit("X12-002", f"ISA13 is {isa.get(13)!r} but IEA02 is {iea[-1].get(2)!r}", _at(iea[-1])))
        n_gs = len(ic.find("GS"))
        if iea[-1].get(1).strip() != str(n_gs):
            out.append(hit("X12-003", f"IEA01 says {iea[-1].get(1)} group(s) but the file has {n_gs}", _at(iea[-1])))

    # Walk groups and transaction sets.
    current_gs: Segment | None = None
    gs_sets = 0
    current_st: Segment | None = None
    st_body: list[Segment] = []
    for seg in segs[1:]:
        tag = seg.tag
        if tag == "GS":
            current_gs, gs_sets = seg, 0
        elif tag == "GE":
            if current_gs is None:
                out.append(hit("X12-011", "GE found without a matching GS", _at(seg)))
            else:
                if seg.get(2).strip() != current_gs.get(6).strip():
                    out.append(hit("X12-004", f"GS06 is {current_gs.get(6)!r} but GE02 is {seg.get(2)!r}", _at(seg)))
                if seg.get(1).strip() != str(gs_sets):
                    out.append(hit("X12-005", f"GE01 says {seg.get(1)} set(s) but the group has {gs_sets}", _at(seg)))
            current_gs = None
        elif tag == "ST":
            current_st, st_body = seg, [seg]
            gs_sets += 1
        elif tag == "SE":
            if current_st is None:
                out.append(hit("X12-011", "SE found without a matching ST", _at(seg)))
                continue
            st_body.append(seg)
            if seg.get(2).strip() != current_st.get(2).strip():
                out.append(hit("X12-006", f"ST02 is {current_st.get(2)!r} but SE02 is {seg.get(2)!r}", _at(seg)))
            if seg.get(1).strip() != str(len(st_body)):
                out.append(hit("X12-007", f"SE01 says {seg.get(1)} segments but ST..SE contains {len(st_body)}", _at(seg)))
            out.extend(_check_set(current_st.get(1).strip(), st_body))
            current_st, st_body = None, []
        elif tag in ("ISA", "IEA"):
            continue
        else:
            if current_st is None:
                out.append(hit("X12-011", f"{tag} appears outside an ST..SE transaction set", _at(seg)))
            else:
                st_body.append(seg)
    if current_st is not None:
        out.append(hit("X12-010", f"transaction set {current_st.get(2)} has no SE trailer; the file may be truncated",
                       _at(current_st)))
    if current_gs is not None:
        out.append(hit("X12-010", "functional group has no GE trailer", _at(current_gs)))
    return out


def _check_set(code: str, body: list[Segment]) -> list[Finding]:
    if code == "850":
        return _check_850(body)
    if code == "856":
        return _check_856(body)
    if code == "997":
        return _check_997(body)
    return [hit("X12-008", f"transaction set {code} ({TRANSACTION_NAMES.get(code, 'unknown')}) only had envelope checks",
                _at(body[0]))]


def _check_850(body: list[Segment]) -> list[Finding]:
    out: list[Finding] = []
    beg = [s for s in body if s.tag == "BEG"]
    if not beg or not beg[0].get(3).strip():
        out.append(hit("X12-015", "BEG segment missing" if not beg else "BEG03 (PO number) is empty",
                       _at(beg[0]) if beg else _at(body[0])))
    elif beg[0].get(5) and not _valid_date(beg[0].get(5).strip()):
        out.append(hit("X12-019", f"BEG05 order date {beg[0].get(5)!r} is not CCYYMMDD", _at(beg[0])))
    if not any(s.tag == "N1" and s.get(1).strip() == "ST" for s in body):
        last_n1 = [s for s in body if s.tag == "N1"]
        where = _at(last_n1[-1]) if last_n1 else _at(body[0])
        out.append(hit("X12-014", "no N1 segment with entity code ST (ship-to) in this purchase order", where))
    lines = [s for s in body if s.tag == "PO1"]
    if not lines:
        out.append(hit("X12-016", "no PO1 segments in this purchase order", _at(body[0])))
    for po1 in lines:
        qty = po1.get(2).strip()
        try:
            ok = float(qty) > 0
        except ValueError:
            ok = False
        if not ok:
            out.append(hit("X12-018", f"PO1 line {po1.get(1) or '?'} has quantity {qty!r}", _at(po1)))
    ctt = [s for s in body if s.tag == "CTT"]
    if ctt and ctt[0].get(1).strip() != str(len(lines)):
        out.append(hit("X12-017", f"CTT01 says {ctt[0].get(1)} line(s) but there are {len(lines)} PO1 segments",
                       _at(ctt[0])))
    for dtm in (s for s in body if s.tag == "DTM"):
        if dtm.get(2) and not _valid_date(dtm.get(2).strip()):
            out.append(hit("X12-019", f"DTM{dtm.get(1)} date {dtm.get(2)!r} is not CCYYMMDD", _at(dtm)))
    return out


def _check_856(body: list[Segment]) -> list[Finding]:
    out: list[Finding] = []
    bsn = [s for s in body if s.tag == "BSN"]
    if not bsn or not bsn[0].get(2).strip():
        out.append(hit("X12-020", "BSN segment missing" if not bsn else "BSN02 (shipment ID) is empty",
                       _at(bsn[0]) if bsn else _at(body[0])))
    elif bsn[0].get(3) and not _valid_date(bsn[0].get(3).strip()):
        out.append(hit("X12-019", f"BSN03 date {bsn[0].get(3)!r} is not CCYYMMDD", _at(bsn[0])))
    seen: set[str] = set()
    for hl in (s for s in body if s.tag == "HL"):
        hl_id, parent = hl.get(1).strip(), hl.get(2).strip()
        if parent and parent not in seen:
            out.append(hit("X12-021", f"HL {hl_id} points to parent {parent}, which does not appear before it", _at(hl)))
        seen.add(hl_id)
    if not any(s.tag == "HL" and s.get(3).strip() == "I" for s in body):
        out.append(hit("X12-022", "no HL segment with level code I (item)", _at(body[0])))
    dtms = [s for s in body if s.tag == "DTM"]
    if not any(s.get(1).strip() == "011" for s in dtms):
        out.append(hit("X12-023", "no DTM*011 (shipped date) segment", _at(body[0])))
    for dtm in dtms:
        if dtm.get(2) and not _valid_date(dtm.get(2).strip()):
            out.append(hit("X12-019", f"DTM{dtm.get(1)} date {dtm.get(2)!r} is not CCYYMMDD", _at(dtm)))
    return out


def _check_997(body: list[Segment]) -> list[Finding]:
    out: list[Finding] = []
    ak1 = next((s for s in body if s.tag == "AK1"), None)
    group = f"group {ak1.get(2)} ({ak1.get(1)})" if ak1 else "the group"
    for seg in body:
        if seg.tag == "AK5" and seg.get(1).strip() == "R":
            ak2 = _previous(body, seg, "AK2")
            ref = f"transaction set {ak2.get(2)} ({ak2.get(1)})" if ak2 else "a transaction set"
            out.append(hit("X12-025", f"partner rejected {ref}", _at(seg)))
        elif seg.tag == "AK9":
            status = seg.get(1).strip()
            if status in ("R", "P"):
                word = "rejected" if status == "R" else "partially accepted"
                out.append(hit("X12-025", f"partner {word} {group}: "
                               f"{seg.get(4) or '?'} of {seg.get(2) or '?'} set(s) accepted", _at(seg)))
            elif status == "E":
                out.append(hit("X12-026", f"partner accepted {group} with errors", _at(seg)))
    return out


def _previous(body: list[Segment], seg: Segment, tag: str) -> Segment | None:
    idx = body.index(seg)
    for s in reversed(body[:idx]):
        if s.tag == tag:
            return s
    return None
