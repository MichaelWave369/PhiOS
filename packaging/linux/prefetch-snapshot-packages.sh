#!/usr/bin/env bash
# Download pinned Arch snapshot packages before attempting installation.
# Package signatures and exact snapshot mirror remain enforced by pacman.
# Only transport errors are retried; no mirror fallback or signature bypass.
phios_prefetch_snapshot_packages() {
    if [[ $# -lt 1 ]]; then
        echo 'PHIOS_ARCH_PREFETCH_REFUSED: no package names supplied' >&2
        return 2
    fi
    local attempt status
    for attempt in 1 2 3; do
        echo "PHIOS_ARCH_PREFETCH_ATTEMPT: ${attempt}/3 (pinned archive; signed packages)"
        # --disable-download-timeout avoids pacman's 10-second low-throughput
        # threshold, while GNU timeout keeps each attempt strictly bounded.
        # -Sw downloads packages and dependencies, but does NOT install them.
        if timeout --signal=TERM --kill-after=15s 600s \
            pacman --disable-download-timeout -Sw --needed --noconfirm "$@"; then
            echo "PHIOS_ARCH_PREFETCH_OK: attempt ${attempt}/3"
            return 0
        else
            status=$?
            echo "PHIOS_ARCH_PREFETCH_RETRY: attempt=${attempt}/3 exit=${status}" >&2
        fi
        if [[ $attempt -lt 3 ]]; then
            sleep 5
        fi
    done
    echo 'PHIOS_ARCH_PREFETCH_FAILED: all 3 attempts failed; signed image build HELD' >&2
    return 1
}
