# SafeFlight Desktop en macOS

Guía para ejecutar y compilar SafeFlight Desktop en un Mac (Apple Silicon o Intel).

**Requisito: macOS 14 (Sonoma) o posterior.** Las dependencias nativas (`av` en Apple
Silicon, `opencv-python` en Intel) solo publican binarios para macOS 14+.

> Estado: el paquete macOS se generará en GitHub Actions tras el primer *push* autorizado. **No se ha validado todavía en
> un Mac real**; las comprobaciones de la sección 5 son precisamente esa validación.

## 1. Opción A: paquete compilado por CI

1. En GitHub → *Actions* → **Desktop build** → última ejecución correcta.
2. Descargar `SafeFlightDesktop-macos-arm64` (Apple Silicon, M1–M4) o
   `SafeFlightDesktop-macos-x64` (Intel). En caso de duda: menú  → *Acerca de este Mac*.
3. Descomprimir y mover `SafeFlightDesktop.app` a `Aplicaciones` (o usar el `.dmg`).
4. Primer arranque: la app **no está firmada ni notarizada**. Gatekeeper la bloqueará.
   * Clic derecho sobre la app → *Abrir* → *Abrir*, o bien
   * *Ajustes del Sistema → Privacidad y seguridad → Abrir igualmente*.
   * Alternativa en Terminal (solo para este paquete de confianza):
     `xattr -dr com.apple.quarantine /Applications/SafeFlightDesktop.app`
5. macOS 15+ preguntará por el acceso a la **red local**: hay que permitirlo para
   recibir MAVLink y vídeo.

## 2. Opción B: desde el código fuente

```bash
# Python 3.12 (python.org o Homebrew: brew install python@3.12)
git clone https://github.com/Joowww/SafeFlightDesktop.git
cd SafeFlightDesktop
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-build.txt
python App_flet.py --self-check     # debe terminar con "ok": true
python App_flet.py                  # interfaz
```

## 3. Compilar el `.app` localmente

```bash
python build.py
```

Genera `dist/artifacts/SafeFlightDesktop-<versión>-macos-<arm64|x64>.zip` (y `.dmg`).
El paquete corresponde a la arquitectura del Mac que compila.

## 4. Dónde están los datos

| Elemento | Ruta |
|---|---|
| Perfiles de conexión | `~/Library/Application Support/SafeFlightDesktop/connection_profiles.json` |
| Logs de sesión | `~/Library/Logs/SafeFlightDesktop/` |

La ruta del log actual aparece al final del panel lateral.

## 5. Lista de validación en Mac (pendiente)

Anotar resultado, versión de macOS y chip en [test-log.md](../evaluation/test-log.md):

- [ ] El `.app` abre tras la excepción de Gatekeeper.
- [ ] `SafeFlightDesktop.app/Contents/MacOS/SafeFlightDesktop --self-check` devuelve `"ok": true`.
- [ ] Se muestra la ventana con mapa y HUD.
- [ ] Perfil SITL + `python scripts/mavlink_test_sender.py --target 127.0.0.1:14560` → CONNECT → estado «MAVLink: OK».
- [ ] Vídeo: `python scripts/rtp_test_sender.py --port 5004` con el perfil SITL → indicador «CAMERA LIVE».
- [ ] Editar un perfil (IP/puerto), guardar, reiniciar la app y comprobar que se conserva.
- [ ] El log de sesión se crea en `~/Library/Logs/SafeFlightDesktop/`.

## 6. Problemas conocidos

* «La app está dañada»: atributo de cuarentena; ver paso 4 de la opción A.
* Sin vídeo ni telemetría y sin aviso: revisar *Privacidad y seguridad → Red local*.
* El cortafuegos de macOS puede pedir permiso para conexiones entrantes UDP.
