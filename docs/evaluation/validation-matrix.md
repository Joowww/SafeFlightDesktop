# Matriz de validación

Fecha de corte: 2026-11-19 (segunda iteración) · Versión 0.3.0 · Revisión base `704a540` con
cambios sin confirmar (rama `feature/multiplatform-android`). Cada celda remite a una entrada
de [test-log.md](test-log.md). No se ha rellenado ninguna celda por suposición.

| Estado | Significado |
|---|---|
| VERIFIED | Ejecutado con resultado correcto y evidencia registrada |
| PARTIAL | Verificado en parte (se indica qué falta) |
| NOT_TESTED | No ejecutado (NO PROBADO) |
| BLOCKED | No ejecutable por falta de hardware o entorno (PENDIENTE DE HARDWARE) |
| FAILED | Ejecutado con resultado incorrecto |
| NOT_APPLICABLE | No aplica |

Correspondencia con la terminología de la memoria del TFG:

| Término | Criterio |
|---|---|
| VERIFICADO EN WINDOWS | VERIFIED en la columna Windows (ejecutable empaquetado y su interfaz) |
| VERIFICADO EN LINUX | VERIFIED en la columna Linux (contenedor Ubuntu 24.04, compilación y arranque) |
| VERIFICADO EN ANDROID EMULADO | VERIFIED en emulador API 36 y/o API 28 |
| COMPILADO EN CI | El workflow de GitHub Actions de esa plataforma terminó correctamente; no implica validación funcional |
| PENDIENTE DE VALIDACIÓN FÍSICA | BLOCKED: requiere dron, Raspberry, enlace SIYI o MK32 |
| DISEÑADO | Especificado sin implementar (p. ej. integración con el supervisor, [integration-points.md](../architecture/integration-points.md)) |

## 1. Matriz principal

| Funcionalidad | Windows | macOS | Linux | Android |
|---|---|---|---|---|
| Compilación | VERIFIED (T-03, T-14) | NOT_TESTED: dependencias resueltas para macOS 15 arm64/x64 (T-16); requiere runner macOS | VERIFIED en contenedor Ubuntu 24.04 (T-17) | VERIFIED (T-08, T-19) |
| Arranque | VERIFIED: ejecutable empaquetado (T-13 D-01) | NOT_TESTED | VERIFIED: paquete con interfaz bajo Xvfb (T-18) | VERIFIED en emulador API 36 (T-20) y API 28/Android 9 (T-21); BLOCKED en MK32 |
| MAVLink | VERIFIED desde la interfaz con datos sintéticos (T-13 D-07) | NOT_TESTED | PARTIAL: pruebas de integración en contenedor (T-17); interfaz no ejercitada | VERIFIED en emulador API 36 (T-20) y API 28 (T-21) |
| Vídeo | VERIFIED: RTP/UDP y RTSP dentro de la ventana (T-13 D-08, D-10) | NOT_TESTED | PARTIAL: receptor RTP/UDP en contenedor (T-17); RTSP omitido, interfaz no ejercitada | VERIFIED RTSP en emulador API 36 y API 28 (T-20, T-21) |
| Configuración | VERIFIED: crear, duplicar, seleccionar, guardar y persistir desde la interfaz (T-13 D-03…D-06) | NOT_TESTED | PARTIAL: lógica (T-17) | VERIFIED: edición y persistencia desde la interfaz en API 36 (T-20) |
| Reconexión | VERIFIED: pérdida y recuperación de heartbeat en pantalla; cambio de fuente de vídeo en caliente (T-13 D-09, D-10) | NOT_TESTED | PARTIAL: lógica (T-17) | VERIFIED API 36 (T-20) |

## 2. Funcionalidades adicionales

| Funcionalidad | Estado | Evidencia |
|---|---|---|
| Cierre de Desktop libera procesos y puertos | VERIFIED (Windows) | T-13 D-11 |
| Logs de sesión de Desktop | VERIFIED (Windows, Linux) | T-13 D-12, T-18 |
| Configuración fuera del ejecutable | VERIFIED (Windows) | T-15 |
| Paquete Windows sin credenciales ni temporales | VERIFIED | T-15 |
| `--clean` limitado y conserva artefactos | VERIFIED (entorno aislado) | T-14 |
| Contrato MAVLink idéntico en Desktop y Android | VERIFIED | T-01, T-07 |
| Comandos físicos bloqueados en Android | VERIFIED | T-07, T-20 A-09 |
| Ciclo de vida Android (liberación y reanudación de vídeo) | VERIFIED (API 36) | T-20 A-07 |
| Persistencia de perfiles Android tras `force-stop` | VERIFIED (API 36) | T-20 A-08 |
| Compatibilidad de la APK con Android 9 (API 28) | VERIFIED en emulador (instalación, arranque, perfil, telemetría, RTSP, ciclo de vida, persistencia, bloqueo de ARM); automatización de la interfaz solo parcial en esa imagen | T-21 |
| Workflows de GitHub Actions | NOT_TESTED: definición revisada, versiones y dependencias comprobadas; requiere *push* autorizado | T-16 |
| Paquete macOS | NOT_TESTED: requiere runner o Mac | — |
| SafeFlight Android en SIYI MK32 | BLOCKED (sin hardware) | [deployment/mk32.md](../deployment/mk32.md) |
| Enlace de datos SIYI real (Raspberry ↔ unidad aérea) | BLOCKED (sin hardware); no implementado en la Raspberry | — |
| Telemetría de un autopiloto real o ArduPilot SITL | NOT_TESTED (solo generador sintético) | — |
| Despegue/aterrizaje de Desktop | NOT_TESTED (excluido por seguridad) | — |

## 3. Interpretación

* Compilar no equivale a validar: macOS solo se considerará verificado tras la lista de
  [development/macos.md](../development/macos.md#5-lista-de-validación-en-mac-pendiente).
* Linux está verificado en compilación y arranque en un contenedor; la interacción con su
  interfaz (CONNECT, editor) no se ha automatizado.
* Las pruebas de MAVLink usan un generador sintético; no se ha conectado un autopiloto.
* El emulador no reproduce el decodificador, la red SIYI ni las restricciones del MK32.
