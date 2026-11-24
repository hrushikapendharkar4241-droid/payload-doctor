"""Every sample file must trigger exactly the rules it was built to demonstrate."""
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from pdoc.engine import check_bytes, check_file, detect
from pdoc.rules import all_rules, epcis_rules

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
FIXED_TODAY = date(2026, 11, 24)
FIXED_NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)

EXPECTED = {
    "850_bad_counts.edi": {"X12-007", "X12-017"},
    "850_missing_shipto.edi": {"X12-014"},
    "850_negative_qty.edi": {"X12-018", "X12-019"},
    "850_test_flag_wrapped.edi": {"X12-009", "X12-012"},
    "850_truncated.edi": {"X12-010"},
    "856_broken_hl.edi": {"X12-021", "X12-023"},
    "997_rejected.edi": {"X12-025"},
    "contrl_rejected.edifact": {"EDI-011"},
    "orders_no_delivery.edifact": {"EDI-004", "EDI-007"},
    "epcis_aggregation_mismatch.xml": {"EPC-005"},
    "epcis_bad_sgtin.xml": {"EPC-003"},
    "epcis_bom.xml": {"GEN-001"},
    "epcis_duplicate_serial.xml": {"EPC-004"},
    "epcis_expired.xml": {"EPC-008"},
    "epcis_malformed.xml": {"XML-001"},
    "epcis_missing_lot_expiry.xml": {"EPC-006", "EPC-010"},
    "epcis_no_owner.xml": {"EPC-009"},
    "inventory_bad.csv": {"CSV-002", "CSV-003", "CSV-004", "CSV-005", "CSV-006"},
    "inventory_semicolon.csv": {"CSV-007"},
}


@pytest.mark.parametrize("name,rules", sorted(EXPECTED.items()))
def test_bad_sample_triggers_expected_rules(name, rules):
    result = check_file(SAMPLES / "bad" / name)
    assert {f.rule.id for f in result.findings} == rules


@pytest.mark.parametrize("path", sorted((SAMPLES / "good").iterdir()), ids=lambda p: p.name)
def test_good_samples_are_clean(path):
    result = check_file(path)
    assert result.findings == [], [f.to_dict() for f in result.findings]
    assert result.exit_code == 0


def test_every_bad_sample_has_an_expectation():
    assert {p.name for p in (SAMPLES / "bad").iterdir()} == set(EXPECTED)


def test_rule_catalogue_is_complete_and_unique():
    rules = all_rules()
    assert len(rules) >= 20
    assert len({r.id for r in rules}) == len(rules)
    for r in rules:
        assert r.severity in ("error", "warning", "info")
        assert r.why and r.cause and r.fix


@pytest.mark.parametrize("data,fmt", [
    (b"ISA*00*", "x12"), (b"UNA:+.? 'UNB+", "edifact"), (b"UNB+UNOC", "edifact"),
    (b"<?xml version='1.0'?><a/>", "xml"), (b"\xef\xbb\xbf<a/>", "xml"),
    (b"a,b,c\n1,2,3\n", "csv"), (b"", "empty"), (b"   \n", "empty"), (b"%PDF-1.7 binary", "unknown"),
])
def test_detect(data, fmt):
    assert detect(data) == fmt


def test_empty_and_unknown_files():
    assert [f.rule.id for f in check_bytes(b"").findings] == ["GEN-003"]
    assert [f.rule.id for f in check_bytes(b"%PDF-1.7").findings] == ["GEN-002"]


def test_invalid_utf8_csv():
    result = check_bytes(b"gtin,qty\n10614141073464,5\nCaf\xe9,1\n")
    assert "GEN-004" in {f.rule.id for f in result.findings}


def test_exit_codes():
    assert check_file(SAMPLES / "bad" / "850_missing_shipto.edi").exit_code == 1
    assert check_file(SAMPLES / "bad" / "inventory_semicolon.csv").exit_code == 2
    assert check_file(SAMPLES / "good" / "po_850.edi").exit_code == 0


def test_epcis_time_checks_with_fixed_clock():
    xml = (SAMPLES / "good" / "epcis_shipment.xml").read_bytes()
    root = epcis_rules.parse(xml)
    assert epcis_rules.check(root, today=FIXED_TODAY, now=FIXED_NOW) == []
    # The same events checked "before" they happened are reported as future-dated.
    early = datetime(2026, 11, 1, tzinfo=timezone.utc)
    ids = {f.rule.id for f in epcis_rules.check(root, today=FIXED_TODAY, now=early)}
    assert ids == {"EPC-011"}


def test_epcis_wrong_namespace():
    result = check_bytes(b'<EPCISDocument xmlns="https://ref.gs1.org/standards/epcis/2.0.0/"/>')
    assert [f.rule.id for f in result.findings] == ["EPC-001"]


def test_epcis_no_events():
    xml = b'<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:1"><EPCISBody><EventList/></EPCISBody></epcis:EPCISDocument>'
    assert [f.rule.id for f in check_bytes(xml).findings] == ["EPC-012"]


def test_xml_external_entities_are_not_resolved(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    xml = (f'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file://{secret}">]>'
           f'<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:1"><EPCISBody><EventList>'
           f'<ObjectEvent><eventTime>&x;</eventTime></ObjectEvent></EventList></EPCISBody></epcis:EPCISDocument>')
    result = check_bytes(xml.encode())
    assert "TOP-SECRET" not in str(result.to_dict())
