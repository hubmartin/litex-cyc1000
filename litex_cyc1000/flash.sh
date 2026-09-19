#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
# CYC1000 configuration flash needs raw configuration data (.rbf/.rpd), never Quartus .sof.
exec openFPGALoader --board cyc1000 --write-flash --verify --reset build/gateware/trenz_cyc1000.rbf
