#!/usr/bin/env python3
"""Opcode sweep, to explore what the APK does not explain.

Sends unknown opcodes one at a time, with a pause, printing every byte it
sends. Watch the lamp while it runs and note the number on screen when
something changes.

WARNING: this writes arbitrary bytes to the firmware. F0, FE and FF are
excluded, since on this chip family they are usually a factory reset, but
the rest of the opcode space is undocumented. Use at your own risk.

    python tools/opcode_sweep.py 0x04 0x0F
"""
import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from vclight import Lamp, discover
from vclight import protocol as p

KNOWN = {p.OP_POWER, p.OP_BRIGHTNESS, p.OP_COLOR, p.OP_MODE}


async def main(lo, hi, pause=2.5):
    found = await discover(20)
    if not found:
        print("no lamps in range")
        return

    async with Lamp(found[0].device) as lamp:
        async def tx(data, wait=pause):
            print("  sending  " + " ".join(f"{b:02x}" for b in data), flush=True)
            await lamp.send(data)
            await asyncio.sleep(wait)

        print(f"connected to {lamp.address[:8]}. Baseline: static white.\n")
        await tx(p.cmd_color(255, 255, 255), 1)
        await tx(p.cmd_brightness(255), 1)
        await tx(p.cmd_power(True), 2)

        for op in range(lo, hi + 1):
            if op in KNOWN or op in p.DANGEROUS_OPCODES:
                continue
            print(f"--- opcode 0x{op:02x} ---")
            for arg in (0x01, 0x05):
                await tx(bytes([op, arg]))
            await tx(p.cmd_color(255, 255, 255), 1.5)   # back to baseline

        print("\ndone. Leaving warm white.")
        await tx(p.cmd_color(255, 180, 110), 1)


if __name__ == "__main__":
    a = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x04
    b = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x0F
    asyncio.run(main(a, b))
