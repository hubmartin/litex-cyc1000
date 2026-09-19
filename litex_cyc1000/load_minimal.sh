#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
exec openFPGALoader --board cyc1000 build-minimal/gateware/trenz_cyc1000.rbf
