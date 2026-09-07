"""Scenes: animations expressed as pure functions of time.

A scene has no loop of its own. It is a function

    scene(t, i, n) -> ((r, g, b), brightness)

where t is seconds since it started, i the index of the lamp and n how
many there are. It returns the colour and the brightness, 0 to 1, that
lamp should show at that instant.

Taking the loop away is what makes scenes composable. Because two scenes
can both be asked about the same instant, their answers can be blended
and one faded into the other without either knowing. That is how `show`
strings six scenes together.

Brightness is kept apart from colour on purpose: colour ships on opcode
03 and brightness on opcode 02, so separating them lets a scene dim
without desaturating, which is exactly what an RGB fade to black gets
wrong.
"""
import asyncio
import math
import time

from .color import (PALETTES, ease_in_out, ease_out_expo, gamma_encode,
                    gradient, mix, oklch)

FPS = 22

SCENES = {}


def scene(name, desc):
    def deco(fn):
        fn.desc = desc
        SCENES[name] = fn
        return fn
    return deco


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

@scene("plasma", "Plasma field: the lamps are two points in one fluid")
def plasma(t, i, n):
    """A sum of waves with incommensurable periods, sampled at each
    lamp's position.

    The trick is that the lamps are not each running their own animation:
    they sample one continuous field at two different places. That is why
    they look related without being in step, like two buoys at sea.

    The periods (0.31, 0.47, 0.23) are not multiples of one another, so
    the figure takes a very long time to repeat and the loop never shows.
    """
    x = i / max(1, n - 1) if n > 1 else 0.5
    v = (math.sin(t * 0.31 + x * 3.1)
         + math.sin(t * 0.47 - x * 1.7)
         + math.sin(t * 0.23 + x * 4.3 + math.sin(t * 0.11) * 2))
    v /= 3
    return oklch(0.62 + 0.18 * v, 0.16, (t * 14 + v * 90 + x * 40) % 360), 0.75 + 0.25 * v


@scene("lava", "Lava lamp: a slow drift through a palette, in OKLab")
def lava(t, i, n):
    """A very slow walk along a colour ramp, with the lightness
    breathing on its own separate cycle.

    The lamps sit a third of the ramp apart: alike but never identical,
    which is what reads as living matter.
    """
    pos = t * 0.035 + i / max(1, n) * 0.33
    color = gradient(PALETTES["embers"], pos)
    breath = 0.5 - 0.5 * math.cos((t / 9 + i * 0.4) * 2 * math.pi)
    return color, 0.45 + 0.55 * ease_in_out(breath)


@scene("comet", "Comet: a core runs across the lamps trailing a tail")
def comet(t, i, n):
    """A pulse travels the group with an exponential tail.

    This is the only way to get movement without the firmware modes: the
    device will not address a single LED, but with several lamps the
    group itself acts as the strip.
    """
    period = 3.2
    head = (t / period) % 1.0
    x = i / max(1, n)
    d = (x - head) % 1.0                       # distance behind the core
    intensity = math.exp(-d * 7)               # tail that dies off fast
    color = mix((40, 0, 90), (120, 230, 255), intensity)
    return color, 0.06 + 0.94 * intensity


@scene("heartbeat", "Heartbeat: a double thump with a heart's cadence")
def heartbeat(t, i, n):
    """Systole and diastole, not a sine wave.

    A heart gives two beats in quick succession and then falls silent:
    the second arrives 0.28 s after the first and weaker. Reproducing
    that cadence is what makes it read as a heartbeat rather than a
    blink.
    """
    cycle = t % 1.15

    def thump(start, strength):
        d = cycle - start
        return strength * ease_out_expo(1 - d / 0.22) if 0 <= d < 0.22 else 0.0

    v = max(thump(0.0, 1.0), thump(0.28, 0.62))
    return mix((60, 0, 6), (255, 20, 30), v), 0.10 + 0.90 * v


@scene("embers", "Embers: coals flaring up and dying back")
def embers(t, i, n):
    """Turbulence noise with a short memory.

    Unlike the usual fire effect, this one is mostly dark and only flares
    now and then. The pauses are what make it believable.
    """
    slow = math.sin(t * 0.9 + i * 2.1) * 0.5 + 0.5
    fast = math.sin(t * 6.3 + i * 5.7) * 0.5 + 0.5
    v = (slow ** 2) * 0.75 + fast * 0.25
    color = gradient(PALETTES["embers"], 0.1 + v * 0.4)
    return color, 0.12 + 0.88 * v


@scene("aurora", "Aurora: green and violet curtains in counterphase")
def aurora(t, i, n):
    """Two curtains crossing.

    Hue swings between green and violet on one period, lightness on a
    different one. Being out of step, the peak colour and the peak
    brightness never land together, and the whole thing appears to ripple.
    """
    # 140 to 320 degrees: from the green of the aurora to its violet edge.
    hue = 230 + 90 * math.sin(t * 0.21 + i * math.pi)
    lum = 0.45 + 0.30 * math.sin(t * 0.37 + i * 2.2)
    return oklch(lum, 0.15, hue), 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 0.29 + i))


@scene("storm", "Storm: leaden blue with lightning")
def storm(t, i, n):
    """Lightning comes from a pseudo-random function of time, not from
    random(), so the scene stays pure: asked twice about the same instant
    it answers the same, which is what lets it be cross-faded with
    another scene without flickering."""
    window = math.floor(t / 2.7)
    seed = (math.sin(window * 127.1 + i * 0.3) * 43758.5453) % 1.0
    start = (window + seed * 0.6) * 2.7
    d = t - start
    bolt = 0.0
    if 0 <= d < 0.45 and seed > 0.35:
        # A bolt is a train of flashes, not a single one.
        bolt = max(0.0, ease_out_expo(1 - d / 0.12) * (1 if int(d * 28) % 2 == 0 else 0.35))
    base = oklch(0.32, 0.09, 265)
    return mix(base, (255, 255, 255), bolt), 0.18 + 0.82 * bolt


@scene("sunrise", "Sunrise: from deep red to warm white")
def sunrise(t, i, n):
    """A scene with an ending: it runs 180 s and then holds still."""
    k = ease_in_out(min(1.0, t / 180))
    color = mix((90, 8, 0), (255, 200, 150), k)
    return color, 0.05 + 0.95 * k


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

async def render(group, scene_fn, secs, fps=FPS, t0=0.0):
    """Draw a scene on the group for a number of seconds."""
    n = len(group)
    start = time.time()
    while (t := time.time() - start) < secs:
        for i, lamp in enumerate(group):
            color, bright = scene_fn(t + t0, i, n)
            await lamp.rgb(*color)
            await lamp.brightness(255 * gamma_encode(bright))
        await asyncio.sleep(1 / fps)


async def transition(group, frm, to, secs=3.0, fps=FPS, t0=0.0):
    """Fade one scene into another.

    Because scenes are pure functions, both are asked about the same
    instant and their answers blended in OKLab. Neither one knows it is
    in a transition.
    """
    n = len(group)
    start = time.time()
    while (t := time.time() - start) < secs:
        k = ease_in_out(t / secs)
        for i, lamp in enumerate(group):
            c1, b1 = frm(t + t0, i, n)
            c2, b2 = to(t + t0, i, n)
            await lamp.rgb(*mix(c1, c2, k))
            await lamp.brightness(255 * gamma_encode(b1 + (b2 - b1) * k))
        await asyncio.sleep(1 / fps)


# The running order: scene, and how many seconds it lasts.
RUNNING_ORDER = [
    ("sunrise", 40), ("plasma", 45), ("aurora", 40),
    ("storm", 35), ("embers", 40), ("lava", 45),
]


async def show(group, scale=1.0, fade=4.0):
    """The full show: six scenes strung together with cross-fades.

    scale multiplies every scene's duration; 0.25 gives a short version
    to demonstrate with, 1.0 runs about four minutes.
    """
    t0 = time.time()
    for k, (name, dur) in enumerate(RUNNING_ORDER):
        scene_fn = SCENES[name]
        dur *= scale
        print(f"  {name:<10} {dur:.0f}s   {scene_fn.desc}", flush=True)
        await render(group, scene_fn, dur, t0=time.time() - t0)
        if k + 1 < len(RUNNING_ORDER):
            nxt = SCENES[RUNNING_ORDER[k + 1][0]]
            await transition(group, scene_fn, nxt, fade, t0=time.time() - t0)
    print("  end of show")
