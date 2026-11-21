#!/usr/bin/env bash
# Fetch exact-version signed packages from the dated Arch Linux Archive pool.
# Pacman still resolves the frozen repo database, verifies signatures/hashes,
# and performs installation in an independent, single-shot transaction.
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo 'PHIOS_ARCH_FETCH_REFUSED: source URL and destination required' >&2
  exit 2
fi
url=$1
output=$2
root=$(cd "$(dirname "$0")/../.." && pwd)
snapshot=$(sed -n 's/.*"arch_snapshot": "\([0-9/]\{10\}\)".*/\1/p' "$root/packaging/linux/release.json")
if [[ ! $snapshot =~ ^[0-9]{4}/[0-9]{2}/[0-9]{2}$ ]]; then
  echo 'PHIOS_ARCH_FETCH_REFUSED: invalid frozen snapshot' >&2
  exit 2
fi
case "$url" in
  "https://umea.archive.pkgbuild.com/repos/$snapshot/"*|"https://archive.archlinux.org/repos/$snapshot/"*) ;;
  *) echo 'PHIOS_ARCH_FETCH_REFUSED: unreviewed archive URL or snapshot' >&2; exit 2 ;;
esac
file=${url##*/}
# ALPM package filenames can include a numeric epoch ("1:") and pacman
# may percent-encode the colon (or plus) in its URL. Accept ONLY these
# two encoded characters, never encoded slashes, path traversal or queries.
url_pattern='^https://(umea\.archive\.pkgbuild\.com|archive\.archlinux\.org)/repos/[0-9]{4}/[0-9]{2}/[0-9]{2}/(core|extra)/os/(x86_64|any)/([A-Za-z0-9@+._:~-]|%3[Aa]|%2[Bb])+$'
if [[ ! $url =~ $url_pattern ]]; then
  echo 'PHIOS_ARCH_FETCH_REFUSED: unreviewed repository path' >&2
  exit 2
fi
file=${file//%3A/:}
file=${file//%3a/:}
file=${file//%2B/+}
file=${file//%2b/+}
package_pattern='^([A-Za-z0-9@._+-]+)-([^-]+)-([0-9][0-9.]*)-(x86_64|any)\.pkg\.tar\.(zst|xz|gz)(\.sig)?$'
if [[ $file =~ $package_pattern ]]; then
  name=${BASH_REMATCH[1]}
  first=${name:0:1}
  if [[ ! $first =~ ^[A-Za-z0-9]$ ]]; then
    echo 'PHIOS_ARCH_FETCH_REFUSED: invalid archive package name' >&2
    exit 2
  fi
  urls=("https://umea.archive.pkgbuild.com/packages/$first/$name/$file" "https://archive.archlinux.org/packages/$first/$name/$file")
elif [[ $file =~ ^(core|extra)\.(db|files)(\.tar\.gz|\.sig)?$ ]]; then
  urls=("$url")
else
  echo 'PHIOS_ARCH_FETCH_REFUSED: unrecognized archive object' >&2
  exit 2
fi
# Use fresh temporary files for each source to prevent mixed partial downloads.
# Curl's HTTPS-only redirect policy prevents HTTP downgrade.
for candidate in "${urls[@]}"; do
  temp=$(mktemp "${output}.phios.XXXXXXXX") || exit 2
  if curl --fail --location --show-error --silent --http1.1 \
    --proto https --proto-redir https --connect-timeout 45 --max-time 240 \
    --retry 1 --retry-connrefused --retry-delay 2 \
    -o "$temp" "$candidate"; then
    mv -f -- "$temp" "$output"
    exit 0
  fi
  rm -f -- "$temp"
done
echo 'PHIOS_ARCH_FETCH_FAILED: exact signed archive object unavailable; image HELD' >&2
exit 1

if [[ ! $url =~ $url_pattern ]]; then
  echo 'PHIOS_ARCH_FETCH_REFUSED: unreviewed repository path' >&2
  exit 2
fi
file=${file//%3A/:}
file=${file//%3a/:}
file=${file//%2B/+}
file=${file//%2b/+}
package_pattern='^([A-Za-z0-9@._+-]+)-([^-]+)-([0-9][0-9.]*)-(x86_64|any)\.pkg\.tar\.(zst|xz|gz)(\.sig)?$'
if [[ $file =~ $package_pattern ]]; then
  name=${BASH_REMATCH[1]}
  first=${name:0:1}
  if [[ ! $first =~ ^[A-Za-z0-9]$ ]]; then
    echo 'PHIOS_ARCH_FETCH_REFUSED: invalid archive package name' >&2
    exit 2
  fi
  urls=("https://umea.archive.pkgbuild.com/packages/$first/$name/$file" "https://archive.archlinux.org/packages/$first/$name/$file")
elif [[ $file =~ ^(core|extra)\.(db|files)(\.tar\.gz|\.sig)?$ ]]; then
  urls=("$url")
else
  echo 'PHIOS_ARCH_FETCH_REFUSED: unrecognized archive object' >&2
  exit 2
fi
# Use fresh temporary files for each source to prevent mixed partial downloads.
# Curl's HTTPS-only redirect policy prevents HTTP downgrade.
for candidate in "${urls[@]}"; do
  temp=$(mktemp "${output}.phios.XXXXXXXX") || exit 2
  if curl --fail --location --show-error --silent --http1.1 \
    --proto https --proto-redir https --connect-timeout 45 --max-time 240 \
    --retry 1 --retry-connrefused --retry-delay 2 \
    -o "$temp" "$candidate"; then
    mv -f -- "$temp" "$output"
    exit 0
  fi
  rm -f -- "$temp"
done
echo 'PHIOS_ARCH_FETCH_FAILED: exact signed archive object unavailable; image HELD' >&2
exit 1
