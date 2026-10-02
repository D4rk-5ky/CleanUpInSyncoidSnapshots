#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv-build}"
DIST_DIR="$PROJECT_DIR/dist"
DIST_EXE="$DIST_DIR/CleanUpInSyncoidSnapshots"

# Always start from a clean build environment and an empty final-output directory.
rm -rf "$VENV_DIR" build "$DIST_DIR"
mkdir -p "$DIST_DIR"

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install -r requirements-build.txt

"$VENV_DIR/bin/pyinstaller" \
    --clean \
    --noconfirm \
    --distpath "$DIST_DIR" \
    --workpath "$PROJECT_DIR/build" \
    CleanUpInSyncoidSnapshots.spec

# The final dist directory is deliberately strict: one executable and nothing else.
mapfile -d '' DIST_ENTRIES < <(find "$DIST_DIR" -mindepth 1 -maxdepth 1 -print0)
if [[ "${#DIST_ENTRIES[@]}" -ne 1 || "${DIST_ENTRIES[0]}" != "$DIST_EXE" || ! -f "$DIST_EXE" || ! -x "$DIST_EXE" ]]; then
    echo "ERROR: dist/ must contain exactly one executable: $DIST_EXE" >&2
    echo "Current dist/ contents:" >&2
    find "$DIST_DIR" -mindepth 1 -maxdepth 1 -printf '  %f\n' >&2 || true
    exit 1
fi

# These smoke checks do not load configuration or touch ZFS.
"$DIST_EXE" --version
"$DIST_EXE" --help >/dev/null

echo "Built: $DIST_EXE"
echo "Verified: dist/ contains only CleanUpInSyncoidSnapshots"
