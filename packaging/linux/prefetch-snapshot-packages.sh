#!/usr/bin/env bash
# Download pinned Arch snapshot packages before attempting installation.
# Package signatures and exact snapshot mirror remain enforced by pacman.
# Only transfer errors are retried; the builder pins two Arch-operated
# historical archive hosts to the same dated snapshot. No current mirror or signature bypass.
# If the pinned archive repeatedly refuses libalpm's 10-second connection
# window, use pacman's documented XferCommand for download-only retries.
# This retains the exact original repositories, trust keys and SigLevel.
phios_make_pinned_archive_curl_config() {
    if [[ $# -ne 1 ]]; then
        echo 'PHIOS_ARCH_CURL_PREFETCH_REFUSED: output config required' >&2
        return 2
    fi
    local output=$1
    local source_config=${PHIOS_PREFETCH_PACMAN_CONFIG:-/etc/pacman.conf}
    local transfer_script
    transfer_script=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/archive-package-fetch.sh
    if [[ ! -r $source_config || ! -x /usr/bin/curl || ! -r $transfer_script ]]; then
        echo 'PHIOS_ARCH_CURL_PREFETCH_REFUSED: pacman configuration or curl unavailable' >&2
        return 2
    fi
    if grep -Eq '^[[:space:]]*XferCommand[[:space:]]*=' "$source_config"; then
        echo 'PHIOS_ARCH_CURL_PREFETCH_REFUSED: existing XferCommand needs review' >&2
        return 2
    fi
    if [[ $transfer_script == *[[:space:]]* ]]; then
        echo 'PHIOS_ARCH_CURL_PREFETCH_REFUSED: unsupported transfer script path' >&2
        return 2
    fi
    awk -v script="$transfer_script" '
        /^[[:space:]]*\[options\][[:space:]]*$/ && !added {
            print
            print "XferCommand = /usr/bin/bash " script " %u %o"
            added=1
            next
        }
        {print}
        END {if (!added) exit 3}
    ' "$source_config" > "$output" || {
        echo 'PHIOS_ARCH_CURL_PREFETCH_REFUSED: invalid pacman options section' >&2
        return 2
    }
    chmod 600 "$output"
}

phios_prefetch_snapshot_packages() {
    if [[ $# -lt 1 ]]; then
        echo 'PHIOS_ARCH_PREFETCH_REFUSED: no package names supplied' >&2
        return 2
    fi
    local attempt status fallback_config=''
    local -a config_args=()
    for attempt in 1 2 3; do
        # Native pacman transfer first. Only after it fails do we use
        # a temporary copy of the same frozen archive configuration with HTTPS-only curl.
        if (( attempt == 2 )); then
            fallback_config=$(mktemp /tmp/phios-signed-pacman-prefetch.XXXXXXXX) || return 2
            if ! phios_make_pinned_archive_curl_config "$fallback_config"; then
                rm -f "$fallback_config"
                echo 'PHIOS_ARCH_PREFETCH_FAILED: secure transfer fallback unavailable; signed image HELD' >&2
                return 1
            fi
            config_args=(--config "$fallback_config")
        fi
        echo "PHIOS_ARCH_PREFETCH_ATTEMPT: ${attempt}/3 (pinned archive; signed packages; transfer=$([[ $attempt == 1 ]] && echo native || echo https-curl))"
        # --disable-download-timeout handles slow transfers, but the native
        # connection can still time out at 10 seconds. GNU timeout caps both
        # the command and curl's bounded internal retries; no installs occur.
        if timeout --signal=TERM --kill-after=15s 600s \
            pacman "${config_args[@]}" --disable-download-timeout -Sw --needed --noconfirm "$@"; then
            echo "PHIOS_ARCH_PREFETCH_OK: attempt ${attempt}/3"
            [[ -z $fallback_config ]] || rm -f "$fallback_config"
            return 0
        else
            status=$?
            echo "PHIOS_ARCH_PREFETCH_RETRY: attempt=${attempt}/3 exit=${status}" >&2
        fi
        [[ $attempt -lt 3 ]] && sleep 5
    done
    [[ -z $fallback_config ]] || rm -f "$fallback_config"
    echo 'PHIOS_ARCH_PREFETCH_FAILED: all 3 attempts failed; signed image build HELD' >&2
    return 1
}

# Download all packages required for the full *pinned snapshot* upgrade before
# allowing one installation transaction. -w / --downloadonly forbids installs.
# The whole snapshot (including eligible downgrades) is selected by -uu.
# Retrying this transport-only stage is safe; never retry a partially applied
# upgrade, disable package signatures, or switch to an unpinned/current mirror.
phios_prefetch_snapshot_upgrade() {
    local attempt status fallback_config=''
    local -a config_args=()
    for attempt in 1 2 3; do
        # Preserve native pacman behavior first. If its 10-second connection
        # deadline fails, use the *same* signed pinned repository configuration
        # with the existing HTTPS-only curl XferCommand for download retries.
        # No mirror substitution, key changes, or partially applied installs.
        if (( attempt == 2 )); then
            fallback_config=$(mktemp /tmp/phios-signed-upgrade-prefetch.XXXXXXXX) || return 2
            if ! phios_make_pinned_archive_curl_config "$fallback_config"; then
                rm -f "$fallback_config"
                echo 'PHIOS_ARCH_UPGRADE_PREFETCH_FAILED: secure transfer fallback unavailable; signed image HELD' >&2
                return 1
            fi
            config_args=(--config "$fallback_config")
        fi
        echo "PHIOS_ARCH_UPGRADE_PREFETCH_ATTEMPT: ${attempt}/3 (pinned archive; no installation; transfer=$([[ $attempt == 1 ]] && echo native || echo https-curl))"
        if timeout --signal=TERM --kill-after=15s 600s \
            pacman "${config_args[@]}" --disable-download-timeout -Syyuu --downloadonly --noconfirm; then
            echo "PHIOS_ARCH_UPGRADE_PREFETCH_OK: attempt ${attempt}/3"
            [[ -z $fallback_config ]] || rm -f "$fallback_config"
            return 0
        else
            status=$?
            echo "PHIOS_ARCH_UPGRADE_PREFETCH_RETRY: attempt=${attempt}/3 exit=${status}" >&2
        fi
        [[ $attempt -lt 3 ]] && sleep 5
    done
    [[ -z $fallback_config ]] || rm -f "$fallback_config"
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
    local fallback_config='' transfer_config=$profile_config
    for attempt in 1 2 3; do
        if (( attempt == 2 )); then
            fallback_config=$(mktemp /tmp/phios-archiso-prefetch.XXXXXXXX) || return 2
            if ! PHIOS_PREFETCH_PACMAN_CONFIG="$profile_config" \
                phios_make_pinned_archive_curl_config "$fallback_config"; then
                rm -f "$fallback_config"
                echo 'PHIOS_ARCHISO_PREFETCH_FAILED: reviewed archive transfer unavailable; ISO HELD' >&2
                return 1
            fi
            transfer_config=$fallback_config
        fi
        echo "PHIOS_ARCHISO_PREFETCH_ATTEMPT: ${attempt}/3 (exact profile, signed archive)"
        # -Syw only prefetches signed packages. The later mkarchiso install
        # retains the original profile and remains single-shot.
        if timeout --signal=TERM --kill-after=15s 600s \
            pacman --config "$transfer_config" --disable-download-timeout \
            -Syw --noconfirm "${packages[@]}"; then
            echo "PHIOS_ARCHISO_PREFETCH_OK: attempt ${attempt}/3"
            [[ -z $fallback_config ]] || rm -f "$fallback_config"
            return 0
        else
            status=$?
            echo "PHIOS_ARCHISO_PREFETCH_RETRY: attempt=${attempt}/3 exit=${status}" >&2
        fi
        [[ $attempt -lt 3 ]] && sleep 5
    done
    [[ -z $fallback_config ]] || rm -f "$fallback_config"
    echo 'PHIOS_ARCHISO_PREFETCH_FAILED: pinned profile packages unavailable; normal ISO HELD' >&2
    return 1
}
