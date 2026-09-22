# Zephyr RTOS on CYC1000 / LiteX VexRiscv

This application runs Zephyr on the VexRiscv LiteX SoC for the Trenz CYC1000.
Its console and Zephyr shell use the LiteX UART at 115200 Bd. The LAN8720 is
instantiated only for LiteX Etherbone: Zephyr networking and the LiteEth MAC
are intentionally disabled.

The Zephyr board target is litex_vexriscv/litex_vexriscv. LiteX peripheral
addresses are not fixed, so the DTS overlay is generated from the CSR map of
the actual Etherbone bitstream before Zephyr is compiled.

## Prerequisites

- pinned LiteX dependencies and the local .venv from the repository root;
- Quartus at /home/martin/altera_lite/25.1std/quartus/bin;
- a Zephyr workspace. scripts/build.sh defaults to
  /home/martin/dev/zephyr/zephyrproject/zephyr; set ZEPHYR_BASE to use another.

## Build

From this directory run:

    ./scripts/build-gateware-etherbone.sh
    ./scripts/generate-dts-overlay.sh
    ./scripts/build.sh

The first command creates ../litex_cyc1000/build-zephyr-etherbone/, whose
gateware includes LAN8720 plus Etherbone but no CPU-accessible LiteEth MAC.
It also enables LiteX timer uptime registers required by Zephyr and uses
read-on-access UART RX FIFO mode, which is required by Zephyr's LiteX UART
driver to avoid losing received characters.
The second command records its UART, timer and SDRAM addresses in
boards/litex_vexriscv.overlay. Do not reuse an overlay from another LiteX
build.

Set ETHERBONE_IP to change the Etherbone address, for example:

    ETHERBONE_IP=192.168.1.241 ./scripts/build-gateware-etherbone.sh

## Load and use

    ./scripts/load.sh

The script loads the FPGA SRAM image and transfers zephyr.bin using the LiteX
serial boot protocol, then stays attached to the UART. The startup line is
followed by the cyc1000:~$ prompt; use help and cyc1000_info.

## Persistent flash boot

The Etherbone gateware build enables LiteX flash boot. At reset BIOS validates
the Zephyr Flash Boot Image CRC, copies it to SDRAM and starts it. If the image
is missing or invalid, BIOS falls back to UART serial boot.

After building, persist the complete boot chain:

    ./scripts/make-flash-image.sh
    ./scripts/flash.sh

The script writes and verifies FPGA configuration at offset 0, LiteX BIOS at
0x00100000 and Zephyr at 0x00120000. It then loads the bitstream into SRAM,
so the result is active immediately and also after power reset.

`kernel reboot` in the Zephyr shell is also supported. The LiteX SoC reset
resets the system logic while keeping the Cyclone 10 LP PLL running; this
avoids an unreliable PLL relock from the one-cycle software-reset request.
Power-on and button resets continue to wait for the PLL lock normally.

Etherbone remains a LiteX transport and has no Zephyr net_if. Testing it is
intentionally deferred.
