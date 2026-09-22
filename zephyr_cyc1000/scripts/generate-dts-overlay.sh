#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root_dir=$(cd -- "$project_dir/.." && pwd)
litex_dir="$root_dir/litex_cyc1000"
csr_json="${1:-$litex_dir/build-zephyr-ethernet/csr.json}"
overlay="$project_dir/boards/litex_vexriscv.overlay"
buttons_template="$project_dir/boards/cyc1000-buttons.overlay"
buttons_overlay="$project_dir/boards/cyc1000-buttons.generated.overlay"

if [[ ! -f "$csr_json" ]]; then
	printf 'CSR map not found: %s\nBuild Etherbone gateware first.\n' "$csr_json" >&2
	exit 1
fi

cd "$litex_dir"
source ./litex_env.sh
"$PYTHON" "$root_dir/third_party/litex/litex/tools/litex_json2dts_zephyr.py" \
	--dts "$overlay" --config /dev/null "$csr_json"
# Zephyr 4.x's LiteX base DTS has no SDHC node. Current LiteX emits this
# disabled node even when the SoC has no SD card controller.
sed -i '/^&sdhc0 {$/,/^};$/d' "$overlay"
# Zephyr 4.x's LiteX UART binding does not yet declare this generator hint.
# The UART driver works with the read-on-access FIFO without a DTS property.
sed -i '/^[[:space:]]*rx-fifo-rx-we;$/d' "$overlay"
buttons_irq=$(jq -r '.constants.buttons_interrupt // empty' "$csr_json")
if [[ ! "$buttons_irq" =~ ^[0-9]+$ ]]; then
	printf 'Button IRQ is missing from %s\n' "$csr_json" >&2
	exit 1
fi
sed "s/@BUTTONS_IRQ@/$buttons_irq/g" "$buttons_template" > "$buttons_overlay"
printf 'Generated %s from %s\n' "$overlay" "$csr_json"
