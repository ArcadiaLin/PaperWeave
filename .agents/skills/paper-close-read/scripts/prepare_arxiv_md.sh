#!/usr/bin/env bash
# Fetch an arXiv paper as Markdown (with images) into a close-read workspace.
#
# Usage:
#   scripts/prepare_arxiv_md.sh <arxiv-id-or-url> <output-dir>
#
# Produces:
#   <output-dir>/source.md        arxiv2md conversion of the paper
#   <output-dir>/images/          downloaded figures (empty when the paper has
#   <output-dir>/images/index.md  no external image assets, e.g. inline SVG)
#
# arxiv2md is the vendored package at packages/arxiv2md in this repository;
# it runs inside the repo's shared uv environment, so nothing needs to be
# installed beforehand.
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 <arxiv-id-or-url> <output-dir>" >&2
    exit 2
fi

INPUT="$1"
OUT_DIR="$(mkdir -p "$2" && cd "$2" && pwd)"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

if [ ! -d "$REPO_ROOT/packages/arxiv2md" ]; then
    echo "error: $REPO_ROOT does not look like the CachePlan repo root" >&2
    echo "       (packages/arxiv2md not found); this script must run from the" >&2
    echo "       repository that vendors arxiv2md." >&2
    exit 1
fi

uv run --project "$REPO_ROOT" arxiv2md "$INPUT" \
    -o "$OUT_DIR/source.md" --download-images

# arxiv2md writes images to '<output-stem>.images/' next to the output file
# and rewrites links to that prefix; normalize to 'images/'.
if [ -d "$OUT_DIR/source.images" ]; then
    mv "$OUT_DIR/source.images" "$OUT_DIR/images"
    sed -i 's|source\.images/|images/|g' "$OUT_DIR/source.md"
fi

if [ -d "$OUT_DIR/images" ]; then
    {
        echo "# Image Index"
        echo
        echo "arxiv2md 下载的论文图片；图注见 source.md 中各图片的 alt 文本。"
        echo
        find "$OUT_DIR/images" -maxdepth 1 -type f ! -name index.md -printf '%f\n' \
            | sort | while read -r name; do
            echo "- \`$name\`"
        done
    } > "$OUT_DIR/images/index.md"
    echo "images: $(find "$OUT_DIR/images" -maxdepth 1 -type f ! -name index.md | wc -l) file(s) in $OUT_DIR/images/"
else
    echo "warning: no images were downloaded." >&2
    echo "         The paper's figures may be inline SVG (ltx_picture) with no" >&2
    echo "         external assets; their text content is kept in source.md." >&2
fi

echo "source: $OUT_DIR/source.md"
