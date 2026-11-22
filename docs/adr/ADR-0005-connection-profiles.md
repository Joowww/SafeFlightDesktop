# ADR-0005: Perfiles de conexión persistentes

**Estado:** Aceptada · **Fecha:** 2026-11-19

## Contexto
En v0.2 la cadena MAVLink estaba fijada en código (`udpin:0.0.0.0:14560`) o en `.env`;
el campo de conexión de la interfaz no se utilizaba. El vídeo se configuraba aparte en
`video_settings.json` y requería reiniciar. Cambiar de red (5G, SIYI, SITL) obligaba a
editar código o ficheros.

## Problema
Separar la configuración de red y equipos del código, sin introducir complejidad
innecesaria para cambios de IP o puerto.

## Alternativas
1. Variables de entorno / `.env`.
2. Un fichero de configuración único editado a mano.
3. Perfiles con nombre, persistentes y editables desde la interfaz.
4. Descubrimiento automático de servicios (mDNS).

## Decisión
Perfiles con nombre (SIYI LOCAL, 5G / VPN, SITL / SIMULACIÓN y personalizados),
persistidos en JSON en el directorio de usuario del SO, con un esquema común
([connection-profiles.schema.json](../../shared/schemas/connection-profiles.schema.json))
para Desktop y Android.

## Justificación
* Un cambio de red con el mismo protocolo se resuelve seleccionando o editando un perfil.
* Los perfiles de fábrica pueden restaurarse sin afectar a otros perfiles.
* Validación estricta antes de usar los datos; fichero corrupto → copia y valores de fábrica.
* Migración: `video_settings.json` y `SIM_conn_str`/`REAL_conn_str` se incorporan a
  los perfiles en el primer arranque; `ENV_MODE=prod` selecciona el perfil 5G.
* El descubrimiento automático se descarta: añade dependencias y superficie de fallo sin
  resolver la necesidad real (valores conocidos que cambian poco).

## Consecuencias
* El selector de perfil se bloquea durante una sesión MAVLink en Desktop; el vídeo sí
  se cambia en caliente.
* Los transportes no soportados por un cliente (serie en Android, RTP en Android) se
  detectan al validar, no se aceptan en silencio.

## Limitaciones
Sin almacenamiento seguro de credenciales: no deben guardarse contraseñas reales en
URL RTSP (se ocultan en logs, pero el fichero las contiene en claro).
