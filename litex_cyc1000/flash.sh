#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

# openFPGALoader applies the CYC1000 Active-Serial bit ordering when writing an
# .rbf. Do not concatenate it with arbitrary data: a raw .bin bypasses that
# conversion and will not boot after reset. Write the XIP BIOS separately.
readonly GATEWARE=build/gateware/trenz_cyc1000.rbf
readonly BIOS=build/software/bios/bios.bin
readonly BIOS_OFFSET=$((0x00100000))
readonly FLASH_SIZE=$((0x00200000)) # On-board W25Q16, 2 MiB.

[[ -f "$GATEWARE" && -f "$BIOS" ]]
[[ $(stat -c%s "$GATEWARE") -le "$BIOS_OFFSET" ]]
[[ $((BIOS_OFFSET + $(stat -c%s "$BIOS"))) -le "$FLASH_SIZE" ]]

# Programming uses a temporary SPI-over-JTAG bridge. It does not reconfigure
# the FPGA from configuration flash afterwards, so explicitly load our RBF to
# SRAM after the verified write. A later power cycle will use the same image
# from flash.
openFPGALoader --board cyc1000 --write-flash --verify "$GATEWARE"
openFPGALoader --board cyc1000 --write-flash --verify --offset "$BIOS_OFFSET" \
  --file-type bin "$BIOS"
exec openFPGALoader --board cyc1000 "$GATEWARE"
