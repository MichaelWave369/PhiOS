#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
command -v docker >/dev/null || { echo 'Docker is required for the isolated Arch image builder.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'Python 3 is required to read the release contract.' >&2; exit 1; }
git -C "$repo" diff --quiet HEAD -- phios phishell packaging build/build_iso.sh || { echo 'Commit candidate inputs before building an exact-source ISO.' >&2; exit 1; }
source_commit=$(git -C "$repo" rev-parse HEAD)
git_common=$(git -C "$repo" rev-parse --path-format=absolute --git-common-dir)
builder_image=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["builder_image"])' "$repo/packaging/linux/release.json")
mkdir -p "$repo/dist/linux"
docker pull "$builder_image"
docker image inspect "$builder_image" > "$repo/dist/linux/builder-image.json"
docker run --rm --privileged \
    -v "$repo:$repo:ro" -v "$git_common:$git_common:ro" \
    -v "$repo/dist/linux:/artifacts" -w "$repo" \
    -e PHIOS_SOURCE_COMMIT="$source_commit" -e PHIOS_OUTPUT_DIR=/artifacts \
    "$builder_image" bash packaging/linux/build-linux.sh
