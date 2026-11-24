#!/usr/bin/env bash
# pdoc-batch.sh - check every payload in a folder and print a one-line summary per file.
# Designed for cron: exits 1 if any file has errors, and can move failures to a quarantine folder.
#
# Usage: pdoc-batch.sh INBOX_DIR [QUARANTINE_DIR]
#   */15 * * * * /opt/payload-doctor/scripts/pdoc-batch.sh /data/inbox /data/quarantine >> /var/log/pdoc-batch.log 2>&1
set -euo pipefail

inbox="${1:?usage: pdoc-batch.sh INBOX_DIR [QUARANTINE_DIR]}"
quarantine="${2:-}"
command -v pdoc >/dev/null || { echo "pdoc not found; pip install payload-doctor" >&2; exit 3; }
command -v jq   >/dev/null || { echo "jq not found; install jq" >&2; exit 3; }

status=0
shopt -s nullglob
for f in "$inbox"/*; do
  [[ -f "$f" ]] || continue
  json=$(pdoc check --json "$f" || true)
  errors=$(jq -r '.errors' <<<"$json")
  warnings=$(jq -r '.warnings' <<<"$json")
  rules=$(jq -r '[.findings[].rule] | unique | join(",")' <<<"$json")
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if [[ "$errors" -gt 0 ]]; then
    echo "$ts FAIL  $f errors=$errors warnings=$warnings rules=$rules"
    status=1
    if [[ -n "$quarantine" ]]; then mkdir -p "$quarantine" && mv "$f" "$quarantine/"; fi
  elif [[ "$warnings" -gt 0 ]]; then
    echo "$ts WARN  $f warnings=$warnings rules=$rules"
  else
    echo "$ts OK    $f"
  fi
done
exit "$status"
