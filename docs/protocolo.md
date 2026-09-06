# Protocolo VC-BLELIGHT, al detalle

Todo lo de este documento sale del APK de la app oficial **Raingel**,
descompilado con `jadx`. No hay conjeturas salvo donde se dice.

## De donde sale

El paquete de la app es `com.raingel.app`, pero el codigo de la lampara
vive bajo `am.doit.dohome.strip`: el fabricante real es **DoHome** y
Raingel es una marca blanca suya. Las clases que importan:

| Clase | Que aporta |
|---|---|
| `service/StripBleManager.java` | los UUID de servicio y caracteristica |
| `service/StripManager.java` | un metodo por comando, con los bytes |
| `bean/Mode.java` | el catalogo de 18 modos y su codificacion |
| `page/ModeFragment.java` | como se juntan modo, velocidad y brillo |

Para reproducirlo:

    unzip Raingel.xapk                 # el xapk contiene el apk base
    unzip com.raingel.app.apk
    jadx -d src --no-res com.raingel.app.apk
    grep -rl "AE01" src/

## Capa de transporte

| | |
|---|---|
| Nombre anunciado | `VC-BLELIGHT` |
| Servicio en el anuncio | `0000AF30-0000-1000-8000-00805F9B34FB` |
| Servicio real | `0000AE30-…` |
| Escritura | `0000AE01-…`, *write without response* |
| Notificacion | `0000AE02-…` |

Dos detalles que cuestan tiempo si no se saben:

1. El servicio que sale en el anuncio (`AF30`) **no es** el que expone al
   conectar (`AE30`). La app filtra el escaneo por `AF30` y luego busca
   `AE30` sobre la conexion ya hecha.
2. La escritura no lleva acuse de recibo. Un comando mal formado no da
   error: simplemente no pasa nada. La unica verificacion posible es
   mirar la lampara.

La app tambien se suscribe a `AE02`, pero en las pruebas hechas la
lampara no envia ninguna notificacion. No parece haber canal de vuelta.

## Comandos

El primer byte es el opcode. Los nombres de la columna derecha son los
metodos de `StripManager`.

| Opcode | Bytes | Metodo en el APK |
|---|---|---|
| `01` | `01 <0\|1>` | `switchLight` |
| `02` | `02 <0-255>` | `updateBrightness` |
| `03` | `03 r g b w1 w2 w3` | `ColorAdjust` |
| `04` | `04 <sens> <modo>` | `deviceMicUpdate` |
| `05` | `05 <on> 01 <lo> <hi>` | `updateDelay` |
| `07` | `07 <modo> <vel> <brillo> <paleta>` | `ModeAdjust` |
| `08` | reloj | `updateDateTime` |
| `0C` | temporizador | `updateTimer` |
| `0D` | hasta 6 alarmas | `updateAlarm` |
| `0E` | `0E <orden>` | `IcOrder` |
| `0F` | `0F <lo> <hi>` | `IcLength` |
| `10` | grabador | `recorderUpdate` |
| `11` | `11 04` | `openPhoneMic` |
| `12` | `12 <a> <b>` | `setRgbOrder` |
| `15` | `15 <on> 00 <nivel>` | `updateMotor` |
| `17` | `17 <on> 00 <nivel> 64` | `updateLaser` |

`updateMotor` y `updateLaser` no hacen nada en una lampara normal: la
app sirve a toda la gama de DoHome, que incluye modelos con motor y con
laser.

**No pruebes opcodes al azar.** En firmwares de esta familia `F0`, `FE`
y `FF` suelen ser reset de fabrica.

### El color lleva seis bytes, no tres

`ColorAdjust(r, g, b, w1, w2, w3)`. La app siempre manda ceros en los
tres ultimos. En modelos con canal blanco esos bytes son el blanco
calido, el frio y un auxiliar.

### Que aparato es cada lampara

La lampara publica su familia en el anuncio BLE, bajo el identificador
de fabricante **22872**, en dos bytes: grupo y tipo.

| Grupo | | Grupo | |
|---|---|---|---|
| 1 | LIGHT_DIM | 6 | LIGHT_RGBCW |
| 2 | LIGHT_CCT | 16 | **LIGHT_MAGIC** |
| 3 | LIGHT_RGB | 17-18 | MAGIC de 2 vias |
| 4 | LIGHT_RGBW | 20 | **LIGHT_MAGIC_W** |
| 5 | LIGHT_RGBC | 21 | **LIGHT_MAGIC_CW** |

Tipo: 1 bombilla, 2 tira, 3 plafon, 4 foco, 5 spot.

`StripDevice.isMagic()` es cierto solo para los grupos 16, 20 y 21. Esos
son los que llevan LEDs direccionables, y por tanto los unicos donde un
efecto se **desplaza** a lo largo de la tira.

Cuidado con la deduccion facil: que la app tenga `IcLength` e `IcOrder`
no prueba que una lampara concreta sea direccionable. La misma app sirve
a toda la gama de DoHome, que tambien incluye modelos con motor y con
laser. El byte del anuncio es la unica fuente fiable.

**No hay ningun comando de pixel individual.** Ni siquiera en las magic:
el movimiento solo se consigue con los modos internos. Desde fuera solo
se puede mandar un color global, asi que cualquier animacion calculada
en el ordenador se ve al unisono en toda la tira. Esa es la frontera del
aparato.

Ademas, un comando de color cancela el modo que estuviera corriendo. Si
quieres ver un efecto desplazarse, lanza el modo y no mandes nada mas.

## Modos dinamicos (opcode 07)

    07  <byte de modo>  <velocidad 0-100>  <brillo 0-100>  <paleta, 5 bytes>

### Byte de modo

De `Mode.formatValue()`:

    valor = (id & 0x1F) | (seccion << 7) | (direccion << 6)

Los cinco bits bajos son el numero de modo, del 1 al 18. Los dos altos
cambian de significado segun el modo:

| Modos | bit 7 | bit 6 |
|---|---|---|
| 1-13, 15, 18 | por secciones | sentido de avance |
| 14 | — | multicolor |
| 16 | — | alternancia |
| 17 | — | telon hacia arriba o hacia abajo |

### Paleta

Un byte con el numero de colores y luego los indices empaquetados de dos
en dos, un nibble cada uno:

    palette(0, 1)     -> 02 01 00 00 00
    palette(2, 3, 4)  -> 03 23 40 00 00

Los dos ejemplos son literales que aparecen tal cual en `Mode.java`, lo
que confirma que la lectura es correcta. Los indices van de 0 a 7 sobre
una paleta interna del firmware.

### Catalogo

El APK guarda 18 modos, cada uno con sus variantes de paleta y sentido.
**Los numeros son del fabricante; los nombres son deduccion propia**, a
partir de lo que describe la app:

| | | | |
|---|---|---|---|
| 1 desplazamiento | 2 persecucion | 3 salto | 4 respiracion |
| 5 flujo | 6 onda | 7 barrido | 8 meteoro |
| 9 estela | 10 apilado | 11 rebote | 12 destello |
| 13 parpadeo | 14 arcoiris | 15 estroboscopio | 16 alternancia |
| 17 telon | 18 fundido | | |

## Limite de velocidad

La escritura sin respuesta vuelve al instante, asi que medir el tiempo
de la llamada no dice nada util: el sistema la encola. El limite real es
el intervalo de conexion BLE, de 15 a 45 ms, o sea entre 20 y 60
comandos por segundo. Este repositorio anima a 22 cuadros por segundo,
que va holgado.

## Lo que queda por saber

- El significado exacto de cada indice de la paleta interna (0 a 7).
- Los parametros de `recorderUpdate` (opcode `10`).
- Si `AE02` llega a notificar algo en alguna situacion.
- Los nombres oficiales de los 18 modos.
