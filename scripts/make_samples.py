"""Generate the synthetic sample library in samples/.

Every company name, GLN, GTIN and serial number here is invented (GS1's documentation prefix 0614141 is used).
Run:  python scripts/make_samples.py
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "samples"
GOOD, BAD, LOGS, CERTS = (ROOT / d for d in ("good", "bad", "logs", "certs"))


# ---------------------------------------------------------------- X12 ---------------------------------------
def isa(control: str = "000000905", usage: str = "P", sender: str = "ACME01", receiver: str = "WHOLESALE02") -> list[str]:
    return ["ISA", "00", " " * 10, "00", " " * 10, "ZZ", sender.ljust(15), "ZZ", receiver.ljust(15),
            "261124", "1200", "U", "00401", control, "0", usage, ">"]


def x12(transactions: list[tuple[str, str, list[list[str]]]], *, control="000000905", usage="P",
        term="~\n", se_count_delta=0, drop_trailers=False, functional_id="PO") -> str:
    """transactions: (code, st_control, body segments without ST/SE)."""
    segs = [isa(control, usage), ["GS", functional_id, "ACME01", "WHOLESALE02", "20261124", "1200", "905", "X", "004010"]]
    for code, st_ctl, body in transactions:
        segs.append(["ST", code, st_ctl])
        segs.extend(body)
        if not drop_trailers:
            segs.append(["SE", str(len(body) + 2 + se_count_delta), st_ctl])
    if not drop_trailers:
        segs.append(["GE", str(len(transactions)), "905"])
        segs.append(["IEA", "1", control])
    return "".join("*".join(s) + term for s in segs)


PO_BODY = [
    ["BEG", "00", "SA", "4500012", "", "20261124"],
    ["REF", "DP", "PHARMA-01"],
    ["DTM", "002", "20261201"],
    ["N1", "BY", "Acme Health Distributors", "92", "ACME01"],
    ["N1", "ST", "Pune Central Warehouse", "92", "PNQ-WH1"],
    ["N3", "Plot 14, Hinjewadi Phase 2"],
    ["N4", "Pune", "MH", "411057", "IN"],
    ["PO1", "1", "120", "EA", "4.75", "", "VN", "AMOX-500"],
    ["PID", "F", "", "", "", "Amoxicillin 500 mg capsules"],
    ["PO1", "2", "60", "EA", "12.10", "", "VN", "PARA-650"],
    ["PID", "F", "", "", "", "Paracetamol 650 mg tablets"],
    ["CTT", "2"],
]

ASN_BODY = [
    ["BSN", "00", "SHP-88213", "20261125", "0930"],
    ["DTM", "011", "20261125"],
    ["HL", "1", "", "S"],
    ["TD1", "CTN", "4"],
    ["N1", "ST", "Pune Central Warehouse", "92", "PNQ-WH1"],
    ["HL", "2", "1", "O"],
    ["PRF", "4500012"],
    ["HL", "3", "2", "I"],
    ["LIN", "1", "VN", "AMOX-500"],
    ["SN1", "1", "120", "EA"],
    ["HL", "4", "2", "I"],
    ["LIN", "2", "VN", "PARA-650"],
    ["SN1", "2", "60", "EA"],
    ["CTT", "4"],
]

ACK_OK_BODY = [["AK1", "PO", "905"], ["AK2", "850", "0001"], ["AK5", "A"], ["AK9", "A", "1", "1", "1"]]
ACK_REJECT_BODY = [["AK1", "PO", "905"], ["AK2", "850", "0001"], ["AK3", "N1", "5", "", "3"],
                   ["AK5", "R", "5"], ["AK9", "R", "1", "1", "0"]]


def replace_seg(body, tag, new=None, nth=1):
    out, seen = [], 0
    for s in body:
        if s[0] == tag:
            seen += 1
            if seen == nth:
                if new is not None:
                    out.append(new)
                continue
        out.append(s)
    return out


# ---------------------------------------------------------------- EDIFACT -----------------------------------
def edifact(mtype: str, body: list[str], *, unt_delta=0, ref="1001", unz_ref="7701") -> str:
    head = [f"UNA:+.? '", f"UNB+UNOC:3+ACME01:ZZ+WHOLESALE02:ZZ+261124:1200+7701'"]
    msg = [f"UNH+{ref}+{mtype}:D:96A:UN'"] + body
    msg.append(f"UNT+{len(msg) + 1 + unt_delta}+{ref}'")
    return "\n".join(head + msg + [f"UNZ+1+{unz_ref}'"]) + "\n"


ORDERS_BODY = ["BGM+220+4500013+9'", "DTM+137:20261124:102'", "NAD+BY+ACME01::9'", "NAD+DP+PNQ-WH1::9'",
               "LIN+1++AMOX-500:VN'", "QTY+21:120'", "LIN+2++PARA-650:VN'", "QTY+21:60'", "UNS+S'"]
DESADV_BODY = ["BGM+351+SHP-88214+9'", "DTM+11:20261125:102'", "NAD+ST+PNQ-WH1::9'",
               "CPS+1'", "LIN+1++AMOX-500:VN'", "QTY+12:120'"]


# ---------------------------------------------------------------- EPCIS -------------------------------------
PREFIX, ITEM = "0614141", "107346"
SSCC = "urn:epc:id:sscc:0614141.1234567890"
SHIPPER, RECEIVER = "urn:epc:id:sgln:0614141.00001.0", "urn:epc:id:sgln:0614141.00777.0"


def sgtin(serial: str, prefix=PREFIX, item=ITEM) -> str:
    return f"urn:epc:id:sgtin:{prefix}.{item}.{serial}"


def epcis(units: list[str], *, children: list[str] | None = None, lot: str | None = "LOT2611A",
          expiry: str | None = "2028-06-30", tz="+05:30", owners=True, extra_commission: list[str] | None = None) -> str:
    def epc_list(urns):
        return "".join(f"<epc>{u}</epc>" for u in urns)

    ilmd = ""
    if lot or expiry:
        ilmd = "<extension><ilmd>"
        if lot:
            ilmd += f"<cbvmda:lotNumber>{lot}</cbvmda:lotNumber>"
        if expiry:
            ilmd += f"<cbvmda:itemExpirationDate>{expiry}</cbvmda:itemExpirationDate>"
        ilmd += "</ilmd></extension>"

    def commission(urns, t):
        return f"""
      <ObjectEvent>
        <eventTime>{t}</eventTime>
        <eventTimeZoneOffset>{tz}</eventTimeZoneOffset>
        <epcList>{epc_list(urns)}</epcList>
        <action>ADD</action>
        <bizStep>urn:epcglobal:cbv:bizstep:commissioning</bizStep>
        <disposition>urn:epcglobal:cbv:disp:active</disposition>
        <readPoint><id>urn:epc:id:sgln:0614141.00001.0</id></readPoint>
        <bizLocation><id>urn:epc:id:sgln:0614141.00001.0</id></bizLocation>
        {ilmd}
      </ObjectEvent>"""

    parties = ""
    if owners:
        parties = (f"<extension><sourceList><source type=\"urn:epcglobal:cbv:sdt:owning_party\">{SHIPPER}</source>"
                   f"</sourceList><destinationList><destination type=\"urn:epcglobal:cbv:sdt:owning_party\">"
                   f"{RECEIVER}</destination></destinationList></extension>")
    events = commission(units, "2026-11-20T04:30:00.000Z")
    if extra_commission:
        events += commission(extra_commission, "2026-11-20T04:35:00.000Z")
    events += f"""
      <AggregationEvent>
        <eventTime>2026-11-21T06:00:00.000Z</eventTime>
        <eventTimeZoneOffset>{tz}</eventTimeZoneOffset>
        <parentID>{SSCC}</parentID>
        <childEPCs>{epc_list(children if children is not None else units)}</childEPCs>
        <action>ADD</action>
        <bizStep>urn:epcglobal:cbv:bizstep:packing</bizStep>
        <disposition>urn:epcglobal:cbv:disp:in_progress</disposition>
        <bizLocation><id>urn:epc:id:sgln:0614141.00001.0</id></bizLocation>
      </AggregationEvent>
      <ObjectEvent>
        <eventTime>2026-11-22T09:15:00.000Z</eventTime>
        <eventTimeZoneOffset>{tz}</eventTimeZoneOffset>
        <epcList><epc>{SSCC}</epc></epcList>
        <action>OBSERVE</action>
        <bizStep>urn:epcglobal:cbv:bizstep:shipping</bizStep>
        <disposition>urn:epcglobal:cbv:disp:in_transit</disposition>
        <bizLocation><id>urn:epc:id:sgln:0614141.00001.0</id></bizLocation>
        <bizTransactionList>
          <bizTransaction type="urn:epcglobal:cbv:btt:po">urn:epcglobal:cbv:bt:0614141000013:4500012</bizTransaction>
        </bizTransactionList>
        {parties}
      </ObjectEvent>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:1" xmlns:cbvmda="urn:epcglobal:cbv:mda"
    schemaVersion="1.2" creationDate="2026-11-22T09:20:00.000Z">
  <EPCISBody>
    <EventList>{events}
    </EventList>
  </EPCISBody>
</epcis:EPCISDocument>
"""


UNITS = [sgtin(f"SN{n:05d}") for n in range(1, 6)]


# ---------------------------------------------------------------- certificates ------------------------------
def make_cert(path: Path, cn: str, not_before: dt.datetime, not_after: dt.datetime, key_size=2048) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Synthetic Partner")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(not_before).not_valid_after(not_after)
            .sign(key, hashes.SHA256()))
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def main() -> None:
    for d in (GOOD, BAD, LOGS, CERTS):
        d.mkdir(parents=True, exist_ok=True)
    w = lambda p, s: p.write_text(s, encoding="utf-8", newline="")  # noqa: E731

    # good
    w(GOOD / "po_850.edi", x12([("850", "0001", PO_BODY)]))
    w(GOOD / "asn_856.edi", x12([("856", "0002", ASN_BODY)], functional_id="SH"))
    w(GOOD / "ack_997.edi", x12([("997", "0003", ACK_OK_BODY)], functional_id="FA"))
    w(GOOD / "orders.edifact", edifact("ORDERS", ORDERS_BODY))
    w(GOOD / "desadv.edifact", edifact("DESADV", DESADV_BODY))
    w(GOOD / "epcis_shipment.xml", epcis(UNITS))
    w(GOOD / "inventory.csv", "gtin,lot,expiry_date,quantity,warehouse\n"
      "10614141073464,LOT2611A,2028-06-30,120,PNQ-WH1\n00614141999996,LOT2611B,2028-01-31,60,PNQ-WH1\n")

    # bad: X12
    w(BAD / "850_missing_shipto.edi", x12([("850", "0001", [s for s in PO_BODY if s[:2] != ["N1", "ST"]])]))
    w(BAD / "850_bad_counts.edi", x12([("850", "0001", replace_seg(PO_BODY, "CTT", ["CTT", "3"]))], se_count_delta=1))
    w(BAD / "850_negative_qty.edi", x12([("850", "0001", [
        ["BEG", "00", "SA", "4500012", "", "24/11/2026"] if s[0] == "BEG" else
        ["PO1", "1", "-120", "EA", "4.75", "", "VN", "AMOX-500"] if s[:2] == ["PO1", "1"] else s for s in PO_BODY])]))
    flat = x12([("850", "0001", PO_BODY)], usage="T", term="~")
    w(BAD / "850_test_flag_wrapped.edi", "\r\n".join(flat[i:i + 80] for i in range(0, len(flat), 80)) + "\r\n")
    w(BAD / "850_truncated.edi", x12([("850", "0001", PO_BODY[:7])], drop_trailers=True))
    hl_bad = replace_seg(ASN_BODY, "HL", ["HL", "4", "9", "I"], nth=4)
    w(BAD / "856_broken_hl.edi", x12([("856", "0002", [s for s in hl_bad if s[:2] != ["DTM", "011"]])], functional_id="SH"))
    w(BAD / "997_rejected.edi", x12([("997", "0003", ACK_REJECT_BODY)], functional_id="FA"))

    # bad: EDIFACT
    w(BAD / "orders_no_delivery.edifact", edifact("ORDERS", [s for s in ORDERS_BODY if not s.startswith("NAD+DP")], unt_delta=2))
    w(BAD / "contrl_rejected.edifact", edifact("CONTRL", ["UCI+7701+ACME01:ZZ+WHOLESALE02:ZZ+4'",
                                                          "UCM+1001+ORDERS:D:96A:UN+4+12'"]))

    # bad: EPCIS
    good_xml = epcis(UNITS)
    w(BAD / "epcis_malformed.xml", good_xml.replace("</eventTimeZoneOffset>", "</eventTimeZoneOfset>", 1))
    w(BAD / "epcis_duplicate_serial.xml", epcis(UNITS, extra_commission=[UNITS[2]]))
    w(BAD / "epcis_aggregation_mismatch.xml", epcis(UNITS, children=UNITS + [sgtin("SN09999")]))
    w(BAD / "epcis_missing_lot_expiry.xml", epcis(UNITS, lot=None, expiry=None, tz="IST"))
    w(BAD / "epcis_no_owner.xml", epcis(UNITS, owners=False))
    w(BAD / "epcis_bad_sgtin.xml", epcis(UNITS[:4] + [sgtin("SN00005", item="1073460")]))
    w(BAD / "epcis_expired.xml", epcis(UNITS, expiry="2025-12-31"))
    (BAD / "epcis_bom.xml").write_bytes(b"\xef\xbb\xbf" + good_xml.encode())

    # bad: CSV
    w(BAD / "inventory_bad.csv", "gtin,lot,expiry_date,quantity,warehouse\n"
      "10614141073465,LOT2611A,2028-06-30,120,PNQ-WH1\n"
      "00614141999996,,31/01/2028,sixty,PNQ-WH1\n"
      "10614141073464,LOT2611C,2028-03-31,40,Pune, Central\n")
    w(BAD / "inventory_semicolon.csv", "gtin;lot;expiry_date;quantity\n10614141073464;LOT2611A;2028-06-30;120\n")

    # logs for `pdoc trace`
    w(LOGS / "ingest.jsonl", "\n".join([
        '{"@timestamp":"2026-11-24T12:01:03.120Z","level":"INFO","txn_id":"TXN-2026-000182","event":"received","message":"file PO_182.edi via SFTP partner=ACME01"}',
        '{"@timestamp":"2026-11-24T12:01:03.480Z","level":"INFO","txn_id":"TXN-2026-000182","event":"validated","message":"X12 850 passed 0 errors"}',
        '{"@timestamp":"2026-11-24T12:01:04.010Z","level":"INFO","txn_id":"TXN-2026-000183","event":"received","message":"file PO_183.edi via AS2"}',
        '{"@timestamp":"2026-11-24T12:01:04.900Z","level":"INFO","txn_id":"TXN-2026-000182","event":"transformed","message":"canonical order 4500012 built"}',
    ]) + "\n")
    w(LOGS / "processor.log", "\n".join([
        "2026-11-24T12:01:05.000Z INFO  [TXN-2026-000182] processing started; calling order-service",
        "2026-11-24T12:01:35.010Z ERROR [TXN-2026-000182] downstream_client.py:142 ConnectionTimeout: 30s exceeded",
        "2026-11-24T12:01:35.020Z WARN  [TXN-2026-000182] retry 1 of 2 scheduled",
        "2026-11-24T12:02:05.030Z ERROR [TXN-2026-000182] downstream_client.py:142 ConnectionTimeout: 30s exceeded",
        "2026-11-24T12:02:05.040Z WARN  [TXN-2026-000182] retry 2 of 2 scheduled",
        "2026-11-24T12:02:35.050Z ERROR [TXN-2026-000182] FAILED after 2 retries: ConnectionTimeout",
        "2026-11-24T12:01:06.000Z INFO  [TXN-2026-000183] processing started; calling order-service",
        "2026-11-24T12:01:06.400Z INFO  [TXN-2026-000183] stored; 997 sent to partner",
    ]) + "\n")

    # AS2 certificates (dates relative to today, so regenerate before a demo) and MDNs
    now = dt.datetime.now(dt.timezone.utc)
    make_cert(CERTS / "partner_valid.pem", "as2.partner-a.example", now - dt.timedelta(days=200), now + dt.timedelta(days=500))
    make_cert(CERTS / "partner_expiring.pem", "as2.partner-b.example", now - dt.timedelta(days=345), now + dt.timedelta(days=20))
    make_cert(CERTS / "partner_expired.pem", "as2.partner-c.example", now - dt.timedelta(days=400), now - dt.timedelta(days=3))
    w(CERTS / "mdn_processed.txt", "Reporting-UA: wholesale02-as2\r\nOriginal-Recipient: rfc822; WHOLESALE02\r\n"
      "Final-Recipient: rfc822; WHOLESALE02\r\nOriginal-Message-ID: <TXN-2026-000183@acme01>\r\n"
      "Received-Content-MIC: 7v7F++fQaNqf5kAacO3TGaEyXq0=, sha1\r\nDisposition: automatic-action/MDN-sent-automatically; processed\r\n")
    w(CERTS / "mdn_failed.txt", "Reporting-UA: wholesale02-as2\r\nOriginal-Recipient: rfc822; WHOLESALE02\r\n"
      "Final-Recipient: rfc822; WHOLESALE02\r\nOriginal-Message-ID: <TXN-2026-000190@acme01>\r\n"
      "Disposition: automatic-action/MDN-sent-automatically; processed/error: decryption-failed\r\n")
    print(f"samples written to {ROOT}")


if __name__ == "__main__":
    main()
