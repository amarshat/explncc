#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <path-to-opt.yaml-or-dir> [--backend rule|ollama|openai|auto] [extra explncc args...]" >&2
  exit 2
fi

explncc explain "$@"
