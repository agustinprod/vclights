"""Motor de color perceptual: OKLab, OKLCh y correccion de gamma.

Por que no basta con interpolar en RGB
--------------------------------------
Un fundido de rojo a azul hecho en RGB pasa por (128, 0, 128), un morado
sucio y oscuro. El ojo no ve el punto medio, ve un bajon de brillo en
mitad de la transicion. Pasa porque los canales RGB no miden lo que el
ojo percibe: solo miden cuanta corriente lleva cada LED.

OKLab si esta construido para que la distancia entre dos colores se
corresponda con lo que el ojo nota. Interpolar ahi da fundidos de brillo
constante, y en su version polar, OKLCh, el tono gira por el camino
cromatico corto en vez de atravesar el centro gris.

Y la gamma
----------
El LED responde de forma lineal a lo que le mandas, pero el ojo no: la
mitad del valor no se ve como la mitad de luz, sino bastante mas clara.
Sin corregir, un fundido lineal se come casi todo su recorrido en la
zona alta y el arranque desde negro es un salto brusco.

Referencia de OKLab: Bjorn Ottosson, 2020.
"""
import math

GAMMA = 2.2


# ------------------------------------------------------------- gamma -----

def gamma_encode(v):
    """De brillo percibido (0-1) al valor que hay que mandar al LED."""
    return max(0.0, min(1.0, v)) ** GAMMA


def gamma_decode(v):
    """La inversa: del valor del LED al brillo que se percibe."""
    return max(0.0, min(1.0, v)) ** (1 / GAMMA)


# ------------------------------------------------------------- OKLab -----

def srgb_to_linear(c):
    c = max(0.0, min(1.0, c))
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def rgb_to_oklab(r, g, b):
    """RGB de 0-255 a OKLab. L es luminosidad, a y b los ejes de color."""
    lr, lg, lb = (srgb_to_linear(x / 255) for x in (r, g, b))
    l = (0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb) ** (1 / 3)
    m = (0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb) ** (1 / 3)
    s = (0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def oklab_to_rgb(L, a, b):
    """OKLab de vuelta a RGB 0-255, recortado al gamut."""
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lr = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    lb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return tuple(round(255 * linear_to_srgb(x)) for x in (lr, lg, lb))


def oklch(L, C, h_deg):
    """Color en coordenadas polares: luminosidad, croma y tono en grados.

    Mas comodo que OKLab para animar, porque girar el tono es sumar
    grados y la luminosidad no se toca.
    """
    rad = math.radians(h_deg)
    return oklab_to_rgb(L, C * math.cos(rad), C * math.sin(rad))


def mix(c1, c2, k):
    """Mezcla dos colores RGB por OKLab. k va de 0 a 1.

    Esta es la funcion que evita el gris del medio: en OKLab el punto
    intermedio entre rojo y azul es un morado limpio, no apagado.
    """
    a = rgb_to_oklab(*c1)
    b = rgb_to_oklab(*c2)
    return oklab_to_rgb(*(x + (y - x) * k for x, y in zip(a, b)))


def gradient(colors, t):
    """Muestrea una rampa de colores en la posicion t, de 0 a 1.

    La rampa es circular: t = 1 vuelve al primer color, asi que sirve
    para bucles que no dan tirones al cerrarse.
    """
    n = len(colors)
    pos = (t % 1.0) * n
    i = int(pos)
    return mix(colors[i % n], colors[(i + 1) % n], pos - i)


# ------------------------------------------------------------ suavizado --

def ease_in_out(t):
    """Curva suave de 0 a 1. Arranca y frena despacio."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ease_out_expo(t):
    """Salida exponencial: golpe seco y cola larga. Para destellos."""
    t = max(0.0, min(1.0, t))
    return 1 - 2 ** (-10 * t)


# ------------------------------------------------------------- paletas ---
# Rampas escogidas a mano. Los nombres son descriptivos, no de marca.

PALETAS = {
    "brasas":    [(255, 30, 0), (255, 120, 10), (255, 200, 60), (140, 20, 0)],
    "oceano":    [(0, 40, 90), (0, 130, 160), (20, 200, 180), (0, 70, 130)],
    "atardecer": [(255, 80, 40), (255, 160, 60), (200, 60, 120), (90, 30, 110)],
    "neon":      [(255, 0, 120), (120, 0, 255), (0, 200, 255), (0, 255, 140)],
    "bosque":    [(10, 80, 30), (60, 160, 50), (200, 220, 90), (20, 100, 70)],
    "hielo":     [(180, 230, 255), (80, 150, 255), (230, 240, 255), (40, 90, 200)],
}
