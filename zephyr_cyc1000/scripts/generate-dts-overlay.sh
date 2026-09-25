#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root_dir=$(cd -- "$project_dir/.." && pwd)
litex_dir="$root_dir/litex_cyc1000"
csr_json="${1:-$litex_dir/build-zephyr-ethernet/csr.json}"
overlay="$project_dir/boards/litex_vexriscv.overlay"
buttons_template="$project_dir/boards/cyc1000-buttons.overlay"
buttons_overlay="$project_dir/boards/cyc1000-buttons.generated.overlay"
flash_template="$project_dir/boards/cyc1000-flash.overlay"
flash_overlay="$project_dir/boards/cyc1000-flash.generated.overlay"

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

# Substitute @NAME_ADDR@ (0x-prefixed) and @NAME@ (DT unit address) for
# each named CSR register or memory region; the CSR map moves whenever a
# LiteX core is added or removed.
subst_args=()
add_subst() {
	local name=$1 value=$2
	if [[ ! "$value" =~ ^[0-9]+$ ]]; then
		printf '%s is missing from %s\n' "$name" "$csr_json" >&2
		exit 1
	fi
	subst_args+=(-e "s/@${name}_ADDR@/$(printf '0x%08x' "$value")/g"
		-e "s/@${name}@/$(printf '%x' "$value")/g")
}
for reg in buttons_in buttons_mode buttons_edge buttons_ev_pending buttons_ev_enable \
	asmi_erase asmi_status; do
	add_subst "${reg^^}" "$(jq -r ".csr_registers.$reg.addr // empty" "$csr_json")"
done
add_subst STORAGE "$(jq -r '.memories.storage.base // empty' "$csr_json")"
storage_size=$(jq -r '.memories.storage.size // empty' "$csr_json")
subst_args+=(-e "s/@STORAGE_SIZE@/$(printf '0x%08x' "$storage_size")/g")
buttons_irq=$(jq -r '.constants.buttons_interrupt // empty' "$csr_json")
if [[ ! "$buttons_irq" =~ ^[0-9]+$ ]]; then
	printf 'Button IRQ is missing from %s\n' "$csr_json" >&2
	exit 1
fi
subst_args+=(-e "s/@BUTTONS_IRQ@/$buttons_irq/g")
sed "${subst_args[@]}" "$buttons_template" > "$buttons_overlay"
sed "${subst_args[@]}" "$flash_template" > "$flash_overlay"
printf 'Generated %s, %s and %s from %s\n' "$overlay" "$buttons_overlay" \
	"$flash_overlay" "$csr_json"
