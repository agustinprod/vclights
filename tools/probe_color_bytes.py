#!/usr/bin/env python3
"""Work out what the six bytes of the colour command actually do.

The app sends ColorAdjust(r, g, b, 0, 0, 0) and always leaves the last
three at zero, so what they are for is not documented anywhere. On top of
that, on some magic strips a single global colour command comes out as
several bars of different colours, which the r-g-b reading does not
explain.

This walks one byte at a time to full scale and waits for you between
steps, so you can look at the lamp without racing a script.

    python tools/probe_color_bytes.py
"""
import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from vclight import Lamp, discover

STEPS = [
    ("byte 1 full", [0xFF, 0, 0, 0, 0, 0],
     "red across the whole strip means byte 1 is red, as the app implies"),
    ("byte 2 full", [0, 0xFF, 0, 0, 0, 0], "green would mean byte 2 is green"),
    ("byte 3 full", [0, 0, 0xFF, 0, 0, 0], "blue would mean byte 3 is blue"),
    ("byte 4 full", [0, 0, 0, 0xFF, 0, 0],
     "if this lights anything, the app is wasting a real channel"),
    ("byte 5 full", [0, 0, 0, 0, 0xFF, 0], "same question"),
    ("byte 6 full", [0, 0, 0, 0, 0, 0xFF], "same question"),
    ("first three full", [0xFF, 0xFF, 0xFF, 0, 0, 0],
     "clean white means the triple really is RGB and only the chip order is off"),
]


async def main():
    found = await discover(15)
    if not found:
        print("no lamps in range")
        return
    f = found[0]
    print(f"one lamp only: {f.address[:8]}  {f.describe()}\n")
    print("For each step, note the COLOUR and WHERE: the whole strip, one bar,")
    print("or several bars in different colours. Press Enter to advance.\n")

    async with Lamp(f.device) as lamp:
        await lamp.on()
        await lamp.brightness(255)
        await asyncio.sleep(0.5)
        for name, payload, meaning in STEPS:
            cmd = bytes([0x03] + payload)
            print(f"  {name:<18} {cmd.hex(' ')}")
            print(f"    {meaning}")
            await lamp.send(cmd)
            await asyncio.sleep(0.4)     # let the write leave before we block
            input("    [Enter to continue] ")
        print("\n  leaving warm white")
        await lamp.send(bytes([0x03, 0xFF, 0xB4, 0x6E, 0, 0, 0]))
        await asyncio.sleep(1.0)


if __name__ == "__main__":
    asyncio.run(main())
