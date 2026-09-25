#!/usr/bin/env python3
"""Migen simulation of ASMIFlash (read cache, storage writes, erase engine).

The ASMI Parallel II IP is replaced by a behavioural model that follows the
generated RTL: one transaction at a time (waitrequest while busy), burst read
beats with arbitrary gaps and no read backpressure, NOR programming, erase
only after WREN, and RDSR polling on the CSR port. Wishbone masters mimic the
VexRiscv ibus line refill (8 beats, CTI 010/111, address incremented after
each ACK) and dbus single reads. A monitor checks every read ACK against the
flash contents at that moment.

Run from litex_cyc1000/:  source ./litex_env.sh && "$PYTHON" sim/asmi_flash_tb.py
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from migen import *
from migen.sim import run_simulation, passive

from soc import ASMIFlash

FLASH_WORDS    = 2*1024*1024 // 4
XIP_OFFSET     = 0x00100000
STORAGE_OFFSET = 0x001c0000
STORAGE_SIZE   = 0x00040000
XIP_BASE_W     = XIP_OFFSET // 4
ST_BASE_W      = STORAGE_OFFSET // 4
SECTOR_W       = 4096 // 4


class Flash:
    def __init__(self, rng):
        self.words  = [rng.getrandbits(32) for _ in range(FLASH_WORDS)]
        self.errors = []
        self.stats  = {"bursts": 0, "writes": 0, "erases": 0, "hits": 0, "reads": 0}

    def error(self, msg):
        if len(self.errors) < 20:
            self.errors.append(msg)


@passive
def avalon_model(dut, flash, rng, erase_busy):
    """ASMI memory port: waitrequest is low only while idle."""
    yield dut.avl_waitrequest.eq(0)
    yield
    while True:
        rd = yield dut.avl_read
        wr = yield dut.avl_write
        wait = yield dut.avl_waitrequest
        if rd and wr:
            flash.error("read and write asserted together")
        if (rd or wr) and not wait:
            if erase_busy[0]:
                flash.error("memory command accepted during erase")
            adr = yield dut.avl_address
            bc  = yield dut.avl_burstcount
            yield dut.avl_waitrequest.eq(1)
            if rd:
                flash.stats["bursts"] += 1
                if bc != 8 or adr % 8:
                    flash.error(f"unexpected read burst {bc} at {adr:#x}")
                # Command, address and dummy byte: 40 flash clocks.
                for _ in range(rng.choice([2, 40])):
                    yield
                for i in range(bc):
                    for _ in range(rng.choice([0, 0, 1, 3, 31])):
                        yield
                    yield dut.avl_readdata.eq(flash.words[adr + i])
                    yield dut.avl_readdatavalid.eq(1)
                    yield
                    yield dut.avl_readdatavalid.eq(0)
            else:
                flash.stats["writes"] += 1
                be   = yield dut.avl_byteenable
                data = yield dut.avl_writedata
                if bc != 1 or be not in (0x1, 0x2, 0x4, 0x8, 0x3, 0xc, 0xf):
                    flash.error(f"illegal write burst {bc} byteenable {be:#x}")
                if not ST_BASE_W <= adr < ST_BASE_W + STORAGE_SIZE//4:
                    flash.error(f"write outside storage at {adr:#x}")
                for _ in range(rng.randrange(3, 60)):
                    yield
                mask = sum(0xff << 8*b for b in range(4) if be >> b & 1)
                flash.words[adr] &= data | ~mask & 0xffffffff
            for _ in range(2): # STATE_COMPLETE, back to idle.
                yield
            yield dut.avl_waitrequest.eq(0)
        yield


@passive
def csr_model(dut, flash, rng, erase_busy):
    """ASMI CSR port: WREN (0), SUBSECTOR_ERASE (5), RD_STATUS (3)."""
    wel  = False
    busy = 0
    pending = None
    yield dut.csr_waitrequest.eq(0)
    yield
    while True:
        if busy:
            busy -= 1
            if busy == 0:
                start = pending - pending % SECTOR_W
                for w in range(start, start + SECTOR_W):
                    flash.words[w] = 0xffffffff
                erase_busy[0] = False
        wr = yield dut.csr_write
        rd = yield dut.csr_read
        if (wr or rd) and not (yield dut.csr_waitrequest):
            adr  = yield dut.csr_address
            data = yield dut.csr_writedata
            yield dut.csr_waitrequest.eq(1)
            yield
            if wr and adr == 0 and data == 1:
                wel = True
            elif wr and adr == 5:
                if not wel:
                    flash.error("erase without WREN")
                else:
                    flash.stats["erases"] += 1
                    pending, busy, wel = data // 4, rng.randrange(200, 2000), False
                    erase_busy[0] = True
                    if not ST_BASE_W <= pending < ST_BASE_W + STORAGE_SIZE//4:
                        flash.error(f"erase outside storage at {data:#x}")
            elif rd and adr == 3:
                yield dut.csr_readdata.eq(1 if busy else 0)
                yield dut.csr_readdatavalid.eq(1)
                yield
                yield dut.csr_readdatavalid.eq(0)
            yield dut.csr_waitrequest.eq(0)
        yield


@passive
def monitor(dut, flash):
    buses = [(dut.bus, XIP_BASE_W), (dut.storage, ST_BASE_W)]
    while True:
        for bus, base in buses:
            if (yield bus.ack):
                if not ((yield bus.cyc) and (yield bus.stb)):
                    flash.error("ACK without request")
                if not (yield bus.we):
                    adr = (yield bus.adr)
                    if bus is dut.storage:
                        adr &= STORAGE_SIZE//4 - 1
                    got, exp = (yield bus.dat_r), flash.words[base + adr]
                    flash.stats["reads"] += 1
                    if got != exp:
                        flash.error(f"read {base + adr:#x}: got {got:08x}, expected {exp:08x}")
        yield


def wb_access(bus, adr, we=0, dat=0, sel=0xf):
    yield bus.adr.eq(adr)
    yield bus.we.eq(we)
    yield bus.dat_w.eq(dat)
    yield bus.sel.eq(sel)
    yield bus.cti.eq(0)
    yield bus.cyc.eq(1)
    yield bus.stb.eq(1)
    yield
    while not (yield bus.ack):
        yield
    yield bus.cyc.eq(0)
    yield bus.stb.eq(0)
    yield


def wb_line_refill(bus, line):
    """VexRiscv InstructionCache.toWishbone(): 8 beats, CYC/STB held."""
    yield bus.adr.eq(line)
    yield bus.we.eq(0)
    yield bus.cti.eq(0b010)
    yield bus.cyc.eq(1)
    yield bus.stb.eq(1)
    yield
    beat = 0
    while beat < 8:
        if (yield bus.ack):
            beat += 1
            if beat < 8:
                yield bus.adr.eq(line + beat)
                yield bus.cti.eq(0b111 if beat == 7 else 0b010)
            else:
                yield bus.cyc.eq(0)
                yield bus.stb.eq(0)
        yield


def xip_master(dut, rng, n, windows):
    """BIOS-like XIP traffic: refills, byte-wise streams, table lookups."""
    for _ in range(n):
        base, size = rng.choice(windows)
        kind = rng.random()
        if kind < 0.3:
            yield from wb_line_refill(dut.bus, base + rng.randrange(size) // 8 * 8)
        elif kind < 0.6:
            start = base + rng.randrange(size)
            for w in range(start, min(start + rng.randrange(1, 24), base + size)):
                for _ in range(4): # lbu x4
                    yield from wb_access(dut.bus, w)
        else:
            yield from wb_access(dut.bus, base + rng.randrange(size))
        for _ in range(rng.choice([0, 0, 1, 5])):
            yield


def storage_master(dut, rng, n, flash):
    """LittleFS-like traffic in two sectors: reads, writes, erases."""
    sectors = [0, 3]
    for _ in range(n):
        sector = rng.choice(sectors) * SECTOR_W
        kind = rng.random()
        if kind < 0.05:
            yield dut.erase.storage.eq(sector * 4)
            yield dut.erase.re.eq(1)
            yield
            yield dut.erase.re.eq(0)
            yield
            while (yield dut.status.fields.busy):
                yield
        elif kind < 0.4:
            adr = sector + rng.randrange(64)
            sel = rng.choice([0x1, 0x2, 0x4, 0x8, 0x3, 0xc, 0xf])
            yield from wb_access(dut.storage, adr, we=1, dat=rng.getrandbits(32), sel=sel)
        else:
            adr = sector + rng.randrange(64)
            for w in range(adr, adr + rng.randrange(1, 12)):
                yield from wb_access(dut.storage, w)
        for _ in range(rng.choice([0, 0, 2, 7])):
            yield


def run(seed, cache_lines, concurrent, n):
    rng   = random.Random(seed)
    flash = Flash(rng)
    dut   = ASMIFlash(None, XIP_OFFSET, STORAGE_OFFSET, STORAGE_SIZE, cache_lines=cache_lines)
    erase_busy = [False]
    # XIP windows (word offsets from the XIP origin). The last one aliases
    # the storage sectors used by storage_master, so coherence is exercised.
    st_as_xip = ST_BASE_W - XIP_BASE_W
    windows = [(0x08000, 512), (0x20000, 256), (st_as_xip, 64), (st_as_xip + 3*SECTOR_W, 64)]

    def sequential():
        for _ in range(n):
            if rng.random() < 0.5:
                yield from xip_master(dut, rng, 1, windows)
            else:
                yield from storage_master(dut, rng, 1, flash)

    gens = [avalon_model(dut, flash, rng, erase_busy), csr_model(dut, flash, rng, erase_busy),
            monitor(dut, flash)]
    if concurrent:
        gens += [xip_master(dut, rng, n, windows), storage_master(dut, rng, n // 2, flash)]
    else:
        gens += [sequential()]
    run_simulation(dut, gens)
    return flash


def perf():
    """Cycles for a BIOS-like byte-wise read of 4 KiB with realistic timing."""
    rng   = random.Random(0)
    flash = Flash(rng)
    dut   = ASMIFlash(None, XIP_OFFSET, STORAGE_OFFSET, STORAGE_SIZE)
    cycles = [0]

    @passive
    def model():
        # 0x0B + 24-bit address + dummy, then 32+ flash clocks per word.
        yield dut.avl_waitrequest.eq(0)
        yield
        while True:
            if (yield dut.avl_read) and not (yield dut.avl_waitrequest):
                adr, bc = (yield dut.avl_address), (yield dut.avl_burstcount)
                yield dut.avl_waitrequest.eq(1)
                for _ in range(44):
                    yield
                for i in range(bc):
                    for _ in range(35):
                        yield
                    yield dut.avl_readdata.eq(flash.words[adr + i])
                    yield dut.avl_readdatavalid.eq(1)
                    yield
                    yield dut.avl_readdatavalid.eq(0)
                for _ in range(2):
                    yield
                yield dut.avl_waitrequest.eq(0)
            yield

    @passive
    def clock():
        while True:
            cycles[0] += 1
            yield

    def byte_reads():
        for w in range(0x8000, 0x8000 + 1024):
            for _ in range(4):
                yield from wb_access(dut.bus, w)

    run_simulation(dut, [model(), clock(), byte_reads()])
    return cycles[0]


def main():
    failed = False
    cases = [(1, 16, False), (2, 16, True), (3, 128, False), (4, 128, True), (5, 4, True)]
    for seed, lines, concurrent in cases:
        flash = run(seed, lines, concurrent, n=600)
        s = flash.stats
        print(f"seed {seed}, {lines:3d} lines, {'concurrent' if concurrent else 'sequential'}: "
              f"{s['reads']} reads, {s['bursts']} line fills, {s['writes']} writes, "
              f"{s['erases']} erases -> {'FAIL' if flash.errors else 'ok'}")
        for e in flash.errors:
            print("   ", e)
        failed |= bool(flash.errors) or s["erases"] == 0 or s["writes"] == 0
    cycles = perf()
    print(f"byte-wise read of 4 KiB: {cycles} cycles ({4096*50e6/cycles/1024:.0f} KiB/s at 50 MHz)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
