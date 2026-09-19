#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2021 Jakub Cabal <jakubcabal@gmail.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.gen import *

from litex_boards.platforms import trenz_cyc1000

from litex.soc.cores.clock import Cyclone10LPPLL
from litex.soc.integration.soc import *
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser
from litex.soc.cores.gpio import GPIOIn
from litex.build.generic_platform import IOStandard, Pins, Subsignal

from liteeth.phy.rmii import LiteEthPHYRMII

from litedram.modules import W9864G6JT
from litedram.phy import GENSDRPHY

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
        self.comb += pll.reset.eq(self.rst)
        pll.register_clkin(clk12, 12e6)
        pll.create_clkout(self.cd_sys,    sys_clk_freq)
        pll.create_clkout(self.cd_sys_ps, sys_clk_freq, phase=90)

        # SDRAM clock
        self.comb += platform.request("sdram_clock").eq(self.cd_sys_ps.clk)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq=50e6, with_led_chaser=True, with_buttons=False,
        with_ethernet=False, eth_ip="192.168.1.50", eth_dynamic_ip=False, **kwargs):
        platform = trenz_cyc1000.Platform()
        # F16 is PMOD PIO_03 and also the optional nCEO configuration pin.
        # CYC1000 does not use nCEO for its single-FPGA configuration chain.
        platform.toolchain.additional_qsf_commands.append(
            'set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "Use as regular IO"')

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
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on CYC1000", **kwargs)

        # SDR SDRAM --------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            self.sdrphy = GENSDRPHY(platform.request("sdram"), sys_clk_freq)
            self.add_sdram("sdram",
                phy           = self.sdrphy,
                module        = W9864G6JT(sys_clk_freq, "1:1"),
                l2_cache_size = kwargs.get("l2_size", 8192)
            )

        # Ethernet / RMII --------------------------------------------------------------------------
        if with_ethernet:
            self.ethphy = LiteEthPHYRMII(
                clock_pads = platform.request("eth_rmii_clocks"),
                pads       = platform.request("eth_rmii"),
                refclk_cd  = None,
            )
            self.add_ethernet(
                phy        = self.ethphy,
                dynamic_ip = eth_dynamic_ip,
                local_ip   = None if eth_dynamic_ip else eth_ip,
                nrxslots   = 1,
                ntxslots   = 1,
            )

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
            self.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq)
            self.leds.add_pwm(default_width=10, default_period=1024, with_csr=True)

        # Buttons ----------------------------------------------------------------------------------
        if with_buttons:
            self.buttons = GPIOIn(Cat(platform.request_all("key")))

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=trenz_cyc1000.Platform, description="LiteX SoC on CYC1000.")
    parser.add_target_argument("--sys-clk-freq",        default=50e6, type=float, help="System clock frequency.")
    parser.add_target_argument("--with-buttons",        action="store_true",      help="Enable Buttons.")
    parser.add_target_argument("--with-ethernet",       action="store_true",      help="Enable LAN8720 RMII Ethernet.")
    parser.add_target_argument("--eth-ip",              default="192.168.1.50",   help="Static IPv4 address.")
    parser.add_target_argument("--eth-dynamic-ip",      action="store_true",      help="Use DHCP instead of static IPv4.")
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq  = args.sys_clk_freq,
        with_buttons  = args.with_buttons,
        with_ethernet = args.with_ethernet,
        eth_ip        = args.eth_ip,
        eth_dynamic_ip = args.eth_dynamic_ip,
        **parser.soc_argdict
    )
    builder = Builder(soc, **parser.builder_argdict)
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

if __name__ == "__main__":
    main()
