#!/usr/bin/env bash
# Build dist/sum-plugin.zip for claude.ai org "Add plugins → Upload a file".
# Zip root = plugin root (.claude-plugin/plugin.json at top level).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p dist
rm -f dist/sum-plugin.zip
if find plugins/sum -name ".summation-config*" | grep -q .; then
  echo "refusing to pack: credential file inside plugins/sum" >&2
  exit 1
fi
(cd plugins/sum && zip -r ../../dist/sum-plugin.zip . -x "*.DS_Store" -x "*__pycache__*")
echo "built dist/sum-plugin.zip"
