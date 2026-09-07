#!/usr/bin/env python3
"""Run each scene and photograph it, to see how it really looks.

Reading a scene's code tells you nothing about whether it reads well on
the wall. This runs each one, grabs a frame partway through, and lays
them out together.

It is also what caught two design faults that no amount of reading would
have: a sunrise whose 180-second arc never started inside a 40-second
slot, and a storm whose lulls landed on 6 of 255 after gamma and so were
simply black.

    python tools/photograph_scenes.py [seconds_per_scene]
"""
import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from camera_probe import OUT, capture, contact_sheet, saved_box   # noqa: E402

from vclight import Group, discover                               # noqa: E402
from vclight.scenes import RUNNING_ORDER, SCENES, render          # noqa: E402


async def main(secs):
    found = await discover(15)
    if not found:
        print("no lamps in range")
        return
    box = saved_box()
    panels = []
    async with Group([f.device for f in found]) as g:
        await g.on()
        await g.brightness(255)
        for name, _ in RUNNING_ORDER:
            scene_fn = SCENES[name]
            job = asyncio.create_task(render(g, scene_fn, secs))
            await asyncio.sleep(secs * 0.55)     # partway in, not at the start
            img = capture(OUT / f"scene_{name}.jpg")
            panels.append((name, img.crop(box) if box else img))
            print(f"  {name:<9} photographed", flush=True)
            await job
        await g.rgb(255, 180, 110)
        await g.brightness(255)
        await asyncio.sleep(1)
    print("\n" + str(contact_sheet(panels, OUT / "scenes.jpg")))


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 9.0))
