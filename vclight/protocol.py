"""BLE protocol of VC-BLELIGHT lamps (made by DoHome).

Everything here comes from the official Raingel app, decompiled with
jadx. The relevant classes:

    am.doit.dohome.strip.service.StripManager     the commands
    am.doit.dohome.strip.service.StripBleManager  the UUIDs
    am.doit.dohome.strip.bean.Mode                mode encoding
    res/values/arrays.xml                         the mode names

Nothing here was guessed by poking bytes at the hardware: every opcode
appears literally in the app's own code.

Transport
---------
The lamp advertises service AF30 but exposes AE30. Commands go to
characteristic AE01, which is "write without response": the lamp
acknowledges nothing, so a malformed command fails silently.
"""

# ------------------------------------------------------ device families ---
# The lamp identifies itself in the BLE advertisement, before you connect.
# Under manufacturer ID 22872 it sends two bytes: group, then type.
#
# This matters because it tells you whether the strip is addressable. The
# app decides with StripDevice.isMagic(), true only for groups 16, 20 and
# 21. On a non-magic lamp the firmware modes still run, but they cannot
# travel: there are no individual LEDs to travel across.

APP_ID = 22872   # DoHome's manufacturer ID in the advertisement

GROUPS = {
    1:  "LIGHT_DIM",          2:  "LIGHT_CCT",           3:  "LIGHT_RGB",
    4:  "LIGHT_RGBW",         5:  "LIGHT_RGBC",          6:  "LIGHT_RGBCW",
    16: "LIGHT_MAGIC",        17: "LIGHT_MAGIC_W_2PATH", 18: "LIGHT_MAGIC_C_2PATH",
    19: "LIGHT_START",        20: "LIGHT_MAGIC_W",       21: "LIGHT_MAGIC_CW",
}

TYPES = {1: "bulb", 2: "strip", 3: "ceiling", 4: "flood", 5: "spot"}

MAGIC_GROUPS = {16, 20, 21}   # StripDevice.isMagic()


def is_magic(group):
    """Whether the device has individually addressable LEDs.

    Only magic devices can move an effect along the strip. On the rest,
    any animation appears at once across the whole lamp.
    """
    return group in MAGIC_GROUPS


# ---------------------------------------------------------------- UUIDs ---

def uuid16(short):
    """Expand a 16-bit short UUID into the full Bluetooth SIG form."""
    return f"0000{short.lower()}-0000-1000-8000-00805f9b34fb"


SERVICE_ADVERTISED = uuid16("AF30")   # what the advertisement carries
SERVICE            = uuid16("AE30")   # what it actually exposes once connected
CHAR_WRITE         = uuid16("AE01")   # every command goes here
CHAR_NOTIFY        = uuid16("AE02")   # the app subscribes; nothing ever arrives
DEVICE_NAME        = "VC-BLELIGHT"


# -------------------------------------------------------------- opcodes ---
# First byte of every command. Names match the StripManager methods.

OP_POWER      = 0x01   # switchLight       01 <0|1>
OP_BRIGHTNESS = 0x02   # updateBrightness  02 <0-255>
OP_COLOR      = 0x03   # ColorAdjust       03 r g b w1 w2 w3
OP_MIC        = 0x04   # deviceMicUpdate   04 <sensitivity> <mode>
OP_DELAY      = 0x05   # updateDelay       05 <on> 01 <lo> <hi>
OP_MODE       = 0x07   # ModeAdjust        07 <mode> <speed> <brightness> <palette>
OP_DATETIME   = 0x08   # updateDateTime    sets the internal clock
OP_TIMER      = 0x0C   # updateTimer
OP_ALARM      = 0x0D   # updateAlarm       up to 6 alarms
OP_IC_ORDER   = 0x0E   # IcOrder           colour order of the LED chip
OP_IC_LENGTH  = 0x0F   # IcLength          number of LEDs on the strip
OP_RECORDER   = 0x10   # recorderUpdate
OP_PHONE_MIC  = 0x11   # openPhoneMic      11 04
OP_RGB_ORDER  = 0x12   # setRgbOrder
OP_MOTOR      = 0x15   # updateMotor       models fitted with a motor
OP_LASER      = 0x17   # updateLaser       models fitted with a laser

# Do not probe these blindly: on this family of chips they are usually a
# factory reset.
DANGEROUS_OPCODES = {0xF0, 0xFE, 0xFF}


# ---------------------------------------------------------------- modes ---
# The firmware carries 18 dynamic effects. On magic lamps they travel
# along the strip; elsewhere they appear at once across the whole lamp.
#
# These are the manufacturer's OWN names, taken from the APK resources:
# the scene_magic array in res/values/arrays.xml, whose 18 entries follow
# the same order as the modes.
#
# The ordering checks out on its own: entry 17 is "curtain up/down", and
# in Mode.format() mode 17 is precisely the one carrying the curtain
# up-or-down flag.

MODES = {
    1:  "fade",         # cross-fade between colours
    2:  "jump",         # hard cut between colours
    3:  "breathe",      # breathing
    4:  "flash",        # flash
    5:  "meteor",       # meteor with a tail
    6:  "stack",        # LEDs pile up one by one
    7:  "float",        # drifting
    8:  "follow spot",  # a spotlight chasing along the strip
    9:  "wave",         # wave
    10: "water",        # running water
    11: "rainbow",      # rainbow
    12: "blink",        # blink
    13: "bounce",       # bouncing end to end
    14: "shuttle",      # back and forth; its flag picks one colour or many
    15: "twinkle",      # random twinkling
    16: "on/off",       # on and off; its flag is the alternation
    17: "curtain",      # a curtain rising or falling; the flag picks which
    18: "alternate",    # alternating between two groups
}

# Modes where bit 6 is not the travel direction but something else.
SPECIAL_FLAG = {
    14: "one colour or many",
    16: "alternation",
    17: "curtain up or down",
}

# Range of the continuous parameters, matching the app's own sliders.
SPEED_MAX      = 100
BRIGHTNESS_MAX = 100


def mode_byte(mode_id, direction=0, section=0):
    """Build the mode byte with its flags.

    A copy of Mode.formatValue() from the APK. The low five bits are the
    mode number; the top two change meaning per mode:

        modes 1-13, 15, 18 : bit7 = split into sections, bit6 = direction
        mode 14            : bit6 = one colour or many
        mode 16            : bit6 = alternation
        mode 17            : bit6 = curtain up or down

    Because bit 6 means different things, it is called 'direction' here
    throughout and the caller knows what it does. See SPECIAL_FLAG.
    """
    return (mode_id & 0x1F) | ((section & 1) << 7) | ((direction & 1) << 6)


# --------------------------------------------------------- the palette ---
# The eight colours of the internal firmware palette, recovered from the
# APK. They are never listed anywhere directly: they were cross-
# referenced out of it.
#
# Every Mode in Mode.java carries both a colorId, which indexes the
# mode_colors array of names, and a colorValue, which encodes the palette
# indices. Line the two up across all 19 entries and each index resolves
# to exactly one name, with no contradiction anywhere.
#
# The clincher is entry 17: indices 0, 6, 3, 1, 4, 2, 5 named
# "RD OR YE GN CYAN BU VT". That is spectral order. A wrong mapping would
# not produce a rainbow out of a scrambled permutation.

# Verified against the hardware with a camera, one index at a time,
# using mode 2 with the index repeated. All eight matched.
PALETTE = {
    0: "red",
    1: "green",
    2: "blue",
    3: "yellow",
    4: "cyan",
    5: "violet",
    6: "orange",
    7: "white",
}

# Approximate RGB for each palette entry. These are for previewing and
# for naming things on screen only: the firmware's actual values are not
# published anywhere in the APK.
PALETTE_RGB = {
    0: (255, 0, 0),     1: (0, 255, 0),     2: (0, 0, 255),    3: (255, 255, 0),
    4: (0, 255, 255),   5: (160, 0, 255),   6: (255, 120, 0),  7: (255, 255, 255),
}

# The 19 combinations the app itself offers, in its own order. The index
# into this list is the colorId used by Mode.java.
PRESETS = [
    (0, 1),                      (0, 2),                   (1, 2),
    (0, 1, 2),                   (2, 3, 4),                (4, 5, 6),
    (0, 1, 2, 3),                (1, 2, 3, 4),             (2, 3, 4, 5),
    (0, 1, 2, 3, 4),             (1, 2, 3, 4, 5),          (2, 3, 4, 5, 6),
    (0, 1, 2, 3, 4, 5),          (1, 2, 3, 4, 5, 6),       (2, 3, 4, 5, 6, 7),
    (0, 1, 2, 3, 4, 5, 6),       (1, 2, 3, 4, 5, 6, 7),
    (0, 6, 3, 1, 4, 2, 5),       # spectral order: the app's rainbow
    (0, 1, 2, 3, 4, 5, 6, 7),
]

SPECTRUM = PRESETS[17]   # the seven colours of the rainbow, in order


def palette_names(indices):
    """Render a list of indices as readable colour names."""
    return " ".join(PALETTE.get(i, "?") for i in indices)


def palette(*indices):
    """Encode a palette of up to 8 colours.

    A palette of ONE colour is ignored: the firmware falls back to its
    default red and green. Repeat the index to get a single colour,
    palette(3, 3), which is how each entry below was verified one at a
    time against the hardware.

    The app's format: one byte saying how many colours there are, then
    the indices packed two per byte, a nibble each.

        palette(0, 1)    -> 02 01 00 00 00
        palette(2, 3, 4) -> 03 23 40 00 00

    Both examples appear verbatim in Mode.java, which is what confirms
    the encoding is read correctly. Indices run 0 to 7 over an internal
    firmware palette.
    """
    if not 1 <= len(indices) <= 8:
        raise ValueError("between 1 and 8 colours")
    if any(not 0 <= i <= 7 for i in indices):
        raise ValueError("colour indices run from 0 to 7")
    nib = list(indices) + [0] * (8 - len(indices))
    packed = [(nib[i] << 4) | nib[i + 1] for i in range(0, 8, 2)]
    return bytes([len(indices)] + packed[:4])


# ------------------------------------------------------------- commands ---
# Each function returns bytes ready to write to AE01.

def cmd_power(on):
    """Turn on or off. This does not cut power: BLE stays alive."""
    return bytes([OP_POWER, 1 if on else 0])


def cmd_brightness(level):
    """Global brightness, 0 to 255."""
    return bytes([OP_BRIGHTNESS, _byte(level)])


def cmd_color(r, g, b):
    """Static colour. Cancels any running dynamic mode.

    The command carries six bytes, not three: the app sends r, g, b and
    then three zeroes. On models with a white channel those three are
    warm white, cool white and an auxiliary.
    """
    return bytes([OP_COLOR, _byte(r), _byte(g), _byte(b), 0, 0, 0])


def cmd_mode(mode_id, speed=50, brightness=100, colors=(0, 1), direction=0, section=0):
    """Start one of the 18 firmware effects.

    speed and brightness run 0 to 100, like the app's sliders. colors is
    a list of indices into the internal palette.
    """
    if mode_id not in MODES:
        raise ValueError(f"mode {mode_id} outside the 1..18 catalogue")
    return (bytes([OP_MODE, mode_byte(mode_id, direction, section),
                   _byte(speed, SPEED_MAX), _byte(brightness, BRIGHTNESS_MAX)])
            + palette(*colors))


def cmd_ic_length(leds):
    """Declare how many LEDs the strip has. Little endian.

    The app exposes it as a settings field accepting 16 to 2048, to fix a
    lamp that ships with the wrong count.

    It also truncates. Declaring fewer LEDs than the strip has lights
    that many from the base and leaves the rest dark, with a crisp edge,
    which is the only way to light a fraction of the tube from outside.
    Measured on a 72 LED tube: 24 lit 35 percent of it, 32 lit 46, 48 lit
    66, 64 lit 89, and 80 filled it. See `Lamp.bar`.

    Below 16 the firmware ignores the value and drives 16 LEDs, so that
    stub, about 22 percent, is the smallest bar the hardware can draw.
    The app's own minimum of 16 is not a coincidence: it declines to send
    what the firmware would ignore. Nothing clamps or rounds the value on
    the way out here, so a smaller number reaches the lamp and the lamp
    is what rejects it.
    """
    return bytes([OP_IC_LENGTH, leds & 0xFF, (leds >> 8) & 0xFF])


def cmd_phone_mic():
    """Put the lamp into streaming mode, so it will accept levels.

    `openPhoneMic()` in the app, sent once before it starts streaming the
    microphone. The 04 is a literal in the app, not a parameter.
    """
    return bytes([OP_PHONE_MIC, 0x04])


def cmd_level(r, g, b, level, effect=0):
    """Push one audio level, which the lamp renders as a beat.

    `recorderUpdate(r, g, b, level, effect)` in the app:

        10 <r> <g> <b> 00 00 <level> <effect>

    The app streams this about twenty times a second from the phone's
    microphone, and displays the same number as a percentage in its own
    UI, which is what identifies byte seven as a 0 to 255 amplitude.
    Level 0 is how the app stops it (`recorderStop`). The effect selects
    the rendering, from the app's four for addressable strips: 0 classic,
    1 soft, 2 dynamic, 3 disco.

    Do not mistake the level for a fill. It reads as a gate, not a bar:
    a held 64 left the tube dark and a held 160 or 255 lit all of it, so
    it never showed a proportion. For a proportional bar use `Lamp.bar`,
    which works through IcLength.
    """
    return bytes([OP_RECORDER, _byte(r), _byte(g), _byte(b), 0, 0,
                  _byte(level), _byte(effect)])


def cmd_ic_order(order):
    """Colour order of the LED chip.

    This is the single most important command on these lamps and the app
    buries it in a settings screen. A strip can be wired with the chip's
    channels in any order; when the firmware's assumption does not match
    the wiring, every colour comes out permuted. Send red, get green.
    Two lamps of the same model can differ, and the ones this was
    developed against did: nothing about colour worked until it was set.

    Values run from 1 (the app sends tab position + 1). Order 1 is plain
    RGB. Verified against the hardware with a camera: order 1 gives red
    for red, green for green and blue for blue; order 2 swaps green and
    blue; 3 to 6 are the remaining permutations.

    Symptom to recognise: warm white coming out magenta or green.
    """
    return bytes([OP_IC_ORDER, _byte(order)])


def cmd_mic(sensitivity, mode=0):
    """Enable the lamp's own microphone."""
    return bytes([OP_MIC, _byte(sensitivity), _byte(mode)])


def cmd_phone_mic():
    """Tell the lamp to expect audio from the phone."""
    return bytes([OP_PHONE_MIC, 0x04])


def _byte(v, top=255):
    """Clamp and round a value into the byte range it belongs to."""
    return max(0, min(top, int(round(v))))
