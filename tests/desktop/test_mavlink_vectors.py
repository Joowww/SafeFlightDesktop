"""Desktop side of the shared MAVLink interoperability contract.

Every frame in shared/protocols/mavlink-test-vectors.json is parsed with
pymavlink (the parser beneath DroneKit) and the contract conversions are
checked. SafeFlight Android runs the same vectors in its Kotlin unit tests.
"""

import json

import pytest
from pymavlink.dialects.v20 import ardupilotmega as mavlink2

from conftest import VECTORS_PATH

VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))["vectors"]

ARDUCOPTER_MODES = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO", 4: "GUIDED", 5: "LOITER",
    6: "RTL", 7: "CIRCLE", 9: "LAND", 11: "DRIFT", 13: "SPORT", 14: "FLIP",
    15: "AUTOTUNE", 16: "POSHOLD", 17: "BRAKE", 18: "THROW", 19: "AVOID_ADSB",
    20: "GUIDED_NOGPS", 21: "SMART_RTL", 22: "FLOWHOLD", 23: "FOLLOW", 24: "ZIGZAG",
    25: "SYSTEMID", 26: "AUTOROTATE", 27: "AUTO_RTL",
}
GCS_TYPES = {mavlink2.MAV_TYPE_GCS, mavlink2.MAV_TYPE_ONBOARD_CONTROLLER}


def parse_all(frame_hex):
    parser = mavlink2.MAVLink(None)
    parser.robust_parsing = True
    messages = parser.parse_buffer(bytes.fromhex(frame_hex)) or []
    return [m for m in messages if m.get_type() != "BAD_DATA"]


def interpret(msg):
    """Reference implementation of mavlink-telemetry-contract.md."""
    t = msg.get_type()
    if t == "HEARTBEAT":
        is_vehicle = msg.type not in GCS_TYPES and msg.autopilot != mavlink2.MAV_AUTOPILOT_INVALID
        mode = None
        if is_vehicle:
            mode = ARDUCOPTER_MODES.get(msg.custom_mode, f"UNKNOWN({msg.custom_mode})")
        return {
            "system_id": msg.get_srcSystem(), "component_id": msg.get_srcComponent(),
            "armed": bool(msg.base_mode & mavlink2.MAV_MODE_FLAG_SAFETY_ARMED),
            "custom_mode": msg.custom_mode, "flight_mode": mode, "vehicle_type": msg.type,
            "autopilot": msg.autopilot, "system_status": msg.system_status, "is_vehicle": is_vehicle,
        }
    if t == "SYS_STATUS":
        return {
            "battery_voltage_v": None if msg.voltage_battery == 65535 else round(msg.voltage_battery / 1000, 3),
            "battery_current_a": None if msg.current_battery == -1 else round(msg.current_battery / 100, 2),
            "battery_remaining_pct": None if msg.battery_remaining == -1 else msg.battery_remaining,
        }
    if t == "GLOBAL_POSITION_INT":
        no_fix = msg.lat == 0 and msg.lon == 0
        return {
            "lat_deg": None if no_fix else msg.lat / 1e7, "lon_deg": None if no_fix else msg.lon / 1e7,
            "alt_msl_m": msg.alt / 1000, "relative_alt_m": msg.relative_alt / 1000,
            "heading_deg": None if msg.hdg == 65535 else msg.hdg / 100,
        }
    if t == "VFR_HUD":
        return {"airspeed_mps": msg.airspeed, "groundspeed_mps": msg.groundspeed, "heading_deg": msg.heading,
                "throttle_pct": msg.throttle, "alt_m": msg.alt, "climb_mps": msg.climb}
    if t == "GPS_RAW_INT":
        return {"fix_type": msg.fix_type,
                "satellites_visible": None if msg.satellites_visible == 255 else msg.satellites_visible,
                "hdop": None if msg.eph == 65535 else msg.eph / 100}
    if t == "STATUSTEXT":
        text = msg.text if isinstance(msg.text, str) else msg.text.decode("utf-8", "replace")
        return {"severity": msg.severity, "text": text.rstrip("\x00")}
    if t == "COMMAND_ACK":
        return {"command": msg.command, "result": msg.result}
    raise AssertionError(f"no contract for {t}")


def _approx(expected):
    if isinstance(expected, dict):
        return {k: (pytest.approx(v, abs=1e-6) if isinstance(v, float) else v) for k, v in expected.items()}
    return expected


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_vector(vector):
    messages = parse_all(vector["frame_hex"])
    if vector["expected"] is None:
        assert messages == [], "corrupted frame must be rejected"
        return
    if vector.get("expect") == "last":
        assert len(messages) >= 1, "parser must recover on a later frame"
    else:
        assert len(messages) == 1
    msg = messages[-1]
    assert msg.get_msgId() == vector["msg_id"]
    assert msg.get_type() == vector["msg_name"]
    assert interpret(msg) == _approx(vector["expected"])


def test_v1_and_v2_framing_present():
    starts = {bytes.fromhex(v["frame_hex"])[0] for v in VECTORS if v["expected"] is not None
              and "expect" not in v}
    assert starts == {0xFD, 0xFE}


def test_mode_table_matches_desktop_dronekit_patch():
    """App_flet.patch_dronekit_modes must use the same ArduCopter table."""
    import re
    from conftest import ROOT
    source = (ROOT / "App_flet.py").read_text(encoding="utf-8")
    block = source[source.index("standard_modes = {"):source.index("}", source.index("standard_modes = {"))]
    table = {int(k): v for k, v in re.findall(r'(\d+):\s*"([A-Z_]+)"', block)}
    assert table == ARDUCOPTER_MODES
