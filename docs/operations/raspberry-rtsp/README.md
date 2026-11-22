# Vídeo RTSP temporal desde la Raspberry Pi (MediaMTX)

SafeFlight Android solo reproduce **RTSP** (Media3 no admite RTP/SDP crudo). Para ver la cámara
de la Raspberry en la MK32 se publica el H.264 de `rpicam-vid` en un servidor RTSP temporal.
SafeFlight Desktop puede seguir usando RTP/UDP 5004 o usar la misma URL RTSP.

Reglas: arranque **manual** en un terminal, **sin servicio** systemd, sin tocar la configuración
de red, solo en la LAN del laboratorio (no se abre nada a Internet). Se detiene con `Ctrl+C`.

## 1. Descarga (una vez, en `~/mediamtx`)

```bash
mkdir -p ~/mediamtx && cd ~/mediamtx
wget https://github.com/bluenviron/mediamtx/releases/download/v1.21.4/mediamtx_v1.21.4_linux_arm64.tar.gz
echo "47784081da54c0608ea4dc359f5cfb19880209434769c532b3ed3a67ea99c29d  mediamtx_v1.21.4_linux_arm64.tar.gz" | sha256sum -c
tar xzf mediamtx_v1.21.4_linux_arm64.tar.gz mediamtx
```

Copiar [mediamtx.yml](mediamtx.yml) a `~/mediamtx/mediamtx.yml` (solo RTSP en el puerto 8554;
RTMP, HLS, WebRTC, SRT, MoQ, API y métricas desactivados).

## 2. Arranque (dos terminales SSH)

Terminal 1 — servidor:
```bash
cd ~/mediamtx && ./mediamtx mediamtx.yml
```

Terminal 2 — publicación de la cámara (1280×720 a 30 FPS, sin recodificar):
```bash
rpicam-vid -t 0 -n --width 1280 --height 720 --framerate 30 --codec h264 --inline --intra 30 -o - \
  | ffmpeg -hide_banner -loglevel warning -framerate 30 -f h264 -i pipe:0 -an -c:v copy \
      -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/cam
```

La cámara solo puede tener **un** proceso: detener antes cualquier `rpicam-vid` que envíe RTP al
MSI (`pgrep -af rpicam-vid`).

## 3. Reproducción

| Cliente | Configuración |
|---|---|
| SafeFlight Android | Perfil **RASPBERRY / CUBE (LAB)** → vídeo RTSP `rtsp://172.16.15.85:8554/cam`, TCP |
| SafeFlight Desktop | Perfil **RASPBERRY / CUBE (LAB)** → modo de vídeo RTSP (la URL ya está en el perfil) |
| Comprobación rápida | `ffprobe -rtsp_transport tcp rtsp://172.16.15.85:8554/cam` |

Si la IP de la Raspberry cambia, editar la URL en el perfil (no en el código).

## 4. Parada

`Ctrl+C` en ambos terminales. No queda nada instalado fuera de `~/mediamtx`.

## Validación previa (sin Raspberry)

- Misma versión de MediaMTX y la misma configuración en Docker (`bluenviron/mediamtx:1.21.4-ffmpeg`)
  con la tubería de publicación anterior: SafeFlight Desktop (PyAV) recibe 1280×720.
- SafeFlight Android en emulador API 28 (Android 9, como la MK32) y API 36: «VÍDEO EN DIRECTO»
  1280×720 desde un servidor RTSP local; recuperación automática tras caída del servidor (API 36).
- **Pendiente**: prueba con la cámara real y la MK32 en la red del laboratorio.
