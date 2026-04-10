#!/usr/bin/env bash
# Append an explncc Markdown report to $GITHUB_STEP_SUMMARY (GitHub Actions).
# Usage: ci_github_step_summary.sh /path/to/file.opt.yaml [extra explncc report args...]
set -euo pipefail
if [[ -z "${GITHUB_STEP_SUMMARY:-}" ]]; then
  echo "GITHUB_STEP_SUMMARY is not set; printing to stdout instead." >&2
fi
TARGET="${1:?usage: $0 <path.opt.yaml> [args...]}"
shift
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  python3 -m explncc report "$TARGET" --format markdown --no-explain "$@" >>"$GITHUB_STEP_SUMMARY"
else
  python3 -m explncc report "$TARGET" --format markdown --no-explain "$@"
fi
