#!/usr/bin/env bash
set -euo pipefail
# Nightly optimization report — timestamped archive (Chapter 12).
# No secrets printed; deterministic report by default.

OPT_YAML="${OPT_YAML:-${HOME}/build/latest.opt.yaml}"
OUT_DIR="${OUT_DIR:-${HOME}/reports/explncc}"
EXPLAIN_BACKEND="${EXPLAIN_BACKEND:-rule}"

mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M)"
MD="${OUT_DIR}/report-${STAMP}.md"
JSON="${OUT_DIR}/report-${STAMP}.json"
MANIFEST="${OUT_DIR}/manifest-${STAMP}.json"

python3 -m explncc report "$OPT_YAML" \
  --format markdown \
  --title "Nightly optimization remarks ${STAMP}" \
  --top-missed 25 \
  --explain-backend "$EXPLAIN_BACKEND" \
  -o "$MD"

python3 -m explncc report "$OPT_YAML" \
  --format json \
  --no-explain \
  -o "$JSON" \
  --write-manifest "$MANIFEST"

echo "Wrote ${MD} and ${JSON}"
