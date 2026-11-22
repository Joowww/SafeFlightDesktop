#!/usr/bin/env python3
"""RTSP validation of a packaged SafeFlight Desktop build with the RASPBERRY / CUBE (LAB) profile.

Uses only local sources: the RTSP test server (Docker, port 18554), the RTP
test pattern and synthetic telemetry. No Raspberry Pi or autopilot is
contacted. Isolated configuration and log directories.

The script never moves the mouse nor types: the profile is prepared in the
isolated configuration before each launch and buttons are pressed through UI
Automation "Invoke", so it can run while the desktop is in use.

  R-01 RASPBERRY / CUBE (LAB) with video RTSP: CONNECT, telemetry, monitor-only state
  R-02 RTSP frames: resolution, FPS and frame age
  R-03 RTSP server down and up: SIGNAL LOST and automatic recovery (MAVLink unaffected)
  R-04 MAVLink and CommandGuard unaffected (no command sent by the GCS)
  R-05 relaunch with the same profile in RTP/UDP 5004: video from RTP
  R-06 close the window: exit code 0

    python tests/gui/desktop_rtsp_validation.py --exe <path to SafeFlightDesktop.exe>
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import desktop_gui_validation as g  # noqa: E402
from desktop_gui_validation import Step  # noqa: E402

sys.path.insert(0, str(g.ROOT))
from models.ConnectionProfiles import ProfileStore  # noqa: E402

PROFILE_ID = "raspberry-lab"
MAVLINK_PORT = 14560
RTP_PORT = 5004
RTSP_URL = "rtsp://127.0.0.1:18554/test"
# MAV_CMD 511/512/519/520 are read-only requests (message interval / capabilities) that
# CommandGuard allows; DroneKit repeats 520 while the synthetic sender does not answer it.
READ_ONLY_COMMANDS = {"COMMAND_LONG:511", "COMMAND_LONG:512", "COMMAND_LONG:519", "COMMAND_LONG:520"}
COMMAND_TYPES = ("COMMAND_LONG", "COMMAND_INT", "SET_MODE", "SET_POSITION_TARGET", "MANUAL_CONTROL",
                 "RC_CHANNELS_OVERRIDE", "MISSION_ITEM", "PARAM_SET")


def prepare_profile(mode):
    """Activates raspberry-lab in the isolated config; only the video mode / RTSP URL change."""
    store = ProfileStore(config_dir=g.CONFIG_DIR, environ={}).load()
    profile = store.get(PROFILE_ID).copy()
    profile.video.mode = mode
    if mode == "rtsp":
        profile.video.rtsp_url = RTSP_URL
    store.upsert(profile)
    store.select(PROFILE_ID)
    store.save()


def metrics(gui):
    text = gui.wait_text(lambda t: t.startswith("RX ") and "FPS" in t, timeout=5) or ""
    m = re.match(r"RX ([\d.]+) FPS\s+\|\s+AGE (\d+|--) ms", text)
    return (float(m.group(1)), None if m.group(2) == "--" else int(m.group(2))) if m else None


def live_metrics(gui, samples=5):
    seen = []
    for _ in range(samples):
        m = metrics(gui)
        if m and m[0] > 0:
            seen.append(m)
        time.sleep(1)
    return max(seen, key=lambda m: m[0]) if seen else None


def console_text():
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(g.WORK.glob("console-*.txt")))


def kill_tree(gui):
    if gui and gui.proc.poll() is None:  # also stops the Flutter client child processes
        subprocess.run(["taskkill", "/PID", str(gui.proc.pid), "/T", "/F"], capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    args = parser.parse_args()
    exe = Path(args.exe)
    g.EXE, g.EXE_DIR = exe, exe.parent
    g.OUT = g.ROOT / "build" / "gui-rtsp-evidence"
    g.WORK = g.ROOT / "build" / "gui-rtsp-test"
    g.CONFIG_DIR, g.LOG_DIR = g.WORK / "config", g.WORK / "logs"
    for d in (g.OUT, g.WORK):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    if not g.rtsp_available():
        print("RTSP test server not available on 18554")
        return 2

    sim = rtp = gui = None
    try:
        s = Step("R-01", "Perfil RASPBERRY / CUBE (LAB) con vídeo RTSP: CONNECT, telemetría, solo monitorización")
        prepare_profile("rtsp")
        gui = g.launch()
        gui.open_sidebar_if_closed()
        mav = gui.edit_value("MAVLink")
        src = gui.wait_text(lambda t: t.startswith("Fuente en uso: RTSP"), timeout=10)
        # The synthetic sender starts once the app is up, as in desktop_gui_validation.py.
        sim = g.TelemetrySimulator("127.0.0.1", MAVLINK_PORT, rate_hz=8, custom_mode=5).start()
        gui.invoke("CONNECT")
        ok = gui.wait_text(lambda t: t.startswith("MAVLink: OK"), timeout=120)
        guard = gui.wait_text(lambda t: t.startswith("SOLO MONITORIZACIÓN"), timeout=10)
        s.ok(f"MAVLink={mav}; '{src}'; '{ok}'; '{guard}'") \
            if mav == f"udpin:0.0.0.0:{MAVLINK_PORT}" and src and ok and guard \
            else s.fail(f"mavlink={mav}, src={src}, ok={ok}, guard={guard}")

        s = Step("R-02", "Vídeo RTSP: fotogramas, resolución, FPS y antigüedad")
        live = gui.wait_text(lambda t: t == "● CAMERA LIVE", timeout=60)
        m = live_metrics(gui)
        res = re.findall(r"Se.al recibida: (\d+x\d+)", console_text())  # console is not UTF-8
        s.ok(f"'{live}'; resolución {res[-1]}; RX {m[0]:.1f} FPS; AGE {m[1]} ms") \
            if live and m and m[0] >= 10 and res else s.fail(f"live={live}, metrics={m}, res={res}")

        s = Step("R-03", "Caída del servidor RTSP y recuperación automática; MAVLink sigue activo")
        subprocess.run(["docker", "stop", "safeflight-rtsp-test"], capture_output=True)
        lost = gui.wait_text(lambda t: t == "● SIGNAL LOST", timeout=30)
        mav_during = gui.wait_text(lambda t: t.startswith("MAVLink: OK"), timeout=5)
        time.sleep(5)
        subprocess.run(["docker", "start", "safeflight-rtsp-test"], capture_output=True)
        t0 = time.monotonic()
        back = gui.wait_text(lambda t: t == "● CAMERA LIVE", timeout=90)
        took = time.monotonic() - t0
        m = live_metrics(gui, samples=3)
        s.ok(f"'{lost}' (MAVLink durante la caída: '{mav_during}') → '{back}' {took:.0f} s tras arrancar el "
             f"servidor; RX {m[0]:.1f} FPS") if lost and back and mav_during and m \
            else s.fail(f"lost={lost}, back={back}, mavlink={mav_during}, m={m}")

        s = Step("R-04", "MAVLink y CommandGuard no se ven afectados por el vídeo")
        ok = gui.wait_text(lambda t: t.startswith("MAVLink: OK"), timeout=10)
        guard = gui.wait_text(lambda t: t.startswith("SOLO MONITORIZACIÓN"), timeout=10)
        sent = {k: v for k, v in sim.received.items()
                if k.startswith(COMMAND_TYPES) and k not in READ_ONLY_COMMANDS}
        s.ok(f"'{ok}'; '{guard}'; recibido del GCS: {sorted(sim.received)}; ningún comando de control") \
            if ok and guard and not sent else s.fail(f"mavlink={ok}, guard={guard}, comandos={sent}")
        gui.close()
        gui.proc.wait(timeout=30)
        sim.stop()
        sim = None
        time.sleep(3)

        s = Step("R-05", "Mismo perfil en RTP/UDP 5004 (relanzado): vídeo RTP")
        prepare_profile("rtp_udp")
        rtp = g.RtpTestSender(port=RTP_PORT, width=1280, height=720, fps=25).start()
        gui = g.launch()
        gui.open_sidebar_if_closed()
        src = gui.wait_text(lambda t: t.startswith("Fuente en uso: RTP"), timeout=10)
        sim = g.TelemetrySimulator("127.0.0.1", MAVLINK_PORT, rate_hz=8, custom_mode=5).start()
        gui.invoke("CONNECT")
        live = gui.wait_text(lambda t: t == "● CAMERA LIVE", timeout=40)
        ok = gui.wait_text(lambda t: t.startswith("MAVLink: OK"), timeout=120)
        m = live_metrics(gui)
        s.ok(f"'{src}' → '{live}'; RX {m[0]:.1f} FPS; '{ok}'") if src and live and m and ok \
            else s.fail(f"src={src}, live={live}, m={m}, mavlink={ok}")

        s = Step("R-06", "Cerrar la ventana")
        gui.close()
        gui.proc.wait(timeout=30)
        s.ok(f"código de salida {gui.proc.returncode}") if gui.proc.returncode == 0 \
            else s.fail(f"código {gui.proc.returncode}")
    except Exception as exc:
        Step.results[-1].update(result="FAIL", detail=f"{type(exc).__name__}: {exc}")
        print(f"  FAIL {type(exc).__name__}: {exc}")
    finally:
        if sim:
            sim.stop()
        if rtp:
            rtp.stop()
        kill_tree(gui)
        subprocess.run(["docker", "start", "safeflight-rtsp-test"], capture_output=True)

    passed = sum(1 for r in Step.results if r["result"] == "PASS")
    (g.OUT / "report.json").write_text(json.dumps({"exe": str(exe), "steps": Step.results}, indent=2,
                                                  ensure_ascii=False), encoding="utf-8")
    print(f"\n{passed}/{len(Step.results)} steps passed. Report: {g.OUT / 'report.json'}")
    return 0 if passed == len(Step.results) else 1


if __name__ == "__main__":
    sys.exit(main())
