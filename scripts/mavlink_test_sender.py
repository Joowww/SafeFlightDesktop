#!/usr/bin/env python3
"""Synthetic MAVLink telemetry source for tests without hardware.

Emits the telemetry subset used by SafeFlight (HEARTBEAT, SYS_STATUS,
GLOBAL_POSITION_INT, VFR_HUD, GPS_RAW_INT, STATUSTEXT) to a UDP endpoint,
impersonating an ArduCopter vehicle (sysid 1, compid 1).

It is a test fixture only:
  * it never forwards anything to a real vehicle;
  * it ignores every message it receives (commands are never executed);
  * all values are synthetic and labelled as such in STATUSTEXT.

Examples::

    # Desktop, profile "SITL / SIMULACIÓN" (udpin:0.0.0.0:14560)
    python scripts/mavlink_test_sender.py --target 127.0.0.1:14560

    # Android emulator listening on UDP 14550 (after `adb emu redir add udp:14550:14550`)
    python scripts/mavlink_test_sender.py --target 127.0.0.1:14550

    # Server mode for GCS profiles using udp_connect (e.g. Android emulator -> 10.0.2.2:14551)
    python scripts/mavlink_test_sender.py --serve 14551

    # Link-loss scenario: heartbeat stops after 10 s for 8 s, then resumes
    python scripts/mavlink_test_sender.py --target 127.0.0.1:14560 --drop-after 10 --drop-for 8
"""

from __future__ import annotations

import argparse
import math
import socket
import sys
import threading
import time

from pymavlink.dialects.v20 import ardupilotmega as mavlink2


class _UdpWriter:
    def __init__(self, sock: socket.socket, target):
        self.sock = sock
        self.target = target

    def write(self, data: bytes) -> None:
        try:
            self.sock.sendto(data, self.target)
        except OSError:
            pass


class TelemetrySimulator:
    """Thread that sends synthetic telemetry at ``rate_hz``."""

    def __init__(self, host: str, port: int, rate_hz: float = 4.0,
                 drop_after: float = None, drop_for: float = 0.0,
                 armed: bool = False, custom_mode: int = 0, serve_port: int = None):
        # In serve mode the target is unknown until a GCS sends a datagram.
        self.target = (host, port) if serve_port is None else None
        self.rate_hz = rate_hz
        self.drop_after = drop_after
        self.drop_for = drop_for
        self.armed = armed
        self.custom_mode = custom_mode
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if serve_port is not None:
            self.sock.bind(("0.0.0.0", serve_port))
        self.sock.setblocking(False)
        self._writer = _UdpWriter(self.sock, self.target)
        self.mav = mavlink2.MAVLink(self._writer, srcSystem=1, srcComponent=1)
        self._parser = mavlink2.MAVLink(None)
        self._parser.robust_parsing = True
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="mavlink-test-sender", daemon=True)
        self.sent_heartbeats = 0
        self.paused = False
        # Everything received from the GCS, for negative tests ("TYPE" or "COMMAND_LONG:<id>").
        self.received = {}

    def start(self) -> "TelemetrySimulator":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self.sock.close()

    def pause(self, value: bool = True) -> None:
        self.paused = value

    def _drain_incoming(self) -> None:
        """Read GCS traffic. Commands are discarded and never executed.

        The only reply is to PARAM_REQUEST_LIST, with one synthetic
        read-only parameter: DroneKit blocks ``connect()`` until the
        initial parameter download has started, as with a real autopilot.
        """
        while True:
            try:
                data, addr = self.sock.recvfrom(4096)
            except (BlockingIOError, OSError):
                return
            if self.target is None or self._writer.target is None or addr != self._writer.target:
                if self.target is None:
                    print(f"GCS registered from {addr[0]}:{addr[1]}", flush=True)
                self.target = addr
                self._writer.target = addr
            try:
                messages = self._parser.parse_buffer(data) or []
            except Exception:
                continue
            for msg in messages:
                key = msg.get_type()
                if key == "COMMAND_LONG":
                    key = f"COMMAND_LONG:{msg.command}"
                self.received[key] = self.received.get(key, 0) + 1
                if msg.get_type() == "PARAM_REQUEST_LIST" and not self.paused:
                    self.mav.param_value_send(b"SIM_TEST_PARAM", 1.0,
                                              mavlink2.MAV_PARAM_TYPE_REAL32, 1, 0)

    def _run(self) -> None:
        start = time.monotonic()
        tick = 0
        base_lat, base_lon = 41.3874, 2.1686
        while not self._stop.is_set():
            elapsed = time.monotonic() - start
            dropped = (
                self.drop_after is not None
                and self.drop_after <= elapsed < self.drop_after + self.drop_for
            )
            self._drain_incoming()
            if not dropped and not self.paused and self.target is not None:
                self._send_cycle(tick, elapsed, base_lat, base_lon)
            tick += 1
            self._stop.wait(1.0 / self.rate_hz)

    def _send_cycle(self, tick, elapsed, base_lat, base_lon) -> None:
        mav = self.mav
        base_mode = mavlink2.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        if self.armed:
            base_mode |= mavlink2.MAV_MODE_FLAG_SAFETY_ARMED
        status = mavlink2.MAV_STATE_ACTIVE if self.armed else mavlink2.MAV_STATE_STANDBY
        mav.heartbeat_send(mavlink2.MAV_TYPE_QUADROTOR, mavlink2.MAV_AUTOPILOT_ARDUPILOTMEGA,
                           base_mode, self.custom_mode, status, 3)
        self.sent_heartbeats += 1

        angle = elapsed / 20.0
        lat = base_lat + 0.0002 * math.sin(angle)
        lon = base_lon + 0.0002 * math.cos(angle)
        rel_alt_mm = int(10000 + 2000 * math.sin(elapsed / 5.0))
        heading_cdeg = int((math.degrees(angle) % 360) * 100)
        voltage_mv = int(16000 - min(elapsed, 600) * 2)
        remaining = max(0, 90 - int(elapsed / 20))

        mav.sys_status_send(0, 0, 0, 450, voltage_mv, 1100, remaining, 0, 0, 0, 0, 0, 0)
        mav.global_position_int_send(int(elapsed * 1000) & 0xFFFFFFFF, int(lat * 1e7), int(lon * 1e7),
                                     rel_alt_mm + 140000, rel_alt_mm, 100, 50, 0, heading_cdeg)
        mav.vfr_hud_send(2.1, 2.0, heading_cdeg // 100, 35, rel_alt_mm / 1000.0, 0.1)
        mav.gps_raw_int_send(int(elapsed * 1e6), 3, int(lat * 1e7), int(lon * 1e7), rel_alt_mm + 140000,
                             80, 120, 200, heading_cdeg, 12)
        if tick % max(1, int(self.rate_hz * 10)) == 0:
            mav.statustext_send(mavlink2.MAV_SEVERITY_INFO, b"SIMULATED telemetry (test sender)")


def _parse_target(value: str):
    host, _, port = value.rpartition(":")
    if not host or not port.isdigit():
        raise argparse.ArgumentTypeError("target must be HOST:PORT")
    return host, int(port)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", type=_parse_target, default=("127.0.0.1", 14560))
    parser.add_argument("--serve", type=int, default=None, metavar="PORT",
                        help="bind UDP PORT and send to whoever sends to it (GCS 'udp_connect' mode)")
    parser.add_argument("--rate", type=float, default=4.0, help="cycles per second (default 4)")
    parser.add_argument("--duration", type=float, default=0, help="seconds to run (0 = until Ctrl+C)")
    parser.add_argument("--drop-after", type=float, default=None, help="stop sending after N seconds")
    parser.add_argument("--drop-for", type=float, default=0.0, help="silence duration in seconds")
    parser.add_argument("--armed", action="store_true", help="report armed state (display test only)")
    parser.add_argument("--mode", type=int, default=0, help="ArduCopter custom_mode to report")
    args = parser.parse_args(argv)

    sim = TelemetrySimulator(*args.target, rate_hz=args.rate, drop_after=args.drop_after,
                             drop_for=args.drop_for, armed=args.armed, custom_mode=args.mode,
                             serve_port=args.serve).start()
    where = f"UDP server :{args.serve} (waiting for a GCS)" if args.serve else f"{args.target[0]}:{args.target[1]}"
    print(f"Sending synthetic MAVLink to {where} at {args.rate:g} Hz (Ctrl+C to stop)", flush=True)
    try:
        deadline = time.monotonic() + args.duration if args.duration else None
        while deadline is None or time.monotonic() < deadline:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()
    print(f"Stopped after {sim.sent_heartbeats} heartbeats.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
