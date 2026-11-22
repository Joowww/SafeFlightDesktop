#!/usr/bin/env python3
"""Map view validation of SafeFlight Desktop (no mouse or keyboard input).

Runs the application from source (or a packaged --exe) with an isolated
configuration and synthetic telemetry; buttons are pressed with UI
Automation "Invoke".

  M-01 no saved view and no vehicle: world view
  M-02 vehicle with a recent 3D fix: the map follows the vehicle
  M-03 "Guardar esta vista como ubicación inicial" writes map_view.json
  M-04 relaunch without vehicle: the saved view is used
  M-05 "Olvidar vista guardada": back to the world view

    python tests/gui/desktop_map_validation.py [--exe SafeFlightDesktop.exe]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import desktop_gui_validation as g  # noqa: E402
from desktop_gui_validation import Step  # noqa: E402

MAVLINK_PORT = 14572
WORK = g.ROOT / "build" / "gui-map-test"
OUT = g.ROOT / "build" / "gui-map-evidence"
CONFIG = WORK / "config"


def launch(exe):
    env = {**os.environ, "SAFEFLIGHT_CONFIG_DIR": str(CONFIG), "SAFEFLIGHT_LOG_DIR": str(WORK / "logs"),
           "PYTHONIOENCODING": "utf-8"}
    cmd = [str(exe)] if exe else [sys.executable, str(g.ROOT / "App_flet.py")]
    console = open(WORK / f"console-{int(time.time())}.txt", "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, cwd=Path(exe).parent if exe else g.ROOT, env=env, stdout=console,
                            stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    gui = g.Gui(proc)
    gui.wait_window(timeout=90)
    time.sleep(3)
    gui.open_sidebar_if_closed()
    return gui


def map_text(gui, predicate=lambda t: True, timeout=15):
    return gui.wait_text(lambda t: t.startswith("Mapa: ") and predicate(t), timeout=timeout)


def saved_view():
    path = CONFIG / "map_view.json"
    return json.loads(path.read_text(encoding="utf-8")).get("initial_view") if path.exists() else None


def use_profile_port():
    """Isolated profiles: SITL profile listening on the test port."""
    sys.path.insert(0, str(g.ROOT))
    from models.ConnectionProfiles import ProfileStore
    store = ProfileStore(config_dir=CONFIG, environ={}).load()
    profile = store.get("sitl").copy()
    profile.mavlink.transport, profile.mavlink.local_port = "udp_listen", MAVLINK_PORT
    profile.video.mode = "none"
    store.upsert(profile)
    store.select("sitl")
    store.save()


def stop(gui):
    if gui and gui.proc.poll() is None:
        try:
            gui.close()
            gui.proc.wait(timeout=30)
        except Exception:
            subprocess.run(["taskkill", "/PID", str(gui.proc.pid), "/T", "/F"], capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe")
    args = parser.parse_args()
    for d in (WORK, OUT):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    CONFIG.mkdir()
    use_profile_port()
    sim = gui = None
    try:
        s = Step("M-01", "Sin vista guardada ni dron: vista mundial")
        gui = launch(args.exe)
        t = map_text(gui)
        s.ok(f"'{t}'") if t and "vista mundial" in t and saved_view() is None else s.fail(f"texto={t}")

        s = Step("M-02", "Dron con GPS 3D reciente: el mapa se centra en el dron (Seguir dron activo)")
        sim = g.TelemetrySimulator("127.0.0.1", MAVLINK_PORT, rate_hz=8, custom_mode=5).start()
        gui.invoke("CONNECT")
        ok = gui.wait_text(lambda t: t.startswith("MAVLink: OK"), timeout=120)
        t = map_text(gui, lambda t: "posición del dron" in t, timeout=30)
        follow = "Seguir dron" in gui.texts()
        s.ok(f"'{ok}'; '{t}'; interruptor 'Seguir dron' presente") if ok and t and follow \
            else s.fail(f"mavlink={ok}, texto={t}, follow={follow}")

        s = Step("M-03", "Guardar esta vista como ubicación inicial")
        time.sleep(3)  # let the camera finish moving to the vehicle
        gui.invoke("Guardar esta vista como ubicación inicial")
        time.sleep(2)
        view = saved_view()
        near = view and abs(view["lat"] - 41.3874) < 0.01 and abs(view["lon"] - 2.1686) < 0.01
        s.ok(f"map_view.json: {view}") if near and view["zoom"] >= 15 else s.fail(f"vista guardada={view}")
        stop(gui)
        sim.stop()
        sim = None
        time.sleep(3)

        s = Step("M-04", "Relanzar sin dron: se usa la vista guardada")
        gui = launch(args.exe)
        t = map_text(gui)
        s.ok(f"'{t}'") if t and "vista inicial guardada" in t else s.fail(f"texto={t}")

        s = Step("M-05", "Olvidar vista guardada: vuelve la vista mundial")
        gui.invoke("Olvidar vista guardada")
        t = map_text(gui, lambda t: "vista mundial" in t)
        s.ok(f"'{t}'; map_view.json initial_view=None") if t and saved_view() is None \
            else s.fail(f"texto={t}, guardada={saved_view()}")
    except Exception as exc:
        Step.results[-1].update(result="FAIL", detail=f"{type(exc).__name__}: {exc}")
        print(f"  FAIL {type(exc).__name__}: {exc}")
    finally:
        if sim:
            sim.stop()
        stop(gui)
    passed = sum(1 for r in Step.results if r["result"] == "PASS")
    (OUT / "report.json").write_text(json.dumps({"steps": Step.results}, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    print(f"\n{passed}/{len(Step.results)} steps passed. Report: {OUT / 'report.json'}")
    return 0 if passed == len(Step.results) else 1


if __name__ == "__main__":
    sys.exit(main())
