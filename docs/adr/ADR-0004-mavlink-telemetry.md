# ADR-0004: MAVLink para telemetría, con un contrato verificable en dos implementaciones

**Estado:** Aceptada · **Fecha:** 2026-11-19

## Contexto
El Cube Orange (ArduCopter 4.6.3) publica su estado por MAVLink; MAVProxy en la
Raspberry lo redistribuye por UDP. Desktop usa DroneKit/pymavlink. Android necesita
recibir la misma telemetría.

## Problema
Cómo recibir MAVLink en Android y garantizar que ambos clientes interpretan igual los
mensajes.

## Alternativas (Android)
1. MAVSDK-Java (requiere servidor `mavsdk_server` nativo por ABI).
2. Bibliotecas Java generadas (p. ej. dronefleet), con mantenimiento limitado.
3. Analizador propio del subconjunto necesario.

## Decisión
* Desktop mantiene DroneKit/pymavlink.
* Android implementa un analizador MAVLink v1/v2 propio, limitado a 7 mensajes de
  telemetría, sin codificador de comandos (solo `HEARTBEAT` de GCS opcional).
* Un contrato ([mavlink-telemetry-contract.md](../../shared/protocols/mavlink-telemetry-contract.md))
  y 17 vectores generados con pymavlink se ejecutan en ambos clientes.

## Justificación
* El subconjunto es pequeño (CRC X.25 + 7 estructuras) y totalmente comprobable.
* Sin binarios nativos ni dependencias que puedan no existir para el MK32.
* La ausencia de codificador de comandos refuerza la política de controles bloqueados.
* Los vectores generados por pymavlink usan la misma biblioteca que Desktop, de modo
  que la referencia es independiente del código Kotlin.

## Consecuencias
* Añadir un mensaje exige: `CRC_EXTRA`, *offsets* (verificables con pymavlink), regla
  en el contrato y vector.
* El analizador Android resincroniza mejor que pymavlink ante falsos bytes de inicio.

## Limitaciones
No soporta firma MAVLink 2 (las tramas firmadas se aceptan sin validar la firma) ni
mensajes fuera del subconjunto.
