#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2021 Jakub Cabal <jakubcabal@gmail.com>
# SPDX-License-Identifier: BSD-2-Clause

import os

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.gen import *

from litex_boards.platforms import trenz_cyc1000

from litex.soc.cores.clock import Cyclone10LPPLL
from litex.soc.integration.soc import *
from litex.soc.integration.builder import *
from litex.soc.interconnect import wishbone
from litex.soc.cores.led import LedChaser
from litex.soc.cores.gpio import GPIOIn
from litex.build.generic_platform import IOStandard, Pins, Subsignal

from liteeth.phy.rmii import LiteEthPHYRMII

from litedram.modules import W9864G6JT
from litedram.phy import GENSDRPHY


# ASMI XIP -----------------------------------------------------------------------------------------

class ASMIFlashXIP(LiteXModule):
    """Wishbone adapter for the dedicated Active-Serial flash interface."""
    def __init__(self, platform, flash_offset):
        self.bus = wishbone.Interface(data_width=32, adr_width=19, mode="r")

        avl_address       = Signal(19)
        avl_read          = Signal()
        avl_waitrequest   = Signal()
        avl_readdata      = Signal(32)
        avl_readdatavalid = Signal()
        busy              = Signal()

        # The ASMI Avalon port is word-addressed (the generated IP converts
        # it to byte addresses itself). The SoC bus strips the XIP origin, so
        # add only the flash offset expressed in 32-bit words.
        self.comb += [
            avl_address.eq(self.bus.adr + flash_offset//4),
            avl_read.eq(self.bus.cyc & self.bus.stb & ~busy),
            self.bus.dat_r.eq(avl_readdata),
            self.bus.ack.eq(busy & avl_readdatavalid),
        ]
        self.sync += If(~busy,
            If(self.bus.cyc & self.bus.stb & ~avl_waitrequest,
                busy.eq(1)
            )
        ).Elif(avl_readdatavalid,
            busy.eq(0)
        )

        ip_dir = os.path.join(os.path.dirname(__file__), "ip", "asmi_xip")
        platform.add_ip(os.path.join(ip_dir, "asmi_xip.qip"))
        self.specials += Instance("asmi_xip",
            i_clk_clk                   = ClockSignal(),
            i_reset_reset_n             = ~ResetSignal(),
            i_avl_csr_address           = 0,
            i_avl_csr_read              = 0,
            i_avl_csr_write             = 0,
            i_avl_csr_writedata         = 0,
            i_avl_mem_write             = 0,
            i_avl_mem_burstcount        = 1,
            i_avl_mem_read              = avl_read,
            i_avl_mem_address           = avl_address,
            i_avl_mem_writedata         = 0,
            i_avl_mem_byteenable        = 0b1111,
            o_avl_mem_waitrequest       = avl_waitrequest,
            o_avl_mem_readdata          = avl_readdata,
            o_avl_mem_readdatavalid     = avl_readdatavalid,
        )

# CRG ----------------------------------------------------------------------------------------------

class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq):
        self.rst       = Signal()
        self.cd_sys    = ClockDomain()
        self.cd_sys_ps = ClockDomain()

        # # #

        # Clk / Rst
        clk12 = platform.request("clk12")

        # PLL
        self.pll = pll = Cyclone10LPPLL(speedgrade="-C8")
        pll.register_clkin(clk12, 12e6)
        # A LiteX SoC reset is a one-cycle CSR pulse. Resetting the PLL with
        # it is too short for a reliable Cyclone 10 LP PLL relock and can make
        # a Zephyr ``kernel reboot`` hang immediately after the BIOS jumps to
        # SDRAM. Keep the PLL running and reset all logic synchronously; a
        # power/configuration reset is still held until the PLL reports lock.
        pll.create_clkout(self.cd_sys,    sys_clk_freq, with_reset=False)
        pll.create_clkout(self.cd_sys_ps, sys_clk_freq, phase=90, with_reset=False)
        self.specials += [
            AsyncResetSynchronizer(self.cd_sys,    ~pll.locked | self.rst),
            AsyncResetSynchronizer(self.cd_sys_ps, ~pll.locked | self.rst),
        ]

        # SDRAM clock
        self.comb += platform.request("sdram_clock").eq(self.cd_sys_ps.clk)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    # FPGA configuration occupies the beginning of the 2 MiB flash.  The BIOS
    # is placed at XIP_FLASH_OFFSET and presented directly at XIP_CPU_ORIGIN.
    mem_map = {**SoCCore.mem_map, **{"spiflash": 0x20100000}}
    XIP_FLASH_OFFSET = 0x00100000
    XIP_CPU_ORIGIN   = 0x20100000
    XIP_ROM_SIZE     = 0x00020000
    ZEPHYR_FLASH_OFFSET = 0x00120000

    def __init__(self, sys_clk_freq=50e6, with_led_chaser=True, with_buttons=False,
        with_ethernet=False, with_etherbone=False, eth_ip="192.168.1.241",
        eth_dynamic_ip=False, with_zephyr_flash_boot=False, **kwargs):
        platform = trenz_cyc1000.Platform()
        # F16 is PMOD PIO_03 and also the optional nCEO configuration pin.
        # CYC1000 does not use nCEO for its single-FPGA configuration chain.
        platform.toolchain.additional_qsf_commands.append(
            'set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "Use as regular IO"')
        # Keep an unplugged UART RX at the idle level so the BIOS console does
        # not consume spurious characters while servicing the network stack.
        platform.toolchain.additional_qsf_commands.append(
            'set_instance_assignment -name WEAK_PULL_UP_RESISTOR ON -to serial_rx')
        # Waveshare LAN8720 ETH Board, connected to CYC1000's J6 PMOD.
        # The LAN8720's nINT/REFCLKO pin is configured by the board as the 50 MHz
        # RMII reference-clock output. TXD1 is wired separately to FPGA pin N2.
        platform.add_extension([
            ("eth_rmii_clocks", 0,
                Subsignal("ref_clk", Pins("B16")), # J6 PIO_07: nINT/REFCLKO.
                IOStandard("3.3-V LVTTL")),
            ("eth_rmii", 0,
                Subsignal("tx_data", Pins("F13 N2")), # TXD0, TXD1.
                Subsignal("rx_data", Pins("C15 F15")), # RXD0, RXD1.
                Subsignal("crs_dv",  Pins("F16")),     # CRS_DV.
                Subsignal("tx_en",   Pins("D15")),     # TX_EN.
                Subsignal("mdc",     Pins("D16")),     # MDC.
                Subsignal("mdio",    Pins("C16")),     # MDIO.
                IOStandard("3.3-V LVTTL")),
        ])

        # CRG --------------------------------------------------------------------------------------
        self.crg = _CRG(platform, sys_clk_freq)

        # SoCCore ----------------------------------------------------------------------------------
        # Keep program code exclusively in external SPI flash.  There is no
        # initialized integrated ROM in this configuration.
        kwargs["integrated_rom_size"] = 0
        kwargs["cpu_reset_address"]   = self.XIP_CPU_ORIGIN
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on CYC1000", **kwargs)

        # Preserve UART input across occasional XIP cache misses and expose
        # framing/overflow evidence to BIOS diagnostics.
        self.uart.add_rx_error_status()

        # Dedicated Active-Serial XIP ----------------------------------------------------------
        # The hard ASMI block is the only logic permitted to access the four
        # configuration-flash pins after FPGA configuration. It serves BIOS
        # fetches directly from the W25Q16; no initialized BRAM ROM is used.
        # Normal BIOS mapping is 128 KiB. Zephyr flash boot maps the complete
        # second flash megabyte: BIOS at 0x00100000 followed by Zephyr.
        xip_rom_size = 0x00100000 if with_zephyr_flash_boot else self.XIP_ROM_SIZE
        self.asmi_xip = ASMIFlashXIP(platform, self.XIP_FLASH_OFFSET)
        self.bus.add_slave("rom", self.asmi_xip.bus, SoCRegion(
            origin = self.XIP_CPU_ORIGIN,
            size   = xip_rom_size,
            mode   = "rx",
            cached = True,
            linker = True,
        ), strip_origin=True)

        if with_zephyr_flash_boot:
            zephyr_flash_address = self.XIP_CPU_ORIGIN + (
                self.ZEPHYR_FLASH_OFFSET - self.XIP_FLASH_OFFSET)
            # BIOS validates the FBI length/CRC, copies it to SDRAM and jumps.
            # A bad or absent image falls through to serial boot for recovery.
            self.add_constant("FLASH_BOOT_ADDRESS", zephyr_flash_address)
            self.add_constant("FLASH_BOOT_REGION_BASE", self.XIP_CPU_ORIGIN)
            self.add_constant("FLASH_BOOT_REGION_SIZE", xip_rom_size)
            self.add_constant("FLASH_BOOT_PRIORITY", 0)
            self.add_constant("SERIAL_BOOT_PRIORITY", 10)

        # SDR SDRAM --------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            self.sdrphy = GENSDRPHY(platform.request("sdram"), sys_clk_freq)
            self.add_sdram("sdram",
                phy           = self.sdrphy,
                module        = W9864G6JT(sys_clk_freq, "1:1"),
                l2_cache_size = kwargs.get("l2_size", 8192)
            )

        # Ethernet / RMII --------------------------------------------------------------------------
        if with_ethernet or with_etherbone:
            eth_rmii_pads = platform.request("eth_rmii")
            self.ethphy = LiteEthPHYRMII(
                clock_pads = platform.request("eth_rmii_clocks"),
                pads       = eth_rmii_pads,
                refclk_cd  = None,
            )
            if with_etherbone:
                self.add_etherbone(
                    phy          = self.ethphy,
                    ip_address   = eth_ip,
                    data_width   = 8,
                    buffer_depth = 4,
                )
            if with_ethernet:
                self.add_ethernet(
                    phy        = self.ethphy,
                    dynamic_ip = eth_dynamic_ip,
                    local_ip   = None if eth_dynamic_ip else eth_ip,
                    # Keep two RX slots. LiteEth's single-slot Wishbone decoder
                    # requires its slot-select address bit to be zero; with one
                    # RX slot the adjacent TX window starts at +0x800, where
                    # that bit is one, so the TX SRAM never acknowledges writes.
                    # Two RX slots align the TX window at +0x1000.
                    nrxslots   = 2,
                    ntxslots   = 1,
                )
                # Run the BIOS software network stack, but skip automatic TFTP boot.
                self.add_constant("NET_BOOT_DISABLE")

        # Leds
        if with_led_chaser:
            self.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq)
            self.leds.add_pwm(default_width=10, default_period=1024, with_csr=True)

        # Buttons ----------------------------------------------------------------------------------
        if with_buttons:
            # Expose the CYC1000 push button as an interrupt-capable LiteX
            # GPIO so Zephyr can use its standard gpio-keys input driver.
            self.buttons = GPIOIn(Cat(platform.request_all("key")), with_irq=True)
            self.irq.add("buttons", use_loc_if_exists=True)

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=trenz_cyc1000.Platform, description="LiteX SoC on CYC1000.")
    parser.add_target_argument("--sys-clk-freq",        default=50e6, type=float, help="System clock frequency.")
    parser.add_target_argument("--with-buttons",        action="store_true",      help="Enable Buttons.")
    parser.add_target_argument("--no-led-chaser",       action="store_true",      help="Disable LED chaser.")
    ethopts = parser.target_group.add_mutually_exclusive_group()
    ethopts.add_argument("--with-ethernet",  action="store_true", help="Enable CPU-accessible LAN8720 Ethernet MAC.")
    ethopts.add_argument("--with-etherbone", action="store_true", help="Enable LiteEth Etherbone.")
    parser.add_target_argument("--eth-ip",              default="192.168.1.241", help="Static IPv4 address.")
    parser.add_target_argument("--eth-dynamic-ip",      action="store_true",      help="Use DHCP instead of static IPv4.")
    parser.add_target_argument("--with-zephyr-flash-boot", action="store_true",
        help="Boot a CRC-checked Zephyr FBI image from SPI flash, with UART fallback.")
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq  = args.sys_clk_freq,
        with_led_chaser = not args.no_led_chaser,
        with_buttons  = args.with_buttons,
        with_ethernet  = args.with_ethernet,
        with_etherbone = args.with_etherbone,
        eth_ip        = args.eth_ip,
        eth_dynamic_ip = args.eth_dynamic_ip,
        with_zephyr_flash_boot = args.with_zephyr_flash_boot,
        **parser.soc_argdict
    )
    builder = Builder(soc, **parser.builder_argdict)
    # Build the normal LiteX BIOS from a local overlay.  The overlay adds the
    # user firmware sources to bios.bin while the upstream BIOS remains an
    # untouched pinned submodule.
    builder.add_software_package("bios", os.path.join(
        os.path.dirname(__file__), "firmware", "bios"))
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

if __name__ == "__main__":
    main()
