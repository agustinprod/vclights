"""Discovery and control of VC-BLELIGHT lamps over BLE.

Typical use:

    import asyncio
    from vclight import discover, Lamp

    async def main():
        lamps = await discover()
        async with Lamp(lamps[0].device) as lamp:
            await lamp.on()
            await lamp.mode(5, speed=50)      # meteor

    asyncio.run(main())
"""
import asyncio
import colorsys
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner

from . import protocol as p


@dataclass
class Found:
    """A lamp seen during a scan.

    Group and type come from the advertisement itself, without
    connecting: the lamp publishes them in two manufacturer data bytes.
    """
    device: object   # bleak BLEDevice
    rssi: int        # signal strength in dBm; less negative means closer
    group: int = 0   # device family, see protocol.GROUPS
    type: int = 0    # physical shape, see protocol.TYPES

    @property
    def address(self):
        return self.device.address

    @property
    def is_magic(self):
        """True when it has addressable LEDs and effects can travel."""
        return p.is_magic(self.group)

    def describe(self):
        return (f"{p.GROUPS.get(self.group, '?')} / {p.TYPES.get(self.type, '?')}"
                f"  {'addressable' if self.is_magic else 'single colour'}")

    def distance(self):
        """Turn RSSI into a rough distance, to hunt a lamp down by hand.

        This is not a measurement: the signal bounces off walls and moves
        several dB from one second to the next. It is good enough for a
        game of hot and cold.
        """
        if self.rssi > -50:  return "very close, under 1 m"
        if self.rssi > -65:  return "close, 1 to 3 m"
        if self.rssi > -80:  return "medium, 3 to 8 m"
        return "far, probably another room"


async def discover(timeout=12.0):
    """Return the lamps in range, closest first.

    A lamp only advertises while it is NOT connected to anything. If none
    show up, the usual reason is that the phone is holding it: close the
    Raingel app or turn the phone's Bluetooth off, then retry.
    """
    found = {}

    def seen(device, adv):
        if (adv.local_name or device.name or "").upper() != p.DEVICE_NAME:
            return
        data = adv.manufacturer_data.get(p.APP_ID, b"")
        group, kind = (data[0], data[1]) if len(data) >= 2 else (0, 0)
        found[device.address] = Found(device, adv.rssi, group, kind)

    scanner = BleakScanner(detection_callback=seen)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    return sorted(found.values(), key=lambda f: -f.rssi)


class Lamp:
    """One connected lamp. Used as an async context manager."""

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
        """Write a raw command. No acknowledgement: a malformed command
        is ignored and there is no way to find out."""
        await self._client.write_gatt_char(p.CHAR_WRITE, bytearray(data), response=False)

    # -------------------------------------------------------- commands ----

    async def on(self):
        await self.send(p.cmd_power(True))

    async def off(self):
        await self.send(p.cmd_power(False))

    async def brightness(self, level):
        """Global brightness, 0 to 255."""
        await self.send(p.cmd_brightness(level))

    async def rgb(self, r, g, b):
        """Static colour. Cancels any dynamic mode in progress."""
        await self.send(p.cmd_color(r, g, b))

    async def hsv(self, h, s=1.0, v=1.0):
        """Same as rgb but in hue, saturation and value. Hue runs 0 to 1
        and wraps, which makes it the convenient one for animating."""
        r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
        await self.rgb(r * 255, g * 255, b * 255)

    async def mode(self, mode_id, speed=50, brightness=100,
                   colors=(0, 1), direction=0, section=0):
        """Start one of the 18 firmware effects.

        These travel along the strip and the lamp computes them itself,
        so they cost no BLE bandwidth and do not break up when the laptop
        wanders off.

        Two gotchas that cost an afternoon if you do not know them:

        - A later colour command cancels the mode. Start the mode and
          send nothing else.
        - Do not disconnect right afterwards. The write has no response
          and returns immediately because the system queues it; closing
          the connection at that moment loses the packet with no warning.
          Wait at least a second.
        """
        await self.send(p.cmd_mode(mode_id, speed, brightness, colors, direction, section))

    async def ic_length(self, leds):
        """Set the declared LED count. Only if effects stop halfway."""
        await self.send(p.cmd_ic_length(leds))

    async def ic_order(self, order):
        """Set the chip's colour order. Only if colours come out swapped."""
        await self.send(p.cmd_ic_order(order))


class Group:
    """Several lamps driven as one.

    Every command goes to all of them. There is no guaranteed sync
    between them, since each BLE connection runs at its own pace, but by
    eye the difference does not show.
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
