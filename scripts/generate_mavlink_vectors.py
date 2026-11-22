#!/usr/bin/env python3
"""Generate the shared MAVLink interoperability vectors.

The vectors are real MAVLink frames encoded with pymavlink (the library used
by SafeFlight Desktop) together with the values every SafeFlight client must
derive from them, as defined in ``shared/protocols/mavlink-telemetry-contract.md``.

SafeFlight Desktop and SafeFlight Android both run their unit tests against
``shared/protocols/mavlink-test-vectors.json``. Regenerate it with::

    python scripts/generate_mavlink_vectors.py

The output is deterministic (fixed sequence numbers and values).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pymavlink.dialects.v10 import ardupilotmega as mavlink1
from pymavlink.dialects.v20 import ardupilotmega as mavlink2

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "shared" / "protocols" / "mavlink-test-vectors.json"

UINT16_MAX = 65535


class _Sink:
    def write(self, data):  # pymavlink requires a file-like object
        pass


def _encoder(sysid=1, compid=1, v1=False):
    dialect = mavlink1 if v1 else mavlink2
    return dialect.MAVLink(_Sink(), srcSystem=sysid, srcComponent=compid)


def _pack(mav, msg, seq):
    mav.seq = seq
    return msg.pack(mav).hex()


def build_vectors():
    vectors = []
    m2 = _encoder()

    m1 = _encoder(v1=True)

    def add(name, msg, expected, seq, v1=False, note="", mav=None):
        mav = mav or (m1 if v1 else m2)
        if v1:
            # Re-encode the same fields with the MAVLink 1 dialect.
            msg = getattr(mavlink1, type(msg).__name__)(*[getattr(msg, f) for f in msg.get_fieldnames()])
        vectors.append({
            "name": name,
            "mavlink_version": 1 if v1 else 2,
            "msg_id": msg.get_msgId(),
            "msg_name": msg.get_type(),
            "frame_hex": _pack(mav, msg, seq),
            "expected": expected,
            "note": note,
        })

    base_armed = mavlink2.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED | mavlink2.MAV_MODE_FLAG_SAFETY_ARMED
    base_disarmed = mavlink2.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED

    add("heartbeat_disarmed_stabilize",
        m2.heartbeat_encode(mavlink2.MAV_TYPE_QUADROTOR, mavlink2.MAV_AUTOPILOT_ARDUPILOTMEGA,
                            base_disarmed, 0, mavlink2.MAV_STATE_STANDBY, 3),
        {"system_id": 1, "component_id": 1, "armed": False, "custom_mode": 0,
         "flight_mode": "STABILIZE", "vehicle_type": 2, "autopilot": 3, "system_status": 3,
         "is_vehicle": True}, seq=0)

    add("heartbeat_armed_guided",
        m2.heartbeat_encode(mavlink2.MAV_TYPE_QUADROTOR, mavlink2.MAV_AUTOPILOT_ARDUPILOTMEGA,
                            base_armed, 4, mavlink2.MAV_STATE_ACTIVE, 3),
        {"system_id": 1, "component_id": 1, "armed": True, "custom_mode": 4,
         "flight_mode": "GUIDED", "vehicle_type": 2, "autopilot": 3, "system_status": 4,
         "is_vehicle": True}, seq=1)

    add("heartbeat_land_v1",
        m2.heartbeat_encode(mavlink2.MAV_TYPE_QUADROTOR, mavlink2.MAV_AUTOPILOT_ARDUPILOTMEGA,
                            base_armed, 9, mavlink2.MAV_STATE_ACTIVE, 3),
        {"system_id": 1, "component_id": 1, "armed": True, "custom_mode": 9,
         "flight_mode": "LAND", "vehicle_type": 2, "autopilot": 3, "system_status": 4,
         "is_vehicle": True}, seq=2, v1=True, note="MAVLink v1 framing (0xFE)")

    add("heartbeat_unknown_mode",
        m2.heartbeat_encode(mavlink2.MAV_TYPE_QUADROTOR, mavlink2.MAV_AUTOPILOT_ARDUPILOTMEGA,
                            base_disarmed, 99, mavlink2.MAV_STATE_STANDBY, 3),
        {"system_id": 1, "component_id": 1, "armed": False, "custom_mode": 99,
         "flight_mode": "UNKNOWN(99)", "vehicle_type": 2, "autopilot": 3, "system_status": 3,
         "is_vehicle": True}, seq=3, note="Unknown custom modes must not be shown as a valid mode")

    gcs = _encoder(sysid=255, compid=190)
    add("heartbeat_from_gcs_is_ignored",
        gcs.heartbeat_encode(mavlink2.MAV_TYPE_GCS, mavlink2.MAV_AUTOPILOT_INVALID, 0, 0, 0, 3),
        {"system_id": 255, "component_id": 190, "armed": False, "custom_mode": 0,
         "flight_mode": None, "vehicle_type": 6, "autopilot": 8, "system_status": 0,
         "is_vehicle": False}, seq=4,
        note="A GCS heartbeat must not update vehicle state nor count as vehicle link", mav=gcs)

    add("sys_status_battery",
        m2.sys_status_encode(0, 0, 0, 500, 15800, 1230, 76, 0, 0, 0, 0, 0, 0),
        {"battery_voltage_v": 15.8, "battery_current_a": 12.3, "battery_remaining_pct": 76}, seq=5)

    add("sys_status_battery_unknown",
        m2.sys_status_encode(0, 0, 0, 500, UINT16_MAX, -1, -1, 0, 0, 0, 0, 0, 0),
        {"battery_voltage_v": None, "battery_current_a": None, "battery_remaining_pct": None},
        seq=6, note="UINT16_MAX voltage and -1 current/remaining mean 'unknown'")

    add("global_position_int",
        m2.global_position_int_encode(123456, 413874000, 21686000, 152340, 12500, 150, -250, 30, 27050),
        {"lat_deg": 41.3874, "lon_deg": 2.1686, "alt_msl_m": 152.34, "relative_alt_m": 12.5,
         "heading_deg": 270.5}, seq=7)

    add("global_position_int_no_heading",
        m2.global_position_int_encode(123457, 0, 0, 0, 0, 0, 0, 0, UINT16_MAX),
        {"lat_deg": None, "lon_deg": None, "alt_msl_m": 0.0, "relative_alt_m": 0.0,
         "heading_deg": None},
        seq=8, note="lat=lon=0 is treated as 'no position'; hdg UINT16_MAX means unknown")

    add("vfr_hud",
        m2.vfr_hud_encode(4.2, 3.75, 271, 48, 12.6, -0.4),
        {"airspeed_mps": 4.2, "groundspeed_mps": 3.75, "heading_deg": 271, "throttle_pct": 48,
         "alt_m": 12.6, "climb_mps": -0.4}, seq=9)

    add("gps_raw_int_3d_fix",
        m2.gps_raw_int_encode(1000, 3, 413874000, 21686000, 152340, 90, 120, 50, 0, 14),
        {"fix_type": 3, "satellites_visible": 14, "hdop": 0.9}, seq=10)

    add("gps_raw_int_no_fix",
        m2.gps_raw_int_encode(1000, 1, 0, 0, 0, UINT16_MAX, UINT16_MAX, 0, 0, 255),
        {"fix_type": 1, "satellites_visible": None, "hdop": None},
        seq=11, note="satellites 255 and eph UINT16_MAX mean unknown")

    add("statustext_prearm",
        m2.statustext_encode(mavlink2.MAV_SEVERITY_CRITICAL, b"PreArm: Need 3D Fix"),
        {"severity": 2, "text": "PreArm: Need 3D Fix"}, seq=12)

    add("command_ack_denied",
        m2.command_ack_encode(mavlink2.MAV_CMD_COMPONENT_ARM_DISARM, mavlink2.MAV_RESULT_DENIED),
        {"command": 400, "result": 2}, seq=13,
        note="Accepted/denied ACK is not completion of the manoeuvre")

    # Invalid frame: flip one byte of the payload -> CRC mismatch.
    good = bytearray.fromhex(vectors[0]["frame_hex"])
    good[12] ^= 0xFF
    vectors.append({
        "name": "heartbeat_bad_crc_rejected",
        "mavlink_version": 2,
        "msg_id": 0,
        "msg_name": "HEARTBEAT",
        "frame_hex": good.hex(),
        "expected": None,
        "note": "Corrupted payload: the parser must reject the frame",
    })

    # Noise without start bytes followed by a valid frame.
    vectors.append({
        "name": "garbage_then_valid_heartbeat",
        "mavlink_version": 2,
        "msg_id": 0,
        "msg_name": "HEARTBEAT",
        "frame_hex": "0011223344" + vectors[1]["frame_hex"],
        "expected": vectors[1]["expected"],
        "expect": "single",
        "note": "Leading noise must be skipped",
    })
    # A false start byte may swallow the next frame (pymavlink drops the
    # bogus length); the contract only requires recovery on a later frame.
    vectors.append({
        "name": "false_start_then_recovery",
        "mavlink_version": 2,
        "msg_id": 0,
        "msg_name": "HEARTBEAT",
        "frame_hex": "fd01" + vectors[1]["frame_hex"] * 3,
        "expected": vectors[1]["expected"],
        "expect": "last",
        "note": "Parser must resynchronise within the following frames and decode at least the last one",
    })
    return vectors


def main() -> int:
    vectors = build_vectors()
    document = {
        "description": "MAVLink frames encoded with pymavlink and the values SafeFlight clients must derive",
        "generator": "scripts/generate_mavlink_vectors.py",
        "pymavlink_dialect": "ardupilotmega (MAVLink 2)",
        "contract": "shared/protocols/mavlink-telemetry-contract.md",
        "vectors": vectors,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"{len(vectors)} vectors written to {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
