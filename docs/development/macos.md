# SafeFlight Desktop en macOS — guía de prueba

Procedimiento para descargar, abrir y validar SafeFlight Desktop en un Mac
(Apple Silicon o Intel) y para comunicar los resultados.

> **Estado:** el paquete macOS se compila en GitHub Actions. **No está firmado ni
> notarizado** y **no se ha validado todavía en un Mac real**: esta guía es esa validación.
> Una compilación correcta en CI no garantiza que la interfaz y las conexiones funcionen.

**Requisito: macOS 14 (Sonoma) o posterior.** Las dependencias nativas (`av` en Apple
Silicon, `opencv-python` en Intel) solo publican binarios para macOS 14+.

## 1. Identificar el procesador del Mac

Menú  → *Acerca de este Mac*: «Chip Apple M…» = **Apple Silicon**; «Procesador Intel» =
**Intel**. Alternativa en Terminal:

```bash
uname -m        # arm64 = Apple Silicon · x86_64 = Intel
sw_vers -productVersion
```

## 2. Descargar el artefacto correcto

1. Iniciar sesión en GitHub (necesario para descargar artefactos de Actions).
2. Abrir *Actions* → **Desktop build** → la ejecución más reciente en verde de la rama
   `feature/multiplatform-android`.
3. En *Artifacts*, descargar:
   * Apple Silicon: `SafeFlightDesktop-macos-arm64`
   * Intel: `SafeFlightDesktop-macos-x64`
4. Descomprimir la descarga. Contiene:
   * `SafeFlightDesktop-<versión>-macos-<arch>.zip` (la aplicación),
   * `SafeFlightDesktop-<versión>-macos-<arch>.dmg` (si se generó),
   * `…build-report.json` (pruebas y SHA-256 de la compilación).
5. Descomprimir el `.zip` interior con doble clic (o abrir el `.dmg`) y arrastrar
   `SafeFlightDesktop.app` a **Aplicaciones**.

Opcional, comprobar integridad: `shasum -a 256 SafeFlightDesktop-*.zip` debe coincidir con
`sha256` del informe JSON.

## 3. Primer arranque de una app no firmada (sin desactivar protecciones)

macOS bloqueará la app porque no está firmada con un certificado de Apple Developer.
Autorizar **solo esta aplicación**:

* **macOS 15 o posterior:** abrir la app (aparecerá un aviso) → *Ajustes del Sistema →
  Privacidad y seguridad* → al final, «Se ha bloqueado SafeFlightDesktop» → **Abrir igualmente**
  → confirmar con la contraseña. En macOS 15 el *Ctrl‑clic → Abrir* ya no basta.
* **macOS 14:** *Ctrl‑clic* sobre la app → *Abrir* → *Abrir*.
* Si macOS indica «está dañada y no se puede abrir» (atributo de cuarentena de la descarga),
  quitar la cuarentena **solo de esta app**:
  `xattr -dr com.apple.quarantine /Applications/SafeFlightDesktop.app`

**No** usar `sudo spctl --master-disable` ni desactivar Gatekeeper globalmente.

Al primer arranque, macOS puede pedir:
* **Red local** («SafeFlight recibe telemetría MAVLink y vídeo…»): **Permitir**. Sin este
  permiso no llegan telemetría ni vídeo, sin otro aviso.
* **Cortafuegos** (conexiones entrantes UDP): **Permitir**.

## 4. Comprobación rápida de arranque

```bash
/Applications/SafeFlightDesktop.app/Contents/MacOS/SafeFlightDesktop --self-check
```

Debe terminar con `"ok": true` (recursos, decodificador H.264, dialectos MAVLink, Flet,
perfiles). Después abrir la app normalmente: debe aparecer la ventana con mapa y HUD.

## 5. Preparar las fuentes de prueba (sin dron)

Las fuentes de prueba están en el repositorio. En otra ventana de Terminal:

```bash
git clone -b feature/multiplatform-android https://github.com/Joowww/SafeFlightDesktop.git
cd SafeFlightDesktop
python3 -m venv .venv && source .venv/bin/activate
python -m pip install pymavlink==2.4.49 av==19.0.2 numpy==2.4.2
```

* **Telemetría MAVLink sintética** (ArduCopter simulado, nunca ejecuta comandos):
  `python scripts/mavlink_test_sender.py --target 127.0.0.1:14560`
* **Vídeo RTP/UDP** (como el enlace 5G actual): `python scripts/rtp_test_sender.py --port 5004`
* **Vídeo RTSP**, una de estas opciones:
  * Docker Desktop: `docker compose -f scripts/rtsp-test-server/docker-compose.yml up -d`
    → `rtsp://127.0.0.1:18554/test`
  * Homebrew: `brew install mediamtx ffmpeg`, ejecutar `mediamtx` y, en otra terminal,
    `ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=30 -c:v libx264 -preset ultrafast -tune zerolatency -f rtsp rtsp://127.0.0.1:8554/test`
    → `rtsp://127.0.0.1:8554/test`

## 6. Lista de validación

Marcar cada punto y anotar resultado, versión de macOS y chip:

- [ ] **V-1** La app abre tras autorizarla (sección 3) y muestra mapa y HUD.
- [ ] **V-2** `--self-check` devuelve `"ok": true`.
- [ ] **V-3** Panel lateral (botón ☰ abajo a la izquierda): perfil «SITL / SIMULACIÓN» y MAVLink `udpin:0.0.0.0:14560`.
- [ ] **V-4** *Editar perfiles…* → *Nuevo* → nombre «Prueba Mac», puerto local `14571` → *Guardar y seleccionar*: el panel muestra `udpin:0.0.0.0:14571`.
- [ ] **V-5** Cerrar y reabrir la app: sigue seleccionado «Prueba Mac».
- [ ] **V-6** Con el generador en el puerto del perfil (`--target 127.0.0.1:14571`), pulsar **CONNECT**: «MAVLink: OK», HUD con `MODE: LOITER` y `SAT: 12`.
- [ ] **V-7** Detener el generador (Ctrl+C) unos 5 s: «TELEMETRÍA OBSOLETA»; relanzarlo: vuelve «MAVLink: OK».
- [ ] **V-8** Vídeo RTP: en el editor, puerto RTP del perfil `5004`, ejecutar `rtp_test_sender.py --port 5004`: indicador «CAMERA LIVE».
- [ ] **V-9** Vídeo RTSP: en el editor, *Fuente de vídeo* → RTSP, URL de la sección 5 → *Guardar*: «CAMERA LIVE» sin reiniciar la app.
- [ ] **V-10** Cerrar la ventana: la app termina (sin icono en el Dock ni proceso `SafeFlightDesktop` en *Monitor de Actividad*).

No conectar con el dron real durante esta prueba.

## 7. Recoger logs y comunicar errores

| Elemento | Ruta |
|---|---|
| Logs de sesión | `~/Library/Logs/SafeFlightDesktop/safeflight-*.log` |
| Perfiles | `~/Library/Application Support/SafeFlightDesktop/connection_profiles.json` |
| Informes de fallo de macOS | `~/Library/Logs/DiagnosticReports/` (ficheros `SafeFlightDesktop*` o `flet*`) |

```bash
cd ~/Desktop && mkdir -p safeflight-mac-report
cp ~/Library/Logs/SafeFlightDesktop/*.log safeflight-mac-report/ 2>/dev/null
cp ~/Library/Logs/DiagnosticReports/*{SafeFlight,flet}* safeflight-mac-report/ 2>/dev/null
/Applications/SafeFlightDesktop.app/Contents/MacOS/SafeFlightDesktop --self-check > safeflight-mac-report/self-check.json
sw_vers > safeflight-mac-report/macos.txt; uname -m >> safeflight-mac-report/macos.txt
zip -r safeflight-mac-report.zip safeflight-mac-report
```

Enviar `safeflight-mac-report.zip` con la lista V-1…V-10 marcada, una captura de cada
error y el nombre exacto del artefacto descargado. Revisar antes que los logs no contengan
direcciones o datos que no deban compartirse.

## 8. Compilar desde el código (opcional)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-build.txt
python build.py        # dist/artifacts/SafeFlightDesktop-<versión>-macos-<arch>.zip
```

## 9. Problemas conocidos

* «Está dañada y no se puede abrir»: cuarentena de la descarga; ver sección 3.
* Sin telemetría ni vídeo y sin aviso: *Ajustes del Sistema → Privacidad y seguridad → Red local*.
* La app no abre en macOS 13 o anterior: requisito mínimo macOS 14.
