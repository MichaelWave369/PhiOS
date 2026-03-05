#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_DIR="$ROOT_DIR/build/archiso-profile"
DIST_DIR="$ROOT_DIR/dist"
WORK_DIR="$ROOT_DIR/build/work"
OUT_DIR="$ROOT_DIR/build/out"

VERSION="$(python - <<'PY'
from phios import __version__
print(__version__)
PY
)"
ISO_NAME="phios-v${VERSION}-x86_64.iso"

echo "[1/6] Validating mkarchiso availability"
if ! command -v mkarchiso >/dev/null 2>&1; then
  echo "Error: mkarchiso not found. Install archiso first."
  exit 1
fi

echo "[2/6] Preparing profile directories"
mkdir -p "$PROFILE_DIR/airootfs/etc/skel/.config/waybar" "$PROFILE_DIR/airootfs/usr/share/pixmaps" "$DIST_DIR"

echo "[3/6] Generating Wayfire/Waybar defaults"
python - <<'PY'
from pathlib import Path
from phios.desktop.waybar_config import WAYBAR_CSS, render_waybar_config
from phios.desktop.wayfire_config import WayfireConfigGenerator

profile = Path("build/archiso-profile/airootfs/etc/skel/.config")
profile.mkdir(parents=True, exist_ok=True)
WayfireConfigGenerator().generate(str(profile / "wayfire.ini"))
waybar = profile / "waybar"
waybar.mkdir(parents=True, exist_ok=True)
(waybar / "config.jsonc").write_text(render_waybar_config(), encoding="utf-8")
(waybar / "style.css").write_text(WAYBAR_CSS, encoding="utf-8")
PY

echo "[4/6] Writing default shell login bootstrap"
cat > "$PROFILE_DIR/airootfs/etc/skel/.bashrc" <<'BASHRC'
if command -v phi >/dev/null 2>&1; then
  phi
fi
BASHRC

if [[ -f "$ROOT_DIR/build/assets/phios-splash.png" ]]; then
  cp "$ROOT_DIR/build/assets/phios-splash.png" "$PROFILE_DIR/airootfs/usr/share/pixmaps/phios-splash.png" || true
fi

echo "[5/6] Building ISO via mkarchiso"
rm -rf "$WORK_DIR" "$OUT_DIR"
mkarchiso -v -w "$WORK_DIR" -o "$OUT_DIR" "$PROFILE_DIR"

echo "[6/6] Finalizing artifact"
FOUND_ISO="$(find "$OUT_DIR" -maxdepth 1 -name '*.iso' | head -n 1)"
if [[ -z "$FOUND_ISO" ]]; then
  echo "Error: mkarchiso completed but no ISO found."
  exit 1
fi
cp "$FOUND_ISO" "$DIST_DIR/$ISO_NAME"
echo "ISO ready: $DIST_DIR/$ISO_NAME"
