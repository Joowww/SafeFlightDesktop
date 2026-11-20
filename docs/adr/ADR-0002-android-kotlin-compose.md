# ADR-0002: Kotlin y Jetpack Compose para SafeFlight Android

**Estado:** Aceptada · **Fecha:** 2026-11-19

## Contexto
El SIYI MK32 es un mando con Android 9 (API 28), SoC Qualcomm de 8 núcleos y
pantalla de 7" de alto brillo. Se requiere una GCS nativa, horizontal, con vídeo
de baja latencia y telemetría.

## Problema
Elegir tecnología de aplicación compatible con Android 9, mantenible y con buen
soporte de vídeo RTSP.

## Alternativas
1. Kotlin + Jetpack Compose.
2. Kotlin + Views (XML).
3. Flet/Flutter compartiendo código Python con Desktop.
4. Reutilizar QGroundControl (Qt).

## Decisión
Kotlin + Jetpack Compose (Material 3), MVVM con `StateFlow`, un solo módulo Gradle,
`minSdk 26`.

## Justificación
* Compose es el kit de interfaz recomendado y soporta API 21+ (las bibliotecas usadas
  exigen 23+); `minSdk 26` cubre el MK32 con margen.
* Media3 (ExoPlayer) es la opción nativa mantenida para RTSP/H.264.
* Flet en Android ejecuta Python embebido: mayor tamaño, peor acceso a decodificación
  por hardware y menor control del ciclo de vida.
* QGroundControl es completo pero no permite integrar la vista de misiones del TFG sin
  mantener un *fork* de Qt/C++.

## Consecuencias
* No se comparte código con Desktop; la coherencia se garantiza con contratos y vectores.
* Separación por paquetes (`mavlink`, `state`, `video`, `config`, `diagnostics`,
  `mission`, `control`, `ui`) en lugar de módulos Gradle.

## Limitaciones
No probado en el MK32 real; rendimiento de vídeo y comportamiento del fabricante pendientes.
