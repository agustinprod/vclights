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
last three. On models with a white channel those bytes are warm white,
cool white and an auxiliary.

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
is correct. Indices run 0 to 7 over an internal firmware palette.

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

### Two traps when starting a mode

1. **A colour command cancels it.** Opcode 03 returns the lamp to static
   colour. Start the mode and send nothing else.
2. **Do not disconnect straight afterwards.** The write has no response:
   the call returns at once because the system queued it, not because it
   went out. Closing the connection at that moment loses the packet with
   no warning whatsoever. Wait a good second.

## Speed ceiling

A write without response returns immediately, so timing the call tells
you nothing useful: the system queues it. The real limit is the BLE
connection interval, 15 to 45 ms, meaning between 20 and 60 commands per
second. This project animates at 22 frames per second, comfortably under.

## Still unknown

- What each index of the internal palette (0 to 7) actually is.
- The parameters of `recorderUpdate` (opcode `10`).
- Whether `AE02` ever notifies anything at all.
