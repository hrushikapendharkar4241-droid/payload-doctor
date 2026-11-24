"""AS2 helpers: certificate health and MDN (Message Disposition Notification) reading."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa

from .models import CheckResult
from .rules import hit


def _days(delta) -> str:
    n = delta.days
    return f"{n} day" if n == 1 else f"{n} days"


def load_cert(path: Path) -> x509.Certificate:
    data = path.read_bytes()
    if b"-----BEGIN CERTIFICATE-----" in data:
        return x509.load_pem_x509_certificate(data)
    return x509.load_der_x509_certificate(data)


def check_cert(path: Path, now: datetime | None = None) -> CheckResult:
    now = now or datetime.now(timezone.utc)
    cert = load_cert(path)
    start, end = cert.not_valid_before_utc, cert.not_valid_after_utc
    days_left = (end - now).days
    subject = cert.subject.rfc4514_string()
    status = f"{_days(end - now)} left" if end >= now else f"EXPIRED {_days(now - end)} ago"
    summary = f"AS2 certificate {subject}; valid {start:%Y-%m-%d} to {end:%Y-%m-%d} ({status})"
    result = CheckResult(str(path), "as2-certificate", summary)
    if end < now:
        result.findings.append(hit("AS2-001", f"expired on {end:%Y-%m-%d %H:%M} UTC ({_days(now - end)} ago)"))
    elif days_left <= 30:
        result.findings.append(hit("AS2-002", f"expires on {end:%Y-%m-%d} ({_days(end - now)} left)"))
    if start > now:
        result.findings.append(hit("AS2-006", f"valid only from {start:%Y-%m-%d %H:%M} UTC"))
    key = cert.public_key()
    if isinstance(key, rsa.RSAPublicKey) and key.key_size < 2048:
        result.findings.append(hit("AS2-003", f"RSA key is {key.key_size} bits"))
    if isinstance(cert.signature_hash_algorithm, hashes.SHA1):
        result.findings.append(hit("AS2-004", "signature algorithm is SHA-1"))
    if cert.issuer == cert.subject:
        result.findings.append(hit("AS2-005", "issuer and subject are the same"))
    return result


DISP_RE = re.compile(r"^Disposition:\s*(.+)$", re.I | re.M)


def check_mdn(path: Path) -> CheckResult:
    text = path.read_text(errors="replace")
    result = CheckResult(str(path), "as2-mdn")
    m = DISP_RE.search(text)
    if not m:
        result.summary = "MDN: no Disposition header found"
        result.findings.append(hit("AS2-008", "no 'Disposition:' line in the file"))
        return result
    disposition = " ".join(m.group(1).split())
    orig = re.search(r"^Original-Message-ID:\s*(.+)$", text, re.I | re.M)
    result.summary = f"MDN for {orig.group(1).strip() if orig else 'unknown message'}: {disposition}"
    if re.search(r"(failed|error|failure)", disposition, re.I):
        result.findings.append(hit("AS2-007", f"disposition is '{disposition}'"))
    return result
