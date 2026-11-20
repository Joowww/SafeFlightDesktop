# Desarrollo de SafeFlight Desktop

## Requisitos

* Python 3.12 (mínimo 3.11).
* Windows 10/11, macOS 11+ o Linux x64 con GTK 3 (Ubuntu 22.04+).
* Linux: `sudo apt install libgl1 libgles2 libegl1 libglib2.0-0 libgtk-3-0 libmpv2 libsecret-1-0 libgstreamer1.0-0 libgstreamer-plugins-base1.0-0` (cliente Flet y OpenCV).

## Entorno

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-build.txt
```

## Ejecutar desde código

```bash
python App_flet.py               # interfaz
python App_flet.py --self-check  # verificación sin interfaz (JSON + código de salida)
```

## Compilar

```bash
python build.py                  # pruebas + paquete + smoke test + informe
```

El resumen final muestra la ruta del artefacto en `dist/artifacts/` y si el paquete
está `validated`.

## Pruebas

```bash
python -m pytest                 # tests/desktop
python -m pytest -m "not integration"   # sin sockets locales
```

| Fichero | Cubre |
|---|---|
| `test_app_paths.py` | Directorios por SO, migración de rutas |
| `test_connection_profiles.py` | Validación, persistencia, corrupción, migración, edición |
| `test_mavlink_vectors.py` | Contrato MAVLink compartido con Android |
| `test_mavlink_link_integration.py` | DroneKit conectado con la cadena de un perfil; pérdida y recuperación |
| `test_video_receiver.py` | RTP/UDP+SDP, cambio de perfil en caliente, RTSP (si hay servidor) |
| `test_imports.py` | Importación de módulos y `--self-check` |

## Validación de la interfaz (Windows)

```bash
python -m pip install pywinauto==0.6.9          # solo para esta validación
docker compose -f scripts/rtsp-test-server/docker-compose.yml up -d
python build.py                                  # genera el ejecutable a validar
python tests/gui/desktop_gui_validation.py       # ≈3 min; toma el foco del teclado
```

Recorre 12 pasos sobre el ejecutable empaquetado (crear/duplicar/seleccionar perfiles,
persistencia, CONNECT, vídeo RTP y RTSP en la ventana, pérdida de heartbeat, cierre y logs)
y deja `build/gui-evidence/report.json` con capturas. Método: [ADR-0009](../adr/ADR-0009-gui-validation-method.md).

## Herramientas de prueba sin hardware

| Herramienta | Uso |
|---|---|
| `scripts/mavlink_test_sender.py --target 127.0.0.1:14560` | Telemetría ArduCopter sintética hacia el perfil SITL |
| `scripts/mavlink_test_sender.py --serve 14551` | Modo servidor para clientes `udp_connect` |
| `scripts/mavlink_test_sender.py --drop-after 10 --drop-for 8` | Escenario de pérdida de enlace |
| `scripts/rtp_test_sender.py --port 5004` | Vídeo H.264 RTP/UDP como el de la Raspberry |
| `docker compose -f scripts/rtsp-test-server/docker-compose.yml up -d` | Servidor RTSP en `rtsp://127.0.0.1:18554/test` |
| `scripts/generate_mavlink_vectors.py` | Regenerar los vectores del contrato |

El generador de telemetría nunca ejecuta comandos: descarta lo que recibe y solo
responde a `PARAM_REQUEST_LIST` con un parámetro sintético, necesario porque DroneKit
no completa `connect()` hasta iniciar la descarga de parámetros.

## Configuración

Perfiles en `connection_profiles.json` (ver [arquitectura](../architecture/desktop.md#4-configuración-y-persistencia)).
`SAFEFLIGHT_CONFIG_DIR` y `SAFEFLIGHT_LOG_DIR` redirigen configuración y logs.
