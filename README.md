# vclights

Control **VC-BLELIGHT** LED lamps over Bluetooth without the official app.

These are the lamps and strips made by DoHome, sold through Temu and
similar under names like AMill, and driven by the **Raingel** app. This
project does the same from Python, and rather more.

The protocol was extracted from the Raingel APK by decompiling it. Every
opcode in `vclight/protocol.py` appears literally in the app's own code;
none of it was guessed by poking bytes at the hardware. The full write-up
is in [`docs/protocol.md`](docs/protocol.md).

## What it does

- Power, brightness and static colour.
- The **18 firmware modes**, with speed, brightness, a palette of up to
  8 colours, travel direction and section splitting. These effects move
  along the strip and the lamp computes them itself.
- **Scenes** built on a perceptual colour engine: plasma, lava, comet,
  heartbeat, embers, aurora, storm, sunrise — plus a show that strings
  six of them together with cross-fades.
- **Frame-by-frame animations** computed here: fire, storm, rainbow,
  a wave that travels between lamps.
- Several lamps driven as one group, choreographed against each other.
- A **proximity meter** by signal strength, to find a lamp you have lost.

## Install

```bash
git clone https://github.com/agustinprod/vclights
cd vclights
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Use

```bash
python -m vclight scan                # lamps in range, family and distance
python -m vclight modes               # the 18 firmware modes
python -m vclight colors              # the internal palette
python -m vclight mode 5 --speed 50   # meteor
python -m vclight mode 11 --colors 0 6 3 1 4 2 5   # rainbow, spectral order
python -m vclight scene plasma 120    # perceptual-colour scene
python -m vclight show                # six scenes with cross-fades
python -m vclight fx fire 60          # frame-by-frame fire
python -m vclight color 255 80 0      # static orange
python -m vclight find                # live proximity meter
```

As a library:

```python
import asyncio
from vclight import discover, Lamp

async def main():
    lamps = await discover()
    async with Lamp(lamps[0].device) as lamp:
        await lamp.on()
        await lamp.mode(11, speed=80, colors=(0, 2, 4, 6))   # rainbow

asyncio.run(main())
```

## Two ways to animate

| | Firmware modes | Computed here |
|---|---|---|
| Where it runs | On the lamp | On the computer |
| Travels along the strip | Yes | No, one colour at a time |
| Colour control | Palette of 8 indices | Any RGB |
| Needs a connection | No, keeps running | Yes, throughout |

The firmware modes are the only thing that produces movement **within**
a lamp. There is no command to address an individual LED, so anything
computed here paints the whole strip one colour and shows at once across
it. What the computed animations offer instead is fine control of colour
and timing, and they can move an effect **between** several lamps.

To watch an effect travel the strip, start a firmware mode and **leave
it alone**:

```bash
python -m vclight mode 5 --speed 50   # and send nothing else
```

Two things will make a mode look broken when it is not:

1. **A later colour command cancels it.** Opcode 03 returns the lamp to
   static colour.
2. **Do not close the connection straight afterwards.** The write has no
   response: the call returns at once because the system queued it, not
   because it went out. Disconnecting at that moment loses the packet in
   silence.

## Is your lamp addressable?

The lamp publishes that in its own advertisement, before you connect.
`python -m vclight scan` translates it:

```
  -63 dBm  5BF1A60D-…
           LIGHT_MAGIC / strip  addressable   close, 1 to 3 m
```

Only groups `LIGHT_MAGIC`, `LIGHT_MAGIC_W` and `LIGHT_MAGIC_CW` carry
addressable LEDs. On the others the firmware modes still work, but they
show across the whole lamp at once because there is nothing to travel.

## If the colours come out wrong, fix this first

```bash
python -m vclight order 1
```

A strip can be wired with the chip's channels in any order, and when the
firmware assumes the wrong one every colour is permuted: you send red
and get green. Two lamps of the same model can differ — the two this was
built against did, and nothing about colour worked until they were set.

White looks correct in every order, which is what makes it confusing.
The giveaway is warm white coming out magenta or green. If you do not
know your value, `python -m vclight order --sweep` shows red under each
of the six in turn; the right one is where the lamp actually looks red.

The setting sticks in the lamp, so it is a one-off. Every command also
takes `--order 1` if you would rather send it each time.

## The lamp confirms nothing

The BLE write is *without response*. A malformed command raises no error:
the lamp ignores it in silence. The only possible verification is looking
at it, which is what `python -m vclight fx test` is for — red, green,
blue and off, three seconds each.

Related warning: **do not probe opcodes at random.** On this chip family
`F0`, `FE` and `FF` are usually a factory reset.

## Colour

Interpolating in RGB sends any fade through a muddy grey: the midpoint
between red and blue is `(128, 0, 127)`. In OKLab it is `(140, 83, 162)`,
a clean violet of the same brightness. All colour here goes through
OKLab, and brightness is gamma corrected, because the LED responds
linearly but the eye does not.

Scenes are pure functions of time, `scene(t, i, n) -> (colour,
brightness)`, with no loop of their own. That is what makes them
composable: two scenes can be asked about the same instant and their
answers blended, which is how the cross-fades in `show` work.

## Finding a lost lamp

A lamp only advertises while it is **not** connected to anything. If it
does not show up in a scan, the usual reason is that the phone is holding
it: close Raingel or turn the phone's Bluetooth off.

Then `python -m vclight find` prints the signal every two seconds. Walk
around with the laptop: the number rises as you close in. It is not a
distance measurement — the signal bounces off walls — but it works for a
game of hot and cold.

## Verified with a camera, not by trust

Because the protocol acknowledges nothing, `tools/camera_probe.py` sends
a command, photographs the lamps with the laptop webcam, and lays every
step out in one labelled contact sheet. That is how these were settled:

- Colour order 1 is plain RGB, and both lamps were on the wrong one.
- Bytes 4, 5 and 6 of the colour command light nothing.
- A colour command really does cancel a running mode.
- All eight palette entries are the colours the APK cross-reference said.
- A single-colour palette is ignored; repeat the index instead.
- Mode 5 does travel along the tube.

The camera tools need `pip install -r requirements-tools.txt` and camera
permission for the terminal.

## Status

Tested on macOS 25.5 with two lamps at once. Firmware modes confirmed
running on the hardware. The palette encoding reproduces the APK's own
literals byte for byte, and the palette itself was then confirmed on the
lamps.

The internal palette is decoded and confirmed on the hardware: 0 red,
1 green, 2 blue, 3 yellow, 4 cyan, 5 violet, 6 orange, 7 white.
`python -m vclight colors` lists it along with the 19 combinations the
app itself offers.

Still open: the firmware's exact RGB values for those eight entries, and
the parameters of opcode `10`.

## Prior work

- [AndrianBdn/open-vc-blelight](https://github.com/AndrianBdn/open-vc-blelight)
- [arizustudio/vc-blelight-studio-pro](https://github.com/arizustudio/vc-blelight-studio-pro)

Both cover three commands: power, brightness and colour. Neither
documents the modes, nor that the strip is addressable.

## Licence

MIT.
