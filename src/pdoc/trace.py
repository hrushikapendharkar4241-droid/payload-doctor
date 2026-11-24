"""Follow one transaction ID across log files and build its timeline."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

TS_RE = re.compile(r"^\[?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\]?\s*")
LEVEL_RE = re.compile(r"^(DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|CRITICAL|FATAL)\b[:\s-]*", re.I)
LOG_SUFFIXES = {".log", ".jsonl", ".json", ".txt", ".out"}
SUCCESS_RE = re.compile(r"\b(processed|delivered|succeeded|success|completed|accepted|stored)\b", re.I)


@dataclass
class TraceEvent:
    when: datetime | None
    raw_time: str
    level: str
    message: str
    source: str
    fields: dict

    @property
    def is_error(self) -> bool:
        return self.level in ("ERROR", "CRITICAL", "FATAL")


def _parse_time(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00").replace(",", "."))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _from_json(obj: dict, source: str) -> TraceEvent:
    raw = str(obj.get("@timestamp") or obj.get("timestamp") or obj.get("ts") or obj.get("time") or "")
    level = str(obj.get("level") or obj.get("severity") or obj.get("log.level") or "INFO").upper()
    event = obj.get("event") or obj.get("stage") or obj.get("step") or ""
    msg = obj.get("message") or obj.get("msg") or ""
    text = f"{event}: {msg}" if event and msg else str(event or msg)
    extra = {k: v for k, v in obj.items() if k not in {"@timestamp", "timestamp", "ts", "time", "level",
                                                         "severity", "log.level", "event", "stage", "step",
                                                         "message", "msg"}}
    return TraceEvent(_parse_time(raw), raw, "WARNING" if level == "WARN" else level, text, source, extra)


def _from_text(line: str, source: str) -> TraceEvent:
    raw, rest = "", line
    m = TS_RE.match(line)
    if m:
        raw, rest = m.group(1), line[m.end():]
    level = "INFO"
    m = LEVEL_RE.match(rest)
    if m:
        level, rest = m.group(1).upper(), rest[m.end():]
    if level == "WARN":
        level = "WARNING"
    return TraceEvent(_parse_time(raw) if raw else None, raw, level, rest.strip(), source, {})


def iter_files(paths: list[Path]):
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and (f.suffix in LOG_SUFFIXES or not f.suffix):
                    yield f
        elif p.is_file():
            yield p


def trace(txn_id: str, paths: list[Path]) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for f in iter_files(paths):
        with f.open(errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if txn_id not in line:
                    continue
                line = line.rstrip("\n").replace(f"[{txn_id}] ", "")
                source = f"{f.name}:{n}"
                stripped = line.strip()
                if stripped.startswith("{"):
                    try:
                        events.append(_from_json(json.loads(stripped), source))
                        continue
                    except json.JSONDecodeError:
                        pass
                events.append(_from_text(line, source))
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    events.sort(key=lambda e: e.when or far_future)
    return events


def summarise(events: list[TraceEvent]) -> dict:
    if not events:
        return {"status": "NOT FOUND", "events": 0}
    retries = sum(1 for e in events if re.search(r"\bretry\b\s*(#|\d|attempt|scheduled|:)", e.message, re.I))
    errors = [e for e in events if e.is_error]
    last = events[-1]
    # The outcome is decided by the latest decisive line: an error, or a success marker.
    # Informational lines after a failure (e.g. "incident opened") do not hide it.
    decisive = [e for e in events if e.is_error or SUCCESS_RE.search(e.message)]
    if not errors:
        status = "OK"
    elif decisive and decisive[-1].is_error:
        status = "FAILED"
    else:
        status = "RECOVERED"
    first_t, last_t = events[0].when, last.when
    duration = (last_t - first_t).total_seconds() if first_t and last_t else None
    return {
        "status": status,
        "events": len(events),
        "errors": len(errors),
        "retries": retries,
        "first_seen": events[0].raw_time,
        "last_seen": last.raw_time,
        "duration_seconds": duration,
        "last_error": errors[-1].message if errors else None,
        "last_error_source": errors[-1].source if errors else None,
    }
