#!/usr/bin/env bash
set -euo pipefail

# Operator helper for advisory rollout workflows.
# Does not change adapters automatically.

MODE="${1:-shadow}"
REPORT_DIR="${2:-./kernel-rollout-artifacts}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$REPORT_DIR"

run_shadow() {
  export PHIOS_KERNEL_ENABLED=true
  export PHIOS_KERNEL_ADAPTER=legacy
  export PHIOS_KERNEL_SHADOW_ADAPTER=tiekat_v50
  export PHIOS_KERNEL_COMPARE_MODE=true

  phi eval-kernel --compare legacy tiekat_v50 --report "$REPORT_DIR/report.shadow.$TIMESTAMP.json" --json
  phi review-kernel-rollout --adapter legacy --markdown "$REPORT_DIR/review.shadow.$TIMESTAMP.md" --json
}

run_promoted() {
  export PHIOS_KERNEL_ENABLED=true
  export PHIOS_KERNEL_ADAPTER=tiekat_v50
  export PHIOS_KERNEL_SHADOW_ADAPTER=legacy
  export PHIOS_KERNEL_COMPARE_MODE=true

  phi eval-kernel --compare tiekat_v50 legacy --report "$REPORT_DIR/report.promoted.$TIMESTAMP.json" --json
  phi review-kernel-rollout --adapter tiekat_v50 --markdown "$REPORT_DIR/review.promoted.$TIMESTAMP.md" --json
}

run_rollback() {
  export PHIOS_KERNEL_ENABLED=true
  export PHIOS_KERNEL_ADAPTER=legacy
  export PHIOS_KERNEL_SHADOW_ADAPTER=tiekat_v50
  export PHIOS_KERNEL_COMPARE_MODE=true

  phi eval-kernel --compare legacy tiekat_v50 --report "$REPORT_DIR/report.rollback.$TIMESTAMP.json" --json
  phi review-kernel-rollout --adapter legacy --markdown "$REPORT_DIR/review.rollback.$TIMESTAMP.md" --json
}

case "$MODE" in
  shadow)
    run_shadow
    ;;
  promoted)
    run_promoted
    ;;
  rollback)
    run_rollback
    ;;
  *)
    echo "Usage: $0 [shadow|promoted|rollback] [report_dir]" >&2
    exit 2
    ;;
esac

printf "\nArtifacts written under: %s\n" "$REPORT_DIR"
