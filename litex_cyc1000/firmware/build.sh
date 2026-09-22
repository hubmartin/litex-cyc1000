#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

# Rebuild bios.bin with the local firmware/bios overlay; gateware is unchanged.
exec ./build_sw.sh "$@"
