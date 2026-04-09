#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DIR="${1:-build/examples}"

if [[ ! -d "$DIR" ]]; then
  echo "directory not found: $DIR (run make examples first)" >&2
  exit 2
fi

explncc summary "$DIR" "${@:2}"
