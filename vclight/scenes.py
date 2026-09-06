"""Escenas: animaciones como funcion pura del tiempo.

Una escena no tiene bucle propio. Es una funcion

    escena(t, i, n) -> ((r, g, b), brillo)

donde t son los segundos desde que empezo, i el indice de la lampara y n
cuantas hay. Devuelve el color y el brillo de 0 a 1 que le tocan a esa
lampara en ese instante.

La ventaja de quitarles el bucle es que se pueden componer. Como puedo
preguntarle a dos escenas por el mismo instante, puedo mezclar sus dos
respuestas y fundir una en otra sin que ninguna se entere. De ahi sale
`show`, que encadena seis escenas con transiciones suaves.

El brillo va aparte del color a proposito: el color se manda con el
opcode 03 y el brillo con el 02, asi que separarlos permite oscurecer
sin desaturar, que es justo lo que un fundido a negro en RGB hace mal.
"""
import asyncio
import math
import random
import time

from .color import (PALETAS, ease_in_out, ease_out_expo, gamma_encode,
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
# Escenas
# ---------------------------------------------------------------------------

@scene("plasma", "Campo de plasma: las lamparas son dos puntos del mismo fluido")
def plasma(t, i, n):
    """Suma de ondas con periodos inconmensurables, muestreada en la
    posicion de cada lampara.

    El truco esta en que las lamparas no ejecutan cada una su animacion:
    muestrean un mismo campo continuo en dos sitios distintos. Por eso se
    las ve relacionadas sin ir sincronizadas, como dos boyas en el mar.

    Los periodos (0.31, 0.47, 0.23) no son multiplos entre si, asi que la
    figura tarda muchisimo en repetirse y nunca se ve el bucle.
    """
    x = i / max(1, n - 1) if n > 1 else 0.5
    v = (math.sin(t * 0.31 + x * 3.1)
         + math.sin(t * 0.47 - x * 1.7)
         + math.sin(t * 0.23 + x * 4.3 + math.sin(t * 0.11) * 2))
    v /= 3
    return oklch(0.62 + 0.18 * v, 0.16, (t * 14 + v * 90 + x * 40) % 360), 0.75 + 0.25 * v


@scene("lava", "Lampara de lava: deriva lenta por una paleta, en OKLab")
def lava(t, i, n):
    """Recorrido muy lento por una rampa de color, con la luminosidad
    respirando por su cuenta.

    Las dos lamparas van desfasadas un tercio de la rampa: se parecen
    pero nunca coinciden, que es lo que da sensacion de materia viva.
    """
    pos = t * 0.035 + i / max(1, n) * 0.33
    color = gradient(PALETAS["brasas"], pos)
    respiro = 0.5 - 0.5 * math.cos((t / 9 + i * 0.4) * 2 * math.pi)
    return color, 0.45 + 0.55 * ease_in_out(respiro)


@scene("comet", "Cometa: un nucleo recorre las lamparas dejando cola")
def comet(t, i, n):
    """Un pulso viaja por el grupo con cola exponencial.

    Es la unica forma de conseguir movimiento sin usar los modos del
    firmware: el aparato no deja dirigir un LED suelto, pero si hay
    varias lamparas, el grupo entero hace de tira.
    """
    periodo = 3.2
    cabeza = (t / periodo) % 1.0
    x = i / max(1, n)
    d = (x - cabeza) % 1.0                     # distancia por detras del nucleo
    intensidad = math.exp(-d * 7)              # cola que se apaga rapido
    color = mix((40, 0, 90), (120, 230, 255), intensidad)
    return color, 0.06 + 0.94 * intensidad


@scene("heartbeat", "Latido: doble golpe con la cadencia de un corazon")
def heartbeat(t, i, n):
    """Sistole y diastole, no un seno.

    Un corazon da dos golpes seguidos y luego calla: el segundo llega a
    los 0.28 s del primero y con menos fuerza. Reproducir esa cadencia
    es lo que hace que se reconozca como latido y no como parpadeo.
    """
    ciclo = t % 1.15
    def golpe(inicio, fuerza):
        d = ciclo - inicio
        return fuerza * ease_out_expo(1 - d / 0.22) if 0 <= d < 0.22 else 0.0
    v = max(golpe(0.0, 1.0), golpe(0.28, 0.62))
    return mix((60, 0, 6), (255, 20, 30), v), 0.10 + 0.90 * v


@scene("embers", "Brasas: rescoldos que se avivan y se apagan")
def embers(t, i, n):
    """Ruido de turbulencia con memoria corta.

    A diferencia del fuego clasico, aqui la mayor parte del tiempo esta
    apagado y solo de vez en cuando se aviva. Las pausas son las que
    hacen creible el efecto.
    """
    lento = math.sin(t * 0.9 + i * 2.1) * 0.5 + 0.5
    rapido = math.sin(t * 6.3 + i * 5.7) * 0.5 + 0.5
    v = (lento ** 2) * 0.75 + rapido * 0.25
    color = gradient(PALETAS["brasas"], 0.1 + v * 0.4)
    return color, 0.12 + 0.88 * v


@scene("aurora", "Aurora: cortinas verdes y violetas en contrafase")
def aurora(t, i, n):
    """Dos cortinas que se cruzan.

    El tono oscila entre verde y violeta con un periodo, y la
    luminosidad con otro distinto. Al no estar sincronizados, el color
    y el brillo maximo no caen a la vez y el conjunto parece ondear.
    """
    # 140 a 320 grados: del verde de la aurora al violeta del borde.
    tono = 230 + 90 * math.sin(t * 0.21 + i * math.pi)
    lum = 0.45 + 0.30 * math.sin(t * 0.37 + i * 2.2)
    return oklch(lum, 0.15, tono), 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 0.29 + i))


@scene("storm", "Tormenta: azul plomizo con relampagos")
def storm(t, i, n):
    """Los relampagos salen de una funcion pseudoaleatoria del tiempo,
    no de random(), para que la escena siga siendo pura: preguntada dos
    veces por el mismo instante devuelve lo mismo, y asi se puede fundir
    con otra escena sin que parpadee."""
    ventana = math.floor(t / 2.7)
    semilla = (math.sin(ventana * 127.1 + i * 0.3) * 43758.5453) % 1.0
    inicio = (ventana + semilla * 0.6) * 2.7
    d = t - inicio
    rayo = 0.0
    if 0 <= d < 0.45 and semilla > 0.35:
        # Tren de destellos dentro del rayo: no es un flash unico.
        rayo = max(0.0, ease_out_expo(1 - d / 0.12) * (1 if int(d * 28) % 2 == 0 else 0.35))
    base = oklch(0.32, 0.09, 265)
    return mix(base, (255, 255, 255), rayo), 0.18 + 0.82 * rayo


@scene("sunrise", "Amanecer: de rojo profundo a blanco calido")
def sunrise(t, i, n):
    """Escena con final: dura 180 s y se queda quieta al llegar."""
    k = ease_in_out(min(1.0, t / 180))
    color = mix((90, 8, 0), (255, 200, 150), k)
    return color, 0.05 + 0.95 * k


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

async def render(group, escena, secs, fps=FPS, t0=0.0):
    """Dibuja una escena en el grupo durante unos segundos."""
    n = len(group)
    inicio = time.time()
    while (t := time.time() - inicio) < secs:
        for i, lamp in enumerate(group):
            color, brillo = escena(t + t0, i, n)
            await lamp.rgb(*color)
            await lamp.brightness(255 * gamma_encode(brillo))
        await asyncio.sleep(1 / fps)


async def transition(group, desde, hacia, secs=3.0, fps=FPS, t0=0.0):
    """Funde una escena en otra.

    Como las escenas son funciones puras, aqui se le pregunta a las dos
    por el mismo instante y se mezclan sus respuestas en OKLab. Ninguna
    de las dos sabe que esta en una transicion.
    """
    n = len(group)
    inicio = time.time()
    while (t := time.time() - inicio) < secs:
        k = ease_in_out(t / secs)
        for i, lamp in enumerate(group):
            c1, b1 = desde(t + t0, i, n)
            c2, b2 = hacia(t + t0, i, n)
            await lamp.rgb(*mix(c1, c2, k))
            await lamp.brightness(255 * gamma_encode(b1 + (b2 - b1) * k))
        await asyncio.sleep(1 / fps)


# Guion del espectaculo: escena y cuantos segundos dura.
GUION = [
    ("sunrise", 40), ("plasma", 45), ("aurora", 40),
    ("storm", 35), ("embers", 40), ("lava", 45),
]


async def show(group, escala=1.0, fundido=4.0):
    """Espectaculo completo, seis escenas encadenadas con fundidos.

    escala multiplica la duracion de cada escena; 0.25 da una version
    corta para enseñarlo, 1.0 dura unos cuatro minutos.
    """
    t0 = time.time()
    for k, (nombre, dur) in enumerate(GUION):
        escena = SCENES[nombre]
        dur *= escala
        print(f"  {nombre:<10} {dur:.0f}s   {escena.desc}", flush=True)
        await render(group, escena, dur, t0=time.time() - t0)
        if k + 1 < len(GUION):
            siguiente = SCENES[GUION[k + 1][0]]
            await transition(group, escena, siguiente, fundido, t0=time.time() - t0)
    print("  fin del espectaculo")
