#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
zephyr_base="${ZEPHYR_BASE:-/home/martin/dev/zephyr/zephyrproject/zephyr}"
overlay="$project_dir/boards/litex_vexriscv.overlay"

if [[ ! -f "$overlay" ]]; then
	printf 'Missing %s\nRun scripts/build-gateware-etherbone.sh and scripts/generate-dts-overlay.sh first.\n' "$overlay" >&2
	exit 1
fi

export ZEPHYR_BASE="$zephyr_base"
west_bin="${WEST:-}"
if [[ -z "$west_bin" ]]; then
	west_bin=$(command -v west || true)
fi
if [[ -z "$west_bin" && -x /home/martin/hardwario/.venv/bin/west ]]; then
	west_bin=/home/martin/hardwario/.venv/bin/west
fi
if [[ -z "$west_bin" ]]; then
	printf 'west was not found; activate a Zephyr Python environment or set WEST.\n' >&2
	exit 1
fi

exec "$west_bin" build --pristine=always --board litex_vexriscv/litex_vexriscv \
	--build-dir "$project_dir/build" "$project_dir" \
	-- -DDTC_OVERLAY_FILE="$overlay"
