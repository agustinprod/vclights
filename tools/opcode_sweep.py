#!/usr/bin/env python3
"""Barrido de opcodes, para explorar lo que el APK no cuenta.

Manda opcodes desconocidos uno a uno, con pausa, e imprime cada byte que
envia. Hay que mirar la lampara mientras corre y apuntar el numero que
salia por pantalla cuando hizo algo distinto.

AVISO: escribe bytes arbitrarios en el firmware. Estan excluidos F0, FE
y FF, que en esta familia de chips suelen ser reset de fabrica, pero el
resto del espacio de opcodes no esta documentado. Uso bajo tu riesgo.

    python tools/opcode_sweep.py 0x04 0x0F
"""
import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from vclight import discover, Lamp
from vclight import protocol as p

CONOCIDOS = {p.OP_POWER, p.OP_BRIGHTNESS, p.OP_COLOR, p.OP_MODE}


async def main(lo, hi, pausa=2.5):
    encontradas = await discover(20)
    if not encontradas:
        print("sin lamparas al alcance")
        return

    async with Lamp(encontradas[0].device) as lamp:
        async def tx(data, espera=pausa):
            print("  enviando  " + " ".join(f"{b:02x}" for b in data), flush=True)
            await lamp.send(data)
            await asyncio.sleep(espera)

        print(f"conectado a {lamp.address[:8]}. Base: blanco fijo.\n")
        await tx(p.cmd_color(255, 255, 255), 1)
        await tx(p.cmd_brightness(255), 1)
        await tx(p.cmd_power(True), 2)

        for op in range(lo, hi + 1):
            if op in CONOCIDOS or op in p.OP_PELIGROSOS:
                continue
            print(f"--- opcode 0x{op:02x} ---")
            for arg in (0x01, 0x05):
                await tx(bytes([op, arg]))
            await tx(p.cmd_color(255, 255, 255), 1.5)   # volver a la base

        print("\nfin. Dejo blanco calido.")
        await tx(p.cmd_color(255, 180, 110), 0.3)


if __name__ == "__main__":
    a = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x04
    b = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x0F
    asyncio.run(main(a, b))
