# Prueba de vuelo supervisada desde SafeFlight Desktop — lista de comprobación

Objetivo: despegue, estacionario y aterrizaje breves del dron (Cube Orange, ArduCopter 4.6.3)
ordenados desde SafeFlight Desktop, con piloto y mando RC de respaldo. **Si cualquier punto
crítico (★) falla, no se despega.** La aplicación no omite ninguna comprobación del autopiloto.

Software validado antes del ensayo solo en simulación (ArduCopter 4.6.3 SITL): bloqueo de
comandos, sesión autorizada, GUIDED → ARM → TAKEOFF, LAND, RTL de emergencia, rechazo tras
pérdida de enlace. Ver [test-log.md](../evaluation/test-log.md). El vuelo físico no está validado.

## 0. Roles

| Rol | Responsabilidad |
|---|---|
| Piloto (★) | Mando RC en mano todo el tiempo; puede tomar el control (cambio de modo/LAND por RC) o desarmar en cualquier momento |
| Operador SafeFlight | Única estación autorizada a enviar comandos; anuncia cada comando en voz alta antes de pulsarlo |
| Observador | Perímetro, tiempo de vuelo y batería |

SafeFlight Android y cualquier otra GCS permanecen **solo en monitorización**.

## 1. Hardware (sin hélices hasta la fase D)

- [ ] ★ Batería cargada y bien sujeta; tensión registrada: ____ V
- [ ] ★ Hélices y sentido de giro inspeccionados (montar solo en fase D)
- [ ] Cube Orange alimentado; Raspberry Pi arrancada
- [ ] Cube visible en la Raspberry: `ls -l /dev/ttyACM*` (habitualmente `/dev/ttyACM0`)
- [ ] ★ Receptor RC enlazado; el piloto ve respuesta de modos en el mando
- [ ] GPS con cielo despejado; brújula lejos de metales

## 2. Red y MAVLink

1. IP del MSI en la red que llega a la Raspberry (**no reutilizar IP anteriores**):
   `Find-NetRoute -RemoteIPAddress <IP_RASPBERRY>` → campo `IPAddress`. En la sesión SSH de la
   Raspberry, `echo $SSH_CLIENT` debe mostrar la misma IP.
2. En la Raspberry, comprobar que **no** hay otro MAVProxy: `pgrep -af mavproxy` (debe estar vacío).
3. Lanzar **una sola** instancia (Raspberry del laboratorio: `172.16.15.85`):
   ```bash
   ~/mavproxy-venv/bin/mavproxy.py --master=/dev/ttyACM0,57600 \
     --out=udpout:<IP_MSI>:14560 --target-system=1 --mav20
   ```
   Para que la tableta MK32 también vea la telemetría (solo monitorización), añadir una segunda
   salida `--out=udpout:<IP_ANDROID>:14550` en la **misma** instancia (nunca un segundo MAVProxy).
4. En SafeFlight Desktop: perfil **RASPBERRY / CUBE (LAB)** (`udpin:0.0.0.0:14560`) →
   **CONNECT** → «MAVLink: OK · último heartbeat < 1 s». Orden validado: abrir SafeFlight y pulsar
   CONNECT, y después lanzar MAVProxy (paso 3). Con un Cube real la descarga inicial de parámetros
   puede tardar; si no conecta en 90 s, cerrar SafeFlight, comprobar IP/puerto y repetir.
5. [ ] ★ Panel lateral en **«SOLO MONITORIZACIÓN · comandos bloqueados»**.
6. En Android: perfil **RASPBERRY / CUBE (LAB)**, «Enviar heartbeat de GCS» **desactivado**.
   Android no tiene autoridad de mando: ARM/TAKEOFF/LAND están bloqueados en la app.

### Primera conexión física — SOLO MONITORIZACIÓN (no se autoriza nada)

Anotar los valores. Si alguno falla, se desconecta y se revisa antes de continuar.

| Comprobación | Dónde | Valor |
|---|---|---|
| ★ SYSID / COMPID / tipo del autopiloto (esperado SYSID 1, QUADROTOR) | Panel de telemetría (`SYSID · HB`) y diálogo «Autorizar control…» (abrir y **cancelar**) | |
| ★ Heartbeat estable < 1 s durante 2 min | Panel (`HB`) e indicador MAVLink | |
| ★ GPS fix ≥ 3 y satélites ≥ 8 | Panel (`GPS fix · sats`) y HUD | |
| ★ Batería: tensión y % coherentes con el voltímetro | Panel (`BAT: V · %`) | |
| ★ Sin mensajes `PreArm:` | Consola de MAVProxy | |
| ★ RC: canales responden al mover sticks/interruptores; modo cambia desde el mando y SafeFlight lo refleja | MAVProxy `status` (RC_CHANNELS) y panel (`MODE`) | |
| Contadores de bloqueo: ningún `[CMD] BLOQUEADO` inesperado | Log de SafeFlight | |

## 3. Fase A — sin movimiento (telemetría)

- [ ] ★ Panel de telemetría: modo, `ARMED: False`; HUD con `SAT` ≥ 8 y altura ≈ 0
- [ ] ★ GPS fix 3D o mejor; posición del dron en el mapa coherente con el lugar
- [ ] Mensajes del autopiloto sin `PreArm:` pendientes (consola de MAVProxy)
- [ ] Valores de failsafe consultados (solo lectura, en MAVProxy: `param show FS_*`,
      `param show BATT_FS*`, `param show RTL_ALT`): ________________________
- [ ] Mover el dron a mano: la orientación y la posición cambian en SafeFlight

## 4. Fase B — control en tierra, **sin hélices**

1. Pulsar **Autorizar control…**: comprobar SYSID/COMPID/tipo; marcar las 5 casillas; escribir el
   SYSID; **Autorizar**. Estado: «CONTROL AUTORIZADO · SYSID 1 · 20:00».
2. **TAKEOFF** con 2,5 m en el deslizador: los motores deben armar y girar
   (sin hélices). Comprobar en el log `[CMD] ENVIADO` y `[CMD] ACK … ACEPTADO`.
3. **LAND** inmediatamente: el autopiloto pasa a LAND y desarma.
4. **Revocar** y comprobar que TAKEOFF queda deshabilitado.
- [ ] ★ La secuencia anterior se comporta como en SITL

## 5. Fase C — mando físico

- [ ] ★ Con motores armados sin hélices (desde el RC), el piloto desarma desde el mando
- [ ] ★ El piloto cambia de modo desde el mando (p. ej. STABILIZE/LOITER/LAND) y SafeFlight lo refleja
- [ ] ★ Se acuerda la orden de aborto: «¡ABORTO!» → el piloto toma el control por RC

## 6. Fase D — decisión y vuelo (con hélices)

- [ ] ★ Zona permitida, perímetro despejado, meteorología adecuada, piloto competente presente
- [ ] ★ Fases A–C superadas; batería suficiente
1. Montar hélices. Re-autorizar la sesión (nueva lista).
2. **TAKEOFF** a 2,5 m. El operador anuncia; el piloto con el mando listo.
3. Estacionario ≤ 30 s observando estabilidad y deriva.
4. **LAND**. Confirmar aterrizaje y desarmado (`ARMED: False`).
5. **Revocar** la sesión.

### Abortar
- Cualquier anomalía: el piloto toma el control por RC (modo/LAND/desarme) — **prioridad absoluta**.
- Desde SafeFlight: **LAND** o **RTL** (permitidos también con la sesión suspendida).
  Si un LAND no se confirma, puede pulsarse de nuevo inmediatamente; solo se rechaza cuando el
  autopiloto ya informa modo LAND (ídem RTL).
- Si SafeFlight pierde el enlace, no envía nada automáticamente: actúan los failsafes del Cube y el piloto.

### Enviado, aceptado y ejecutado

| Log / mensaje | Significado |
|---|---|
| `[CMD] ENVIADO …` | SafeFlight escribió el comando en el enlace; no garantiza que llegue |
| `[CMD] ACK … ACEPTADO` | El autopiloto lo recibió y lo aceptó (COMMAND_ACK) |
| «… confirmado por el autopiloto» | El efecto se observó en la telemetría (modo, armado, altura) |
| `[CMD] BLOQUEADO …` | CommandGuard lo descartó antes de salir del equipo |

Solo la última fila de éxito («confirmado») indica que la orden se ejecutó.

## 7. Después

- Guardar el log de sesión (`%LOCALAPPDATA%\SafeFlightDesktop\logs\`) y el `.tlog` de MAVProxy.
- Anotar resultado y observaciones en el registro de pruebas.
