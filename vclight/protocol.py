"""Protocolo BLE de las lamparas VC-BLELIGHT (fabricante DoHome).

Todo lo que hay aqui esta extraido del APK de la app oficial Raingel,
en concreto de estas clases:

    am.doit.dohome.strip.service.StripManager     los comandos
    am.doit.dohome.strip.service.StripBleManager  los UUID
    am.doit.dohome.strip.bean.Mode                el catalogo de modos

No hay adivinanzas: cada opcode de este fichero aparece literalmente en
el codigo de la app. Los nombres de los modos si son deduccion propia,
porque en el APK son solo numeros.

Capa de transporte
------------------
La lampara anuncia el servicio AF30 pero expone el AE30. Se escribe en
la caracteristica AE01, que es "write without response": la lampara no
confirma nada, asi que un comando mal formado se pierde en silencio.
"""

# ------------------------------------------------- familias de aparato ----
# La lampara se identifica en el propio anuncio BLE, sin necesidad de
# conectar. Bajo el identificador de fabricante 22872 manda dos bytes:
# el primero es el grupo y el segundo el tipo fisico.
#
# Esto importa porque de ahi sale si la tira es direccionable o no. La
# app lo decide con StripDevice.isMagic(), que es cierto solo para los
# grupos 16, 20 y 21. En una lampara que no sea magic, los modos del
# firmware existen igual pero no se desplazan: no hay LEDs que recorrer.

APP_ID = 22872   # identificador de fabricante de DoHome en el anuncio

GRUPOS = {
    1:  "LIGHT_DIM",         2:  "LIGHT_CCT",          3:  "LIGHT_RGB",
    4:  "LIGHT_RGBW",        5:  "LIGHT_RGBC",         6:  "LIGHT_RGBCW",
    16: "LIGHT_MAGIC",       17: "LIGHT_MAGIC_W_2PATH", 18: "LIGHT_MAGIC_C_2PATH",
    19: "LIGHT_START",       20: "LIGHT_MAGIC_W",      21: "LIGHT_MAGIC_CW",
}

TIPOS = {1: "bombilla", 2: "tira", 3: "plafon", 4: "foco", 5: "spot"}

GRUPOS_MAGIC = {16, 20, 21}   # StripDevice.isMagic()


def es_magic(grupo):
    """Dice si el aparato lleva LEDs direccionables.

    Solo los magic pueden mover un efecto a lo largo de la tira. En los
    demas, cualquier animacion se ve al unisono en toda la lampara.
    """
    return grupo in GRUPOS_MAGIC


# ---------------------------------------------------------------- UUID ----

def uuid16(short):
    """Expande un UUID corto de 16 bits al UUID largo de Bluetooth SIG."""
    return f"0000{short.lower()}-0000-1000-8000-00805f9b34fb"


SERVICE_ADVERTISED = uuid16("AF30")   # el que sale en el anuncio, para filtrar
SERVICE            = uuid16("AE30")   # el que expone de verdad al conectar
CHAR_WRITE         = uuid16("AE01")   # aqui van todos los comandos
CHAR_NOTIFY        = uuid16("AE02")   # la app se suscribe, pero no llega nada
DEVICE_NAME        = "VC-BLELIGHT"


# ------------------------------------------------------------- opcodes ----
# Primer byte de cada comando. Los nombres son los metodos de StripManager.

OP_POWER      = 0x01   # switchLight       01 <0|1>
OP_BRIGHTNESS = 0x02   # updateBrightness  02 <0-255>
OP_COLOR      = 0x03   # ColorAdjust       03 r g b w1 w2 w3
OP_MIC        = 0x04   # deviceMicUpdate   04 <sensibilidad> <modo>
OP_DELAY      = 0x05   # updateDelay       05 <on> 01 <lo> <hi>
OP_MODE       = 0x07   # ModeAdjust        07 <modo> <velocidad> <brillo> <paleta>
OP_DATETIME   = 0x08   # updateDateTime    pone en hora el reloj interno
OP_TIMER      = 0x0C   # updateTimer
OP_ALARM      = 0x0D   # updateAlarm       hasta 6 alarmas
OP_IC_ORDER   = 0x0E   # IcOrder           orden de color del chip direccionable
OP_IC_LENGTH  = 0x0F   # IcLength          numero de LEDs de la tira
OP_RECORDER   = 0x10   # recorderUpdate
OP_PHONE_MIC  = 0x11   # openPhoneMic      11 04
OP_RGB_ORDER  = 0x12   # setRgbOrder
OP_MOTOR      = 0x15   # updateMotor       modelos con motor
OP_LASER      = 0x17   # updateLaser       modelos con laser

# Opcodes que NO conviene probar a ciegas: en firmwares de esta familia
# suelen ser reset de fabrica.
OP_PELIGROSOS = {0xF0, 0xFE, 0xFF}


# --------------------------------------------------------------- modos ----
# El firmware lleva 18 efectos dinamicos. Se mueven solos: la tira es
# direccionable (de ahi que existan IcLength e IcOrder), asi que el
# movimiento lo calcula la lampara, no hace falta mandar pixel a pixel.
#
# AVISO: estos nombres son deduccion propia a partir del comportamiento
# que describe la app. El APK solo guarda numeros del 1 al 18.

MODES = {
    1:  "desplazamiento",   2:  "persecucion",    3:  "salto",
    4:  "respiracion",      5:  "flujo",          6:  "onda",
    7:  "barrido",          8:  "meteoro",        9:  "estela",
    10: "apilado",          11: "rebote",         12: "destello",
    13: "parpadeo",         14: "arcoiris",       15: "estroboscopio",
    16: "alternancia",      17: "telon",          18: "fundido",
}

# Rango de los parametros continuos, tal como los mandan los sliders de la app.
SPEED_MAX      = 100
BRIGHTNESS_MAX = 100


def mode_byte(mode_id, direction=0, section=0):
    """Compone el byte de modo con sus banderas.

    Copia de Mode.formatValue() del APK. Los cinco bits bajos son el
    numero de modo; los dos altos cambian de significado segun el modo:

        modos 1-13, 15, 18 : bit7 = por secciones, bit6 = sentido
        modo 14            : bit6 = multicolor
        modo 16            : bit6 = alternancia
        modo 17            : bit6 = telon hacia arriba o hacia abajo

    Como el significado del bit6 depende del modo, aqui se llama
    'direction' en todos los casos y el que llama sabe que quiere decir.
    """
    return (mode_id & 0x1F) | ((section & 1) << 7) | ((direction & 1) << 6)


def palette(*indices):
    """Codifica una paleta de hasta 8 colores.

    Formato de la app: un byte con cuantos colores hay, y luego los
    indices empaquetados de dos en dos, un nibble cada uno.

        palette(0, 1)    -> 02 01 00 00 00
        palette(2, 3, 4) -> 03 23 40 00 00

    Los dos ejemplos son literales que aparecen tal cual en Mode.java,
    asi que sirven de comprobacion de que la codificacion es correcta.
    Los indices van del 0 al 7 sobre la paleta interna del firmware.
    """
    if not 1 <= len(indices) <= 8:
        raise ValueError("entre 1 y 8 colores")
    if any(not 0 <= i <= 7 for i in indices):
        raise ValueError("los indices de color van de 0 a 7")
    nib = list(indices) + [0] * (8 - len(indices))
    packed = [(nib[i] << 4) | nib[i + 1] for i in range(0, 8, 2)]
    return bytes([len(indices)] + packed[:4])


# ------------------------------------------------------------ comandos ----
# Cada funcion devuelve los bytes listos para escribir en AE01.

def cmd_power(on):
    """Enciende o apaga. No corta la corriente: el BLE sigue vivo."""
    return bytes([OP_POWER, 1 if on else 0])


def cmd_brightness(level):
    """Brillo global, 0 a 255."""
    return bytes([OP_BRIGHTNESS, _byte(level)])


def cmd_color(r, g, b):
    """Color fijo. Cancela el modo dinamico que estuviera corriendo.

    El comando lleva seis bytes, no tres: la app manda r, g, b y luego
    tres ceros. En modelos con canal blanco esos tres bytes son el
    blanco calido, frio y auxiliar.
    """
    return bytes([OP_COLOR, _byte(r), _byte(g), _byte(b), 0, 0, 0])


def cmd_mode(mode_id, speed=50, brightness=100, colors=(0, 1), direction=0, section=0):
    """Lanza uno de los 18 efectos dinamicos del firmware.

    speed y brightness van de 0 a 100, como los sliders de la app.
    colors es la lista de indices de la paleta interna.
    """
    if mode_id not in MODES:
        raise ValueError(f"modo {mode_id} fuera del catalogo 1..18")
    return (bytes([OP_MODE, mode_byte(mode_id, direction, section),
                   _byte(speed, SPEED_MAX), _byte(brightness, BRIGHTNESS_MAX)])
            + palette(*colors))


def cmd_ic_length(leds):
    """Declara cuantos LEDs tiene la tira. Little endian.

    Solo hace falta si la lampara viene mal configurada de fabrica y los
    efectos se cortan a mitad de la tira.
    """
    return bytes([OP_IC_LENGTH, leds & 0xFF, (leds >> 8) & 0xFF])


def cmd_ic_order(order):
    """Orden de color del chip: RGB, GRB, BRG... Si los colores salen
    cambiados (rojo por verde), es esto lo que hay que ajustar."""
    return bytes([OP_IC_ORDER, _byte(order)])


def cmd_mic(sensitivity, mode=0):
    """Activa el microfono de la propia lampara."""
    return bytes([OP_MIC, _byte(sensitivity), _byte(mode)])


def cmd_phone_mic():
    """Le dice a la lampara que espere audio del movil."""
    return bytes([OP_PHONE_MIC, 0x04])


def _byte(v, top=255):
    """Recorta y redondea un valor al rango del byte que toca."""
    return max(0, min(top, int(round(v))))
