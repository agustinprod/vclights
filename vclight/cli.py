"""Command line interface.

    python -m vclight scan              find lamps and read their signal
    python -m vclight find              live proximity meter
    python -m vclight modes             list the 18 firmware modes
    python -m vclight colors            list the internal palette
    python -m vclight mode 5 --speed 50 start a firmware mode
    python -m vclight fx fire 60        run a computer-side animation
    python -m vclight scene plasma 60   run a perceptual-colour scene
    python -m vclight show              six scenes strung together
    python -m vclight color 255 80 0    static colour
    python -m vclight on / off
"""
import argparse
import asyncio
import sys
import time

from . import protocol as p
from .effects import EFFECTS, play
from .lamp import Group, discover
from .scenes import SCENES, render, show


async def _group(timeout):
    """Find lamps and wrap them in a group. Fails with a useful message
    when there are none, which is by far the commonest error."""
    found = await discover(timeout)
    if not found:
        print("No lamps in range.\n"
              "  - Check they have power.\n"
              "  - Close the Raingel app: while the phone holds the lamp,\n"
              "    it stops advertising and nobody else can see it.")
        sys.exit(1)
    print(f"{len(found)} lamp(s): " +
          ", ".join(f"{f.address[:8]} {f.rssi} dBm" for f in found))
    return Group([f.device for f in found])


async def cmd_scan(args):
    for f in await discover(args.timeout):
        print(f"{f.rssi:>5} dBm  {f.address}")
        print(f"             {f.describe()}   {f.distance()}")
        if not f.is_magic:
            print("             note: no addressable LEDs, effects will not "
                  "travel along the strip")


async def cmd_find(args):
    """Proximity meter. Walk around with the laptop: the number rises as
    you close in. It is the only way to find a mislaid lamp, since the
    device has neither a buzzer nor a display."""
    last = {}

    def seen(device, adv):
        if (adv.local_name or device.name or "").upper() == p.DEVICE_NAME:
            last[device.address] = (adv.rssi, time.time())

    from bleak import BleakScanner
    scanner = BleakScanner(detection_callback=seen)
    await scanner.start()
    t0 = time.time()
    try:
        while time.time() - t0 < args.seconds:
            await asyncio.sleep(2)
            print(f"--- t={time.time() - t0:4.0f}s ---")
            for addr, (rssi, ts) in sorted(last.items()):
                if time.time() - ts > 6:
                    print(f"  {addr[:8]}  (no signal)")
                    continue
                bar = "#" * max(0, min(20, int((rssi + 100) / 3)))
                print(f"  {addr[:8]}  [{bar:<20}] {rssi:>4} dBm")
            sys.stdout.flush()
    finally:
        await scanner.stop()


async def cmd_modes(args):
    print("Firmware modes (opcode 07).")
    print("Official names, from the APK's scene_magic array.\n")
    for i, name in p.MODES.items():
        extra = p.SPECIAL_FLAG.get(i, "")
        print(f"  {i:>2}  {name:<12}" + (f"  --direction switches: {extra}" if extra else ""))
    print("\n--direction reverses the travel, --section splits it into runs.")
    print("A later colour command cancels the mode: start it and send nothing else.")


async def cmd_colors(args):
    print("Internal firmware palette. Use the indices with --colors.\n")
    for i, name in p.PALETTE.items():
        r, g, b = p.PALETTE_RGB[i]
        print(f"  {i}  {name:<8} about rgb({r}, {g}, {b})")
    print("\nThe 19 combinations the app itself offers:\n")
    for i, combo in enumerate(p.PRESETS):
        mark = "   <- spectral order" if combo == p.SPECTRUM else ""
        print(f"  {i:>2}  --colors {' '.join(map(str, combo)):<16} "
              f"{p.palette_names(combo)}{mark}")


async def cmd_mode(args):
    async with await _group(args.timeout) as g:
        await g.on()
        await g.mode(args.id, speed=args.speed, brightness=args.brightness,
                     colors=tuple(args.colors), direction=args.direction,
                     section=args.section)
        # The write has no response: it returns at once because the system
        # queues it. Disconnecting right here can lose the packet before
        # it ever goes out. A second is enough for it to leave.
        await asyncio.sleep(1.0)
        print(f"mode {args.id} ({p.MODES[args.id]}) started; it now runs on its own")


async def cmd_fx(args):
    if args.name not in EFFECTS:
        print("Available effects:\n")
        for k, fn in EFFECTS.items():
            print(f"  {k:<10} {fn.desc}")
        return
    async with await _group(args.timeout) as g:
        print(f"effect '{args.name}' for {args.seconds:.0f}s")
        await play(g, args.name, args.seconds)
        print("done")


async def cmd_scene(args):
    """Scenes from the perceptual engine: OKLab colour, gamma corrected."""
    if args.name not in SCENES:
        print("Available scenes:\n")
        for k, fn in SCENES.items():
            print(f"  {k:<10} {fn.desc}")
        return
    async with await _group(args.timeout) as g:
        await g.on()
        print(f"scene '{args.name}' for {args.seconds:.0f}s")
        try:
            await render(g, SCENES[args.name], args.seconds)
        finally:
            await g.rgb(255, 180, 110)
            await g.brightness(255)


async def cmd_show(args):
    """The full show: six scenes with cross-fades between them."""
    async with await _group(args.timeout) as g:
        await g.on()
        print()
        try:
            await show(g, scale=args.scale)
        finally:
            await g.rgb(255, 180, 110)
            await g.brightness(255)


async def cmd_color(args):
    async with await _group(args.timeout) as g:
        await g.on()
        await g.brightness(args.brightness)
        await g.rgb(args.r, args.g, args.b)
        await asyncio.sleep(1.0)      # let the write leave before closing


async def cmd_power(args):
    async with await _group(args.timeout) as g:
        await (g.on() if args.on else g.off())
        await asyncio.sleep(1.0)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vclight", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeout", type=float, default=12.0,
                    help="seconds to scan before connecting")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan", help="list the lamps in range").set_defaults(fn=cmd_scan)

    f = sub.add_parser("find", help="live proximity meter")
    f.add_argument("seconds", nargs="?", type=float, default=300)
    f.set_defaults(fn=cmd_find)

    sub.add_parser("modes", help="list the firmware modes").set_defaults(fn=cmd_modes)
    sub.add_parser("colors", help="list the internal palette").set_defaults(fn=cmd_colors)

    m = sub.add_parser("mode", help="start a firmware mode")
    m.add_argument("id", type=int, choices=sorted(p.MODES))
    m.add_argument("--speed", type=int, default=50)
    m.add_argument("--brightness", type=int, default=100)
    m.add_argument("--colors", type=int, nargs="+", default=[0, 1],
                   help="indices into the internal palette, 0 to 7")
    m.add_argument("--direction", type=int, choices=[0, 1], default=0)
    m.add_argument("--section", type=int, choices=[0, 1], default=0)
    m.set_defaults(fn=cmd_mode)

    x = sub.add_parser("fx", help="run a computer-side animation")
    x.add_argument("name", nargs="?", default="")
    x.add_argument("seconds", nargs="?", type=float, default=20)
    x.set_defaults(fn=cmd_fx)

    s_ = sub.add_parser("scene", help="run a perceptual-colour scene")
    s_.add_argument("name", nargs="?", default="")
    s_.add_argument("seconds", nargs="?", type=float, default=60)
    s_.set_defaults(fn=cmd_scene)

    sh = sub.add_parser("show", help="six scenes strung together")
    sh.add_argument("--scale", type=float, default=1.0,
                    help="multiplies every duration; 0.25 gives a short version")
    sh.set_defaults(fn=cmd_show)

    c = sub.add_parser("color", help="static colour")
    c.add_argument("r", type=int); c.add_argument("g", type=int); c.add_argument("b", type=int)
    c.add_argument("--brightness", type=int, default=255)
    c.set_defaults(fn=cmd_color)

    sub.add_parser("on").set_defaults(fn=cmd_power, on=True)
    sub.add_parser("off").set_defaults(fn=cmd_power, on=False)

    args = ap.parse_args(argv)
    asyncio.run(args.fn(args))


if __name__ == "__main__":
    main()
