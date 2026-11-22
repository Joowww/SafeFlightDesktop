# ADR-0009: Validación de la interfaz con el ejecutable empaquetado y UI Automation

**Estado:** Aceptada · **Fecha:** 2026-11-19

## Contexto
La primera iteración verificó la lógica de Desktop (perfiles, MAVLink, vídeo) con
pruebas unitarias y de integración, pero no la interfaz: no se había comprobado que el
botón CONNECT, el editor de perfiles o el vídeo funcionasen dentro de la ventana del
ejecutable distribuido.

## Problema
Validar de forma reproducible la interfaz Flet (Flutter) de Windows sin hardware y sin
depender de comprobaciones manuales.

## Alternativas
1. Pruebas manuales con lista de comprobación.
2. Pruebas de *widgets* con el SDK de Flutter (requiere toolchain Flutter, no prueba el paquete).
3. Automatizar el **ejecutable empaquetado** mediante Windows UI Automation (UIA), leyendo
   el árbol de accesibilidad que expone el cliente Flutter, y entrada de teclado real.
4. Comparación de capturas por píxeles.

## Decisión
Alternativa 3: [`tests/gui/desktop_gui_validation.py`](../../tests/gui/desktop_gui_validation.py)
(pywinauto), con fuentes de prueba locales (generador MAVLink, emisor RTP, servidor RTSP),
directorios de configuración y logs aislados y un informe JSON con capturas por paso.

## Justificación
* Prueba el mismo artefacto que se distribuye, incluidos los módulos que PyInstaller
  debe empaquetar (así se detectó la ausencia del dialecto MAVLink 2, ADR-0003).
* Las aserciones se basan en textos de la interfaz (estado MAVLink, HUD, indicador de
  vídeo) y en el fichero de perfiles, no en coordenadas de píxel.
* Las capturas por paso constituyen evidencia para la memoria.

## Consecuencias y limitaciones
* Flutter activa su árbol de accesibilidad tras la primera consulta UIA.
* Los campos de texto no admiten `SetValue` de UIA: se usa teclado real (`Ctrl+A` + texto),
  por lo que la ventana debe tener el foco durante la ejecución (≈3 min).
* Los desplegables de Flutter no se abren con el patrón *Invoke*: se usa un clic real.
* Solo Windows. macOS y Linux requieren una validación equivalente (lista manual en
  [development/macos.md](../development/macos.md)).
* `pywinauto` es una herramienta de validación local; no forma parte de los requisitos
  de ejecución ni de CI.
