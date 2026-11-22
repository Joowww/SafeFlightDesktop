"""End-to-end check of the Desktop MAVLink path on the local machine.

A synthetic telemetry source (scripts/mavlink_test_sender.py) sends to a
UDP port; DroneManager connects with the connection string produced by a
connection profile, exactly as App_flet does. No real vehicle is involved
and no flight command is issued by the test.
"""

import collections
import collections.abc
import socket
import sys
import time

import pytest

from conftest import ROOT

if not hasattr(collections, "MutableMapping"):
    collections.MutableMapping = collections.abc.MutableMapping

sys.path.insert(0, str(ROOT / "scripts"))
from mavlink_test_sender import TelemetrySimulator  # noqa: E402

from models.ConnectionProfiles import ConnectionProfile, MavlinkEndpoint, Timeouts  # noqa: E402
from models.DroneManager import DroneManager  # noqa: E402


def _free_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


@pytest.mark.integration
def test_profile_connection_receives_telemetry_and_detects_loss():
    port = _free_udp_port()
    profile = ConnectionProfile(
        id="test-sitl", name="Test", kind="sitl",
        mavlink=MavlinkEndpoint(transport="udp_listen", local_host="127.0.0.1", local_port=port),
        timeouts=Timeouts(connect_timeout_s=20, heartbeat_timeout_s=10),
    )
    sim = TelemetrySimulator("127.0.0.1", port, rate_hz=10, custom_mode=5).start()
    manager = DroneManager()
    try:
        assert manager.setup_drone(
            connection_string=profile.mavlink_connection_string(),
            heartbeat_timeout=profile.timeouts.heartbeat_timeout_s,
            connect_timeout=profile.timeouts.connect_timeout_s,
        )
        vehicle = manager.link.vehicle
        assert _wait_for(lambda: vehicle.mode.name == "LOITER", 10), vehicle.mode
        assert vehicle.armed is False
        assert _wait_for(lambda: vehicle.battery.voltage and vehicle.battery.voltage > 15.0, 10)
        assert _wait_for(lambda: vehicle.location.global_relative_frame.alt is not None, 10)
        assert _wait_for(lambda: vehicle.gps_0.satellites_visible == 12, 10)
        assert vehicle.last_heartbeat < 1.0

        # Link loss: the sender stops; heartbeat age must grow (what the UI shows).
        sim.pause(True)
        assert _wait_for(lambda: vehicle.last_heartbeat > profile.timeouts.telemetry_stale_s, 8)

        # Recovery without reconnecting (UDP is connectionless).
        sim.pause(False)
        assert _wait_for(lambda: vehicle.last_heartbeat < 1.0, 8)
    finally:
        # Stop the monitor first so that no emergency callback can fire.
        if manager.health:
            manager.health.stop()
        if manager.link:
            manager.link.disconnect()
        sim.stop()
