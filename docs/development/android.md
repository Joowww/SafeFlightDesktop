# Desarrollo de SafeFlight Android

## Requisitos

* JDK 17 o superior (el JBR incluido en Android Studio sirve).
* Android SDK con `platforms;android-36` y `build-tools;35.0.0`.
* Opcional: Android Studio (abrir la carpeta `android/`).

## Compilar

```bash
python build.py --target android
# o directamente:
cd android && ./gradlew testDebugUnitTest lintDebug assembleDebug
```

APK: `dist/artifacts/SafeFlight-Android-<versión>-debug.apk`
(identificador `org.safeflight.android.debug`).

## Pruebas unitarias (JVM)

| Clase | Cubre |
|---|---|
| `SharedVectorsTest` | Los 17 vectores MAVLink compartidos con Desktop |
| `MavlinkParserTest` | CRC, fragmentación, resincronización, codificador de GCS |
| `MavlinkClientUdpTest` | Sockets UDP reales: recepción, STALE/LOST, recuperación, error de *bind* y reintento |
| `StateMachinesTest` | Umbrales de enlace, filtrado por sistema/componente, supervisor y *watchdog* de vídeo |
| `ProfilesTest` | Persistencia, corrupción, validación, ejemplo compartido de Desktop |
| `CommandGateTest` | Bloqueo de todos los comandos |

## Probar en el emulador

1. Servidor RTSP: `docker compose -f scripts/rtsp-test-server/docker-compose.yml up -d`
   (el emulador lo ve en `rtsp://10.0.2.2:18554/test`).
2. Telemetría: `python scripts/mavlink_test_sender.py --serve 14551`.
3. En la app, perfil SITL → transporte **UDP hacia remoto** `10.0.2.2:14551` con
   heartbeat de GCS → *Guardar* → *Conectar*.

`adb emu redir add udp:...` no sirve en las imágenes recientes (API 30+ con Wi‑Fi
virtual): el tráfico redirigido va a 10.0.2.15 y el invitado usa 10.0.2.16 en `wlan0`.
Por eso se usa el modo `udp_connect`. El modo `udp_listen` está cubierto por
`MavlinkClientUdpTest` con sockets reales.

## Instalar en un dispositivo

```bash
adb install -r dist/artifacts/SafeFlight-Android-<versión>-debug.apk
```

Para el MK32 ver [deployment/mk32.md](../deployment/mk32.md).
