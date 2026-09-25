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


# ASMI flash ---------------------------------------------------------------------------------------

class ASMIFlash(LiteXModule):
    """Dedicated Active-Serial flash interface.

    ``bus`` is the read-only XIP window used for BIOS fetches and Zephyr flash
    boot. The optional ``storage`` window maps only the mutable flash tail
    [storage_offset, storage_offset + storage_size) and accepts writes; the
    ASMI IP turns every write into WREN + page program + busy polling. Erase
    is a CSR-driven engine restricted to the same tail, so software can not
    erase or program the configuration image, BIOS or Zephyr boot image.
    """
    ERASE_SIZE = 4096 # W25Q16 subsector (opcode 0x20).

    def __init__(self, platform, flash_offset, storage_offset=None, storage_size=0):
        self.bus = wishbone.Interface(data_width=32, adr_width=19, mode="r")
        with_storage = storage_size > 0

        avl_address       = Signal(19)
        avl_read          = Signal()
        avl_write         = Signal()
        avl_writedata     = Signal(32)
        avl_byteenable    = Signal(4)
        avl_waitrequest   = Signal()
        avl_readdata      = Signal(32)
        avl_readdatavalid = Signal()

        csr_address       = Signal(6)
        csr_read          = Signal()
        csr_write         = Signal()
        csr_writedata     = Signal(32)
        csr_readdata      = Signal(32)
        csr_waitrequest   = Signal()
        csr_readdatavalid = Signal()

        busy      = Signal() # A read has been accepted; waiting for its data.
        owner     = Signal() # 0: XIP bus, 1: storage bus.
        erasing   = Signal() # Erase engine owns the flash; memory port blocked.
        xip_req   = self.bus.cyc & self.bus.stb
        issue     = Signal()
        grant     = Signal()

        # The ASMI Avalon port is word-addressed (the generated IP converts
        # it to byte addresses itself). The SoC bus strips the region origin,
        # so add only the flash offset expressed in 32-bit words.
        self.comb += [
            issue.eq(~busy & ~erasing),
            self.bus.dat_r.eq(avl_readdata),
            self.bus.ack.eq(busy & ~owner & avl_readdatavalid),
        ]
        self.sync += If(~busy,
            If(avl_read & ~avl_waitrequest,
                busy.eq(1),
                owner.eq(grant),
            )
        ).Elif(avl_readdatavalid,
            busy.eq(0)
        )

        if not with_storage:
            self.comb += [
                avl_address.eq(self.bus.adr + flash_offset//4),
                avl_read.eq(xip_req & issue),
                avl_byteenable.eq(0b1111),
            ]
        else:
            assert storage_offset % self.ERASE_SIZE == 0
            assert storage_size % self.ERASE_SIZE == 0
            assert storage_size & (storage_size - 1) == 0
            self.storage = wishbone.Interface(data_width=32)
            storage_req  = self.storage.cyc & self.storage.stb
            storage_word = self.storage.adr[:log2_int(storage_size) - 2]

            # XIP has priority; Zephyr executes from SDRAM, so contention only
            # exists while the BIOS runs from flash, which never uses storage.
            self.comb += [
                grant.eq(~xip_req),
                If(grant,
                    avl_address.eq(storage_word + storage_offset//4),
                    avl_read.eq(storage_req & ~self.storage.we & issue),
                    avl_write.eq(storage_req & self.storage.we & issue),
                    avl_byteenable.eq(self.storage.sel),
                ).Else(
                    avl_address.eq(self.bus.adr + flash_offset//4),
                    avl_read.eq(issue),
                    avl_byteenable.eq(0b1111),
                ),
                avl_writedata.eq(self.storage.dat_w),
                self.storage.dat_r.eq(avl_readdata),
                # A write is acknowledged when the IP accepts it. The IP then
                # holds waitrequest until the flash finished programming, so
                # the next flash access waits instead of reading a busy flash.
                self.storage.ack.eq((busy & owner & avl_readdatavalid) |
                                    (avl_write & ~avl_waitrequest)),
            ]

            # Erase engine -------------------------------------------------------------------------
            self.erase = CSRStorage(32, description=
                "Write a byte offset within the storage window to erase its 4 KiB block.")
            self.status = CSRStatus(fields=[
                CSRField("busy",  size=1, description="Erase in progress."),
                CSRField("flash", size=8, offset=8, description="Last flash status register read."),
            ])
            erase_address = Signal(24)
            flash_status  = Signal(8)
            self.comb += self.status.fields.flash.eq(flash_status)
            self.fsm = fsm = FSM(reset_state="IDLE")
            fsm.act("IDLE",
                If(self.erase.re,
                    NextValue(erase_address, storage_offset +
                        (self.erase.storage[:log2_int(storage_size)] & ~(self.ERASE_SIZE - 1))),
                    NextState("WAIT-MEM")
                )
            )
            # Let a pending read or programming operation finish first, then
            # block new memory-port requests until the flash is idle again.
            fsm.act("WAIT-MEM",
                erasing.eq(1),
                If(~busy & ~avl_waitrequest, NextState("WREN"))
            )
            fsm.act("WREN",
                erasing.eq(1),
                csr_address.eq(0),
                csr_writedata.eq(1),
                csr_write.eq(1),
                If(~csr_waitrequest, NextState("ERASE"))
            )
            fsm.act("ERASE",
                erasing.eq(1),
                csr_address.eq(5),
                csr_writedata.eq(erase_address),
                csr_write.eq(1),
                If(~csr_waitrequest, NextState("POLL"))
            )
            fsm.act("POLL",
                erasing.eq(1),
                csr_address.eq(3),
                csr_read.eq(1),
                If(~csr_waitrequest, NextState("POLL-DATA"))
            )
            fsm.act("POLL-DATA",
                erasing.eq(1),
                If(csr_readdatavalid,
                    NextValue(flash_status, csr_readdata[:8]),
                    If(csr_readdata[0], # WIP
                        NextState("POLL")
                    ).Else(
                        NextState("IDLE")
                    )
                )
            )
            self.comb += self.status.fields.busy.eq(~fsm.ongoing("IDLE"))

        ip_dir = os.path.join(os.path.dirname(__file__), "ip", "asmi_xip")
        platform.add_ip(os.path.join(ip_dir, "asmi_xip.qip"))
        self.specials += Instance("asmi_xip",
            i_clk_clk                   = ClockSignal(),
            i_reset_reset_n             = ~ResetSignal(),
            i_avl_csr_address           = csr_address,
            i_avl_csr_read              = csr_read,
            i_avl_csr_write             = csr_write,
            i_avl_csr_writedata         = csr_writedata,
            o_avl_csr_readdata          = csr_readdata,
            o_avl_csr_waitrequest       = csr_waitrequest,
            o_avl_csr_readdatavalid     = csr_readdatavalid,
            i_avl_mem_write             = avl_write,
            i_avl_mem_burstcount        = Constant(1, 7),
            i_avl_mem_read              = avl_read,
            i_avl_mem_address           = avl_address,
            i_avl_mem_writedata         = avl_writedata,
            i_avl_mem_byteenable        = avl_byteenable,
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
    # Mutable tail of the W25Q16 (last 256 KiB), exposed uncached in the IO
    # region. The Zephyr boot image must end below STORAGE_FLASH_OFFSET.
    STORAGE_FLASH_OFFSET = 0x001c0000
    STORAGE_SIZE         = 0x00040000
    STORAGE_CPU_ORIGIN   = 0x90000000

    def __init__(self, sys_clk_freq=50e6, with_led_chaser=True, with_buttons=False,
        with_ethernet=False, with_etherbone=False, eth_ip="192.168.1.241",
        eth_dynamic_ip=False, with_zephyr_flash_boot=False, with_flash_storage=False, **kwargs):
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
        self.asmi = ASMIFlash(platform, self.XIP_FLASH_OFFSET,
            storage_offset = self.STORAGE_FLASH_OFFSET,
            storage_size   = self.STORAGE_SIZE if with_flash_storage else 0)
        self.bus.add_slave("rom", self.asmi.bus, SoCRegion(
            origin = self.XIP_CPU_ORIGIN,
            size   = xip_rom_size,
            mode   = "rx",
            cached = True,
            linker = True,
        ), strip_origin=True)
        if with_flash_storage:
            self.bus.add_slave("storage", self.asmi.storage, SoCRegion(
                origin = self.STORAGE_CPU_ORIGIN,
                size   = self.STORAGE_SIZE,
                cached = False,
            ), strip_origin=True)
            self.add_constant("STORAGE_FLASH_OFFSET", self.STORAGE_FLASH_OFFSET)

        if with_zephyr_flash_boot:
            zephyr_flash_address = self.XIP_CPU_ORIGIN + (
                self.ZEPHYR_FLASH_OFFSET - self.XIP_FLASH_OFFSET)
            # BIOS validates the FBI length/CRC, copies it to SDRAM and jumps.
            # A bad or absent image falls through to serial boot for recovery.
            self.add_constant("FLASH_BOOT_ADDRESS", zephyr_flash_address)
            self.add_constant("FLASH_BOOT_REGION_BASE", self.XIP_CPU_ORIGIN)
            # With storage, the boot image may not extend into the flash tail.
            self.add_constant("FLASH_BOOT_REGION_SIZE", (
                self.STORAGE_FLASH_OFFSET - self.XIP_FLASH_OFFSET) if with_flash_storage else xip_rom_size)
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
                    # Zephyr's LiteEth driver alternates between two TX slots.
                    ntxslots   = 2,
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
    parser.add_target_argument("--with-flash-storage", action="store_true",
        help="Expose the last 256 KiB of SPI flash as writable storage with a guarded erase engine.")
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
        with_flash_storage     = args.with_flash_storage,
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
