"""Parsers, GS1 helpers, trace, diff, AS2 checks and the CLI."""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pdoc.as2check import check_cert, check_mdn
from pdoc.cli import app
from pdoc.diff import diff
from pdoc.gs1 import check_digit, gtin_valid, parse_epc
from pdoc.parsers import edifact, x12
from pdoc.trace import summarise, trace

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
sys.path.insert(0, str(ROOT / "scripts"))
from make_samples import make_cert  # noqa: E402

runner = CliRunner()


# ---- GS1 --------------------------------------------------------------------------------------
@pytest.mark.parametrize("gtin,ok", [("10614141073464", True), ("10614141073465", False),
                                     ("4006381333931", True), ("400638133393", False), ("abc", False)])
def test_gtin_valid(gtin, ok):
    assert gtin_valid(gtin) is ok


def test_check_digit():
    assert check_digit("1061414107346") == 4


def test_parse_sgtin_rebuilds_gtin():
    epc = parse_epc("urn:epc:id:sgtin:0614141.107346.SN1")
    assert epc.gtin == "10614141073464" and epc.serial == "SN1" and epc.error is None


@pytest.mark.parametrize("urn", ["urn:epc:id:sgtin:0614141.1073460.1", "urn:epc:id:sgtin:06141A1.107346.1",
                                 "urn:epc:id:sgtin:0614141.107346." + "9" * 21, "urn:epc:id:sscc:0614141.12",
                                 "SN0001"])
def test_parse_epc_errors(urn):
    assert parse_epc(urn).error


# ---- parsers ----------------------------------------------------------------------------------
def test_x12_reads_delimiters_from_isa():
    text = (SAMPLES / "good" / "po_850.edi").read_text()
    ic = x12.parse(text.replace("*", "|"))
    assert ic.element_sep == "|" and ic.segments[3].tag == "BEG"


def test_x12_short_isa():
    with pytest.raises(x12.X12ParseError):
        x12.parse("ISA*00*short~")


def test_edifact_release_character():
    ic = edifact.parse("UNB+UNOC:3+A+B+261124:1200+1'UNH+1+ORDERS:D:96A:UN'FTX+AAI+++Price 10?+5?% off?'s'UNT+3+1'UNZ+1+1'")
    ftx = ic.find("FTX")[0]
    assert ftx.el(4) == "Price 10+5% off's"


def test_edifact_unterminated():
    with pytest.raises(edifact.EdifactParseError):
        edifact.parse("UNB+UNOC:3+A+B+261124:1200+1'UNH+1")


# ---- trace ------------------------------------------------------------------------------------
def test_trace_merges_json_and_text_logs():
    events = trace("TXN-2026-000182", [SAMPLES / "logs"])
    assert len(events) == 9
    assert events[0].source == "ingest.jsonl:1"
    s = summarise(events)
    assert s["status"] == "FAILED" and s["retries"] == 2 and s["errors"] == 3
    assert "ConnectionTimeout" in s["last_error"]


def test_trace_success_and_missing():
    assert summarise(trace("TXN-2026-000183", [SAMPLES / "logs"]))["status"] == "OK"
    assert summarise(trace("TXN-NOPE", [SAMPLES / "logs"]))["status"] == "NOT FOUND"


# ---- diff -------------------------------------------------------------------------------------
def test_diff_x12_element_level():
    fmt, changes = diff((SAMPLES / "good" / "po_850.edi").read_bytes(), (SAMPLES / "bad" / "850_negative_qty.edi").read_bytes())
    assert fmt == "x12"
    assert {(c.location, c.old, c.new) for c in changes} == {
        ("segment 4 BEG05", "20261124", "24/11/2026"), ("segment 11 PO102", "120", "-120")}


def test_diff_xml_paths():
    fmt, changes = diff((SAMPLES / "good" / "epcis_shipment.xml").read_bytes(),
                        (SAMPLES / "bad" / "epcis_no_owner.xml").read_bytes())
    assert fmt == "xml" and changes and all(c.kind == "removed" for c in changes)


def test_diff_identical_and_format_mismatch():
    data = (SAMPLES / "good" / "orders.edifact").read_bytes()
    assert diff(data, data)[1] == []
    assert diff(data, (SAMPLES / "good" / "po_850.edi").read_bytes())[0] == "edifact vs x12"


# ---- AS2 --------------------------------------------------------------------------------------
NOW = dt.datetime(2026, 11, 24, 12, 0, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("start,end,expected", [
    (-100, 400, {"AS2-005"}),
    (-100, 10, {"AS2-002", "AS2-005"}),
    (-400, -2, {"AS2-001", "AS2-005"}),
    (5, 400, {"AS2-006", "AS2-005"}),
])
def test_cert_checks(tmp_path, start, end, expected):
    pem = tmp_path / "c.pem"
    make_cert(pem, "t", NOW + dt.timedelta(days=start), NOW + dt.timedelta(days=end))
    assert {f.rule.id for f in check_cert(pem, now=NOW).findings} == expected


def test_mdn():
    assert check_mdn(SAMPLES / "certs" / "mdn_processed.txt").findings == []
    assert [f.rule.id for f in check_mdn(SAMPLES / "certs" / "mdn_failed.txt").findings] == ["AS2-007"]


def test_mdn_unreadable(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("hello")
    assert [f.rule.id for f in check_mdn(p).findings] == ["AS2-008"]


# ---- CLI --------------------------------------------------------------------------------------
def test_cli_check_json_and_exit_code():
    r = runner.invoke(app, ["check", "--json", str(SAMPLES / "bad" / "850_missing_shipto.edi")])
    assert r.exit_code == 1
    assert json.loads(r.stdout)["findings"][0]["rule"] == "X12-014"


def test_cli_check_folder():
    r = runner.invoke(app, ["check", "-b", str(SAMPLES / "good")])
    assert r.exit_code == 0 and "7 file(s) checked, 0 with errors" in r.stdout


def test_cli_trace_diff_rules():
    assert runner.invoke(app, ["trace", "TXN-2026-000183", str(SAMPLES / "logs")]).exit_code == 0
    assert runner.invoke(app, ["diff", str(SAMPLES / "good" / "po_850.edi"), str(SAMPLES / "good" / "po_850.edi")]).exit_code == 0
    r = runner.invoke(app, ["rules", "--markdown"])
    assert r.exit_code == 0 and "### X12-014" in r.stdout


def test_cli_missing_file():
    assert runner.invoke(app, ["check", "nope.edi"]).exit_code == 3


def test_diff_csv_cells():
    fmt, changes = diff((SAMPLES / "good" / "inventory.csv").read_bytes(), (SAMPLES / "bad" / "inventory_bad.csv").read_bytes())
    assert fmt == "csv"
    assert ("line 3, quantity", "60", "sixty") in {(c.location, c.old, c.new) for c in changes}
    assert any(c.kind == "added" for c in changes)


def test_cli_human_output_explains_fix():
    r = runner.invoke(app, ["check", str(SAMPLES / "bad" / "850_missing_shipto.edi")])
    assert "Why it matters" in r.stdout and "Fix:" in r.stdout and "X12-014" in r.stdout


def test_trace_status_ignores_info_after_failure_and_detects_recovery(tmp_path):
    log = tmp_path / "a.jsonl"
    log.write_text(
        '{"@timestamp":"2026-11-24T10:00:00Z","level":"ERROR","txn_id":"TXN-A","event":"failed","message":"timeout"}\n'
        '{"@timestamp":"2026-11-24T10:00:01Z","level":"WARNING","txn_id":"TXN-A","event":"incident_opened","message":"INC-1"}\n'
        '{"@timestamp":"2026-11-24T10:00:00Z","level":"ERROR","txn_id":"TXN-B","event":"delivery_error","message":"timeout"}\n'
        '{"@timestamp":"2026-11-24T10:00:05Z","level":"INFO","txn_id":"TXN-B","event":"delivered","message":"HTTP 201"}\n')
    assert summarise(trace("TXN-A", [log]))["status"] == "FAILED"
    assert summarise(trace("TXN-B", [log]))["status"] == "RECOVERED"
