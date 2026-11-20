#!/usr/bin/env python3
"""End-to-end validation of the SafeFlight Desktop user interface (Windows).

Drives the *packaged* executable through Windows UI Automation (the Flutter
client exposes its accessibility tree) and real keyboard input, using only
local test sources:

  * scripts/mavlink_test_sender.py  - synthetic ArduCopter telemetry (UDP)
  * scripts/rtp_test_sender.py      - H.264 RTP/UDP test pattern
  * scripts/rtsp-test-server         - RTSP test server (Docker, port 18554)

No vehicle, Raspberry Pi or autopilot is contacted and no flight command is
sent. The scenario uses an isolated configuration and log directory.

Requirements: Windows, `pip install pywinauto==0.6.9`, a packaged build in
dist/desktop/windows-x64 and, for the RTSP step, the Docker test server.
While it runs (about 3 minutes) the script briefly takes keyboard focus.

    python tests/gui/desktop_gui_validation.py

Results: build/gui-evidence/report.json and numbered screenshots.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab
from pywinauto import Desktop, keyboard

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from mavlink_test_sender import TelemetrySimulator  # noqa: E402
from rtp_test_sender import RtpTestSender  # noqa: E402

EXE_DIR = ROOT / "dist" / "desktop" / "windows-x64" / "SafeFlightDesktop"
EXE = EXE_DIR / "SafeFlightDesktop.exe"
OUT = ROOT / "build" / "gui-evidence"
WORK = ROOT / "build" / "gui-test"
CONFIG_DIR = WORK / "config"
LOG_DIR = WORK / "logs"
TITLE = "SafeFlight Desktop"

PROFILE_NAME = "Banco de pruebas"
MAVLINK_PORT = 14571
RTP_PORT = 5610
RTSP_URL = "rtsp://127.0.0.1:18554/test"


class Step:
    results: list = []

    def __init__(self, sid: str, description: str):
        self.entry = {"id": sid, "description": description, "result": "FAIL", "detail": "", "evidence": []}
        Step.results.append(self.entry)
        print(f"\n[{sid}] {description}", flush=True)

    def ok(self, detail: str = ""):
        self.entry.update(result="PASS", detail=detail)
        print(f"  PASS {detail}", flush=True)

    def fail(self, detail: str):
        self.entry.update(result="FAIL", detail=detail)
        print(f"  FAIL {detail}", flush=True)

    def evidence(self, name: str):
        self.entry["evidence"].append(name)


class Gui:
    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.win = None

    def wait_window(self, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            wins = [w for w in Desktop(backend="uia").windows() if w.window_text() == TITLE]
            if wins:
                self.win = wins[0]
                # The first UIA query makes Flutter enable its semantics tree.
                for _ in range(10):
                    if len(self.win.descendants()) > 10:
                        return
                    time.sleep(1)
                return
            time.sleep(1)
        raise RuntimeError("main window not found")

    def elements(self, control_type=None):
        return self.win.descendants(control_type=control_type) if control_type else self.win.descendants()

    def texts(self):
        out = []
        for e in self.elements():
            try:
                out.append(e.window_text())
            except Exception:
                pass
        return out

    def find(self, name, control_type=None, prefix=False, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for e in self.elements(control_type):
                try:
                    t = e.window_text()
                except Exception:
                    continue
                if (t.startswith(name) if prefix else t == name):
                    return e
            time.sleep(0.5)
        raise LookupError(f"element not found: {name!r}")

    def invoke(self, name, control_type="Button", **kw):
        self.find(name, control_type, **kw).invoke()
        time.sleep(1.2)

    def edit_value(self, label):
        # Read-only TextFields are exposed as Text, editable ones as Edit.
        return self.find(label).iface_value.CurrentValue

    def type_into(self, label, text):
        self.win.set_focus()
        field = self.find(label, "Edit")
        field.set_focus()
        time.sleep(0.4)
        escaped = "".join("{%s}" % c if c in "+^%~(){}[]" else c for c in text)
        keyboard.send_keys("^a" + escaped, pause=0.03, with_spaces=True)
        time.sleep(0.6)
        value = self.edit_value(label)
        if value != text:
            raise AssertionError(f"{label}: typed {text!r}, field shows {value!r}")

    def select(self, dropdown_label, option):
        # Flutter dropdowns do not open through UIA Invoke: a real click is used.
        self.win.set_focus()
        self.find(dropdown_label).click_input()
        time.sleep(1.5)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            for e in self.elements():
                try:
                    if e.window_text() == option and e.element_info.control_type != "Edit":
                        r = e.rectangle()
                        if r.width() > 0:
                            e.click_input()
                            time.sleep(1.2)
                            return
                except Exception:
                    continue
            time.sleep(0.5)
        raise LookupError(f"option {option!r} not found in {dropdown_label!r}")

    def wait_text(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        last = []
        while time.monotonic() < deadline:
            last = self.texts()
            hits = [t for t in last if t and predicate(t)]
            if hits:
                return hits[0]
            time.sleep(0.7)
        return None

    def shot(self, name, step: Step):
        try:
            self.win.set_focus()
        except Exception:
            pass
        time.sleep(0.8)
        r = self.win.rectangle()
        path = OUT / name
        ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True).save(path)
        step.evidence(name)

    def open_sidebar_if_closed(self):
        if "CONNECT" not in self.texts() and not any(t.startswith("ONLINE") for t in self.texts()):
            buttons = [e for e in self.elements("Button") if e.window_text().startswith("Error displaying")]
            # Bottom-left icon button toggles the sidebar.
            target = min(buttons, key=lambda e: e.rectangle().left - e.rectangle().top)
            target.invoke()
            time.sleep(1.5)

    def close(self):
        [e for e in self.elements("Button") if e.window_text() == "Cerrar" and e.rectangle().top < self.win.rectangle().top + 60][0].invoke()


def app_processes():
    cmd = ["powershell", "-NoProfile", "-Command",
           f"Get-Process | Where-Object {{ $_.Path -like '{EXE_DIR}*' }} | ForEach-Object {{ $_.ProcessName + ':' + $_.Id }}"]
    return [line for line in subprocess.run(cmd, capture_output=True, text=True).stdout.split() if line]


def launch():
    env = {**os.environ, "SAFEFLIGHT_CONFIG_DIR": str(CONFIG_DIR), "SAFEFLIGHT_LOG_DIR": str(LOG_DIR)}
    console = open(WORK / f"console-{int(time.time())}.txt", "w", encoding="utf-8")
    proc = subprocess.Popen([str(EXE)], cwd=EXE_DIR, env=env, stdout=console, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    gui = Gui(proc)
    gui.wait_window()
    time.sleep(3)
    return gui


def udp_port_free(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False


def rtsp_available():
    try:
        with socket.create_connection(("127.0.0.1", 18554), timeout=1):
            return True
    except OSError:
        return False


def load_profiles():
    return json.loads((CONFIG_DIR / "connection_profiles.json").read_text(encoding="utf-8"))


def main() -> int:
    if not EXE.exists():
        print(f"packaged executable not found: {EXE}")
        return 2
    if app_processes():
        print("SafeFlight Desktop from dist/ is already running; close it first.")
        return 2
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    WORK.mkdir(parents=True)
    OUT.mkdir(parents=True)
    sim = rtp = None

    try:
        # ---------------------------------------------------------------- 1
        s = Step("D-01", "El ejecutable empaquetado arranca y muestra la ventana principal")
        gui = launch()
        s.ok(f"ventana '{TITLE}', {len(gui.elements())} elementos accesibles")
        gui.shot("D-01-arranque.png", s)

        s = Step("D-02", "Panel lateral: perfil por defecto y cadena MAVLink derivada del perfil")
        gui.open_sidebar_if_closed()
        mav = gui.edit_value("MAVLink")
        if mav == "udpin:0.0.0.0:14560" and "Fuente en uso: RTP/UDP :5004" in gui.texts():
            s.ok(f"MAVLink={mav}; vídeo RTP/UDP :5004")
        else:
            s.fail(f"MAVLink={mav}")
        gui.shot("D-02-panel-lateral.png", s)

        # ---------------------------------------------------------------- 3
        s = Step("D-03", "Crear un perfil nuevo desde el editor y guardarlo")
        gui.invoke("Editar perfiles…")
        gui.invoke("Nuevo")
        gui.type_into("Nombre", PROFILE_NAME)
        gui.type_into("Puerto local", str(MAVLINK_PORT))
        gui.type_into("Puerto RTP local (UDP)", str(RTP_PORT))
        gui.shot("D-03-editor-nuevo.png", s)
        gui.invoke("Guardar y seleccionar")
        doc = load_profiles()
        active = next(p for p in doc["profiles"] if p["id"] == doc["active_profile_id"])
        mav = gui.edit_value("MAVLink")
        if (active["name"] == PROFILE_NAME and active["mavlink"]["local_port"] == MAVLINK_PORT
                and active["video"]["rtp_udp_port"] == RTP_PORT and mav == f"udpin:0.0.0.0:{MAVLINK_PORT}"):
            s.ok(f"perfil '{active['id']}' activo; panel lateral MAVLink={mav}; fichero actualizado")
        else:
            s.fail(f"activo={active}, MAVLink={mav}")
        new_id = active["id"]

        # ---------------------------------------------------------------- 4
        s = Step("D-04", "Duplicar un perfil desde el editor y guardar la copia")
        gui.invoke("Editar perfiles…")
        gui.invoke("Duplicar")
        gui.invoke("Guardar y seleccionar")
        doc = load_profiles()
        copies = [p for p in doc["profiles"] if p["name"].startswith(PROFILE_NAME) and p["id"] != new_id]
        if copies and doc["active_profile_id"] == copies[0]["id"] and len(doc["profiles"]) == 5:
            s.ok(f"copia '{copies[0]['name']}' ({copies[0]['id']}); 5 perfiles en el fichero")
        else:
            s.fail(f"perfiles={[p['id'] for p in doc['profiles']]}, activo={doc['active_profile_id']}")

        s = Step("D-05", "Seleccionar el perfil desde el desplegable del panel lateral")
        gui.select("Perfil de conexión", PROFILE_NAME)
        doc = load_profiles()
        if doc["active_profile_id"] == new_id and gui.edit_value("MAVLink") == f"udpin:0.0.0.0:{MAVLINK_PORT}":
            s.ok(f"perfil activo {new_id}")
        else:
            s.fail(f"activo={doc['active_profile_id']}")

        # ---------------------------------------------------------------- 6
        s = Step("D-06", "Persistencia: el perfil activo se conserva tras cerrar y reabrir")
        gui.close()
        gui.proc.wait(timeout=30)
        time.sleep(3)
        gui = launch()
        gui.open_sidebar_if_closed()
        mav = gui.edit_value("MAVLink")
        if mav == f"udpin:0.0.0.0:{MAVLINK_PORT}":
            s.ok(f"tras reiniciar: MAVLink={mav}")
        else:
            s.fail(f"tras reiniciar: MAVLink={mav}")
        gui.shot("D-06-reapertura.png", s)

        # ---------------------------------------------------------------- 7
        s = Step("D-07", "CONNECT usa el endpoint del perfil (generador solo en el puerto del perfil)")
        sim = TelemetrySimulator("127.0.0.1", MAVLINK_PORT, rate_hz=8, custom_mode=5).start()
        rtp = RtpTestSender(port=RTP_PORT).start()
        gui.invoke("CONNECT")
        ok = gui.wait_text(lambda t: t.startswith("MAVLink: OK"), timeout=60)
        mode = gui.wait_text(lambda t: t == "MODE: LOITER", timeout=20)
        sats = gui.wait_text(lambda t: t == "SAT: 12", timeout=20)
        if ok and mode and sats:
            s.ok(f"'{ok}', HUD '{mode}', '{sats}'")
        else:
            s.fail(f"estado={ok}, modo={mode}, sat={sats}")

        s = Step("D-08", "Vídeo RTP/UDP del perfil visible en la ventana")
        live = gui.wait_text(lambda t: t == "● CAMERA LIVE", timeout=40)
        fps = gui.wait_text(lambda t: t.startswith("RX ") and not t.startswith("RX 0.0"), timeout=10)
        gui.shot("D-08-telemetria-video-rtp.png", s)
        s.ok(f"'{live}', '{fps}'") if live and fps else s.fail(f"live={live}, fps={fps}")

        # ---------------------------------------------------------------- 9
        s = Step("D-09", "Pérdida y recuperación del heartbeat reflejadas en pantalla")
        sim.pause(True)
        stale = gui.wait_text(lambda t: "TELEMETRÍA OBSOLETA" in t, timeout=12)
        gui.shot("D-09-heartbeat-perdido.png", s)
        sim.pause(False)  # resumed well before the 15 s link-loss monitor of the app
        back = gui.wait_text(lambda t: t.startswith("MAVLink: OK"), timeout=15)
        s.ok(f"'{stale}' → '{back}'") if stale and back else s.fail(f"stale={stale}, back={back}")

        # ---------------------------------------------------------------- 10
        s = Step("D-10", "Cambiar la fuente de vídeo a RTSP desde el editor, sin reiniciar")
        if not rtsp_available():
            s.entry.update(result="NOT_RUN", detail="servidor RTSP de pruebas no disponible en 18554")
        else:
            rtp.stop()
            rtp = None
            lost = gui.wait_text(lambda t: t == "● SIGNAL LOST", timeout=15)
            gui.invoke("Editar perfiles…")
            gui.select("Fuente de vídeo", "RTSP (servidor remoto)")
            gui.type_into("URL RTSP", RTSP_URL)
            gui.invoke("Guardar y seleccionar")
            live = gui.wait_text(lambda t: t == "● CAMERA LIVE", timeout=60)
            src = gui.wait_text(lambda t: t.startswith("Fuente en uso: RTSP"), timeout=5)
            try:  # make the video the main view for the evidence screenshot
                swap = max((e for e in gui.elements("Button") if e.window_text().startswith("Error displaying")),
                           key=lambda e: e.rectangle().right - e.rectangle().top)
                swap.invoke()
                time.sleep(2)
            except ValueError:
                pass
            gui.shot("D-10-video-rtsp.png", s)
            s.ok(f"RTP detenido → '{lost}'; '{src}' → '{live}'") if live and src else s.fail(f"live={live}, src={src}")

        # ---------------------------------------------------------------- 11
        s = Step("D-11", "Cerrar la ventana libera procesos y puertos")
        gui.close()
        try:
            gui.proc.wait(timeout=30)
            exited = True
        except subprocess.TimeoutExpired:
            exited = False
        time.sleep(3)
        left = app_processes()
        ports = {MAVLINK_PORT: udp_port_free(MAVLINK_PORT), RTP_PORT: udp_port_free(RTP_PORT)}
        if exited and not left and all(ports.values()):
            s.ok(f"código de salida {gui.proc.returncode}; sin procesos; puertos libres {ports}")
        else:
            s.fail(f"exited={exited}, procesos={left}, puertos={ports}")

        # ---------------------------------------------------------------- 12
        s = Step("D-12", "Registro de sesión en el directorio de logs del usuario")
        logs = sorted(LOG_DIR.glob("safeflight-*.log"))
        content = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in logs)
        needed = [f"Conectando con perfil '{PROFILE_NAME}'", f"udpin:0.0.0.0:{MAVLINK_PORT}",
                  "Fuente aplicada: RTSP", "SESIÓN CERRADA"]
        missing = [n for n in needed if n not in content]
        if len(logs) >= 2 and not missing:
            s.ok(f"{len(logs)} ficheros de sesión; contienen conexión, cambio de vídeo y cierre")
        else:
            s.fail(f"logs={len(logs)}, faltan={missing}")
    except Exception as exc:  # record the failure of the current step
        Step.results[-1].update(result="FAIL", detail=f"{type(exc).__name__}: {exc}")
        print(f"  FAIL {type(exc).__name__}: {exc}")
    finally:
        if sim:
            sim.stop()
        if rtp:
            rtp.stop()
        for pid in [p.split(":")[1] for p in app_processes()]:
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)

    report = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "executable": str(EXE), "steps": Step.results}
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    passed = sum(r["result"] == "PASS" for r in Step.results)
    print(f"\n{passed}/{len(Step.results)} steps passed. Report: {OUT / 'report.json'}")
    return 0 if passed == len(Step.results) else 1


if __name__ == "__main__":
    sys.exit(main())
