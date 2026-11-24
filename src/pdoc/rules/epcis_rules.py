"""Rules for GS1 EPCIS 1.2 XML documents, focused on pharma serialization (DSCSA-style) data."""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from lxml import etree

from ..gs1 import parse_epc
from ..models import Finding
from . import define, hit

NS_EPCIS = "urn:epcglobal:epcis:xsd:1"
NS_MDA = "urn:epcglobal:cbv:mda"
COMMISSIONING = "urn:epcglobal:cbv:bizstep:commissioning"
SHIPPING = "urn:epcglobal:cbv:bizstep:shipping"
OWNING_PARTY = "urn:epcglobal:cbv:sdt:owning_party"
EVENT_TAGS = ("ObjectEvent", "AggregationEvent", "TransactionEvent", "TransformationEvent")

define("XML-001", "xml", "error", "XML is not well-formed",
       "A non-well-formed document cannot be parsed at all, so every event in it is lost.",
       "Unclosed or mismatched tag, unescaped '&' or '<' in a value, or a truncated transfer.",
       "Open the file at the reported line, fix the markup (escape & as &amp;) and resend.")
define("XML-002", "xml", "error", "Document fails XSD schema validation",
       "Receivers validate against the official schema and reject documents that do not conform.",
       "Element in the wrong order, missing required element, or a value of the wrong type.",
       "Fix the element named in the message; validate locally against the same XSD before resending.")
define("EPC-001", "epcis", "error", "Not an EPCIS 1.2 document",
       "The receiver expects an EPCISDocument in the urn:epcglobal:epcis:xsd:1 namespace.",
       "Wrong namespace (e.g. EPCIS 2.0), wrong root element, or a different XML message sent.",
       "Confirm the agreed EPCIS version with the partner and send an EPCISDocument with the 1.2 namespace.")
define("EPC-002", "epcis", "error", "Event is missing a required field",
       "eventTime, eventTimeZoneOffset and action are mandatory; events without them are rejected.",
       "Mapping gap in the serialization or warehouse system.",
       "Populate the missing field for every event in the export.")
define("EPC-003", "epcis", "error", "Malformed EPC identifier",
       "A malformed SGTIN or SSCC cannot be matched to a product or pallet, so verification fails.",
       "Wrong GS1 company prefix length, extra digits, or a serial number longer than 20 characters.",
       "Rebuild the EPC from the correct GS1 company prefix and item reference (13 digits together for SGTIN).")
define("EPC-004", "epcis", "error", "Duplicate serial number",
       "Each serialized unit must be unique; duplicates are a red flag for counterfeit or data errors and block receiving.",
       "Serial number re-used by the serialization system, or the same event sent twice in one document.",
       "Investigate the serial range with the packaging line; decommission the duplicate and send corrected data.")
define("EPC-005", "epcis", "error", "Aggregated unit was never commissioned",
       "A case or pallet claims to contain a unit that has no commissioning event, so its data cannot be verified.",
       "Units re-packed after commissioning, or commissioning events dropped from the file.",
       "Include the commissioning event for every child EPC, or correct the aggregation (childEPCs).")
define("EPC-006", "epcis", "error", "Commissioning event without lot number or expiry date",
       "Lot and expiry are required product data for pharma traceability (for example US DSCSA).",
       "ILMD block missing or mapped to the wrong namespace.",
       "Add <extension><ilmd> with cbvmda:lotNumber and cbvmda:itemExpirationDate to each commissioning event.")
define("EPC-007", "epcis", "error", "Invalid expiry date format",
       "Expiry must be an ISO date (YYYY-MM-DD); other formats cannot be compared or displayed reliably.",
       "Date sent as DD/MM/YYYY or YYMMDD from a label system.",
       "Send cbvmda:itemExpirationDate as YYYY-MM-DD.")
define("EPC-008", "epcis", "warning", "Product is already expired",
       "Expired product should not be shipped; the receiver will quarantine it.",
       "Wrong lot selected at picking, or an incorrect expiry date in master data.",
       "Confirm the lot and expiry with the warehouse before the goods arrive.")
define("EPC-009", "epcis", "error", "Shipping event has no source or destination owning party",
       "Pharma traceability data must name who shipped and who received the goods.",
       "sourceList/destinationList not mapped, or a different source/destination type used.",
       "Add sourceList and destinationList entries of type urn:epcglobal:cbv:sdt:owning_party.")
define("EPC-010", "epcis", "error", "Malformed eventTimeZoneOffset",
       "Without a valid offset the event time cannot be placed correctly on the timeline.",
       "Offset sent as 'IST', '+0530' or '5:30' instead of '+05:30'.",
       "Send the offset as +HH:MM or -HH:MM, for example +05:30.")
define("EPC-011", "epcis", "warning", "Event time is in the future",
       "Events dated in the future usually mean a time zone mistake and confuse sequence checks.",
       "Local time sent with a UTC 'Z' suffix, or the server clock is wrong.",
       "Check the sender's clock and that eventTime and eventTimeZoneOffset describe the same instant.")
define("EPC-012", "epcis", "error", "Document contains no events",
       "An EPCIS document without events carries no traceability data.",
       "Export ran before the events were captured, or the EventList was filtered out.",
       "Re-export after the events are captured.")

TZ_RE = re.compile(r"^[+-](0\d|1[0-4]):[0-5]\d$")


def _parser() -> etree.XMLParser:
    # No external entities, no network: protects against XXE in partner files.
    return etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=True)


def parse(data: bytes):
    return etree.fromstring(data, _parser())


def _local(el) -> str:
    return etree.QName(el).localname


def _events(root) -> list:
    events = []
    for el in root.iter():
        if isinstance(el.tag, str) and _local(el) in EVENT_TAGS:
            events.append(el)
    return events


def _child_text(el, name: str) -> str | None:
    for c in el:
        if isinstance(c.tag, str) and _local(c) == name:
            return (c.text or "").strip()
    return None


def _epcs(el, container: str) -> list[str]:
    out = []
    for c in el.iter():
        if isinstance(c.tag, str) and _local(c) == container:
            out.extend((e.text or "").strip() for e in c if isinstance(e.tag, str) and _local(e) == "epc")
    return out


def _where(ev, i: int) -> str:
    return f"line {ev.sourceline}, event {i} ({_local(ev)})"


def describe(root) -> str:
    events = _events(root)
    kinds = Counter()
    units = set()
    for ev in events:
        step = (_child_text(ev, "bizStep") or "").rsplit(":", 1)[-1] or _local(ev)
        kinds[step] += 1
        for urn in _epcs(ev, "epcList") + _epcs(ev, "childEPCs"):
            if urn.startswith("urn:epc:id:sgtin:"):
                units.add(urn)
    parts = ", ".join(f"{n} {k}" for k, n in kinds.items())
    return f"EPCIS 1.2 document: {len(events)} event(s) ({parts}); {len(units)} serialized unit(s)"


def validate_xsd(data: bytes, schema_dir: Path) -> list[Finding]:
    xsd = schema_dir / "EPCglobal-epcis-1_2.xsd"
    if not xsd.exists():
        return []
    schema = etree.XMLSchema(etree.parse(str(xsd)))
    doc = etree.fromstring(data, _parser())
    if schema.validate(doc):
        return []
    return [hit("XML-002", e.message, f"line {e.line}") for e in list(schema.error_log)[:10]]


def check(root, today: date | None = None, now: datetime | None = None) -> list[Finding]:
    today = today or date.today()
    now = now or datetime.now(timezone.utc)
    out: list[Finding] = []
    if etree.QName(root).namespace != NS_EPCIS or _local(root) != "EPCISDocument":
        ns = etree.QName(root).namespace
        out.append(hit("EPC-001", f"root is {_local(root)!r} in namespace {ns!r}", f"line {root.sourceline}"))
        return out

    events = _events(root)
    if not events:
        out.append(hit("EPC-012", "EventList is empty or missing"))
        return out

    commissioned: Counter[str] = Counter()
    for i, ev in enumerate(events, 1):
        if _child_text(ev, "bizStep") == COMMISSIONING and _child_text(ev, "action") == "ADD":
            commissioned.update(set(_epcs(ev, "epcList")))

    for i, ev in enumerate(events, 1):
        where = _where(ev, i)
        # required fields
        missing = [f for f in ("eventTime", "eventTimeZoneOffset") if not _child_text(ev, f)]
        if _local(ev) in ("ObjectEvent", "AggregationEvent", "TransactionEvent") and not _child_text(ev, "action"):
            missing.append("action")
        if missing:
            out.append(hit("EPC-002", f"missing {', '.join(missing)}", where))
        tz = _child_text(ev, "eventTimeZoneOffset")
        if tz and not TZ_RE.match(tz):
            out.append(hit("EPC-010", f"eventTimeZoneOffset is {tz!r}", where))
        et = _child_text(ev, "eventTime")
        if et:
            try:
                when = datetime.fromisoformat(et.replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if when > now + timedelta(minutes=10):
                    out.append(hit("EPC-011", f"eventTime {et} is after the current time", where))
            except ValueError:
                out.append(hit("EPC-002", f"eventTime {et!r} is not an ISO 8601 date-time", where))

        # identifiers
        listed = _epcs(ev, "epcList") + _epcs(ev, "childEPCs")
        parent = _child_text(ev, "parentID")
        for urn in listed + ([parent] if parent else []):
            epc = parse_epc(urn)
            if epc.error:
                out.append(hit("EPC-003", f"{urn}: {epc.error}", where))
        for urn, n in Counter(listed).items():
            if n > 1:
                out.append(hit("EPC-004", f"{urn} is listed {n} times in the same event", where))

        step = _child_text(ev, "bizStep")
        if step == COMMISSIONING:
            lot = expiry = None
            for c in ev.iter():
                if isinstance(c.tag, str) and etree.QName(c).namespace == NS_MDA:
                    if _local(c) == "lotNumber":
                        lot = (c.text or "").strip()
                    elif _local(c) == "itemExpirationDate":
                        expiry = (c.text or "").strip()
            missing = [n for n, v in (("lotNumber", lot), ("itemExpirationDate", expiry)) if not v]
            if missing:
                out.append(hit("EPC-006", f"commissioning event has no {' or '.join(missing)}", where))
            if expiry:
                try:
                    exp = date.fromisoformat(expiry)
                    if exp < today:
                        out.append(hit("EPC-008", f"expiry {expiry} is before today ({today.isoformat()})", where))
                except ValueError:
                    out.append(hit("EPC-007", f"itemExpirationDate is {expiry!r}", where))

        if _local(ev) == "AggregationEvent" and commissioned and _child_text(ev, "action") == "ADD":
            for urn in _epcs(ev, "childEPCs"):
                if urn.startswith("urn:epc:id:sgtin:") and urn not in commissioned:
                    out.append(hit("EPC-005", f"{urn} is packed into {parent or 'a parent'} but never commissioned", where))

        if step == SHIPPING:
            def has_party(list_name: str) -> bool:
                for c in ev.iter():
                    if isinstance(c.tag, str) and _local(c) == list_name:
                        for item in c:
                            if isinstance(item.tag, str) and item.get("type") == OWNING_PARTY and (item.text or "").strip():
                                return True
                return False
            missing = [n for n in ("sourceList", "destinationList") if not has_party(n)]
            if missing:
                out.append(hit("EPC-009", f"no owning_party entry in {' and '.join(missing)}", where))

    for urn, n in commissioned.items():
        if n > 1:
            out.append(hit("EPC-004", f"{urn} is commissioned {n} times in this document"))
    return out
