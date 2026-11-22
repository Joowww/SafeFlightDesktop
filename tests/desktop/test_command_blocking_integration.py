"""Negative test: in monitor mode no control command reaches the vehicle.

DroneKit is connected to the synthetic vehicle and every legacy command path
is exercised on purpose (DroneKit setters, send_mavlink, controllers, the
manager sequences and the link-loss handler). The assertion is made on what
the *receiving* side actually got, not on mocks.
"""

import collections
import collections.abc
import socket
import sys
import threading
import time

import pytest

from conftest import ROOT

if not hasattr(collections, "MutableMapping"):
    collections.MutableMapping = collections.abc.MutableMapping

sys.path.insert(0, str(ROOT / "scripts"))
from mavlink_test_sender import TelemetrySimulator  # noqa: E402

from dronekit import VehicleMode  # noqa: E402
from pymavlink import mavutil  # noqa: E402

from models import CommandGuard as cg  # noqa: E402
from models.DroneManager import DroneManager  # noqa: E402
from models.Trajectory import Trajectory  # noqa: E402

CONTROL_KEYS = ("COMMAND_LONG:400", "COMMAND_LONG:22", "COMMAND_LONG:176", "COMMAND_LONG:115",
                "SET_MODE", "SET_POSITION_TARGET_LOCAL_NED", "SET_POSITION_TARGET_GLOBAL_INT",
                "PARAM_SET", "RC_CHANNELS_OVERRIDE", "MANUAL_CONTROL")


def _free_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.integration
def test_no_control_command_leaves_the_application_in_monitor_mode():
    port = _free_udp_port()
    sim = TelemetrySimulator("127.0.0.1", port, rate_hz=10, custom_mode=4).start()  # GUIDED
    manager = DroneManager()
    try:
        assert manager.setup_drone(connection_string=f"udpin:127.0.0.1:{port}",
                                   heartbeat_timeout=10, connect_timeout=20)
        vehicle = manager.link.vehicle
        deadline = time.monotonic() + 10
        while manager.identity is None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert manager.guard.state == cg.MONITOR

        # 1. Direct DroneKit setters and raw messages.
        vehicle.mode = VehicleMode("LAND")
        vehicle.armed = True
        vehicle.simple_takeoff(5)
        vehicle.send_mavlink(vehicle.message_factory.set_position_target_local_ned_encode(
            0, 1, 1, mavutil.mavlink.MAV_FRAME_BODY_NED, 0b0000011111000111,
            0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0))
        # 2. Manager sequences used by the buttons.
        assert manager.arm_and_takeoff_safe(3.0) is False
        assert manager.land() is False
        assert manager.return_to_launch() is False
        assert manager.set_mode_infantil() is False
        traj = Trajectory("t")
        traj.points = []
        assert not manager.set_mode_trajectory(traj)
        # 3. Controllers driven directly (bypassing the manager).
        manager.kb_controller.start()
        manager.kb_controller.set_pressed_keys({"arrow up", "w"})
        for _ in range(10):
            manager.kb_controller.update()
        manager.kb_controller.stop()
        # 4. Link-loss handler (previously sent LAND).
        manager._handle_link_loss()
        time.sleep(2.0)
    finally:
        if manager.health:
            manager.health.stop()
        if manager.link:
            manager.link.disconnect()
        sim.stop()

    received_control = {k: v for k, v in sim.received.items() if k in CONTROL_KEYS}
    assert received_control == {}, f"control commands reached the vehicle: {received_control}"
    assert sim.received.get("HEARTBEAT", 0) > 0          # telemetry link was alive
    assert sim.received.get("PARAM_REQUEST_LIST", 0) > 0
    blocked = manager.guard.blocked_counts
    assert any(k.startswith(("SET_MODE", "COMMAND_LONG:400", "COMMAND_LONG:22")) for k in blocked), blocked
