#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="$ROOT_DIR/phios"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "No phios runtime directory found; skipping policy scan."
  exit 0
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
if rg -n -i --glob '!docs/**' --glob '!MANIFESTO/**' "$joined" "$TARGET_DIR"; then
  echo "Policy violation: tracking-related term found in runtime code under phios/."
  exit 1
fi

echo "Policy check passed: no tracking-related runtime terms found."
