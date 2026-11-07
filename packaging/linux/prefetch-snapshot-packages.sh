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

# Download all packages required for the full *pinned snapshot* upgrade before
# allowing one installation transaction. -w / --downloadonly forbids installs.
# The whole snapshot (including eligible downgrades) is selected by -uu.
# Retrying this transport-only stage is safe; never retry a partially applied
# upgrade, disable package signatures, or change the reviewed mirror.
phios_prefetch_snapshot_upgrade() {
    local attempt status
    for attempt in 1 2 3; do
        echo "PHIOS_ARCH_UPGRADE_PREFETCH_ATTEMPT: ${attempt}/3 (pinned archive; no installation)"
        if timeout --signal=TERM --kill-after=15s 600s \
            pacman --disable-download-timeout -Syyuu --downloadonly --noconfirm; then
            echo "PHIOS_ARCH_UPGRADE_PREFETCH_OK: attempt ${attempt}/3"
            return 0
        else
            status=$?
            echo "PHIOS_ARCH_UPGRADE_PREFETCH_RETRY: attempt=${attempt}/3 exit=${status}" >&2
        fi
        if [[ $attempt -lt 3 ]]; then
            sleep 5
        fi
    done
    echo 'PHIOS_ARCH_UPGRADE_PREFETCH_FAILED: signed pinned-snapshot prefetch exhausted; image build HELD' >&2
    return 1
}



# Warm the exact package cache used by mkarchiso's separate pacstrap step.
# Builder prefetch is insufficient: pacstrap installs a fresh airootfs and
# needs packages already installed on the builder. No --needed here.
phios_prefetch_archiso_profile_packages() {
    if [[ $# -ne 2 || ! -f $1 || ! -f $2 ]]; then
        echo 'PHIOS_ARCHISO_PREFETCH_REFUSED: profile config and package file required' >&2
        return 2
    fi
    local profile_config=$1 package_file=$2 package attempt status
    local -a packages=()
    while IFS= read -r package || [[ -n $package ]]; do
        [[ -z $package || $package == \#* ]] && continue
        if [[ ! $package =~ ^[a-zA-Z0-9@._+-]+$ ]]; then
            echo 'PHIOS_ARCHISO_PREFETCH_REFUSED: invalid package token' >&2
            return 2
        fi
        packages+=("$package")
    done < "$package_file"
    if (( ${#packages[@]} == 0 )); then
        echo 'PHIOS_ARCHISO_PREFETCH_REFUSED: empty profile package list' >&2
        return 2
    fi
    # mkarchiso shares the system cache unless profile CacheDir differs.
    local builder_cache profile_cache
    builder_cache=$(pacman-conf CacheDir) || return 2
    profile_cache=$(pacman-conf --config "$profile_config" CacheDir) || return 2
    if [[ $builder_cache != "$profile_cache" ]]; then
        echo 'PHIOS_ARCHISO_PREFETCH_REFUSED: profile and builder cache differ' >&2
        return 2
    fi
    for attempt in 1 2 3; do
        echo "PHIOS_ARCHISO_PREFETCH_ATTEMPT: ${attempt}/3 (exact profile, signed archive)"
        # -Syw downloads but never installs; the profile pins the snapshot.
        # Retain verified cache across three bounded attempts. No mirror
        # fallback, signature bypass, or retry of a partial installation.
        if timeout --signal=TERM --kill-after=15s 600s \
            pacman --config "$profile_config" --disable-download-timeout \
            -Syw --noconfirm "${packages[@]}"; then
            echo "PHIOS_ARCHISO_PREFETCH_OK: attempt ${attempt}/3"
            return 0
        else
            status=$?
            echo "PHIOS_ARCHISO_PREFETCH_RETRY: attempt=${attempt}/3 exit=${status}" >&2
        fi
        [[ $attempt -lt 3 ]] && sleep 5
    done
    echo 'PHIOS_ARCHISO_PREFETCH_FAILED: pinned profile packages unavailable; normal ISO HELD' >&2
    return 1
}
