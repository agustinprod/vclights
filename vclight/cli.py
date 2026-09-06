"""Interfaz de linea de ordenes.

    python -m vclight scan              busca lamparas y mide su senal
    python -m vclight find              medidor de proximidad en vivo
    python -m vclight modes             lista los 18 modos del firmware
    python -m vclight mode 8 --speed 70 lanza un modo del firmware
    python -m vclight fx fire 60        lanza una animacion del ordenador
    python -m vclight scene plasma 60   lanza una escena en color perceptual
    python -m vclight show              espectaculo de 6 escenas encadenadas
    python -m vclight color 255 80 0    color fijo
    python -m vclight on / off
"""
import argparse
import asyncio
import sys
import time

from . import protocol as p
from .effects import EFFECTS, play
from .scenes import SCENES, render, show
from .lamp import Group, Lamp, discover


async def _group(timeout):
    """Busca lamparas y devuelve un grupo con todas. Falla con un mensaje
    util si no hay ninguna, que es el error mas comun."""
    encontradas = await discover(timeout)
    if not encontradas:
        print("No hay lamparas al alcance.\n"
              "  - Comprueba que tienen corriente.\n"
              "  - Cierra la app Raingel: mientras el movil esta conectado,\n"
              "    la lampara deja de anunciarse y nadie mas la ve.")
        sys.exit(1)
    print(f"{len(encontradas)} lampara(s): " +
          ", ".join(f"{f.address[:8]} {f.rssi} dBm" for f in encontradas))
    return Group([f.device for f in encontradas])


async def cmd_scan(args):
    for f in await discover(args.timeout):
        print(f"{f.rssi:>5} dBm  {f.address}")
        print(f"             {f.describe()}   {f.distancia()}")
        if not f.is_magic:
            print("             aviso: sin LEDs direccionables, los efectos "
                  "no se desplazan por la tira")


async def cmd_find(args):
    """Medidor de proximidad. Camina con el portatil: el numero sube
    cuando te acercas. Es el unico modo de encontrar una lampara perdida,
    porque el aparato no tiene ni zumbador ni pantalla."""
    ultimo = {}

    def visto(device, adv):
        if (adv.local_name or device.name or "").upper() == p.DEVICE_NAME:
            ultimo[device.address] = (adv.rssi, time.time())

    from bleak import BleakScanner
    scanner = BleakScanner(detection_callback=visto)
    await scanner.start()
    t0 = time.time()
    try:
        while time.time() - t0 < args.seconds:
            await asyncio.sleep(2)
            print(f"--- t={time.time() - t0:4.0f}s ---")
            for addr, (rssi, ts) in sorted(ultimo.items()):
                if time.time() - ts > 6:
                    print(f"  {addr[:8]}  (sin senal)")
                    continue
                barra = "#" * max(0, min(20, int((rssi + 100) / 3)))
                print(f"  {addr[:8]}  [{barra:<20}] {rssi:>4} dBm")
            sys.stdout.flush()
    finally:
        await scanner.stop()


async def cmd_modes(args):
    print("Modos internos del firmware (opcode 07).")
    print("Nombres oficiales, del array scene_magic del APK.\n")
    for i, nombre in p.MODES.items():
        extra = p.BANDERA_ESPECIAL.get(i, "")
        print(f"  {i:>2}  {nombre:<12}" + (f"  --direction cambia: {extra}" if extra else ""))
    print("\n--direction invierte el sentido de avance, --section lo parte por tramos.")
    print("Un comando de color posterior cancela el modo: lanzalo y no mandes nada mas.")


async def cmd_mode(args):
    async with await _group(args.timeout) as g:
        await g.on()
        await g.mode(args.id, speed=args.speed, brightness=args.brightness,
                     colors=tuple(args.colors), direction=args.direction,
                     section=args.section)
        # La escritura es sin respuesta: vuelve al instante porque el
        # sistema la encola. Si desconectamos aqui mismo, el paquete se
        # puede perder antes de salir. Un segundo basta para que salga.
        await asyncio.sleep(1.0)
        print(f"modo {args.id} ({p.MODES[args.id]}) lanzado; sigue solo en la lampara")


async def cmd_fx(args):
    if args.name not in EFFECTS:
        print("Efectos disponibles:\n")
        for k, fn in EFFECTS.items():
            print(f"  {k:<10} {fn.desc}")
        return
    async with await _group(args.timeout) as g:
        print(f"efecto '{args.name}' durante {args.seconds:.0f}s")
        await play(g, args.name, args.seconds)
        print("fin")


async def cmd_scene(args):
    """Escenas del motor perceptual, en OKLab y con gamma corregida."""
    if args.name not in SCENES:
        print("Escenas disponibles:\n")
        for k, fn in SCENES.items():
            print(f"  {k:<10} {fn.desc}")
        return
    async with await _group(args.timeout) as g:
        await g.on()
        print(f"escena '{args.name}' durante {args.seconds:.0f}s")
        try:
            await render(g, SCENES[args.name], args.seconds)
        finally:
            await g.rgb(255, 180, 110)
            await g.brightness(255)


async def cmd_show(args):
    """Espectaculo completo: seis escenas con fundidos entre ellas."""
    async with await _group(args.timeout) as g:
        await g.on()
        print()
        try:
            await show(g, escala=args.scale)
        finally:
            await g.rgb(255, 180, 110)
            await g.brightness(255)


async def cmd_color(args):
    async with await _group(args.timeout) as g:
        await g.on()
        await g.brightness(args.brightness)
        await g.rgb(args.r, args.g, args.b)


async def cmd_power(args):
    async with await _group(args.timeout) as g:
        await (g.on() if args.on else g.off())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vclight", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeout", type=float, default=12.0,
                    help="segundos de escaneo antes de conectar")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan", help="lista las lamparas al alcance").set_defaults(fn=cmd_scan)

    f = sub.add_parser("find", help="medidor de proximidad en vivo")
    f.add_argument("seconds", nargs="?", type=float, default=300)
    f.set_defaults(fn=cmd_find)

    sub.add_parser("modes", help="lista los modos del firmware").set_defaults(fn=cmd_modes)

    m = sub.add_parser("mode", help="lanza un modo del firmware")
    m.add_argument("id", type=int, choices=sorted(p.MODES))
    m.add_argument("--speed", type=int, default=50)
    m.add_argument("--brightness", type=int, default=100)
    m.add_argument("--colors", type=int, nargs="+", default=[0, 1],
                   help="indices de la paleta interna, de 0 a 7")
    m.add_argument("--direction", type=int, choices=[0, 1], default=0)
    m.add_argument("--section", type=int, choices=[0, 1], default=0)
    m.set_defaults(fn=cmd_mode)

    x = sub.add_parser("fx", help="lanza una animacion calculada aqui")
    x.add_argument("name", nargs="?", default="")
    x.add_argument("seconds", nargs="?", type=float, default=20)
    x.set_defaults(fn=cmd_fx)

    s_ = sub.add_parser("scene", help="escena del motor de color perceptual")
    s_.add_argument("name", nargs="?", default="")
    s_.add_argument("seconds", nargs="?", type=float, default=60)
    s_.set_defaults(fn=cmd_scene)

    sh = sub.add_parser("show", help="espectaculo de 6 escenas encadenadas")
    sh.add_argument("--scale", type=float, default=1.0,
                    help="multiplica la duracion; 0.25 da una version corta")
    sh.set_defaults(fn=cmd_show)

    c = sub.add_parser("color", help="color fijo")
    c.add_argument("r", type=int); c.add_argument("g", type=int); c.add_argument("b", type=int)
    c.add_argument("--brightness", type=int, default=255)
    c.set_defaults(fn=cmd_color)

    sub.add_parser("on").set_defaults(fn=cmd_power, on=True)
    sub.add_parser("off").set_defaults(fn=cmd_power, on=False)

    args = ap.parse_args(argv)
    asyncio.run(args.fn(args))


if __name__ == "__main__":
    main()
