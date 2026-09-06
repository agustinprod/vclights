"""Animaciones calculadas en el ordenador y enviadas cuadro a cuadro.

Dos formas de animar una lampara VC-BLELIGHT:

1. Los 18 modos internos del firmware (Lamp.mode). Se mueven a lo largo
   de la tira, no gastan ancho de banda y siguen corriendo aunque el
   portatil se apague. Pero solo se puede elegir modo, velocidad, brillo
   y paleta: no hay control fino.

2. Lo de este fichero: el ordenador calcula cada cuadro y manda un color
   por cuadro. Control total sobre el color y el ritmo, a cambio de tener
   que mantener la conexion BLE abierta.

Techo de velocidad
------------------
La escritura es "sin respuesta", asi que medir el tiempo de la llamada
no dice nada: macOS la encola y vuelve al instante. El limite de verdad
es el intervalo de conexion BLE, entre 15 y 45 ms, o sea unos 20 a 60
comandos por segundo. Por encima de eso los comandos se pierden. FPS = 22
va sobrado y deja margen.
"""
import asyncio
import colorsys
import math
import random
import time

FPS = 22


def _hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return r * 255, g * 255, b * 255


# Cada efecto recibe:
#   lamp  la lampara sobre la que pinta
#   i     su indice dentro del grupo, para desfasarlo de las demas
#   n     cuantas lamparas hay en total
#   secs  cuanto tiene que durar
# Asi el mismo efecto sirve para una lampara o para diez, y las coreografia.

EFFECTS = {}


def effect(name, desc):
    def deco(fn):
        fn.desc = desc
        EFFECTS[name] = fn
        return fn
    return deco


@effect("rainbow", "Arcoiris continuo; cada lampara desfasada en el circulo cromatico")
async def rainbow(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        await lamp.rgb(*_hsv(t * 0.12 + i / n))
        await asyncio.sleep(1 / FPS)


@effect("wave", "Onda: el brillo viaja de una lampara a la siguiente")
async def wave(lamp, i, n, secs):
    await lamp.rgb(0, 160, 255)
    await lamp.on()
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        # Coseno desfasado segun la posicion: el maximo recorre el grupo.
        phase = (t / 2.5 - i / n) * 2 * math.pi
        await lamp.brightness(15 + 240 * (0.5 - 0.5 * math.cos(phase)))
        await asyncio.sleep(1 / FPS)


@effect("fire", "Fuego: naranjas y rojos con turbulencia propia en cada lampara")
async def fire(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    seed = random.random() * 100          # que ninguna lata igual que otra
    while (t := time.time() - t0) < secs:
        # Dos senoidales de periodo incomensurable mas ruido: parece fuego
        # justamente porque nunca se repite igual.
        flick = (math.sin(t * 7 + seed) + math.sin(t * 13.3 + seed * 2)) / 2
        flick = max(0.15, min(1.0, 0.5 + 0.5 * flick + random.gauss(0, 0.12)))
        await lamp.rgb(255, 60 + 90 * flick, 8 * flick)
        await lamp.brightness(60 + 195 * flick)
        await asyncio.sleep(1 / FPS)


@effect("storm", "Tormenta: azul oscuro con trenes de relampagos aleatorios")
async def storm(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    while time.time() - t0 < secs:
        await lamp.rgb(20, 30, 90)
        await lamp.brightness(45)
        await asyncio.sleep(random.uniform(1.5, 5.0))
        for _ in range(random.randint(1, 4)):   # un rayo son varios destellos
            await lamp.rgb(255, 255, 255)
            await lamp.brightness(255)
            await asyncio.sleep(random.uniform(0.03, 0.09))
            await lamp.brightness(40)
            await asyncio.sleep(random.uniform(0.04, 0.16))


@effect("aurora", "Aurora boreal: verdes y violetas derivando en contrafase")
async def aurora(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        h = 0.33 + 0.25 * math.sin(t * 0.23 + i * math.pi)   # verde a violeta
        v = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * 0.41 + i * 2))
        await lamp.rgb(*_hsv(h, 0.9, v))
        await asyncio.sleep(1 / FPS)


@effect("breathe", "Respiracion lenta, todas en fase")
async def breathe(lamp, i, n, secs):
    await lamp.rgb(255, 90, 20)
    await lamp.on()
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        await lamp.brightness(10 + 245 * (0.5 - 0.5 * math.cos(t / 4 * 2 * math.pi)))
        await asyncio.sleep(1 / FPS)


@effect("sunrise", "Amanecer: rojo tenue a blanco calido pleno")
async def sunrise(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    while (k := (time.time() - t0) / secs) < 1:
        # El azul entra al cuadrado para que el blanco llegue solo al final.
        await lamp.rgb(255, 40 + 175 * k, 10 + 150 * k ** 2)
        await lamp.brightness(15 + 240 * k)
        await asyncio.sleep(1 / FPS)


@effect("police", "Una lampara roja, otra azul, en rafagas alternas")
async def police(lamp, i, n, secs):
    await lamp.rgb(*((255, 0, 0) if i % 2 == 0 else (0, 40, 255)))
    t0 = time.time()
    while time.time() - t0 < secs:
        for _ in range(3):
            await lamp.on()
            await asyncio.sleep(0.06)
            await lamp.off()
            await asyncio.sleep(0.06)
        await asyncio.sleep(0.45)


@effect("identify", "Parpadean por turnos, para saber cual es cual")
async def identify(lamp, i, n, secs):
    await lamp.rgb(255, 255, 255)
    t0 = time.time()
    while time.time() - t0 < secs:
        await asyncio.sleep(i * 1.5)                  # espera su turno
        for _ in range(3):
            await lamp.on()
            await asyncio.sleep(0.15)
            await lamp.off()
            await asyncio.sleep(0.15)
        await asyncio.sleep((n - i - 1) * 1.5)        # deja pasar a las demas
    await lamp.on()


@effect("test", "Prueba lenta y evidente: rojo, verde, azul, apagado")
async def test(lamp, i, n, secs):
    """Para comprobar a ojo que la lampara obedece. Como el protocolo no
    acusa recibo, esta es la unica forma de verificar que llega."""
    for nombre, color in [("ROJO", (255, 0, 0)), ("VERDE", (0, 255, 0)), ("AZUL", (0, 0, 255))]:
        if i == 0:
            print(f"   -> {nombre}", flush=True)
        await lamp.brightness(255)
        await lamp.rgb(*color)
        await lamp.on()
        await asyncio.sleep(3)
    if i == 0:
        print("   -> APAGADO", flush=True)
    await lamp.off()
    await asyncio.sleep(3)


async def play(group, name, secs):
    """Corre un efecto en todas las lamparas del grupo a la vez.

    Al terminar las deja en blanco calido, nunca a oscuras: si el efecto
    se corta a media noche, mejor luz que sorpresa.
    """
    fn = EFFECTS[name]
    n = len(group)
    try:
        await asyncio.gather(*(fn(lamp, i, n, secs) for i, lamp in enumerate(group)))
    finally:
        for lamp in group:
            try:
                await lamp.rgb(255, 180, 110)
                await lamp.brightness(255)
                await lamp.on()
            except Exception:
                pass          # si ya se cayo la conexion, no hay nada que hacer
