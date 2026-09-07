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
    """One connected lamp. Used as an async context manager.

    color_order matters more than it looks. These strips can be wired
    with the chip's channels in any order, and when the firmware's
    assumption does not match the wiring, every colour comes out
    permuted: you send red and get green. Two lamps of the same model
    can differ.

    Send it ONCE and then leave it alone. The app puts it behind a
    settings screen for a reason: resending 0E on every connection was
    tried here and it corrupted colour instead of fixing it. Order 1 is
    plain RGB. Use `python -m vclight order 1` once per lamp, or
    `order --sweep` to find yours.

    gain scales each channel on the way out, to compensate the weaker
    red die. See rgb().
    """

    def __init__(self, device, timeout=25.0, color_order=None, gain=None):
        self.device = device
        self.color_order = color_order
        self.gain = gain
        # Last length bar() declared, so it knows whether the next bar
        # grows, in which case the clear and its flash are unnecessary.
        # None means unknown, so the first bar always clears.
        self._bar_n = None
        self._client = BleakClient(device, timeout=timeout)

    async def __aenter__(self):
        await self._client.connect()
        if self.color_order is not None:
            await self.send(p.cmd_ic_order(self.color_order))
            await asyncio.sleep(0.3)
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
        """Static colour. Cancels any dynamic mode in progress.

        If a gain was given, each channel is scaled by it first. The red
        die on these strips is weaker than the green and blue at partial
        duty, so warm tones drift green and mid greys drift blue. A gain
        of roughly (1.0, 0.62, 0.55) pulls them back. See `vclight
        calibrate`.
        """
        if self.gain:
            r, g, b = (v * k for v, k in zip((r, g, b), self.gain))
        await self.send(p.cmd_color(r, g, b))

    async def hsv(self, h, s=1.0, v=1.0):
        """Same as rgb but in hue, saturation and value. Hue runs 0 to 1
        and wraps, which makes it the convenient one for animating."""
        r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
        await self.rgb(r * 255, g * 255, b * 255)

    # LEDs on the tubes this was built against, found by declaring
    # lengths and photographing: the fill grew linearly and stopped
    # growing at 72. Pass leds= for a different strip.
    LEDS = 72

    # The firmware ignores a declared length below this and drives
    # exactly this many LEDs instead. Measured: 12, 13, 14, 15 and 16 are
    # the same photograph. The app's settings screen refuses anything
    # under 16 before it reaches the wire, which is how the number is
    # confirmed from two directions. See docs/protocol.md.
    MIN_LEDS = 16

    async def bar(self, fraction, rgb=(255, 255, 255), leds=None, clear=False):
        """Light a fraction of the tube, as a progress bar.

        There is no per pixel command on these lamps, but `IcLength`
        truncates: tell the lamp the strip is shorter than it is and it
        drives that many LEDs from the base. So the bar is drawn by lying
        about the length.

        The smallest bar this hardware can draw is `MIN_LEDS`, which is
        about 22 percent of the tube. It is a firmware floor, not optics
        and not a rounding error: below it the lamp draws the 16 LED bar
        unchanged. So the bar has two states below 22 percent, that stub
        and off, and one LED of resolution above it. Anything under half
        of `MIN_LEDS` turns the strip off rather than showing a stub that
        would misreport the progress by 20 points.

        The clear is the part that is easy to get wrong. LEDs past the
        declared length are not switched off, they stop receiving data
        and hold their last value, so shortening the bar leaves the old
        fill lit above the new one. Painting the whole strip black at
        full length first latches every LED off, and only then does the
        truncated fill show on its own. Without this, a bar that only
        ever grows looks perfect and one that goes down is nonsense.

        The clear costs a visible flash, so it is skipped when the bar
        only grows, which is the common case for progress. Pass
        `clear=True` to force it if something else has touched the lamp.

        `IcLength` is a configuration command the app keeps behind a
        settings screen, and whether the lamp commits it to flash is not
        known. Stepping a bar every few seconds is fine; driving it at
        animation rates is not a good idea.

        The declared length is left on the lamp, so set it back with
        `ic_length(256)` when you are done using it as a bar.
        """
        total = leds or self.LEDS
        n = round(min(1.0, max(0.0, float(fraction))) * total)
        if n < self.MIN_LEDS // 2:
            n = 0
        elif n < self.MIN_LEDS:
            n = self.MIN_LEDS      # the lamp would do this anyway
        if clear or n == 0 or self._bar_n is None or n < self._bar_n:
            await self.send(p.cmd_ic_length(256))
            await asyncio.sleep(0.45)
            await self.brightness(255)
            await self.send(p.cmd_color(0, 0, 0))  # latch every LED off
            await asyncio.sleep(0.7)
        self._bar_n = n
        if n == 0:
            return
        await self.send(p.cmd_ic_length(n))
        await asyncio.sleep(0.45)
        await self.brightness(255)
        await self.rgb(*rgb)

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

    def __init__(self, devices, color_order=None, gain=None):
        self.lamps = [Lamp(d, color_order=color_order, gain=gain) for d in devices]

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

    # These delegate to each Lamp rather than building the command here.
    # Anything held per lamp, the channel gain for instance, lives on the
    # Lamp; a Group that formats its own commands silently ignores it.
    async def on(self):
        for lamp in self.lamps:
            await lamp.on()

    async def off(self):
        for lamp in self.lamps:
            await lamp.off()

    async def rgb(self, r, g, b):
        for lamp in self.lamps:
            await lamp.rgb(r, g, b)

    async def brightness(self, level):
        for lamp in self.lamps:
            await lamp.brightness(level)

    async def mode(self, mode_id, **kw):
        await self.send(p.cmd_mode(mode_id, **kw))

    async def bar(self, fraction, rgb=(255, 255, 255), leds=None, clear=False):
        for lamp in self.lamps:
            await lamp.bar(fraction, rgb, leds, clear)
