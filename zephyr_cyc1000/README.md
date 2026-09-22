# Zephyr RTOS on CYC1000 / LiteX VexRiscv

This application runs Zephyr on the VexRiscv LiteX SoC for the Trenz CYC1000.
Its console and Zephyr shell use the LiteX UART at 115200 Bd. The LAN8720 is
connected through the LiteX LiteEth MAC and exposed to Zephyr networking.

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

    ./scripts/build-gateware-ethernet.sh
    ./scripts/generate-dts-overlay.sh
    ./scripts/build.sh

The first command creates ../litex_cyc1000/build-zephyr-ethernet/, whose
gateware includes the CPU-accessible LiteEth MAC and JTAGBone, but no
Etherbone endpoint.
It also enables LiteX timer uptime registers required by Zephyr and uses
read-on-access UART RX FIFO mode, which is required by Zephyr's LiteX UART
driver to avoid losing received characters.
The second command records its UART, timer and SDRAM addresses in
boards/litex_vexriscv.overlay. Do not reuse an overlay from another LiteX
build.

The Ethernet gateware uses dynamic IP mode; address assignment is done by
Zephyr (DHCPv4 and IPv6 Router Advertisements), not by a fixed LiteX address.

## Load and use

    ./scripts/load.sh

The script loads the FPGA SRAM image and transfers zephyr.bin using the LiteX
serial boot protocol, then stays attached to the UART. The startup line is
followed by the cyc1000:~$ prompt; use help and cyc1000_info.

## Ethernet

The Ethernet profile obtains its IPv4 address through DHCPv4. LiteX owns the
RMII and MAC hardware; Zephyr uses the LiteEth CSR and buffer RAM driver.
Use `net iface` on the UART to see the assigned address, then verify it from
a host on the same subnet.

The previously used static `192.168.1.241/24` address is no longer configured.

The LAN router advertises IPv6 prefix `2a00:6500:2811:6d00::/64`. Zephyr uses
SLAAC for its stable global address and RFC 8981 Privacy Extensions for a
second, temporary global address. The temporary address is preferred for
outbound connections and rotates; use the stable SLAAC address for a service
that needs a durable inbound address. Inspect both addresses with `net iface`.

The application also provides a deliberately small test HTTP server on port
80. Its static status page verifies the complete TCP path:

    curl http://192.168.1.241/

It publishes `CYC1000 Zephyr test message <n>` every 10 seconds to MQTT topic
`cyc1000/test`. The broker is `nasbuntu.home` (`192.168.1.112`) on TCP port
1883; it is intentionally configured by numeric address in firmware, so it
does not depend on a DNS server. For example, receive the test traffic with:

    bch -H 192.168.1.112 sub cyc1000/test

The UART shell network diagnostics are enabled and show useful runtime state:

    net stats
    net sockets
    net allocs

## Shared UART console

`tmux` owns the physical `/dev/ttyUSB3` port in the `cyc1000-uart` session.
Attach to the shared console with:

    tmux attach -t cyc1000-uart

Multiple viewers can attach, but coordinate command entry: all clients share
one input stream.

## UART logs and button

Zephyr logs share the UART with the shell.
The CYC1000 push button is exposed as an interrupt-driven Zephyr
`gpio-keys` input; a press emits `CYC1000 button pressed` to the UART log.

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
