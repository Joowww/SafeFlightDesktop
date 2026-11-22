# ADR-0006: Vídeo y telemetría como canales separados; RTSP como formato común

**Estado:** Aceptada · **Fecha:** 2026-11-19

## Contexto
El vídeo H.264 de la Raspberry llega hoy a Desktop como RTP/UDP descrito por un SDP
local. Android (Media3) no reproduce un SDP local, pero sí RTSP. El MK32 recibirá
datos por el enlace SIYI.

## Problema
Definir cómo se configuran, supervisan y diagnostican vídeo y telemetría, y qué formato
de vídeo deben soportar ambas aplicaciones.

## Alternativas
1. Un único estado de «conexión» para vídeo y telemetría.
2. Canales independientes con estados y diagnósticos propios.
3. Vídeo encapsulado en MAVLink.

## Decisión
Canales independientes. Desktop soporta `rtp_udp` y `rtsp`; Android soporta `rtsp`.
RTSP es el formato objetivo común para el enlace SIYI (servidor en la Raspberry).

## Justificación
* Fallan de forma distinta: perder vídeo no implica perder telemetría (verificado en
  emulador: telemetría perdida con vídeo en directo y viceversa).
* RTSP negocia la sesión y permite TCP (más robusto ante pérdidas) o UDP; RTP/UDP
  directo no tiene control de sesión y depende de puertos fijos.
* Se conserva `rtp_udp` en Desktop para no romper el flujo 5G actual.

## Consecuencias
* Cada canal tiene umbral de obsolescencia y política de reintento propios.
* Android incorpora un *watchdog* que reabre la sesión si no llegan fotogramas.

## Limitaciones
La Raspberry aún no publica RTSP: el perfil SIYI usa una URL provisional.
