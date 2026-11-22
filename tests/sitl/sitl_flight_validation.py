#!/usr/bin/env python3
"""Flight-control validation against ArduCopter SITL (no hardware).

Uses the same DroneManager / CommandGuard calls as the Desktop buttons and
checks the *effect* on the simulated vehicle:

  S1 monitor mode: direct arm and mode-change attempts have no effect
  S2 operator session authorised for the identified vehicle
  S3 GUIDED -> ARM -> TAKEOFF 5 m, confirmed by telemetry
  S4 stable hover
  S5 LAND, duplicate LAND rejected, landing and automatic disarm
  S6 second take-off, link stall (container paused): session suspended,
     movement and take-off refused, emergency RTL accepted; RTL lands and disarms
  S7 session revoked: back to monitor mode

Start SITL first (isolated container, localhost only):

  docker run -d --rm --name safeflight-sitl -p 127.0.0.1:5760:5760 ubuntu:24.04 bash -c "<see docs>"

  python tests/sitl/sitl_flight_validation.py [--connect tcp:127.0.0.1:5760] [--container safeflight-sitl]

Report: build/sitl-evidence/report.json
"""

from __future__ import annotations

import argparse
import collections
import collections.abc
import json
import subprocess
import sys
import time
from pathlib import Path

if not hasattr(collections, "MutableMapping"):
    collections.MutableMapping = collections.abc.MutableMapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dronekit import VehicleMode  # noqa: E402

from models import CommandGuard as cg  # noqa: E402
from models.DroneManager import DroneManager  # noqa: E402

OUT = ROOT / "build" / "sitl-evidence"
steps = []


def step(sid, text):
    entry = {"id": sid, "description": text, "result": "FAIL", "detail": "", "t": time.strftime("%H:%M:%S")}
    steps.append(entry)
    print(f"\n[{sid}] {text}", flush=True)
    return entry


def ok(entry, detail):
    entry.update(result="PASS", detail=detail)
    print(f"  PASS {detail}", flush=True)


def fail(entry, detail):
    entry.update(result="FAIL", detail=detail)
    print(f"  FAIL {detail}", flush=True)


def wait(pred, timeout, period=0.5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(period)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", default="tcp:127.0.0.1:5760")
    ap.add_argument("--container", default="safeflight-sitl")
    ap.add_argument("--altitude", type=float, default=5.0)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    m = DroneManager()
    alt_trace = []
    try:
        e = step("S0", f"Conexión a SITL ({args.connect}) e identidad del vehículo")
        assert m.setup_drone(connection_string=args.connect, heartbeat_timeout=30, connect_timeout=60)
        v = m.link.vehicle
        wait(lambda: m.identity is not None, 10)
        version = str(v.version)
        ok(e, f"identidad {m.identity}, firmware {version}")

        e = step("S0b", "Autopiloto listo para armar (GPS/EKF), sin comandos")
        ready = wait(lambda: v.is_armable and v.gps_0.fix_type >= 3, 120)
        (ok if ready else fail)(e, f"is_armable={v.is_armable}, fix={v.gps_0.fix_type}, sats={v.gps_0.satellites_visible}")
        if not ready:
            return 1

        e = step("S1", "Modo monitorización: armar y cambiar de modo directamente no tiene efecto")
        mode_before = v.mode.name
        v.mode = VehicleMode("GUIDED")
        v.armed = True
        time.sleep(5)
        if not v.armed and v.mode.name == mode_before and m.guard.state == cg.MONITOR:
            ok(e, f"sigue desarmado en {v.mode.name}; bloqueados: {m.guard.blocked_counts}")
        else:
            fail(e, f"armed={v.armed} mode={v.mode.name}")
            return 1

        e = step("S2", "Sesión de control autorizada por el operador para el vehículo identificado")
        d = m.guard.authorize([True] * 5, str(m.identity[0]))
        (ok if d else fail)(e, d.reason + " · " + m.guard.status_text())
        if not d:
            return 1

        e = step("S3", f"GUIDED → ARM → TAKEOFF {args.altitude:.0f} m (secuencia del botón TAKEOFF)")
        t0 = time.monotonic()
        took_off = m.arm_and_takeoff_safe(args.altitude, mode="GUIDED")
        alt = v.location.global_relative_frame.alt
        if took_off and v.armed and v.mode.name == "GUIDED":
            ok(e, f"altitud {alt:.2f} m en {time.monotonic() - t0:.1f} s")
        else:
            fail(e, f"{m.last_error} (armed={v.armed}, mode={v.mode.name}, alt={alt})")
            return 1

        e = step("S4", "Vuelo estacionario estable 10 s")
        samples = []
        for _ in range(20):
            a = v.location.global_relative_frame.alt
            samples.append(a)
            alt_trace.append({"t": round(time.monotonic() - t0, 1), "alt": round(a, 2), "phase": "hover"})
            time.sleep(0.5)
        spread = max(samples) - min(samples)
        stable = all(abs(a - args.altitude) < 1.0 for a in samples) and v.armed
        (ok if stable else fail)(e, f"altitud {min(samples):.2f}–{max(samples):.2f} m (variación {spread:.2f} m)")

        e = step("S5", "LAND (botón LAND), LAND duplicado rechazado, aterrizaje y desarmado automático")
        landed_cmd = m.land()
        duplicate = m.land()
        down = wait(lambda: not v.armed, 90)
        alt = v.location.global_relative_frame.alt
        if landed_cmd and not duplicate and "ya está en land" in m.last_error.lower() and down:
            ok(e, f"modo {v.mode.name}, desarmado, altitud {alt:.2f} m; duplicado: '{m.last_error}'")
        else:
            fail(e, f"land={landed_cmd} dup={duplicate} ({m.last_error}) disarmed={not v.armed}")

        e = step("S6", "Segundo despegue, pérdida de enlace simulada, rechazo de órdenes y RTL de emergencia")
        time.sleep(2.5)
        if not m.arm_and_takeoff_safe(4.0, mode="GUIDED"):
            fail(e, f"segundo despegue: {m.last_error}")
            return 1
        subprocess.run(["docker", "pause", args.container], check=True, capture_output=True)
        time.sleep(4)
        m.guard.tick()
        suspended = m.guard.state == cg.SUSPENDED
        movement = m.guard.request(cg.VELOCITY)
        takeoff = m.guard.request(cg.TAKEOFF, altitude=3)
        subprocess.run(["docker", "unpause", args.container], check=True, capture_output=True)
        wait(lambda: v.last_heartbeat < 1.0, 15)
        rtl = m.return_to_launch()
        home = wait(lambda: not v.armed, 180)
        alt = v.location.global_relative_frame.alt
        if suspended and not movement and not takeoff and rtl and home:
            ok(e, f"suspendida={suspended}; VELOCITY='{movement.reason}'; TAKEOFF='{takeoff.reason}'; "
                  f"RTL aceptado y aterrizado (alt {alt:.2f} m, desarmado)")
        else:
            fail(e, f"suspended={suspended} movement={bool(movement)} takeoff={bool(takeoff)} rtl={rtl} "
                    f"disarmed={not v.armed} err={m.last_error}")

        e = step("S7", "Revocar sesión: vuelta a solo monitorización")
        m.guard.revoke("Fin de la validación SITL")
        v.armed = True
        time.sleep(4)
        (ok if m.guard.state == cg.MONITOR and not v.armed else fail)(
            e, f"estado {m.guard.state}, armado={v.armed}")
    except Exception as exc:
        steps[-1].update(result="FAIL", detail=f"{type(exc).__name__}: {exc}")
        print(f"  FAIL {exc}")
    finally:
        subprocess.run(["docker", "unpause", args.container], capture_output=True)
        audit = [{"t": round(a.at, 1), "event": a.event, "detail": a.detail} for a in m.guard.audit]
        if m.health:
            m.health.stop()
        if m.link:
            m.link.disconnect()
    report = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "connection": args.connect,
              "steps": steps, "audit": audit, "altitude_trace": alt_trace}
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    passed = sum(s["result"] == "PASS" for s in steps)
    print(f"\n{passed}/{len(steps)} steps passed. Report: {OUT / 'report.json'}")
    return 0 if passed == len(steps) else 1


if __name__ == "__main__":
    sys.exit(main())
