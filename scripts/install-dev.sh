#!/bin/sh
# Install the agy-memory plugin into a workspace (copy) for local testing.
# Usage: sh scripts/install-dev.sh <workspace_dir>
set -eu
WS="${1:?usage: install-dev.sh <workspace_dir>}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$WS/.agents/plugins/agy-memory"
mkdir -p "$WS/.agents/plugins"
rm -rf "$DEST"
cp -R "$HERE/plugin/agy-memory" "$DEST"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +
echo "installed: $DEST"
