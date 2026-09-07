"""Animations computed on the computer and sent frame by frame.

Two ways to animate a VC-BLELIGHT lamp:

1. The 18 firmware modes (Lamp.mode). They travel along the strip, cost
   no bandwidth and keep running even if the laptop shuts down. But you
   only get to pick mode, speed, brightness and palette: no fine control.

2. What is in this file: the computer works out every frame and sends
   one colour per frame. Full control over colour and timing, at the cost
   of holding the BLE connection open.

Note that these cannot travel along the strip. Every command here goes
out on opcode 03, which paints the whole lamp one colour, so an effect
computed here shows at once across the entire lamp. Only the firmware
modes move. What these can do is move an effect BETWEEN several lamps.

Speed ceiling
-------------
The write has no response, so timing the call tells you nothing: macOS
queues it and returns at once. The real limit is the BLE connection
interval, 15 to 45 ms, meaning roughly 20 to 60 commands per second.
FPS = 22 leaves plenty of headroom.
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


# Every effect receives:
#   lamp  the lamp it paints on
#   i     its index within the group, so it can be offset from the others
#   n     how many lamps there are
#   secs  how long it should last
# One effect therefore serves one lamp or ten, and choreographs them.

EFFECTS = {}


def effect(name, desc):
    def deco(fn):
        fn.desc = desc
        EFFECTS[name] = fn
        return fn
    return deco


@effect("rainbow", "Continuous rainbow; each lamp offset around the colour wheel")
async def rainbow(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        await lamp.rgb(*_hsv(t * 0.12 + i / n))
        await asyncio.sleep(1 / FPS)


@effect("wave", "Wave: brightness travels from one lamp to the next")
async def wave(lamp, i, n, secs):
    await lamp.rgb(0, 160, 255)
    await lamp.on()
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        # A cosine offset by position: the peak runs across the group.
        phase = (t / 2.5 - i / n) * 2 * math.pi
        await lamp.brightness(15 + 240 * (0.5 - 0.5 * math.cos(phase)))
        await asyncio.sleep(1 / FPS)


@effect("fire", "Fire: oranges and reds, each lamp with its own turbulence")
async def fire(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    seed = random.random() * 100          # so no two lamps beat alike
    while (t := time.time() - t0) < secs:
        # Two sines of incommensurable period plus noise: it looks like
        # fire precisely because it never repeats.
        flick = (math.sin(t * 7 + seed) + math.sin(t * 13.3 + seed * 2)) / 2
        flick = max(0.15, min(1.0, 0.5 + 0.5 * flick + random.gauss(0, 0.12)))
        await lamp.rgb(255, 60 + 90 * flick, 8 * flick)
        await lamp.brightness(60 + 195 * flick)
        await asyncio.sleep(1 / FPS)


@effect("storm", "Storm: dark blue with random trains of lightning")
async def storm(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    while time.time() - t0 < secs:
        await lamp.rgb(20, 30, 90)
        await lamp.brightness(45)
        await asyncio.sleep(random.uniform(1.5, 5.0))
        for _ in range(random.randint(1, 4)):   # a bolt is several flashes
            await lamp.rgb(255, 255, 255)
            await lamp.brightness(255)
            await asyncio.sleep(random.uniform(0.03, 0.09))
            await lamp.brightness(40)
            await asyncio.sleep(random.uniform(0.04, 0.16))


@effect("aurora", "Aurora: greens and violets drifting in counterphase")
async def aurora(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        h = 0.33 + 0.25 * math.sin(t * 0.23 + i * math.pi)   # green to violet
        v = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * 0.41 + i * 2))
        await lamp.rgb(*_hsv(h, 0.9, v))
        await asyncio.sleep(1 / FPS)


@effect("breathe", "Slow breathing, all lamps in phase")
async def breathe(lamp, i, n, secs):
    await lamp.rgb(255, 90, 20)
    await lamp.on()
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        await lamp.brightness(10 + 245 * (0.5 - 0.5 * math.cos(t / 4 * 2 * math.pi)))
        await asyncio.sleep(1 / FPS)


@effect("sunrise", "Sunrise: faint red to full warm white")
async def sunrise(lamp, i, n, secs):
    await lamp.on()
    t0 = time.time()
    while (k := (time.time() - t0) / secs) < 1:
        # Blue enters squared so the white only arrives at the very end.
        await lamp.rgb(255, 40 + 175 * k, 10 + 150 * k ** 2)
        await lamp.brightness(15 + 240 * k)
        await asyncio.sleep(1 / FPS)


@effect("police", "One lamp red, another blue, in alternating bursts")
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


@effect("identify", "Lamps blink in turn, to tell which is which")
async def identify(lamp, i, n, secs):
    await lamp.rgb(255, 255, 255)
    t0 = time.time()
    while time.time() - t0 < secs:
        await asyncio.sleep(i * 1.5)                  # wait for its turn
        for _ in range(3):
            await lamp.on()
            await asyncio.sleep(0.15)
            await lamp.off()
            await asyncio.sleep(0.15)
        await asyncio.sleep((n - i - 1) * 1.5)        # let the others go
    await lamp.on()


@effect("test", "Slow, obvious check: red, green, blue, off")
async def test(lamp, i, n, secs):
    """To confirm by eye that the lamp obeys. Since the protocol never
    acknowledges anything, this is the only way to verify it arrives."""
    for name, color in [("RED", (255, 0, 0)), ("GREEN", (0, 255, 0)), ("BLUE", (0, 0, 255))]:
        if i == 0:
            print(f"   -> {name}", flush=True)
        await lamp.brightness(255)
        await lamp.rgb(*color)
        await lamp.on()
        await asyncio.sleep(3)
    if i == 0:
        print("   -> OFF", flush=True)
    await lamp.off()
    await asyncio.sleep(3)


async def play(group, name, secs):
    """Run an effect on every lamp of the group at once.

    On the way out it leaves them warm white, never dark: if an effect is
    cut short in the middle of the night, light beats a surprise.
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
                pass          # connection already gone; nothing to do
