"""Payload Doctor: plain-English diagnostics for failed B2B payloads."""
__version__ = "0.1.0"

from .engine import check_bytes, check_file, detect  # noqa: E402,F401
