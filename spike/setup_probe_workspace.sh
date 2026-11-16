#!/bin/sh
# Create an isolated test workspace with the agy-probe plugin and a large workload.
# Usage: sh spike/setup_probe_workspace.sh <target_dir>
set -eu
TARGET="${1:?usage: setup_probe_workspace.sh <target_dir>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$TARGET/.agents/plugins"
rm -rf "$TARGET/.agents/plugins/agy-probe"
cp -R "$HERE/probe-plugin/agy-probe" "$TARGET/.agents/plugins/agy-probe"
python3 "$HERE/gen_workload.py" "$TARGET" --modules 40
cd "$TARGET"
[ -d .git ] || git init -q
echo "ready: $TARGET"
