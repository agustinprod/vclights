#!/usr/bin/env python3
"""Find the right colour order for each lamp, by photographing red.

The problem
-----------
These strips can be wired with the chip's colour channels in any order.
When the order the firmware assumes does not match the hardware, every
colour comes out permuted: send red, get green. Two lamps of the same
model can differ, and ours do.

The fix is opcode 0E, which the app sends as tab position + 1. Three
channels give six possible orders, so this walks 1 to 6, sends pure red
after each, and photographs the result. The right value is the one where
red actually looks red.

    python tools/fix_color_order.py                 sweep every lamp at once
    python tools/fix_color_order.py --lamp 5BF1A60D  sweep just that one
    python tools/fix_color_order.py 1               set order 1 everywhere
    python tools/fix_color_order.py 1 --lamp 5BF1     set it on one lamp

Lamps are addressed by an address prefix, never by position. discover()
sorts by signal strength, so an index points at a different lamp as soon
as one of them gets a better signal, and a sweep ends up reporting on the
wrong device.

Sweep one lamp at a time when they disagree: the order command goes to
whatever is connected, so with two lamps needing different values no
single panel can look right on both.
"""
import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from camera_probe import (OUT, capture, contact_sheet, lamp_box,   # noqa: E402
                          save_box, saved_box)
from vclight import Group, discover                              # noqa: E402
from vclight import protocol as p                                # noqa: E402


async def sweep(only=None):
    OUT.mkdir(exist_ok=True)
    found = await discover(15)
    if not found:
        print("no lamps in range")
        return
    if only:
        found = [f for f in found if f.address.upper().startswith(only.upper())]
        if not found:
            print(f"no lamp whose address starts with {only}")
            return
    print(f"{len(found)} lamp(s): " + ", ".join(f.address[:8] for f in found))

    async with Group([f.device for f in found]) as g:
        box = saved_box()
        if box is None:
            await g.send(p.cmd_power(False))
            await asyncio.sleep(2.5)
            off = capture(OUT / "order_off.jpg")
            await g.send(p.cmd_power(True))
            await g.send(p.cmd_color(255, 255, 255))
            await asyncio.sleep(2.5)
            box = lamp_box(capture(OUT / "order_on.jpg"), off)
            save_box(box)
        await g.send(p.cmd_power(True))
        await g.send(p.cmd_brightness(255))

        panels = []
        for order in range(1, 7):
            await g.send(p.cmd_ic_order(order))
            await asyncio.sleep(0.6)
            await g.send(p.cmd_color(255, 0, 0))     # pure red, nothing else
            await asyncio.sleep(2.2)
            img = capture(OUT / f"order_{order}.jpg")
            panels.append((f"order {order} + red", img.crop(box) if box else img))
            print(f"  order {order}: sent 0e {order:02x}, then red", flush=True)

        sheet = contact_sheet(panels, OUT / "order_sheet.jpg")
        print(f"\n  contact sheet: {sheet}")
        print("  the right order is the panel where the tube looks RED")


async def apply(order, only=None):
    found = await discover(15)
    if not found:
        print("no lamps in range")
        return
    if only:
        found = [f for f in found if f.address.upper().startswith(only.upper())]
        if not found:
            print(f"no lamp whose address starts with {only}")
            return
    async with Group([f.device for f in found]) as g:
        print(f"target: " + ", ".join(f.address[:8] for f in found))
        await g.send(p.cmd_ic_order(order))
        await asyncio.sleep(0.8)
        await g.send(p.cmd_color(255, 0, 0))
        await asyncio.sleep(1.0)
        print(f"order {order} applied to {len(g)} lamp(s); showing red")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    only = None
    if "--lamp" in args:
        i = args.index("--lamp")
        only = args[i + 1]
        del args[i:i + 2]
    if args:
        asyncio.run(apply(int(args[0], 0), only))
    else:
        asyncio.run(sweep(only))
