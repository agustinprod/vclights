# vclight

Control de lámparas LED **VC-BLELIGHT** por Bluetooth, sin la app oficial.

Son las lámparas y tiras que vende DoHome y que en España llegan por
Temu bajo marcas como AMill. Se manejan con la app **Raingel**. Este
repositorio hace lo mismo desde Python, y bastante más.

El protocolo está sacado del APK de Raingel, descompilado. Cada opcode
de `vclight/protocol.py` aparece literalmente en el código de la app;
no hay nada adivinado a base de probar bytes al azar. El detalle
completo está en [`docs/protocolo.md`](docs/protocolo.md).

## Qué permite

- Encender, apagar, brillo y color fijo.
- Los **18 modos dinámicos** del firmware, con velocidad, brillo, paleta
  de hasta 8 colores, sentido de avance y división por secciones. Estos
  efectos se desplazan a lo largo de la tira y los calcula la lámpara.
- **Animaciones propias** calculadas en el ordenador, cuadro a cuadro:
  fuego, tormenta, aurora, amanecer, onda entre lámparas.
- Varias lámparas como un solo grupo, coreografiadas entre sí.
- Un **medidor de proximidad** por intensidad de señal, para encontrar
  una lámpara que no sabes dónde está.

## Instalación

```bash
git clone https://github.com/agustinprod/lights
cd lights
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
python -m vclight scan               # lámparas al alcance y su distancia
python -m vclight modes              # los 18 modos del firmware
python -m vclight mode 8 --speed 70  # meteoro, rápido
python -m vclight fx fire 60         # fuego durante un minuto
python -m vclight color 255 80 0     # naranja fijo
python -m vclight find               # medidor de proximidad en vivo
```

Como librería:

```python
import asyncio
from vclight import discover, Lamp

async def main():
    lamps = await discover()
    async with Lamp(lamps[0].device) as lamp:
        await lamp.on()
        await lamp.mode(14, speed=80, colors=(0, 2, 4, 6))   # arcoíris

asyncio.run(main())
```

## Dos formas de animar

| | Modos del firmware | Animaciones propias |
|---|---|---|
| Dónde se calcula | En la lámpara | En el ordenador |
| Se mueve por la tira | Sí | No, color global |
| Control del color | Paleta de 8 índices | Cualquier RGB |
| Necesita conexión | No, sigue solo | Sí, mientras dure |

Los modos del firmware son los únicos que producen movimiento **dentro**
de una lámpara: no existe ningún comando para dirigir un LED concreto.
Desde fuera solo se puede pintar la lámpara entera de un color, así que
cualquier animación propia se ve al unísono en toda la tira. Compensan
con control fino del color y del ritmo, y pueden desplazar un efecto
**entre** varias lámparas.

Si quieres ver un efecto recorrer la tira, lanza un modo del firmware y
**déjalo correr**: cualquier comando de color posterior lo cancela.

```bash
python -m vclight mode 5 --speed 50   # meteoro, y no mandes nada más
```

Y no cierres la conexión justo después de mandar el modo. La escritura
es *sin respuesta*: la llamada vuelve al instante porque el sistema la
encola, no porque haya salido. Desconectar en ese momento pierde el
paquete en silencio.

## Saber si tu lámpara es direccionable

La lámpara lo publica en su propio anuncio, sin necesidad de conectar.
`python -m vclight scan` lo traduce:

```
  -63 dBm  5BF1A60D-…
           LIGHT_MAGIC / tira  direccionable   cerca, 1 a 3 m
```

Solo los grupos `LIGHT_MAGIC`, `LIGHT_MAGIC_W` y `LIGHT_MAGIC_CW` llevan
LEDs direccionables. En los demás los modos del firmware funcionan, pero
se ven a la vez en toda la lámpara porque no hay nada que recorrer.

## La lámpara no confirma nada

La escritura BLE es *sin respuesta*. Un comando mal formado no da error:
la lámpara lo ignora en silencio. La única verificación posible es
mirarla. Para eso está `python -m vclight fx test`, que hace rojo,
verde, azul y apagado, tres segundos cada uno.

Aviso relacionado: **no pruebes opcodes al azar**. En firmwares de esta
familia `F0`, `FE` y `FF` suelen ser reset de fábrica.

## Encontrar una lámpara perdida

Una lámpara solo se anuncia cuando **no** está conectada a nada. Si no
aparece en el escaneo, lo normal es que la tenga cogida el móvil: cierra
Raingel o apaga el Bluetooth del teléfono.

Después, `python -m vclight find` imprime la señal cada dos segundos.
Camina con el portátil: el número sube al acercarte. No es una medida de
distancia, la señal rebota en las paredes, pero para el juego de frío o
caliente sirve.

## Estado

Comprobado en macOS 25.5 con dos lámparas a la vez. La codificación de
paletas reproduce byte a byte los literales del APK, así que la lectura
del protocolo es correcta.

Los nombres de los 18 modos son los oficiales del fabricante, sacados de
los recursos del APK.

Lo que sigue abierto: el significado de cada índice de la paleta interna
y los parámetros del opcode `10`.

## Trabajo previo

- [AndrianBdn/open-vc-blelight](https://github.com/AndrianBdn/open-vc-blelight)
- [arizustudio/vc-blelight-studio-pro](https://github.com/arizustudio/vc-blelight-studio-pro)

Ambos cubren tres comandos: encendido, brillo y color. Ninguno documenta
los modos ni el hecho de que la tira sea direccionable.

## Licencia

MIT.
