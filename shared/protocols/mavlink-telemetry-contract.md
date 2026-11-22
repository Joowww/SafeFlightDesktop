# Contrato de telemetría MAVLink de SafeFlight

**Estado:** IMPLEMENTADO y VERIFICADO con vectores de prueba en ambos clientes.

Este documento fija cómo SafeFlight Desktop y SafeFlight Android interpretan el
subconjunto de MAVLink que muestran al operador. Su objetivo es que ambos
clientes presenten los mismos valores ante los mismos mensajes y que ninguno
muestre como válido un dato desconocido.

La conformidad se comprueba con [`mavlink-test-vectors.json`](mavlink-test-vectors.json),
generado con pymavlink por [`scripts/generate_mavlink_vectors.py`](../../scripts/generate_mavlink_vectors.py)
y ejecutado por:

* Desktop: [`tests/desktop/test_mavlink_vectors.py`](../../tests/desktop/test_mavlink_vectors.py) (pymavlink).
* Android: [`SharedVectorsTest.kt`](../../android/app/src/test/java/org/safeflight/android/mavlink/SharedVectorsTest.kt) (analizador propio en Kotlin).

## 1. Alcance

* Protocolo: MAVLink 1 (`0xFE`) y MAVLink 2 (`0xFD`), dialecto `ardupilotmega`.
* Uso: **solo recepción de telemetría**. El único mensaje que Android puede emitir es
  un `HEARTBEAT` de estación de tierra (opcional, por perfil). No se emiten comandos.
* Vehículo de referencia: ArduCopter 4.6.x (Cube Orange).

## 2. Identificación del vehículo

| Regla | Detalle |
|---|---|
| Heartbeat de vehículo | `autopilot != MAV_AUTOPILOT_INVALID (8)` y `type ∉ {MAV_TYPE_GCS (6), MAV_TYPE_ONBOARD_CONTROLLER (18)}` |
| Bloqueo | El primer heartbeat de vehículo fija `(system_id, component_id)`; los heartbeats de otros sistemas o componentes (GCS, gimbal, otro vehículo) se ignoran. |
| Resto de mensajes | Solo se aceptan del `system_id` bloqueado y después del primer heartbeat. |
| Enlace | La edad del último heartbeat **del vehículo** determina el estado del enlace; un heartbeat de GCS no cuenta. |

## 3. Conversiones

| Mensaje | Campo mostrado | Conversión | Valor desconocido |
|---|---|---|---|
| HEARTBEAT (0) | armado | `base_mode & MAV_MODE_FLAG_SAFETY_ARMED (0x80)` | — |
| HEARTBEAT (0) | modo | tabla ArduCopter de `custom_mode` | `UNKNOWN(n)` si no está en la tabla |
| SYS_STATUS (1) | tensión batería | `voltage_battery / 1000` V | `65535` |
| SYS_STATUS (1) | corriente | `current_battery / 100` A | `-1` |
| SYS_STATUS (1) | batería restante | `battery_remaining` % | `-1` |
| GLOBAL_POSITION_INT (33) | latitud/longitud | `lat/1e7`, `lon/1e7` grados | `lat = lon = 0` |
| GLOBAL_POSITION_INT (33) | altitud MSL / relativa | `alt/1000`, `relative_alt/1000` m | — |
| GLOBAL_POSITION_INT (33) | rumbo | `hdg/100` grados | `65535` |
| VFR_HUD (74) | velocidad suelo / aire / vertical | m/s (float) | valor no finito |
| GPS_RAW_INT (24) | fix, satélites, HDOP | `fix_type`, `satellites_visible`, `eph/100` | sats `255`, eph `65535` |
| STATUSTEXT (253) | mensaje del autopiloto | texto hasta el primer `\0`, severidad 0–7 | — |
| COMMAND_ACK (77) | último ACK | `command`, `result` | — |

Tabla de modos ArduCopter (`custom_mode`): 0 STABILIZE, 1 ACRO, 2 ALT_HOLD, 3 AUTO,
4 GUIDED, 5 LOITER, 6 RTL, 7 CIRCLE, 9 LAND, 11 DRIFT, 13 SPORT, 14 FLIP, 15 AUTOTUNE,
16 POSHOLD, 17 BRAKE, 18 THROW, 19 AVOID_ADSB, 20 GUIDED_NOGPS, 21 SMART_RTL,
22 FLOWHOLD, 23 FOLLOW, 24 ZIGZAG, 25 SYSTEMID, 26 AUTOROTATE, 27 AUTO_RTL.
La prueba `test_mode_table_matches_desktop_dronekit_patch` verifica que la tabla
usada por el parche de DroneKit en `App_flet.py` coincide con esta.

Un `COMMAND_ACK` con `MAV_RESULT_ACCEPTED` indica aceptación del comando, **no**
la finalización de la maniobra.

## 4. Robustez del analizador

* Las tramas con CRC incorrecto (incluido `CRC_EXTRA`) se descartan.
* MAVLink 2 elimina los ceros finales de la carga útil; el receptor la completa con ceros.
* Ruido antes de una trama: se descarta hasta el siguiente byte de inicio.
* Falso byte de inicio: el contrato exige recuperar la sincronización en tramas posteriores.
  pymavlink puede perder la trama inmediatamente siguiente; el analizador Android
  descarta solo el byte de inicio falso y no pierde ninguna (prueba `falseStartDoesNotSwallowNextFrame`).

## 5. Supervisión del enlace (Android)

| Estado | Condición |
|---|---|
| `WAITING_HEARTBEAT` | socket abierto, sin heartbeat del vehículo |
| `CONNECTED` | edad ≤ `telemetry_stale_s` |
| `STALE` | edad > `telemetry_stale_s` |
| `LOST` | edad > 3 × `telemetry_stale_s` |
| `ERROR` | error de socket; reintento cada 2 s |

SafeFlight Desktop muestra la edad del último heartbeat que proporciona DroneKit
(`vehicle.last_heartbeat`) con el mismo umbral `telemetry_stale_s`. El monitor propio
de Desktop que ordena `LAND` tras 15 s sin heartbeat (`models/HeartbeatMonitor.py`)
es comportamiento previo y no se ha modificado.
