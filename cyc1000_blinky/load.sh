#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
exec openFPGALoader --board cyc1000 cyc1000_blinky.rbf
