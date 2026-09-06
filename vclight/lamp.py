"""Descubrimiento y control de lamparas VC-BLELIGHT por BLE.

Uso tipico:

    import asyncio
    from vclight import discover, Lamp

    async def main():
        lamps = await discover()
        async with Lamp(lamps[0].device) as lamp:
            await lamp.on()
            await lamp.mode(8, speed=70)      # meteoro

    asyncio.run(main())
"""
import asyncio
import colorsys
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner

from . import protocol as p


@dataclass
class Found:
    """Una lampara vista en el escaneo."""
    device: object   # BLEDevice de bleak
    rssi: int        # intensidad de senal en dBm; menos negativo es mas cerca

    @property
    def address(self):
        return self.device.address

    def distancia(self):
        """Traduce el RSSI a una distancia aproximada, para buscarla a mano.

        No es una medida: la senal rebota en las paredes y varia varios
        dB de un segundo a otro. Sirve para el juego de frio o caliente.
        """
        if self.rssi > -50:  return "muy cerca, menos de 1 m"
        if self.rssi > -65:  return "cerca, 1 a 3 m"
        if self.rssi > -80:  return "media, 3 a 8 m"
        return "lejos, probablemente otra habitacion"


async def discover(timeout=12.0):
    """Devuelve las lamparas al alcance, la mas cercana primero.

    Una lampara solo se anuncia cuando NO esta conectada a nada. Si no
    aparece ninguna, lo normal es que la tenga cogida el movil: cierra
    la app Raingel o apaga el Bluetooth del telefono y repite.
    """
    encontradas = {}

    def visto(device, adv):
        if (adv.local_name or device.name or "").upper() == p.DEVICE_NAME:
            encontradas[device.address] = Found(device, adv.rssi)

    scanner = BleakScanner(detection_callback=visto)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    return sorted(encontradas.values(), key=lambda f: -f.rssi)


class Lamp:
    """Una lampara conectada. Se usa como context manager asincrono."""

    def __init__(self, device, timeout=25.0):
        self.device = device
        self._client = BleakClient(device, timeout=timeout)

    async def __aenter__(self):
        await self._client.connect()
        return self

    async def __aexit__(self, *exc):
        await self._client.disconnect()

    @property
    def address(self):
        return self.device.address

    async def send(self, data):
        """Escribe un comando crudo. Sin acuse de recibo: si el comando
        esta mal, la lampara lo ignora y no hay forma de enterarse."""
        await self._client.write_gatt_char(p.CHAR_WRITE, bytearray(data), response=False)

    # ------------------------------------------------------ comandos ----

    async def on(self):
        await self.send(p.cmd_power(True))

    async def off(self):
        await self.send(p.cmd_power(False))

    async def brightness(self, level):
        """Brillo global, 0 a 255."""
        await self.send(p.cmd_brightness(level))

    async def rgb(self, r, g, b):
        """Color fijo. Corta cualquier modo dinamico en curso."""
        await self.send(p.cmd_color(r, g, b))

    async def hsv(self, h, s=1.0, v=1.0):
        """Igual que rgb pero en tono, saturacion y valor. El tono va de
        0 a 1 y da la vuelta, asi que es lo comodo para animar colores."""
        r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
        await self.rgb(r * 255, g * 255, b * 255)

    async def mode(self, mode_id, speed=50, brightness=100,
                   colors=(0, 1), direction=0, section=0):
        """Lanza un efecto interno del firmware, de los 18 del catalogo.

        Estos efectos se mueven a lo largo de la tira y los calcula la
        propia lampara, asi que no gastan ancho de banda BLE ni se cortan
        si el portatil se aleja.
        """
        await self.send(p.cmd_mode(mode_id, speed, brightness, colors, direction, section))

    async def ic_length(self, leds):
        """Ajusta el numero de LEDs declarado. Solo si los efectos se
        cortan a mitad de la tira."""
        await self.send(p.cmd_ic_length(leds))

    async def ic_order(self, order):
        """Ajusta el orden de color del chip. Solo si los colores salen
        cambiados de sitio."""
        await self.send(p.cmd_ic_order(order))


class Group:
    """Varias lamparas manejadas como una sola.

    Cada comando se manda a todas. No hay sincronia garantizada entre
    ellas, porque cada conexion BLE tiene su propio ritmo, pero a ojo
    la diferencia no se aprecia.
    """

    def __init__(self, devices):
        self.lamps = [Lamp(d) for d in devices]

    async def __aenter__(self):
        for lamp in self.lamps:
            await lamp.__aenter__()
        return self

    async def __aexit__(self, *exc):
        for lamp in self.lamps:
            await lamp.__aexit__(*exc)

    def __len__(self):
        return len(self.lamps)

    def __iter__(self):
        return iter(self.lamps)

    async def send(self, data):
        for lamp in self.lamps:
            await lamp.send(data)

    async def on(self):                 await self.send(p.cmd_power(True))
    async def off(self):                await self.send(p.cmd_power(False))
    async def rgb(self, r, g, b):       await self.send(p.cmd_color(r, g, b))
    async def brightness(self, level):  await self.send(p.cmd_brightness(level))

    async def mode(self, mode_id, **kw):
        await self.send(p.cmd_mode(mode_id, **kw))
