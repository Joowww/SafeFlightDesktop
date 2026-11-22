# ADR-0008: Comandos de vuelo deshabilitados en SafeFlight Android

**Estado:** Aceptada · **Fecha:** 2026-11-19

## Contexto
La GCS Android debe preparar ARM, DISARM, TAKEOFF, LAND, cambio de modo, inicio y
detención de misión. No existe todavía validación SITL, análisis de seguridad ni
autorización operativa, y no se ha completado un vuelo físico acreditado.

## Problema
Preparar interfaz y arquitectura para comandos futuros sin permitir acciones físicas.

## Alternativas
1. Omitir los controles hasta que estén validados.
2. Mostrar controles deshabilitados por una bandera configurable.
3. Mostrar controles bloqueados por una constante de compilación, sin codificador de
   comandos en la capa MAVLink.

## Decisión
Alternativa 3. `CommandGate.PHYSICAL_COMMANDS_ENABLED = false`; toda pulsación pasa por
`CommandGate.evaluate()`, que devuelve `Blocked` con los motivos (incluidas las
precondiciones de enlace y vehículo). La capa MAVLink solo codifica `HEARTBEAT` de GCS.

## Justificación
* Una bandera configurable podría activarse por error; una constante requiere cambiar
  el código y pasar revisión y pruebas.
* La ausencia del codificador elimina el riesgo incluso ante un defecto en la interfaz.
* Mantener los botones visibles con su motivo documenta los requisitos pendientes.

## Consecuencias
Habilitar comandos exigirá: codificador `COMMAND_LONG`, confirmación del operador,
comprobación de estado, ACK con tiempo de espera, prevención de duplicados, pruebas
SITL y autorización. La aceptación (`COMMAND_ACK`) no se interpretará como finalización.

## Limitaciones
No afecta a SafeFlight Desktop, cuyas funciones previas de despegue/aterrizaje se
conservan sin cambios y siguen sin validación en vuelo físico. El RC del mando no
depende de SafeFlight.
