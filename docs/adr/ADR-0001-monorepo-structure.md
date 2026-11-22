# ADR-0001: Un repositorio con dos aplicaciones independientes

**Estado:** Aceptada · **Fecha:** 2026-11-19

## Contexto
SafeFlight Desktop existe como aplicación Python en la raíz del repositorio
`SafeFlightDesktop`. Se añade una GCS nativa para el SIYI MK32 y ambas deben
evolucionar juntas (mismos perfiles, mismo protocolo, misma versión).

## Problema
Cómo alojar Desktop y Android sin acoplar sus tecnologías ni romper las rutas,
imports y empaquetado existentes de Desktop.

## Alternativas
1. Dos repositorios separados.
2. Un repositorio con Desktop movido a `desktop/` y Android en `android/`.
3. Un repositorio con Desktop **en su ubicación actual** y Android en `android/`.

## Decisión
Alternativa 3. Android es un proyecto Gradle autónomo en `android/`; los contratos
comunes viven en `shared/`; `build.py` y `VERSION` en la raíz sirven a ambos.

## Justificación
* Mover Desktop exigiría reescribir imports, rutas de recursos, `Dockerfile` y la
  especificación PyInstaller sin aportar funcionalidad; la prioridad es no romperlo.
* Un solo repositorio permite cambiar a la vez el contrato y los dos clientes, con
  pruebas de ambos lados en el mismo commit.
* Compartir contratos (esquema JSON, vectores MAVLink) y no código evita forzar un
  lenguaje común.

## Consecuencias
* La raíz mezcla ficheros de Desktop con carpetas de proyecto (`android/`, `shared/`, `docs/`).
* CI usa filtros de rutas para no compilar lo que no cambia.

## Limitaciones
Si Desktop crece, puede justificarse moverlo a `desktop/` en un cambio aislado, con
pruebas antes y después y verificación de ejecutables (procedimiento de la Parte III
del encargo).
