# Registro de pruebas

## Entorno de ejecución (2026-11-19)

| Elemento | Valor |
|---|---|
| Anfitrión | Windows 11 Home 10.0.26300, x64 |
| Revisión | `704a540` + cambios sin confirmar, rama `feature/multiplatform-android` |
| Python | 3.12.1 (entorno virtual limpio creado desde `requirements.txt` + `requirements-build.txt`) |
| Desktop | Flet 0.82.0, PyAV 19.0.2, OpenCV 4.13.0, DroneKit 2.9.2, pymavlink 2.4.49, PyInstaller 6.22.3, pytest 8.4.2 |
| Android | JDK 21.0.6 (JBR), AGP 8.13.2, Gradle 8.14, Kotlin 2.3.21, Compose BOM 2026.06.01, Media3 1.10.1 |
| Emulador | AVD Medium_Phone, Android 16 (API 36), x86_64, renderizado por software, sin ventana |
| Servidor RTSP | MediaMTX 1.21.4 (imagen `bluenviron/mediamtx:1.21.4-ffmpeg`), Docker 29.9.3 |
| Hardware de vuelo | No utilizado |

## Línea base

**T-00 — Importación de la versión original.** Antes de cualquier cambio, `import App_flet`
y los módulos de `models/` importan correctamente en el entorno limpio. Resultado: correcto.

## Desktop

**T-01 — Pruebas unitarias y de contrato** (`python -m pytest`, 75 pruebas en la ejecución
final). Incluye rutas por SO, validación/persistencia/corrupción/migración de perfiles,
sincronización del ejemplo compartido y los 17 vectores MAVLink con pymavlink.
Resultado: 75/75 correctas. Defectos encontrados y corregidos durante el desarrollo:
(1) la codificación MAVLink 1 de los vectores requería el dialecto `v10`; (2) pymavlink
pierde la trama siguiente a un falso byte de inicio, por lo que el contrato exige
recuperación eventual.

**T-02 — Integración MAVLink con DroneKit** (`test_mavlink_link_integration.py`).
Generador sintético → `udpin:127.0.0.1:<puerto>` construido desde un perfil →
`DroneManager.setup_drone()`. Comprobado: modo LOITER, desarmado, tensión > 15 V,
altitud, 12 satélites; tras pausar el generador la edad del heartbeat supera
`telemetry_stale_s`; al reanudar baja de 1 s sin reconectar. Resultado: correcto.
Hallazgo: DroneKit no completa `connect()` hasta recibir un `PARAM_VALUE`; el generador
responde a `PARAM_REQUEST_LIST` con un parámetro sintético.

**T-03 — Compilación con `python build.py`.** Entorno → pruebas → PyInstaller →
*smoke test* → archivo → informe. Resultado: `SafeFlightDesktop-0.3.0-windows-x64.zip`
(159,7 MB), `validated: true`, SHA-256
`6ca04344bfa9b551c4e872d4c60b0ea5ed3e5c6736496b2896418d81cdb50355`, 457 s.

**T-04 — Arranque del ejecutable empaquetado.** `--self-check` sobre el `.exe`: recursos,
SDP, decodificador H.264, OpenCV, Flet y ciclo de perfiles correctos. Lanzamiento con
interfaz: proceso del cliente Flet con ventana «SafeFlight Desktop», mapa, HUD e
indicador de vídeo «SIGNAL LOST»; log de sesión creado con el perfil activo.
Evidencia: [desktop-windows-startup.png](evidence/desktop-windows-startup.png). El
Firewall de Windows solicitó permiso para el nuevo ejecutable; no se concedió durante la prueba.

**T-05 — Receptor de vídeo** (`test_video_receiver.py`). (a) RTP/UDP H.264 generado con
`scripts/rtp_test_sender.py` y SDP de usuario → fotogramas 640×360; (b) cambio a otro
puerto (otro perfil) sin reiniciar el hilo; (c) perfil sin vídeo → sin fotogramas;
(d) RTSP `rtsp://127.0.0.1:18554/test` → fotogramas. Resultado: correcto. Hallazgo: en
Windows los puertos UDP efímeros pueden estar reservados por Hyper‑V/WSL; la prueba usa
pares de puertos pares libres desde 5600.

**T-06 — Workflows de CI.** Sintaxis YAML validada y disparadores/rutas revisados. No
ejecutados (requieren *push*, no autorizado). Resultado: pendiente.

## Android

**T-07 — Pruebas unitarias JVM** (`gradlew testDebugUnitTest`): 25 pruebas en 6 clases,
0 fallos. Incluye los 17 vectores compartidos, CRC de referencia (0x6F91), fragmentación,
resincronización, sockets UDP reales con transición CONNECTED → STALE → LOST →
CONNECTED, error de *bind* con reintentos, perfiles, ejemplo de Desktop, *watchdog* de
vídeo y bloqueo de comandos.

**T-08 — Compilación** (`python build.py --target android`: pruebas + Android Lint + APK).
Resultado: `SafeFlight-Android-0.3.0-debug.apk` (15,4 MB), SHA-256
`fb45842e372a963717a72a32522528114b0d0bf0cc164bfa620e5bd494b810bc`. Lint: 3 avisos
justificados (orientación fija deseada, `allowBackup`, carpeta `-v26` requerida por AAPT2).

**T-09 — Arranque en emulador.** Instalación, apertura en horizontal, pantalla de vuelo
con todos los valores «—» y perfil SIYI LOCAL activo; el vídeo hacia la URL provisional
inalcanzable entra en ciclo error → reintento cada 1 s. Evidencia:
[android-01-flight-initial.png](evidence/android-01-flight-initial.png).

**T-10 — Telemetría y vídeo en emulador.** Perfil SITL con `udp_connect` a
`10.0.2.2:14551`, generador en modo `--serve`, RTSP en `10.0.2.2:18554`. Resultado:
CONECTADO, 778 tramas válidas / 0 descartadas, 92 heartbeats de GCS; vídeo 1280×720 en
directo con edad de fotograma 3–36 ms; modo LOITER, desarmado, altitud, velocidad,
rumbo y batería coherentes con el generador. Evidencias:
[android-02](evidence/android-02-connection-diagnostics.png),
[android-03](evidence/android-03-flight-telemetry-video.png). Hallazgo: `adb emu redir`
no entrega UDP en imágenes con Wi‑Fi virtual (el invitado usa 10.0.2.16); se documenta
y se prueba `udp_listen` en T-07.

**T-11 — Pérdida y recuperación en emulador.** Generador detenido: STALE a 3,0 s y LOST a
9,2 s, banner rojo, valores en ámbar, armado y modo atenuados como «último», vídeo en
directo (diagnóstico separado). Servidor RTSP detenido y reiniciado: recuperación
automática. Defectos encontrados y corregidos: (1) reproductor bloqueado en «conectando»
sin error tras caída del servidor → *watchdog* de 10 s; (2) falsa detección de vídeo
congelado sin superficie visible → la supervisión se suspende sin superficie; (3) reapertura
doble por reintentos de un reproductor sustituido → eventos filtrados. Tras las
correcciones: 0 reaperturas espurias al cambiar de pantalla. Evidencia:
[android-04-link-loss.png](evidence/android-04-link-loss.png).

**T-12 — Controles y misiones.** Pulsar «ARM» muestra «ARM no disponible: Controles
deshabilitados…» y se registra el rechazo; no se emite ningún mensaje MAVLink de comando.
Pantalla de misiones con banner de datos de demostración. Evidencias:
[android-07](evidence/android-07-command-blocked.png),
[android-06](evidence/android-06-missions-demo.png).

## Limitaciones del registro

* Las pruebas de interfaz Android se condujeron con `adb`/`uiautomator`; la escritura en
  campos de texto resultó poco fiable con renderizado por software, por lo que el perfil
  de prueba se cargó escribiendo las preferencias de la app *debug* con `run-as`.
* Ninguna prueba ha utilizado el dron, la Raspberry, el Cube Orange ni el MK32.

---

# Segunda iteración (2026-11-19): validación de interfaz y consolidación

Entorno adicional: pywinauto 0.6.9 (UI Automation), uv 0.x (resolución multiplataforma),
contenedor `ubuntu:24.04` (Python 3.12.3, glibc 2.39), AVD API 36 (Medium_Phone) y AVD
Android 9 API 28 (`SafeFlight_API28`, perfil Pixel C 2560×1800, imagen `google_apis` x86_64).

**T-13 — Interfaz del ejecutable Windows** ([`tests/gui/desktop_gui_validation.py`](../../tests/gui/desktop_gui_validation.py),
método en [ADR-0009](../adr/ADR-0009-gui-validation-method.md)). Resultado final: **12/12**.

| Paso | Comprobación | Resultado |
|---|---|---|
| D-01 | Arranque del ejecutable empaquetado | PASS |
| D-02 | Panel lateral: perfil por defecto, `udpin:0.0.0.0:14560`, vídeo RTP/UDP 5004 | PASS |
| D-03 | Crear perfil desde el editor (nombre, puerto MAVLink 14571, RTP 5610) y guardar | PASS |
| D-04 | Duplicar perfil y guardar la copia | PASS |
| D-05 | Seleccionar perfil desde el desplegable | PASS |
| D-06 | Cerrar y reabrir: perfil activo conservado | PASS |
| D-07 | CONNECT con generador **solo** en 14571: «MAVLink: OK», HUD `MODE: LOITER`, `SAT: 12` | PASS |
| D-08 | Vídeo RTP/UDP en la ventana: «CAMERA LIVE», ≈25 FPS | PASS |
| D-09 | Heartbeat detenido: «TELEMETRÍA OBSOLETA · 3.0 s» → reanudado: «MAVLink: OK» | PASS |
| D-10 | Fuente cambiada a RTSP desde el editor sin reiniciar: «CAMERA LIVE» | PASS |
| D-11 | Cerrar la ventana: código 0, sin procesos, puertos 14571 y 5610 libres | PASS |
| D-12 | Logs de sesión con conexión, cambio de vídeo y cierre | PASS |

Defectos encontrados por esta validación y corregidos:
1. **Dialecto MAVLink 2 ausente del paquete** (preexistente, también en el `.spec` de v0.2):
   pymavlink cambia a `pymavlink.dialects.v20.ardupilotmega` al recibir la primera trama
   `0xFD` y lo importa dinámicamente; PyInstaller no lo incluía y CONNECT agotaba el tiempo
   de espera solo en el ejecutable. Corregido con `hiddenimports`; el *self-check* lo comprueba.
2. **Error al cerrar** (preexistente): se llamaba a `DroneConnection.close()`, inexistente.
3. **Botones del editor de perfiles** fuera de la vista inicial en 1366×768: pie fijo.

Hallazgo no corregido (preexistente, menor): los tres botones de solo icono (`ft.Button` con
`icon` sin `content`) se dibujan correctamente pero su etiqueta de accesibilidad es un mensaje
de error de Flet; afecta a lectores de pantalla.

**T-14 — `build.py`.** Compilación Windows tras los cambios: 78/78 pruebas (con servidor RTSP),
*smoke test* con 8 comprobaciones (incluidos dialectos MAVLink 1 y 2), `validated: true`,
SHA-256 `018774120dc9786afaf4cbd0d6e70378b2916c809f9c637f9acb1fb0dc6b57ee`. El informe incluye
ahora `test_summary`. `--clean` probado en un directorio aislado (`test_build_script.py`):
elimina solo intermedios y conserva `dist/artifacts`, código, documentación y `android/app/build`.
Una compilación nueva incorporó los cambios guardados (pie del editor y nueva comprobación del
*self-check* presentes en el ejecutable validado en T-13).

**T-15 — Contenido del paquete Windows.** 2 389 ficheros (379 MB): ejecutable, `assets/`,
`stream.sdp`, `VERSION`, cliente `flet.exe`, FFmpeg de PyAV y OpenCV presentes. Sin `.env`,
perfiles, logs, claves, copias `.bak` ni interfaces heredadas (el único `.pem` es el almacén
público de `certifi`). Tras T-13 no hay ficheros nuevos dentro de `dist/desktop/`: perfiles,
SDP y logs se escriben en los directorios de usuario.

**T-16 — Revisión de CI sin ejecutar GitHub Actions.**
* Resolución de dependencias solo con *wheels* (`uv pip compile --only-binary :all:`): Windows
  x64, Linux x64 y macOS 15 arm64/x64 resuelven. Con objetivo macOS 13 fallan `av` (arm64) y
  `opencv-python` (x64): mínimo macOS 14, aplicado al `Info.plist`.
* `flet-desktop 0.82.0` publica *wheels* para Windows, macOS arm64/x64 y Linux x64/arm64.
* Etiquetas de runner vigentes comprobadas (`windows-2025`, `ubuntu-24.04`, `macos-15`,
  `macos-15-intel`); acciones actualizadas a sus mayores actuales (Node 24).
* Sin secretos en los *workflows*; la publicación es un borrador solo con etiqueta `v*`.
* `.github/workflows/main.yml` (Docker Hub, local, nunca versionado) excluido por `.gitignore`.

**T-17 — Compilación Linux en contenedor `ubuntu:24.04`** (`python build.py`): 77/78 pruebas
(RTSP omitida: servidor no accesible desde el contenedor), PyInstaller, *smoke test* del
ejecutable Linux superado, `SafeFlightDesktop-0.3.0-linux-x64.tar.gz` (195,6 MB), SHA-256
`6706e81e4bbbdf37e96387bb145b529b00ae7916b486a9b1ff37167c3bb8084b`.

**T-18 — Arranque gráfico Linux** (paquete de T-17 en un contenedor limpio con Xvfb). Primer
intento: el cliente Flet no arrancaba por bibliotecas del sistema ausentes. Dependencias
determinadas con `ldd`: `libsecret-1-0`, `libgstreamer1.0-0`, `libgstreamer-plugins-base1.0-0`,
`libgles2`, `libegl1` (añadidas al *workflow* y a la documentación). Con ellas: procesos
`SafeFlightDesktop` y `flet` activos a los 60 s, servicios iniciados, log de sesión creado e
interfaz renderizada. Evidencia: [linux-gui-startup.jpg](evidence/linux/linux-gui-startup.jpg).

**T-19 — Android: compilación y pruebas.** `build.py --target android`: APK y lint correctos;
pruebas unitarias reejecutadas desde cero (`--rerun`): 25/25.

**T-20 — Android 16 (API 36), emulador** ([`tests/gui/android_emulator_validation.py`](../../tests/gui/android_emulator_validation.py)).
Resultado: **10/10** — arranque con valores «—»; edición del perfil SITL desde la interfaz
(`udp_connect 10.0.2.2:14551`, verificado en `SharedPreferences`); conexión; telemetría y vídeo
RTSP; pérdida (log: obsoleta → pérdida → heartbeat) y recuperación; caída y vuelta del servidor
RTSP; HOME libera el decodificador y al volver se reanuda; persistencia tras `force-stop`;
ARM rechazado con motivo; banner de demostración en misiones.
Evidencias: [android-api36/](evidence/android-api36/).

**T-21 — Android 9 (API 28), emulador de tableta (Pixel C, 2560×1800).**
Verificado: instalación y arranque (14 valores «—»); edición del perfil SITL desde la
interfaz y guardado (1 de 3 pasadas automatizadas; en las demás, la escritura con
`adb input text` sobre Compose fue intermitente en este emulador); conexión de telemetría
(`udp_connect`, log «Heartbeat del vehículo recibido»); pantalla de vuelo con modo LOITER,
desarmado, batería, GPS, posición y mensajes del autopiloto; vídeo RTSP 1280×720 en directo
(>3 000 fotogramas, edad 4–55 ms); pérdida y recuperación de telemetría en el log; vuelta del
vídeo tras caída del servidor; HOME/reanudación; persistencia tras `force-stop`; ARM rechazado
(log «ARM rechazado: Controles deshabilitados…»). Los pasos de navegación y ARM se completaron
manualmente con `adb` porque `uiautomator` devolvía volcados incompletos en este emulador
(carga media ≈ 5). Conclusión: la APK funciona en Android 9 en emulador; el arnés automatizado
es fiable en API 36 pero no en esta imagen API 28.
Evidencias: [android-api28/](evidence/android-api28/).
