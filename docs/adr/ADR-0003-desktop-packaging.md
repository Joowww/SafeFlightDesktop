# ADR-0003: PyInstaller para empaquetar SafeFlight Desktop

**Estado:** Aceptada · **Fecha:** 2026-11-19

## Contexto
La versión 0.2 se distribuía con PyInstaller en Windows mediante un `.spec` local con
una ruta absoluta de Windows. Se necesitan paquetes para Windows, macOS y Linux.

## Problema
Elegir la herramienta de empaquetado multiplataforma que conserve el funcionamiento
actual (Flet + PyAV + DroneKit).

## Alternativas
1. PyInstaller con una especificación multiplataforma.
2. `flet pack` (envoltorio de PyInstaller).
3. `flet build` (compila una app Flutter con Python embebido).
4. Nuitka / Briefcase.

## Decisión
PyInstaller 6.22 en modo *one-folder* con `packaging/desktop/SafeFlightDesktop.spec`,
que genera un `.app` (`BUNDLE`) en macOS.

## Justificación
* Es la herramienta con la que ya funcionaba la versión distribuida.
* `collect_all("av")` y `collect_all("flet_desktop")` incluyen FFmpeg y el cliente
  Flutter de cada SO; no hace falta compilar Flutter.
* `flet build` requiere el SDK de Flutter y toolchains nativas (Xcode, Visual Studio),
  y cambia el modelo de ejecución.
* *One-folder* arranca más rápido y evita extraer ~300 MB a un temporal en cada inicio.

## Consecuencias
* Cada plataforma se compila en su propio sistema (local o CI).
* macOS: paquetes separados arm64 y x64 (los wheels nativos no son *universal2*).
* UPX desactivado para evitar corromper bibliotecas de FFmpeg/Flutter.
* Las importaciones dinámicas no son visibles para PyInstaller. pymavlink cambia al
  dialecto MAVLink 2 (`pymavlink.dialects.v20.ardupilotmega`) al recibir la primera trama
  `0xFD`; ese módulo faltaba en el paquete (también en la especificación de v0.2), por lo
  que el ejecutable no completaba la conexión con un emisor MAVLink 2 como ArduPilot.
  Detectado en la validación de interfaz ([ADR-0009](ADR-0009-gui-validation-method.md)),
  se corrigió con `hiddenimports` y el *self-check* comprueba ambos dialectos.
* macOS mínimo 14.0: los *wheels* de `av` (arm64) y `opencv-python` (x86_64) lo exigen.

## Limitaciones
Sin firma de código ni notarización: Gatekeeper y SmartScreen avisarán.
