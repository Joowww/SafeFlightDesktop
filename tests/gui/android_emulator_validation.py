#!/usr/bin/env python3
"""End-to-end validation of SafeFlight Android on an emulator (or test device).

Drives the debug APK through `adb` and `uiautomator` and uses local test
sources only: the synthetic MAVLink generator in server mode (UDP 14551,
reached from the emulator as 10.0.2.2) and the RTSP test server
(scripts/rtsp-test-server, rtsp://10.0.2.2:18554/test). No vehicle is
contacted and flight commands remain disabled in the app.

    python tests/gui/android_emulator_validation.py [--serial emulator-5554] [--apk path]

Results: build/android-evidence/report.json and numbered screenshots.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from mavlink_test_sender import TelemetrySimulator  # noqa: E402

PACKAGE = "org.safeflight.android.debug"
ACTIVITY = f"{PACKAGE}/org.safeflight.android.MainActivity"
OUT_BASE = ROOT / "build" / "android-evidence"
OUT = OUT_BASE
SDK = Path(os.environ.get("ANDROID_HOME") or Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk")
ADB = str(SDK / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb"))

results = []


class Device:
    def __init__(self, serial):
        self.serial = serial

    def adb(self, *args, check=True, binary=False, timeout=120):
        cmd = [ADB, "-s", self.serial, *args]
        out = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if check and out.returncode != 0:
            raise RuntimeError(f"adb {' '.join(args)} failed: {out.stderr.decode(errors='replace')}")
        return out.stdout if binary else out.stdout.decode("utf-8", errors="replace")

    def shell(self, *args, **kw):
        return self.adb("shell", *args, **kw)

    def nodes(self):
        for _ in range(3):
            # Remove the previous dump: a failed dump must never return a stale screen.
            self.shell("rm", "-f", "/sdcard/ui.xml", check=False)
            self.shell("uiautomator", "dump", "/sdcard/ui.xml", check=False)
            raw = self.shell("cat", "/sdcard/ui.xml", check=False)
            if raw.strip().startswith("<?xml"):
                root = ET.fromstring(raw[raw.index("<"):])
                nodes = list(root.iter("node"))
                # System "isn't responding" dialogs (slow emulators) are dismissed with "Wait".
                if any("keeps stopping" in (n.get("text") or "") for n in nodes):
                    close = [n for n in nodes if n.get("text") == "Close app"]
                    if close:
                        x, y = self.center(close[0])
                        self.shell("input", "tap", str(x), str(y))
                        time.sleep(2)
                        continue
                if any("isn't responding" in (n.get("text") or "") for n in nodes):
                    wait = [n for n in nodes if n.get("text") == "Wait"]
                    if wait:
                        x, y = self.center(wait[0])
                        self.shell("input", "tap", str(x), str(y))
                        time.sleep(2)
                        continue
                return nodes
            time.sleep(1)
        return []

    def texts(self):
        return [n.get("text") for n in self.nodes() if n.get("text")]

    @staticmethod
    def center(node):
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
        return (x1 + x2) // 2, (y1 + y2) // 2

    def find(self, text, timeout=15, prefix=False):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for n in self.nodes():
                t = n.get("text") or ""
                if (t.startswith(text) if prefix else t == text):
                    return n
            time.sleep(1)
        raise LookupError(f"text not found: {text!r}")

    def tap(self, text, settle=2.0, **kw):
        x, y = self.center(self.find(text, **kw))
        self.shell("input", "tap", str(x), str(y))
        time.sleep(settle)

    SCREEN_MARKERS = {"Vuelo": "VUELO", "Conexión": "PERFIL ACTIVO", "Misiones": "PENDING"}

    def go(self, screen, attempts=5):
        """Taps a navigation item until the destination screen is visible."""
        marker = self.SCREEN_MARKERS[screen]
        for _ in range(attempts):
            self.tap(screen, settle=2.5)
            if marker in self.texts():
                return
        raise LookupError(f"screen {screen!r} not reached")

    def wait_text(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            hits = [t for t in self.texts() if predicate(t)]
            if hits:
                return hits[0]
            time.sleep(1)
        return None

    def ime_shown(self):
        return "mInputShown=true" in self.shell("dumpsys", "input_method", check=False)

    def hide_ime(self):
        if self.ime_shown():
            self.shell("input", "keyevent", "KEYCODE_BACK")
            time.sleep(1.5)

    # Java/XML app: TextInputLayout keeps the label outside the EditText, so the
    # fields are found by resource id (res/layout/fragment_connection.xml).
    FIELD_IDS = {
        "Nombre": "edit_name", "Dirección local": "edit_local_host", "Puerto local": "edit_local_port",
        "IP remota": "edit_remote_host", "Puerto remoto": "edit_remote_port", "URL RTSP": "edit_rtsp_url",
        "Telemetría obsoleta (s)": "edit_stale", "Vídeo obsoleto (s)": "edit_video_stale",
        "Reintento vídeo (s)": "edit_video_retry",
    }

    def edit_field(self, label):
        """EditText for ``label``: by resource id (Views) or descendant label text (Compose)."""
        field_id = self.FIELD_IDS.get(label)
        for n in self.nodes():
            if n.get("class") == "android.widget.EditText":
                if field_id and (n.get("resource-id") or "").endswith(":id/" + field_id):
                    return n
                if n.get("hint") == label or any(c.get("text") == label for c in n.iter("node")):
                    return n
        return None

    def scroll_until(self, label, x, max_swipes=6):
        for _ in range(max_swipes):
            if self.edit_field(label) is not None or label in self.texts():
                return True
            self.shell("input", "swipe", str(x), "900", str(x), "350", "600")
            time.sleep(1.5)
        return False

    @staticmethod
    def field_text(field, label):
        """Field value: on API 30+ it is the EditText text; on API 28 a child node."""
        if field is None:
            return None
        if field.get("text") and field.get("text") != label:
            return field.get("text")
        for child in field.iter("node"):
            t = child.get("text")
            if t and t != label:
                return t
        return ""

    def type_into(self, label, text, x_scroll):
        self.scroll_until(label, x_scroll)
        field = self.edit_field(label)
        if field is None:
            raise LookupError(f"field not found: {label}")
        x, y = self.center(field)
        self.shell("input", "tap", str(x), str(y))
        time.sleep(2.0)
        field = self.edit_field(label)  # layout may move when the keyboard opens
        current = self.field_text(field, label)
        self.shell("input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(len(current or "") + 2):
            self.shell("input", "keyevent", "KEYCODE_DEL")
        self.shell("input", "text", text.replace(" ", "%s"))
        time.sleep(1.5)
        self.hide_ime()
        field = self.edit_field(label)
        value = self.field_text(field, label)
        if value != text:
            raise AssertionError(f"{label}: expected {text!r}, field shows {value!r}")

    def screenshot(self, name):
        (OUT / name).write_bytes(self.adb("exec-out", "screencap", "-p", binary=True))
        return name

    def prefs_json(self):
        raw = self.shell("run-as", PACKAGE, "cat", "shared_prefs/safeflight.xml", check=False)
        match = re.search(r'name="connection_profiles_json">(.*)</string>', raw, re.S)
        if not match:
            return None
        import html
        return json.loads(html.unescape(match.group(1)))

    def logcat(self):
        return self.adb("logcat", "-d", "-s", "SafeFlight/MAVLink:*", "SafeFlight/Vídeo:*",
                        "SafeFlight/Control:*", "SafeFlight/Perfiles:*", "SafeFlight/App:*", check=False)

    def launch(self):
        self.shell("am", "start", "-n", ACTIVITY)
        self.find("Vuelo", timeout=60)
        time.sleep(4)


def preseed(dev, video=True):
    """Writes the SITL udp_connect test profile into the debug app preferences."""
    import html
    doc = {"schema_version": 1, "active_profile_id": "sitl", "profiles": [
        {"id": "sitl", "name": "SITL / SIMULACIÓN", "kind": "sitl", "builtin": True,
         "mavlink": {"transport": "udp_connect", "remote_host": "10.0.2.2", "remote_port": 14551,
                     "send_gcs_heartbeat": True},
         "video": {"mode": "rtsp" if video else "none", "rtsp_url": "rtsp://10.0.2.2:18554/test",
                   "rtsp_transport": "tcp"}}]}
    header = "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>"
    value = html.escape(json.dumps(doc, ensure_ascii=False))
    xml = chr(10).join([header, "<map>", f'    <string name="connection_profiles_json">{value}</string>', "</map>", ""])
    local = OUT / "prefs.xml"
    local.write_text(xml, encoding="utf-8")
    dev.shell("am", "force-stop", PACKAGE)
    dev.adb("push", str(local), "/data/local/tmp/safeflight.xml")
    dev.shell(f"run-as {PACKAGE} sh -c 'mkdir -p shared_prefs && "
              "cp /data/local/tmp/safeflight.xml shared_prefs/safeflight.xml'")
    dev.launch()


def step(sid, description):
    entry = {"id": sid, "description": description, "result": "FAIL", "detail": "", "evidence": []}
    results.append(entry)
    print(f"\n[{sid}] {description}", flush=True)
    return entry


def passed(entry, detail):
    entry.update(result="PASS", detail=detail)
    print(f"  PASS {detail}", flush=True)


def failed(entry, detail):
    entry.update(result="FAIL", detail=detail)
    print(f"  FAIL {detail}", flush=True)


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--apk", default=str(ROOT / "dist" / "artifacts" / "SafeFlight-Android-0.3.0-debug.apk"))
    parser.add_argument("--skip-rtsp-outage", action="store_true")
    parser.add_argument("--preseed-profile", action="store_true",
                        help="write the SITL test profile with run-as instead of typing it (slow emulators)")
    parser.add_argument("--no-video", action="store_true",
                        help="profile without video: uiautomator cannot dump the UI while video plays on API 28; "
                             "RTSP on that image is documented with screenshots instead")
    args = parser.parse_args()
    OUT_BASE.mkdir(parents=True, exist_ok=True)
    dev = Device(args.serial)
    sim = TelemetrySimulator("127.0.0.1", 0, rate_hz=4, custom_mode=5, serve_port=14551).start()
    release = dev.shell("getprop", "ro.build.version.release").strip()
    sdk = dev.shell("getprop", "ro.build.version.sdk").strip()
    print(f"Device {args.serial}: Android {release} (API {sdk})")
    OUT = OUT_BASE / f"api{sdk}"
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        e = step("A-01", "Instalación limpia y arranque: valores desconocidos como '—'")
        dev.adb("uninstall", PACKAGE, check=False)
        dev.adb("install", "-r", args.apk, timeout=300)
        dev.adb("logcat", "-c", check=False)
        dev.launch()
        unknown = 0
        for _ in range(10):  # first frame may take a while on software-rendered emulators
            unknown = sum(1 for t in dev.texts() if t == "—")
            if unknown >= 5:
                break
            time.sleep(2)
        e["evidence"].append(dev.screenshot("A-01-arranque.png"))
        passed(e, f"Android {release} (API {sdk}); {unknown} valores '—'") if unknown >= 5 else failed(e, f"{unknown} valores '—'")

        e = step("A-02", "Editar el perfil SITL desde la interfaz (UDP hacia remoto 10.0.2.2:14551) y guardar")
        if args.preseed_profile:
            preseed(dev, video=not args.no_video)
            dev.go("Conexión")
            e.update(result="NOT_RUN", detail="perfil cargado con run-as (--preseed-profile); edición por interfaz no ejercitada")
            print("  NOT_RUN preseeded")
        else:
            dev.go("Conexión")
            dev.tap("SITL / SIMULACIÓN")
            dev.tap("UDP hacia remoto")
            dev.type_into("IP remota", "10.0.2.2", x_scroll=800)
            dev.type_into("Puerto remoto", "14551", x_scroll=800)
            dev.scroll_until("Guardar", 800, max_swipes=8)
            dev.tap("Guardar", settle=3)
            doc = dev.prefs_json()
            sitl = next(p for p in doc["profiles"] if p["id"] == "sitl")
            m = sitl["mavlink"]
            if doc["active_profile_id"] == "sitl" and m["transport"] == "udp_connect" and m["remote_host"] == "10.0.2.2"                     and m["remote_port"] == 14551 and m["send_gcs_heartbeat"]:
                passed(e, "perfil guardado en SharedPreferences: udp_connect 10.0.2.2:14551 con heartbeat de GCS")
            else:
                failed(e, f"perfil guardado: {m}, activo={doc['active_profile_id']}")

        e = step("A-03", "Conectar telemetría desde la pantalla de conexión")
        dev.hide_ime()
        status = None
        for _ in range(3):  # a tap can land while the screen is still settling after saving
            dev.tap("Conectar", settle=6)
            status = dev.wait_text(lambda t: t == "CONECTADO", timeout=15)
            if status:
                break
        e["evidence"].append(dev.screenshot("A-03-conexion.png"))
        passed(e, "estado CONECTADO") if status else failed(e, "sin CONECTADO")

        e = step("A-04", "Pantalla de vuelo: telemetría y vídeo RTSP")
        dev.go("Vuelo")
        mode = dev.wait_text(lambda t: t == "MODO LOITER", timeout=20)
        live = "sin vídeo (--no-video)" if args.no_video else dev.wait_text(lambda t: t == "VÍDEO EN DIRECTO", timeout=60)
        e["evidence"].append(dev.screenshot("A-04-vuelo.png"))
        passed(e, f"'{mode}', '{live}'") if mode and live else failed(e, f"modo={mode}, vídeo={live}")

        e = step("A-05", "Pérdida de telemetría (STALE → LOST) y recuperación")
        dev.adb("logcat", "-c", check=False)
        sim.pause(True)
        lost = dev.wait_text(lambda t: "PÉRDIDA DE TELEMETRÍA" in t, timeout=40)
        e["evidence"].append(dev.screenshot("A-05-perdida.png"))
        sim.pause(False)
        back = dev.wait_text(lambda t: t == "MAVLINK CONECTADO", timeout=30)
        # The STALE window (3-9 s) is shorter than a UI dump cycle: verified from the app log.
        log = dev.logcat()
        stale = "Telemetría obsoleta" in log
        lost_log = "Pérdida de telemetría" in log
        recovered = "Heartbeat del vehículo recibido" in log
        if lost and back and stale and lost_log and recovered:
            passed(e, "log: obsoleta → pérdida → heartbeat recibido; pantalla: banner de pérdida → CONECTADO")
        else:
            failed(e, f"banner={lost}, vuelta={back}, log stale/lost/recovered={stale}/{lost_log}/{recovered}")

        e = step("A-06", "Caída y vuelta del servidor RTSP: recuperación automática del vídeo")
        if args.skip_rtsp_outage or args.no_video:
            e.update(result="NOT_RUN", detail="omitido por opción")
        else:
            subprocess.run(["docker", "stop", "safeflight-rtsp-test"], capture_output=True)
            down = dev.wait_text(lambda t: t in ("VÍDEO SIN SEÑAL", "VÍDEO CONECTANDO", "VÍDEO CONGELADO"), timeout=30)
            time.sleep(8)
            subprocess.run(["docker", "start", "safeflight-rtsp-test"], capture_output=True)
            back = dev.wait_text(lambda t: t == "VÍDEO EN DIRECTO", timeout=90)
            passed(e, f"'{down}' → '{back}'") if down and back else failed(e, f"down={down}, back={back}")

        e = step("A-07", "Ciclo de vida: HOME libera el decodificador; al volver se reanuda")
        dev.shell("input", "keyevent", "KEYCODE_HOME")
        time.sleep(5)
        stopped = args.no_video or "Reproducción detenida" in dev.logcat()
        dev.launch()
        live = True if args.no_video else dev.wait_text(lambda t: t == "VÍDEO EN DIRECTO", timeout=60)
        hb = dev.wait_text(lambda t: t == "MAVLINK CONECTADO", timeout=20)
        passed(e, "decodificador liberado y reanudado; telemetría continua") if stopped and live and hb \
            else failed(e, f"stopped={stopped}, live={live}, mavlink={hb}")

        e = step("A-08", "Persistencia: forzar cierre y reabrir conserva el perfil editado")
        dev.shell("am", "force-stop", PACKAGE)
        time.sleep(2)
        dev.launch()
        dev.go("Conexión")
        hint = dev.wait_text(lambda t: t == "UDP hacia remoto", timeout=10)
        doc = dev.prefs_json()
        m = next(p for p in doc["profiles"] if p["id"] == "sitl")["mavlink"]
        ok = doc["active_profile_id"] == "sitl" and m["remote_host"] == "10.0.2.2" and m["remote_port"] == 14551
        passed(e, "perfil SITL editado conservado tras force-stop") if ok and hint else failed(e, f"{m}")

        e = step("A-09", "Controles bloqueados: ARM se rechaza con motivo y no se envía comando")
        dev.tap("Conectar", settle=6)
        dev.go("Vuelo")
        for _ in range(3):
            dev.shell("input", "swipe", "2000", "950", "2000", "150", "600")
            time.sleep(1)
        time.sleep(2)  # let the scroll settle before tapping
        snack = None
        for _ in range(3):
            dev.tap("🔒 ARM", settle=1.0)
            snack = dev.wait_text(lambda t: t.startswith("ARM no disponible"), timeout=8)
            if snack:
                break
        e["evidence"].append(dev.screenshot("A-09-arm-bloqueado.png"))
        logged = "ARM rechazado" in dev.logcat()
        passed(e, snack) if snack and logged else failed(e, f"snackbar={snack}, log={logged}")

        e = step("A-11", "Restablecer configuración: Cancelar no cambia nada; Restablecer recupera el perfil de fábrica")
        dev.go("Conexión")
        dev.scroll_until("Restablecer configuración", 800, max_swipes=8)
        dev.tap("Restablecer configuración", settle=2)
        dialog = dev.wait_text(lambda t: t == "¿Restablecer la configuración?", timeout=10)
        dev.tap("Cancelar", settle=2)
        after_cancel = next(p for p in dev.prefs_json()["profiles"] if p["id"] == "sitl")["mavlink"]
        dev.tap("Restablecer configuración", settle=2)
        dev.tap("Restablecer", settle=3)
        doc = dev.prefs_json()
        after_reset = next(p for p in doc["profiles"] if p["id"] == "sitl")["mavlink"]
        others = sorted(p["id"] for p in doc["profiles"])
        ok_reset = (dialog and after_cancel["transport"] == "udp_connect"
                    and after_reset["transport"] == "udp_listen" and after_reset["local_port"] == 14550
                    and "siyi-local" in others and "raspberry-lab" in others)
        e["evidence"].append(dev.screenshot("A-11-restablecer.png"))
        passed(e, f"diálogo='{dialog}'; tras Cancelar={after_cancel['transport']}; "
                  f"tras Restablecer={after_reset['transport']}:{after_reset['local_port']}; perfiles={others}")             if ok_reset else failed(e, f"dialog={dialog} cancel={after_cancel} reset={after_reset}")

        e = step("A-10", "Pantalla de misiones identifica los datos como demostración")
        dev.go("Misiones")
        banner = dev.wait_text(lambda t: t.startswith("DATOS DE DEMOSTRACIÓN"), timeout=10)
        e["evidence"].append(dev.screenshot("A-10-misiones.png"))
        passed(e, "banner presente") if banner else failed(e, "sin banner")
    except Exception as exc:
        results[-1].update(result="FAIL", detail=f"{type(exc).__name__}: {exc}")
        print(f"  FAIL {type(exc).__name__}: {exc}")
        try:
            dev.screenshot(f"{results[-1]['id']}-error.png")
        except Exception:
            pass
    finally:
        sim.stop()
    report = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "device": f"Android {release} (API {sdk})",
              "apk": args.apk, "steps": results}
    name = "report.json"
    (OUT / name).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = sum(r["result"] == "PASS" for r in results)
    print(f"\n{ok}/{len(results)} steps passed. Report: {OUT / name}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
