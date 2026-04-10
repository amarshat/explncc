#!/usr/bin/env bash
set -euo pipefail
# Nightly Markdown report from the latest .opt.yaml (edit OPT_YAML).
OPT_YAML="${OPT_YAML:-${HOME}/build/latest.opt.yaml}"
OUT_DIR="${OUT_DIR:-${HOME}/reports/explncc}"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M)"
python3 -m explncc report "$OPT_YAML" \
  --format markdown \
  --title "Nightly optimization remarks ${STAMP}" \
  --top-missed 25 \
  --no-explain \
  -o "${OUT_DIR}/report-${STAMP}.md"
