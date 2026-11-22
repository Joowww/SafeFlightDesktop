#!/usr/bin/env python3
"""Focused emulator check of profile editing and "Restablecer configuración" (SafeFlight Android).

Designed for the API 28 image (Android 9, as the SIYI MK32): uiautomator cannot
dump the UI while video plays or a telemetry counter keeps redrawing, so the
SITL profile is preseeded without video and nothing is connected.

  P-01 edit the SITL profile in the UI (UDP hacia remoto 10.0.2.2:14551) and save
  P-02 "Restablecer configuración" → Cancelar: stored data unchanged
  P-03 "Restablecer configuración" → Restablecer: SITL back to factory values
  P-04 the other profiles (SIYI, 5G/VPN, RASPBERRY / CUBE) are unchanged

    python tests/gui/android_profile_edit_validation.py --apk <apk>
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import android_emulator_validation as a  # noqa: E402


def preseed_without_video(dev):
    doc = {"schema_version": 1, "active_profile_id": "sitl", "profiles": [
        {"id": "sitl", "name": "SITL / SIMULACIÓN", "kind": "sitl", "builtin": True,
         "video": {"mode": "none", "rtsp_url": "rtsp://10.0.2.2:18554/test", "rtsp_transport": "tcp"}}]}
    value = html.escape(json.dumps(doc, ensure_ascii=False))
    xml = "\n".join(["<?xml version='1.0' encoding='utf-8' standalone='yes' ?>", "<map>",
                     f'    <string name="connection_profiles_json">{value}</string>', "</map>", ""])
    local = a.OUT / "prefs-novideo.xml"
    local.write_text(xml, encoding="utf-8")
    dev.shell("am", "force-stop", a.PACKAGE)
    dev.adb("push", str(local), "/data/local/tmp/safeflight.xml")
    dev.shell(f"run-as {a.PACKAGE} sh -c 'mkdir -p shared_prefs && "
              "cp /data/local/tmp/safeflight.xml shared_prefs/safeflight.xml'")
    dev.launch()


def tap_xy(dev, xy, settle=2.0):
    dev.shell("input", "tap", str(xy[0]), str(xy[1]))
    time.sleep(settle)


def replace_text(dev, xy, text):
    """Focus a field by coordinates and replace its content (no UI dump needed)."""
    tap_xy(dev, xy)
    dev.shell("input", "keyevent", "KEYCODE_MOVE_END")
    for _ in range(25):
        dev.shell("input", "keyevent", "KEYCODE_DEL")
    dev.shell("input", "text", text)
    time.sleep(1)


def positions(dev, labels, fields):
    """Screen positions taken while the UI is idle (a focused field blocks uiautomator on API 28)."""
    pos = {label: dev.center(dev.find(label)) for label in labels}
    for label in fields:
        node = dev.edit_field(label)
        if node is None:
            raise LookupError(f"field not found: {label}")
        pos[label] = dev.center(node)
    return pos


def profiles(dev):
    return {p["id"]: p for p in dev.prefs_json()["profiles"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--apk", required=True)
    args = parser.parse_args()
    dev = a.Device(args.serial)
    sdk = dev.shell("getprop", "ro.build.version.sdk").strip()
    a.OUT = a.OUT_BASE / f"api{sdk}-perfiles"
    a.OUT.mkdir(parents=True, exist_ok=True)
    step, passed, failed = a.step, a.passed, a.failed
    try:
        dev.adb("uninstall", a.PACKAGE, check=False)
        dev.adb("install", "-r", args.apk, timeout=300)
        dev.launch()
        preseed_without_video(dev)
        dev.go("Conexión")
        before = profiles(dev)

        e = step("P-01", "Editar el perfil SITL en la interfaz (UDP hacia remoto 10.0.2.2:14551) y guardar")
        dev.tap("SITL / SIMULACIÓN")
        dev.tap("UDP hacia remoto")
        pos = positions(dev, ["Guardar", "Restablecer configuración"], ["IP remota", "Puerto remoto"])
        replace_text(dev, pos["IP remota"], "10.0.2.2")
        replace_text(dev, pos["Puerto remoto"], "14551")
        dev.hide_ime()
        e["evidence"].append(dev.screenshot("P-01-editado.png"))
        tap_xy(dev, pos["Guardar"], settle=3)
        saved = profiles(dev)
        m = saved["sitl"]["mavlink"]
        e["evidence"].append(dev.screenshot("P-01-guardado.png"))
        if m["transport"] == "udp_connect" and m["remote_host"] == "10.0.2.2" and m["remote_port"] == 14551:
            passed(e, "guardado en SharedPreferences: udp_connect 10.0.2.2:14551")
        else:
            failed(e, f"guardado: {m}")

        e = step("P-02", "Restablecer configuración → Cancelar: los datos guardados no cambian")
        tap_xy(dev, pos["Restablecer configuración"])
        dialog = dev.wait_text(lambda t: t == "¿Restablecer la configuración?", timeout=20)
        e["evidence"].append(dev.screenshot("P-02-dialogo.png"))
        dev.tap("Cancelar", settle=2)
        after_cancel = profiles(dev)
        passed(e, f"diálogo '{dialog}'; perfiles idénticos tras Cancelar") if dialog and after_cancel == saved \
            else failed(e, f"dialog={dialog}, cambiado={after_cancel != saved}")

        e = step("P-03", "Restablecer configuración → Restablecer: SITL vuelve a fábrica")
        tap_xy(dev, pos["Restablecer configuración"])
        dev.wait_text(lambda t: t == "¿Restablecer la configuración?", timeout=20)
        dev.tap("Restablecer", settle=3)
        after_reset = profiles(dev)
        m = after_reset["sitl"]["mavlink"]
        e["evidence"].append(dev.screenshot("P-03-restablecido.png"))
        passed(e, f"SITL: {m['transport']} {m['local_host']}:{m['local_port']}, heartbeat GCS={m['send_gcs_heartbeat']}") \
            if m["transport"] == "udp_listen" and m["local_port"] == 14550 else failed(e, f"SITL tras restablecer: {m}")

        e = step("P-04", "Los demás perfiles no cambian")
        others = [pid for pid in before if pid != "sitl"]
        changed = [pid for pid in others if after_reset.get(pid) != before[pid]]
        passed(e, f"sin cambios: {others}") if others and not changed and "raspberry-lab" in others \
            else failed(e, f"perfiles={others}, cambiados={changed}")
    except Exception as exc:
        a.results[-1].update(result="FAIL", detail=f"{type(exc).__name__}: {exc}") if a.results else None
        print(f"  FAIL {type(exc).__name__}: {exc}")
    ok = sum(1 for r in a.results if r["result"] == "PASS")
    (a.OUT / "report.json").write_text(json.dumps({"device": f"API {sdk}", "steps": a.results}, indent=2,
                                                  ensure_ascii=False), encoding="utf-8")
    print(f"\n{ok}/{len(a.results)} steps passed. Report: {a.OUT / 'report.json'}")
    return 0 if a.results and ok == len(a.results) else 1


if __name__ == "__main__":
    sys.exit(main())
