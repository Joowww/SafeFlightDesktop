# ADR-0007: Estrategia de compilación multiplataforma

**Estado:** Aceptada · **Fecha:** 2026-11-19

## Contexto
El propietario desarrolla en Windows; otro miembro del equipo usa macOS. El flujo
deseado es editar, ejecutar un comando y obtener el programa actualizado.

## Problema
Ofrecer compilación reproducible para tres sistemas de escritorio y Android sin
mantener procedimientos distintos.

## Alternativas
1. Scripts por plataforma (`.bat`, `.sh`) y Gradle por separado.
2. Un `build.py` en Python como punto único, reutilizado por CI.
3. Sistemas genéricos (Make, Nox, Bazel).

## Decisión
`build.py` (solo biblioteca estándar) para todos los objetivos; GitHub Actions ejecuta
el mismo comando en una matriz Windows / Linux / macOS arm64 / macOS x64 y en Ubuntu
para Android. Versiones Android: AGP 8.13.2 y Gradle 8.14 (última línea 8.x), Kotlin
2.3.21, Compose BOM 2026.06.01, Media3 1.10.1.

## Justificación
* Python ya es requisito de Desktop: no se añade herramienta nueva.
* Mismo comando local y en CI: un fallo en CI se reproduce localmente.
* El informe JSON por artefacto (pruebas, *smoke test*, SHA-256, commit) aporta
  trazabilidad para la memoria.
* AGP 9 exige Gradle 9 y cambia la integración de Kotlin; la línea 8.x reduce el riesgo
  en esta primera versión y es compatible con `compileSdk 36`.

## Consecuencias
* `--clean` solo borra directorios de salida controlados (comprobación de rutas).
* `--skip-tests` produce artefactos marcados `validated: false`.

## Limitaciones
* Migración futura a AGP 9 / Gradle 9.
* CI requiere un primer *push* para validarse; hasta entonces su estado es NO PROBADO.
