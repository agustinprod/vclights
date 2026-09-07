"""Perceptual colour engine: OKLab, OKLCh and gamma correction.

Why interpolating in RGB is not enough
--------------------------------------
A red-to-blue fade done in RGB passes through (128, 0, 128), a muddy
dark purple. The eye does not see a midpoint, it sees the brightness
collapse halfway through. That happens because RGB channels do not
measure what the eye perceives: they only measure how much current each
LED draws.

OKLab is built so that distance between two colours matches what the eye
notices. Interpolating there gives fades of even brightness, and in its
polar form, OKLCh, the hue takes the short way round the colour wheel
instead of cutting through grey.

And gamma
---------
The LED responds linearly to what you send it; the eye does not. Half
the value does not look like half the light, it looks considerably
brighter. Uncorrected, a linear fade spends most of its travel in the
top end and the climb out of black is an abrupt jump.

OKLab reference: Bjorn Ottosson, 2020.
"""
import math

GAMMA = 2.2


# -------------------------------------------------------------- gamma ----

def gamma_encode(v):
    """From perceived brightness (0-1) to the value to send the LED."""
    return max(0.0, min(1.0, v)) ** GAMMA


def gamma_decode(v):
    """The inverse: from the LED value to the brightness perceived."""
    return max(0.0, min(1.0, v)) ** (1 / GAMMA)


# -------------------------------------------------------------- OKLab ----

def srgb_to_linear(c):
    c = max(0.0, min(1.0, c))
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def rgb_to_oklab(r, g, b):
    """RGB 0-255 to OKLab. L is lightness, a and b the colour axes."""
    lr, lg, lb = (srgb_to_linear(x / 255) for x in (r, g, b))
    l = (0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb) ** (1 / 3)
    m = (0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb) ** (1 / 3)
    s = (0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def oklab_to_rgb(L, a, b):
    """OKLab back to RGB 0-255, clipped to the gamut."""
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lr = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    lb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return tuple(round(255 * linear_to_srgb(x)) for x in (lr, lg, lb))


def oklch(L, C, h_deg):
    """Colour in polar coordinates: lightness, chroma and hue in degrees.

    Easier than OKLab to animate with, because turning the hue is adding
    degrees and the lightness stays untouched.
    """
    rad = math.radians(h_deg)
    return oklab_to_rgb(L, C * math.cos(rad), C * math.sin(rad))


def mix(c1, c2, k):
    """Blend two RGB colours through OKLab. k runs 0 to 1.

    This is the function that avoids the grey midpoint: in OKLab the
    halfway point between red and blue is a clean violet, not a muddy
    one.
    """
    a = rgb_to_oklab(*c1)
    b = rgb_to_oklab(*c2)
    return oklab_to_rgb(*(x + (y - x) * k for x, y in zip(a, b)))


def gradient(colors, t):
    """Sample a colour ramp at position t, 0 to 1.

    The ramp wraps: t = 1 returns to the first colour, so it suits loops
    that must not jolt when they close.
    """
    n = len(colors)
    pos = (t % 1.0) * n
    i = int(pos)
    return mix(colors[i % n], colors[(i + 1) % n], pos - i)


# ------------------------------------------------------------- easing ----

def ease_in_out(t):
    """Smooth 0 to 1 curve. Starts and stops gently."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ease_out_expo(t):
    """Exponential decay: sharp hit, long tail. For flashes."""
    t = max(0.0, min(1.0, t))
    return 1 - 2 ** (-10 * t)


# ----------------------------------------------------------- palettes ----
# Hand-picked ramps. Names describe the look, not a brand.

PALETTES = {
    "embers": [(255, 30, 0), (255, 120, 10), (255, 200, 60), (140, 20, 0)],
    "ocean":  [(0, 40, 90), (0, 130, 160), (20, 200, 180), (0, 70, 130)],
    "sunset": [(255, 80, 40), (255, 160, 60), (200, 60, 120), (90, 30, 110)],
    "neon":   [(255, 0, 120), (120, 0, 255), (0, 200, 255), (0, 255, 140)],
    "forest": [(10, 80, 30), (60, 160, 50), (200, 220, 90), (20, 100, 70)],
    "ice":    [(180, 230, 255), (80, 150, 255), (230, 240, 255), (40, 90, 200)],
}
