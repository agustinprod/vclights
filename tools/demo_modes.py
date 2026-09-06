#!/usr/bin/env python3
"""Recorre unos cuantos modos del firmware para verlos.

    python tools/demo_modes.py [segundos_por_modo]
"""
import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from vclight import Group, discover
from vclight import protocol as p

MOSTRAR = [1, 6, 8, 14]


async def main(hold):
    encontradas = await discover(15)
    if not encontradas:
        print("sin lamparas al alcance")
        return
    async with Group([f.device for f in encontradas]) as g:
        print(f"{len(g)} lampara(s)\n")
        await g.on()
        for mid in MOSTRAR:
            cmd = p.cmd_mode(mid, speed=60, brightness=100, colors=(0, 1, 2, 3))
            print(f"  modo {mid:>2}  {p.MODES[mid]:<16} {cmd.hex(' ')}", flush=True)
            await g.send(cmd)
            await asyncio.sleep(hold)
        print("\n  vuelta a color fijo")
        await g.rgb(255, 180, 110)


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 7.0))
