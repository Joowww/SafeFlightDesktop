#!/usr/bin/env python3
"""Flight controls of the packaged Desktop app against ArduCopter SITL (Windows).

Drives the real buttons through UI Automation and checks the effect on the
simulated vehicle shown by the app (HUD altitude and armed state):

  F-01 connect with a TCP profile to SITL (127.0.0.1:5760)
  F-02 monitor mode: TAKEOFF / LAND / RTL disabled, status "SOLO MONITORIZACIÓN"
  F-03 authorisation dialog: wrong SYSID refused; checklist + SYSID accepted
  F-04 TAKEOFF button: vehicle armed and at the slider altitude
  F-05 LAND button: vehicle lands and disarms
  F-06 revoke: back to monitor mode, TAKEOFF disabled
  F-07 close the window: process exits

Requirements: SITL container running (see tests/sitl/sitl_flight_validation.py),
pywinauto, a packaged build. The script briefly takes keyboard focus.

    python tests/gui/desktop_sitl_flight.py --exe <path to SafeFlightDesktop.exe>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab
from pywinauto import Desktop, keyboard

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from models.ConnectionProfiles import ConnectionProfile, MavlinkEndpoint, ProfileStore, VideoSource  # noqa: E402

TITLE = "SafeFlight Desktop"
OUT = ROOT / "build" / "gui-sitl-evidence"
WORK = ROOT / "build" / "gui-sitl-test"
steps = []


def step(sid, text):
    entry = {"id": sid, "description": text, "result": "FAIL", "detail": "", "evidence": []}
    steps.append(entry)
    print(f"\n[{sid}] {text}", flush=True)
    return entry


def done(entry, ok, detail):
    entry.update(result="PASS" if ok else "FAIL", detail=detail)
    print(f"  {'PASS' if ok else 'FAIL'} {detail}", flush=True)
    return ok


class App:
    def __init__(self, exe: Path):
        env = {**os.environ, "SAFEFLIGHT_CONFIG_DIR": str(WORK / "config"), "SAFEFLIGHT_LOG_DIR": str(WORK / "logs")}
        self.proc = subprocess.Popen([str(exe)], cwd=exe.parent, env=env, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 60
        self.win = None
        while time.monotonic() < deadline and self.win is None:
            wins = [w for w in Desktop(backend="uia").windows() if w.window_text() == TITLE]
            self.win = wins[0] if wins else None
            time.sleep(1)
        for _ in range(15):
            if len(self.win.descendants()) > 10:
                break
            time.sleep(1)

    def els(self, ct=None):
        return self.win.descendants(control_type=ct) if ct else self.win.descendants()

    def texts(self):
        out = []
        for e in self.els():
            try:
                out.append(e.window_text())
            except Exception:
                pass
        return out

    def find(self, name, ct=None, prefix=False, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for e in self.els(ct):
                try:
                    t = e.window_text()
                except Exception:
                    continue
                if (t.startswith(name) if prefix else t == name):
                    return e
            time.sleep(0.4)
        raise LookupError(name)

    def wait_text(self, pred, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            hits = [t for t in self.texts() if t and pred(t)]
            if hits:
                return hits[0]
            time.sleep(0.7)
        return None

    def invoke(self, name):
        self.find(name, "Button").invoke()
        time.sleep(1.2)

    def type_into(self, label, text):
        self.win.set_focus()
        self.find(label, "Edit").set_focus()
        time.sleep(0.4)
        keyboard.send_keys("^a" + text, pause=0.03)
        time.sleep(0.6)

    def shot(self, name, entry):
        try:
            self.win.set_focus()
        except Exception:
            pass
        time.sleep(0.8)
        try:
            self.win.restore()
        except Exception:
            pass
        r = self.win.rectangle()
        if r.width() <= 0 or r.height() <= 0:
            entry["evidence"].append(f"{name} (captura no disponible: ventana sin área visible)")
            return
        ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True).save(OUT / name)
        entry["evidence"].append(name)

    def open_sidebar(self):
        if "CONNECT" in self.texts():
            return
        btns = [e for e in self.els("Button") if e.window_text().startswith("Error displaying")]
        min(btns, key=lambda e: e.rectangle().left - e.rectangle().top).invoke()
        time.sleep(1.5)

    def open_telemetry_panel(self):
        """Bottom-right icon button; the panel shows 'MODE: x / ARMED: y'."""
        if any(t.startswith("MODE: ") and "ARMED" in t for t in self.texts()):
            return
        btns = [e for e in self.els("Button") if e.window_text().startswith("Error displaying")]
        max(btns, key=lambda e: e.rectangle().left + e.rectangle().top).invoke()
        time.sleep(1.5)


def hud_altitude(app):
    t = app.wait_text(lambda s: s.startswith("H: "), 3)
    m = re.match(r"H: (-?[\d.]+)m", t or "")
    return float(m.group(1)) if m else None


def armed(app):
    t = app.wait_text(lambda s: s.startswith("MODE: ") and "ARMED" in s, 3)
    return None if t is None else ("ARMED: True" in t), t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    args = ap.parse_args()
    exe = Path(args.exe)
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    store = ProfileStore(config_dir=WORK / "config", environ={}).load()
    store.upsert(ConnectionProfile(id="sitl-tcp", name="SITL TCP 5760", kind="sitl",
                                   mavlink=MavlinkEndpoint(transport="tcp_client", remote_host="127.0.0.1",
                                                           remote_port=5760),
                                   video=VideoSource(mode="none")))
    store.select("sitl-tcp")
    store.save()
    app = App(exe)
    try:
        e = step("F-01", "Conexión al SITL con un perfil TCP desde la interfaz")
        app.open_sidebar()
        app.open_telemetry_panel()
        app.invoke("CONNECT")
        ok = app.wait_text(lambda t: t.startswith("MAVLink: OK"), 90)
        done(e, bool(ok), ok or "sin heartbeat")

        e = step("F-02", "Solo monitorización: pulsar TAKEOFF, LAND y RTL no tiene efecto en el vehículo")
        status = app.wait_text(lambda t: t.startswith("SOLO MONITORIZACIÓN"), 10)
        mode_before = app.wait_text(lambda t: t.startswith("MODE: ") and "ARMED" in t, 5)
        for name in ("TAKEOFF", "LAND", "RTL"):
            try:
                app.find(name, "Button").invoke()   # disabled in the UI; tried anyway
            except Exception:
                pass
            time.sleep(1)
        time.sleep(6)
        is_armed, after = armed(app)
        app.shot("F-02-monitorizacion.png", e)
        unchanged = (after or "").split()[1:2] == (mode_before or "").split()[1:2]
        done(e, bool(status) and is_armed is False and unchanged,
             f"'{status}'; antes {mode_before!r}; después {after!r}")

        e = step("F-03", "Diálogo de autorización: SYSID incorrecto rechazado; correcto aceptado")
        app.invoke("Autorizar control…")
        checklist = ("Piloto con mando RC", "Zona despejada", "Comprobaciones pre-arm",
                     "Failsafes del autopiloto", "Autorizo esta sesión")
        for label in checklist:
            app.find(label, "CheckBox", prefix=True).toggle()
        app.type_into("Escribe el SYSID del vehículo", "7")
        app.invoke("Autorizar")
        refused = app.wait_text(lambda t: "no coincide" in t, 5)
        app.type_into("Escribe el SYSID del vehículo", "1")
        app.shot("F-03-autorizacion.png", e)
        app.invoke("Autorizar")
        authorized = app.wait_text(lambda t: t.startswith("CONTROL AUTORIZADO"), 10)
        done(e, bool(refused) and bool(authorized), f"rechazo='{refused}'; estado='{authorized}'")

        e = step("F-04", "Botón TAKEOFF: armado y altura del deslizador (2,5 m) en SITL")
        app.invoke("TAKEOFF")
        end = time.monotonic() + 90
        alt = None
        while time.monotonic() < end:
            alt = hud_altitude(app)
            if alt is not None and alt >= 2.3:
                break
            time.sleep(1)
        is_armed, status = armed(app)
        app.shot("F-04-despegue.png", e)
        done(e, alt is not None and alt >= 2.3 and bool(is_armed), f"H={alt} m · {status!r}")

        e = step("F-05", "Botón LAND: aterrizaje y desarmado")
        time.sleep(5)
        app.invoke("LAND")
        end = time.monotonic() + 90
        while time.monotonic() < end:
            is_armed, status = armed(app)
            if is_armed is False:
                break
            time.sleep(1)
        app.shot("F-05-aterrizaje.png", e)
        done(e, is_armed is False, f"H={hud_altitude(app)} m · {status!r}")

        e = step("F-06", "Revocar: vuelta a solo monitorización")
        app.invoke("Revocar")
        status = app.wait_text(lambda t: t.startswith("SOLO MONITORIZACIÓN"), 10)
        try:
            app.find("TAKEOFF", "Button").invoke()   # disabled in the UI; tried anyway
        except Exception:
            pass
        time.sleep(8)
        is_armed, after = armed(app)
        done(e, bool(status) and is_armed is False,
             f"'{status}'; tras pulsar TAKEOFF: {after!r}")

        e = step("F-07", "Cerrar la ventana")
        [b for b in app.els("Button") if b.window_text() == "Cerrar" and b.rectangle().top < app.win.rectangle().top + 60][0].invoke()
        try:
            app.proc.wait(timeout=30)
            done(e, True, f"código de salida {app.proc.returncode}")
        except subprocess.TimeoutExpired:
            done(e, False, "el proceso no terminó")
    except Exception as exc:
        steps[-1].update(result="FAIL", detail=f"{type(exc).__name__}: {exc}")
        print(f"  FAIL {exc}")
    finally:
        if app.proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(app.proc.pid), "/T", "/F"], capture_output=True)
    logs = sorted((WORK / "logs").glob("*.log"))
    audit = [l for p in logs for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if "[CMD]" in l]
    (OUT / "report.json").write_text(json.dumps({"date": time.strftime("%Y-%m-%d %H:%M:%S"), "exe": exe.name,
                                                 "steps": steps, "command_audit": audit},
                                                indent=2, ensure_ascii=False), encoding="utf-8")
    passed = sum(s["result"] == "PASS" for s in steps)
    print(f"\n{passed}/{len(steps)} steps passed. Report: {OUT / 'report.json'}")
    return 0 if passed == len(steps) else 1


if __name__ == "__main__":
    sys.exit(main())
