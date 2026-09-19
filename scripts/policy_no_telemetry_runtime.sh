#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="$ROOT_DIR/phios"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "Policy error: phios runtime directory is missing; refusing to skip scan."
  exit 2
fi

patterns=(
  "telemetry"
  "analytics"
  "segment"
  "mixpanel"
  "amplitude"
  "posthog"
  "ga4"
  "google-analytics"
)

joined="$(IFS='|'; echo "${patterns[*]}")"

if command -v rg >/dev/null 2>&1; then
  if rg -n -i --glob '!docs/**' --glob '!MANIFESTO/**' "$joined" "$TARGET_DIR"; then
    echo "Policy violation: tracking-related term found in runtime code under phios/."
    exit 1
  fi
elif command -v grep >/dev/null 2>&1; then
  set +e
  grep -RniE --exclude-dir='__pycache__' "$joined" "$TARGET_DIR"
  grep_status=$?
  set -e
  if [[ $grep_status -eq 0 ]]; then
    echo "Policy violation: tracking-related term found in runtime code under phios/."
    exit 1
  fi
  if [[ $grep_status -ne 1 ]]; then
    echo "Policy error: fallback grep scan failed."
    exit 2
  fi
else
  echo "Policy error: neither rg nor grep is available; refusing a false-green scan."
  exit 2
fi

echo "Policy check passed: no tracking-related runtime terms found."
