#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <example-name>" >&2
  echo "example: $0 vectorize_aliasing_fail" >&2
  exit 2
fi

name="$1"
case "$name" in
  inline_miss_no_definition) make build-inline-miss ;;
  inline_too_costly) make build-inline-costly ;;
  vectorize_aliasing_fail) make build-vectorize-fail ;;
  vectorize_success) make build-vectorize-success ;;
  unroll_fixed_trip) make build-unroll-fixed ;;
  unroll_unknown_trip) make build-unroll-unknown ;;
  *)
    echo "unknown example: $name" >&2
    exit 2
    ;;
esac
