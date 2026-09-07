# The VC-BLELIGHT protocol, in detail

Everything in this document comes from the official **Raingel** app,
decompiled with `jadx`. Nothing is guesswork except where stated.

## Where it comes from

The app's package is `com.raingel.app`, but the lamp code lives under
`am.doit.dohome.strip`: the real manufacturer is **DoHome** and Raingel
is one of its white labels. The classes that matter:

| Class | What it gives |
|---|---|
| `service/StripBleManager.java` | the service and characteristic UUIDs |
| `service/StripManager.java` | one method per command, with the bytes |
| `bean/Mode.java` | the 18-mode catalogue and its encoding |
| `bean/StripDevice.java` | the device families |
| `page/ModeFragment.java` | how mode, speed and brightness combine |
| `res/values/arrays.xml` | the official mode names |

To reproduce it:

    unzip Raingel.xapk                 # the xapk holds the base apk
    unzip com.raingel.app.apk
    jadx -d src com.raingel.app.apk    # without --no-res: the names are in there
    grep -rl "AE01" src/

## Transport

| | |
|---|---|
| Advertised name | `VC-BLELIGHT` |
| Service in the advertisement | `0000AF30-0000-1000-8000-00805F9B34FB` |
| Actual service | `0000AE30-…` |
| Write | `0000AE01-…`, *write without response* |
| Notify | `0000AE02-…` |

Two details that cost time if you do not know them:

1. The service in the advertisement (`AF30`) **is not** the one exposed
   once connected (`AE30`). The app filters its scan on `AF30` and then
   looks for `AE30` over the established connection.
2. The write carries no acknowledgement. A malformed command raises no
   error: nothing simply happens. The only possible verification is
   looking at the lamp.

The app also subscribes to `AE02`, but across these tests the lamp never
sent a single notification. There appears to be no return channel.

## Commands

The first byte is the opcode. The right-hand column names the
`StripManager` method.

| Opcode | Bytes | Method in the APK |
|---|---|---|
| `01` | `01 <0\|1>` | `switchLight` |
| `02` | `02 <0-255>` | `updateBrightness` |
| `03` | `03 r g b w1 w2 w3` | `ColorAdjust` |
| `04` | `04 <sens> <mode>` | `deviceMicUpdate` |
| `05` | `05 <on> 01 <lo> <hi>` | `updateDelay` |
| `07` | `07 <mode> <speed> <brightness> <palette>` | `ModeAdjust` |
| `08` | clock | `updateDateTime` |
| `0C` | timer | `updateTimer` |
| `0D` | up to 6 alarms | `updateAlarm` |
| `0E` | `0E <order>` | `IcOrder` |
| `0F` | `0F <lo> <hi>` | `IcLength` |
| `10` | recorder | `recorderUpdate` |
| `11` | `11 04` | `openPhoneMic` |
| `12` | `12 <a> <b>` | `setRgbOrder` |
| `15` | `15 <on> 00 <level>` | `updateMotor` |
| `17` | `17 <on> 00 <level> 64` | `updateLaser` |

`updateMotor` and `updateLaser` do nothing on an ordinary lamp: the app
serves DoHome's whole range, which includes models fitted with a motor
and with a laser.

**Do not probe opcodes at random.** On this chip family `F0`, `FE` and
`FF` are usually a factory reset.

### Colour takes six bytes, not three

`ColorAdjust(r, g, b, w1, w2, w3)`. The app always sends zeroes in the
last three. On models with a white channel those bytes are meant to be
warm white, cool white and an auxiliary.

Tested one at a time on a magic strip: bytes 4, 5 and 6 light nothing.
On this hardware they really are padding, and the app is right to zero
them.

### Set the colour order first, or nothing else makes sense

Before anything about colour can be trusted, the chip's colour order has
to match the wiring. Opcode `0E`, value 1, is plain RGB.

A strip can be wired with the chip's channels in any order. When the
firmware assumes the wrong one, every colour comes out permuted: send
red, get green. Two lamps of the same model can differ. The two used
here did:

| Sent | Lamp A showed | Lamp B showed |
|---|---|---|
| `03 ff 00 00` red | red | green |
| `03 00 ff 00` green | blue | blue |
| `03 00 00 ff` blue | green | red |
| `03 ff ff ff` white | white | white |

White looks right in every order, which is what makes the fault
confusing: it only shows up on colours. The giveaway is warm white
coming out magenta or green.

After `0E 01` both lamps map red to red, green to green and blue to
blue. Verified with a camera; order 2 swaps green and blue, and 3 to 6
are the other permutations.

### Which device each lamp is

The lamp publishes its family in the BLE advertisement, under
manufacturer ID **22872**, as two bytes: group, then type.

| Group | | Group | |
|---|---|---|---|
| 1 | LIGHT_DIM | 6 | LIGHT_RGBCW |
| 2 | LIGHT_CCT | 16 | **LIGHT_MAGIC** |
| 3 | LIGHT_RGB | 17-18 | MAGIC, two-path |
| 4 | LIGHT_RGBW | 20 | **LIGHT_MAGIC_W** |
| 5 | LIGHT_RGBC | 21 | **LIGHT_MAGIC_CW** |

Type: 1 bulb, 2 strip, 3 ceiling, 4 flood, 5 spot.

`StripDevice.isMagic()` is true only for groups 16, 20 and 21. Those are
the ones with addressable LEDs, and therefore the only ones where an
effect **travels** along the strip.

Beware the easy inference: the app having `IcLength` and `IcOrder` does
not prove any particular lamp is addressable. The same app serves
DoHome's whole range, motors and lasers included. The advertisement byte
is the only reliable source.

**There is no individual pixel command.** Not even on magic devices:
movement comes only from the internal modes. From outside you can send a
global colour and nothing else, so any animation computed on a computer
shows at once across the whole strip. That is the boundary of the device.

## Dynamic modes (opcode 07)

    07  <mode byte>  <speed 0-100>  <brightness 0-100>  <palette, 5 bytes>

### The mode byte

From `Mode.formatValue()`:

    value = (id & 0x1F) | (section << 7) | (direction << 6)

The low five bits are the mode number, 1 to 18. The top two change
meaning per mode:

| Modes | bit 7 | bit 6 |
|---|---|---|
| 1-13, 15, 18 | split into sections | travel direction |
| 14 | — | one colour or many |
| 16 | — | alternation |
| 17 | — | curtain up or down |

### The palette

One byte with the number of colours, then the indices packed two per
byte, a nibble each:

    palette(0, 1)     -> 02 01 00 00 00
    palette(2, 3, 4)  -> 03 23 40 00 00

Both examples appear verbatim in `Mode.java`, which confirms the reading
is correct. Indices run 0 to 7 over an internal firmware palette:

| | | | |
|---|---|---|---|
| 0 red | 1 green | 2 blue | 3 yellow |
| 4 cyan | 5 violet | 6 orange | 7 white |

That mapping is nowhere stated in the APK. It was cross-referenced out
of it. Every `Mode` carries both a `colorId`, which indexes the
`mode_colors` array of names, and a `colorValue`, which encodes the
palette indices. Line the two up across all 19 entries and each index
resolves to exactly one name, with no contradiction anywhere:

| colorId | name | colorValue | indices |
|---|---|---|---|
| 0 | RD GN | `0201000000` | 0, 1 |
| 4 | BU YE CYAN | `0323400000` | 2, 3, 4 |
| 5 | CYAN VT OG | `0345600000` | 4, 5, 6 |
| 17 | RD OR YE GN CYAN BU VT | `0706314250` | 0, 6, 3, 1, 4, 2, 5 |
| 18 | RD GN BU YE CYAN VT OR WT | `0801234567` | 0 to 7 |

Entry 17 is the clincher. Its indices are a scrambled permutation, yet
the names it maps to come out in spectral order — red, orange, yellow,
green, cyan, blue, violet. A wrong mapping would not turn a shuffled
permutation into a rainbow.

`protocol.PRESETS` holds all 19 combinations in the app's own order, so
`PRESETS[colorId]` gives the indices the app would have sent.

### The catalogue

These are the **manufacturer's own names**, from the `scene_magic` array
in `res/values/arrays.xml` inside the APK. Its 18 entries follow the same
order as the modes.

The ordering checks out on its own: entry 17 is "curtain up/down", and in
`Mode.format()` mode 17 is precisely the one carrying the curtain
up-or-down flag.

| | | | |
|---|---|---|---|
| 1 fade | 2 jump | 3 breathe | 4 flash |
| 5 meteor | 6 stack | 7 float | 8 follow spot |
| 9 wave | 10 water | 11 rainbow | 12 blink |
| 13 bounce | 14 shuttle | 15 twinkle | 16 on/off |
| 17 curtain | 18 alternate | | |

In three modes bit 6 is not the travel direction:

| Mode | What bit 6 switches |
|---|---|
| 14 shuttle | one colour or many |
| 16 on/off | alternation |
| 17 curtain | up or down |

### A single-colour palette is ignored

Send a palette of one colour and the firmware discards it, falling back
to its default red and green. To get one flat colour out of a mode,
repeat the index: `palette(3, 3)`. That is also the trick that let each
palette entry be verified on its own.

### Two traps when starting a mode

1. **A colour command cancels it.** Opcode 03 returns the lamp to static
   colour. Start the mode and send nothing else. Confirmed with a
   camera: a mode showing bands along the tube, then one colour
   command, and the tube goes flat again.
2. **Do not disconnect straight afterwards.** The write has no response:
   the call returns at once because the system queued it, not because it
   went out. Closing the connection at that moment loses the packet with
   no warning whatsoever. Wait a good second.

## Speed ceiling

A write without response returns immediately, so timing the call tells
you nothing useful: the system queues it. The real limit is the BLE
connection interval, 15 to 45 ms, meaning between 20 and 60 commands per
second. This project animates at 22 frames per second, comfortably under.

## How this was verified

The protocol acknowledges nothing, so every claim about what a command
does needs somebody looking at the lamp. `tools/camera_probe.py` takes
the person out of the loop: it sends a command, photographs the lamps
with the laptop webcam, and lays every step out in one labelled contact
sheet.

Automatic colour measurement was tried first and abandoned. The webcam
re-runs exposure and white balance on every shot, so the frame shifts
between captures and background subtraction lights up the whole room;
and skin tones sit in the same hue range as a warm lamp. Reading the
pictures is less clever and works.

`tools/fix_color_order.py` applies the same idea to one question: it
walks all six colour orders, shows pure red after each, and the right
value is the panel where the lamp actually looks red.

## Still unknown

- The firmware's exact RGB values for the eight palette entries. Which
  colour each index is has been confirmed on the hardware; the precise
  shade has not.
- The parameters of `recorderUpdate` (opcode `10`).
- Whether `AE02` ever notifies anything at all.
