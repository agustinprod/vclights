#!/usr/bin/env python3
"""Send commands, photograph the lamps, build one contact sheet to read.

Why this exists
---------------
The protocol acknowledges nothing, so the only way to verify a command
is to look at the lamp. That puts a person in the loop for every test.
A webcam takes them out of it.

Automatic colour measurement was tried first and abandoned. The webcam
re-runs its own exposure and white balance on every shot, so the frame
shifts between captures and background subtraction lights up the whole
room; and skin tones sit in the same hue range as a warm lamp. Reading
the pictures directly is less clever and works.

The tubes are located once from a dark frame against a bright one, and
every capture is cropped to them. One image comes out with every step
side by side, labelled.

Requires ffmpeg and camera permission for the terminal.

    python tools/camera_probe.py
"""
import asyncio
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from vclight import Group, discover
from vclight import protocol as p

OUT = Path("captures")
CAM = "0"
TILE_H = 260          # height of each panel in the contact sheet


def capture(path):
    """Grab one frame. nv12 is forced: the built-in camera rejects
    ffmpeg's default pixel format."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "avfoundation",
         "-pixel_format", "nv12", "-framerate", "30", "-i", CAM,
         "-frames:v", "1", "-y", str(path)],
        check=True, timeout=40)
    return Image.open(path)


BOX_FILE = OUT / "box.json"


def saved_box():
    """Reuse a crop that worked before.

    Automatic detection depends on the room being dark and nobody
    walking through the shot. Once a good crop is known, keeping it is
    more reliable than finding it again, and it keeps the rest of the
    room out of every capture.
    """
    import json
    if BOX_FILE.exists():
        try:
            return tuple(json.load(open(BOX_FILE)))
        except Exception:
            return None
    return None


def save_box(box):
    import json
    if box:
        BOX_FILE.write_text(json.dumps(list(int(v) for v in box)))


def lamp_box(on_img, off_img, margin=40):
    """Bounding box of whatever lit up between the two frames.

    Cropping to this keeps the contact sheet small and keeps the rest of
    the room out of it.
    """
    a = np.asarray(on_img.convert("RGB"), dtype=np.float32)
    b = np.asarray(off_img.convert("RGB"), dtype=np.float32)
    d = (a - b).clip(0, None).mean(axis=2)
    if d.max() < 15:
        return None
    ys, xs = np.where(d > max(25.0, float(np.percentile(d, 99.5))))
    if len(xs) < 50:
        return None
    h, w = d.shape
    return (max(0, xs.min() - margin), max(0, ys.min() - margin),
            min(w, xs.max() + margin), min(h, ys.max() + margin))


def contact_sheet(panels, path):
    """Lay every capture out in a row, each with its label."""
    tiles = []
    for label, img in panels:
        scale = TILE_H / img.height
        t = img.resize((max(1, int(img.width * scale)), TILE_H))
        strip = Image.new("RGB", (t.width, TILE_H + 22), (16, 16, 16))
        strip.paste(t, (0, 22))
        ImageDraw.Draw(strip).text((4, 6), label[:40], fill=(235, 235, 235))
        tiles.append(strip)
    total = sum(t.width + 4 for t in tiles)
    sheet = Image.new("RGB", (total, TILE_H + 22), (16, 16, 16))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width + 4
    sheet.save(path, quality=88)
    return path


async def run(steps, settle=2.2):
    OUT.mkdir(exist_ok=True)
    found = await discover(15)
    if not found:
        print("no lamps in range")
        return
    print(f"{len(found)} lamp(s): " + ", ".join(f.address[:8] for f in found))

    async with Group([f.device for f in found]) as g:
        await g.send(p.cmd_power(False))
        await asyncio.sleep(2.5)
        off = capture(OUT / "ref_off.jpg")
        await g.send(p.cmd_power(True))
        await g.send(p.cmd_brightness(255))
        await g.send(p.cmd_color(255, 255, 255))
        await asyncio.sleep(2.5)
        on = capture(OUT / "ref_on.jpg")

        box = lamp_box(on, off)
        print(f"  crop: {box}" if box else "  no crop found, using the full frame")

        panels = []
        for i, (label, cmd) in enumerate(steps, start=1):
            await g.send(cmd)
            await asyncio.sleep(settle)
            img = capture(OUT / f"{i:02d}.jpg")
            panels.append((label, img.crop(box) if box else img))
            print(f"  {i:>2}. {label:<26} {bytes(cmd).hex(' ')}", flush=True)

        sheet = contact_sheet(panels, OUT / "sheet.jpg")
        print(f"\n  contact sheet: {sheet}")


# The open questions, in order:
#   - do the three colour bytes behave as red, green and blue at all?
#   - do the last three bytes, which the app always zeroes, do anything?
#   - does a colour command really cancel a running mode?
#   - is there a mode 0?
STEPS = [
    ("1 red   03 ff0000",     p.cmd_color(255, 0, 0)),
    ("2 green 03 00ff00",     p.cmd_color(0, 255, 0)),
    ("3 blue  03 0000ff",     p.cmd_color(0, 0, 255)),
    ("4 white 03 ffffff",     p.cmd_color(255, 255, 255)),
    ("5 byte4 03 000000ff0000", bytes([0x03, 0, 0, 0, 0xFF, 0, 0])),
    ("6 byte5 03 00000000ff00", bytes([0x03, 0, 0, 0, 0, 0xFF, 0])),
    ("7 byte6 03 0000000000ff", bytes([0x03, 0, 0, 0, 0, 0, 0xFF])),
    ("8 mode 5 meteor",       p.cmd_mode(5, speed=60)),
    ("9 red after the mode",  p.cmd_color(255, 0, 0)),
    ("10 mode 0 unknown",     bytes([0x07, 0x00])),
]

if __name__ == "__main__":
    asyncio.run(run(STEPS))
