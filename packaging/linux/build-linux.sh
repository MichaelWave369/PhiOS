#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ $EUID -ne 0 || $(uname -m) != x86_64 ]]; then
    echo 'The isolated image builder requires an x86_64 Arch Linux root environment.' >&2
    exit 1
fi
snapshot=$(sed -n 's/.*"arch_snapshot": "\([0-9/]\{10\}\)".*/\1/p' "$repo/packaging/linux/release.json")
expected_archiso=$(sed -n 's/.*"archiso_version": "\([0-9-]\+\)".*/\1/p' "$repo/packaging/linux/release.json")
[[ $snapshot =~ ^[0-9]{4}/[0-9]{2}/[0-9]{2}$ && $expected_archiso =~ ^[0-9]+-[0-9]+$ ]] || exit 1
cat > /etc/pacman.d/mirrorlist <<MIRRORS
Server = https://archive.archlinux.org/repos/$snapshot/\$repo/os/\$arch
MIRRORS
pacman -Syyuu --noconfirm
pacman -S --needed --noconfirm archiso base-devel python python-build python-installer python-setuptools python-wheel python-psutil python-mcp nodejs npm git wayfire waybar wofi foot chromium ttf-dejavu mesa
[[ $(pacman -Q archiso) == "archiso $expected_archiso" ]] || { echo 'Archiso version differs from locked release input.' >&2; exit 1; }
[[ -n ${PHIOS_SOURCE_COMMIT:-} ]] || { echo 'PHIOS_SOURCE_COMMIT is required.' >&2; exit 1; }
[[ $(git -c safe.directory="$repo" -C "$repo" rev-parse HEAD) == "$PHIOS_SOURCE_COMMIT" ]] || { echo 'Source commit mismatch.' >&2; exit 1; }
export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH=$(git -c safe.directory="$repo" -C "$repo" show -s --format=%ct HEAD)
work=$(mktemp -d /tmp/phios-build.XXXXXXXX)
output="${PHIOS_OUTPUT_DIR:-$repo/dist/linux}"
mkdir -p "$output" "$work/source" "$work/packages"
git -c safe.directory="$repo" -C "$repo" archive --format=tar --prefix=phios-source/ HEAD | tar -xf - -C "$work/source"
printf '%s\n' "$PHIOS_SOURCE_COMMIT" > "$work/source/phios-source/PHIOS_SOURCE_COMMIT"
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner --use-compress-program='gzip -n' -cf "$work/phios-source.tar.gz" -C "$work/source" phios-source
export PHIOS_SOURCE_SHA256
PHIOS_SOURCE_SHA256=$(sha256sum "$work/phios-source.tar.gz" | cut -d' ' -f1)
id phios-build &>/dev/null || useradd -m phios-build
chmod 755 "$work"
for package in phios phishell; do
    mkdir "$work/$package"
    cp "$repo/packaging/arch/$package/PKGBUILD" "$work/$package/"
    cp "$work/phios-source.tar.gz" "$work/$package/"
    chown -R phios-build:phios-build "$work/$package"
    runuser -u phios-build -- env PHIOS_SOURCE_SHA256="$PHIOS_SOURCE_SHA256" SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" bash -c 'cd "$1"; makepkg --noconfirm --cleanbuild' _ "$work/$package"
    cp "$work/$package/"*.pkg.tar.zst "$work/packages/"
    pacman -U --noconfirm "$work/$package/"*.pkg.tar.zst
done
(cd /tmp; python -c 'import phios, phios.mcp.server, phios.ghostwalk_operator; assert phios.__file__.startswith("/usr/lib/"); print(phios.__version__)'; phi version; phi-operator --help)
node "$repo/phishell/host/packageObserver.mjs" --require-native
repo-add "$work/packages/phios-local.db.tar.gz" "$work/packages/"*.pkg.tar.zst
smoke_args=()
[[ ${PHIOS_CI_SMOKE:-0} == 1 ]] && smoke_args+=(--smoke)
python "$repo/packaging/linux/prepare_profile.py" --upstream /usr/share/archiso/configs/releng --destination "$work/profile" --repo "$repo" --package-repo "$work/packages" "${smoke_args[@]}"
mkarchiso -v -w "$work/archiso-work" -o "$output" "$work/profile" 2>&1 | tee "$output/mkarchiso.log"
# Pacman hooks can print an initramfs error while the package transaction and
# mkarchiso still return zero. Preserve it and hold the candidate explicitly.
if grep -Eq '==> ERROR:|error: command failed to execute correctly' "$output/mkarchiso.log"; then
    echo 'Image contains a failed build hook; candidate qualification is held.' >&2
    exit 1
fi
cp "$work/packages/"*.pkg.tar.zst "$output/"
cp "$work/phios-source.tar.gz" "$output/"
cp "$repo/packaging/linux/release.json" "$output/"
pacman -Q > "$output/builder-packages.txt"
pacman --root "$work/archiso-work/x86_64/airootfs" -Q > "$output/image-packages.txt"
printf '%s\n' "$PHIOS_SOURCE_COMMIT" > "$output/source-commit.txt"
printf '%s\n' "$PHIOS_SOURCE_SHA256" > "$output/source-archive-sha256.txt"
cp "$repo/LICENSE_HISTORY.md" "$output/LICENSE_HISTORY.md"
inventory_args=()
[[ ${PHIOS_CI_SMOKE:-0} == 1 ]] && inventory_args+=(--ci-fixtures)
python "$repo/packaging/linux/release_inventory.py" \
    --root "$work/archiso-work/x86_64/airootfs" --output "$output" \
    --source "$PHIOS_SOURCE_COMMIT" --epoch "$SOURCE_DATE_EPOCH" "${inventory_args[@]}"
echo "Unsigned development candidate and provenance: $output"
