#!/usr/bin/env python3
"""Photograph what the lamp actually shows, for the two colour checks
that turned out to matter.

    python tools/verify_colors.py primaries    red, green, blue per lamp
    python tools/verify_colors.py palette      the 8 internal palette entries

primaries
    Sends each primary to one lamp at a time and photographs it. This is
    how the colour order was settled: with the right order every primary
    matches, and a wrong one permutes them. It works on one lamp at a
    time because lamps are addressed individually and can need different
    orders.

palette
    Sends each palette index through a firmware mode and photographs it.
    The index is REPEATED, palette(3, 3), because a single-colour palette
    is discarded by the firmware, which falls back to its default red and
    green. This confirmed all eight entries against the APK reading.

Both write a labelled contact sheet into captures/. Needs ffmpeg, camera
permission for the terminal, and requirements-tools.txt.
"""
import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from camera_probe import OUT, capture, contact_sheet, saved_box   # noqa: E402

from vclight import Group, Lamp, discover                         # noqa: E402
from vclight import protocol as p                                 # noqa: E402

PRIMARIES = [("red", (255, 0, 0)), ("green", (0, 255, 0)), ("blue", (0, 0, 255))]


async def primaries(order=None):
    """One lamp at a time, each primary, photographed."""
    found = await discover(15)
    if not found:
        print("no lamps in range")
        return
    box = saved_box()
    panels = []
    for f in sorted(found, key=lambda x: x.address):
        async with Lamp(f.device) as lamp:
            await lamp.on()
            await lamp.brightness(255)
            if order is not None:
                await lamp.send(p.cmd_ic_order(order))
                await asyncio.sleep(0.8)
            for name, colour in PRIMARIES:
                await lamp.rgb(*colour)
                await asyncio.sleep(2.2)
                img = capture(OUT / f"prim_{f.address[:4]}_{name}.jpg")
                panels.append((f"{f.address[:4]} {name}", img.crop(box) if box else img))
                print(f"  {f.address[:8]}  sent {name}", flush=True)
    print("\n" + str(contact_sheet(panels, OUT / "primaries.jpg")))


async def palette():
    """Each palette index on its own, through a mode."""
    found = await discover(15)
    if not found:
        print("no lamps in range")
        return
    box = saved_box()
    panels = []
    async with Group([f.device for f in found]) as g:
        await g.on()
        await g.brightness(255)
        for i in range(8):
            # The index is repeated: one colour alone gets discarded.
            await g.send(p.cmd_mode(2, speed=100, brightness=100, colors=(i, i)))
            await asyncio.sleep(3.0)
            img = capture(OUT / f"pal_{i}.jpg")
            panels.append((f"{i} = {p.PALETTE[i]}", img.crop(box) if box else img))
            print(f"  index {i}: expecting {p.PALETTE[i]}", flush=True)
        await g.rgb(255, 180, 110)
        await asyncio.sleep(1)
    print("\n" + str(contact_sheet(panels, OUT / "palette.jpg")))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "primaries"
    order = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    asyncio.run(palette() if what == "palette" else primaries(order))
