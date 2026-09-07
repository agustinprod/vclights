#!/usr/bin/env python3
"""Walk through a few firmware modes to see them.

Each mode is left running for a while, and nothing is sent in between:
any colour command would cancel it.

    python tools/demo_modes.py [seconds_per_mode]
"""
import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from vclight import Group, discover
from vclight import protocol as p

SHOW = [5, 9, 11, 13]      # meteor, wave, rainbow, bounce


async def main(hold):
    found = await discover(15)
    if not found:
        print("no lamps in range")
        return
    async with Group([f.device for f in found]) as g:
        print(f"{len(g)} lamp(s)\n")
        await g.on()
        for mid in SHOW:
            cmd = p.cmd_mode(mid, speed=60, brightness=100, colors=(0, 1, 2, 3))
            print(f"  mode {mid:>2}  {p.MODES[mid]:<12} {cmd.hex(' ')}", flush=True)
            await g.send(cmd)
            await asyncio.sleep(hold)
        print("\n  back to static colour")
        await g.rgb(255, 180, 110)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 12.0))
