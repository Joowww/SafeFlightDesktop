"""CommandGuard: default-deny filter, sessions, preconditions and permits."""

import pytest
from pymavlink.dialects.v20 import ardupilotmega as m

from models import CommandGuard as cg


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class _Sink:
    def write(self, data):
        pass


ENC = m.MAVLink(_Sink(), srcSystem=255, srcComponent=190)


def frame(msg):
    return msg.pack(ENC)


def arm(value=1, force=0):
    return frame(ENC.command_long_encode(1, 1, m.MAV_CMD_COMPONENT_ARM_DISARM, 0, value, force, 0, 0, 0, 0, 0))


def set_mode(mode_id):
    return frame(ENC.set_mode_encode(1, m.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id))


def takeoff(alt=5):
    return frame(ENC.command_long_encode(1, 1, m.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, alt))


def velocity():
    return frame(ENC.set_position_target_local_ned_encode(0, 1, 1, m.MAV_FRAME_BODY_NED, 0b0000011111000111,
                                                          0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0))


def position():
    return frame(ENC.set_position_target_global_int_encode(0, 1, 1, m.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, 0,
                                                           0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0))


def param_set():
    return frame(ENC.param_set_encode(1, 1, b"ARMING_CHECK", 0, m.MAV_PARAM_TYPE_INT32))


READ_ONLY = [
    frame(ENC.heartbeat_encode(m.MAV_TYPE_GCS, m.MAV_AUTOPILOT_INVALID, 0, 0, 0)),
    frame(ENC.param_request_list_encode(1, 1)),
    frame(ENC.request_data_stream_encode(1, 1, 0, 4, 1)),
    frame(ENC.command_long_encode(1, 1, m.MAV_CMD_REQUEST_AUTOPILOT_CAPABILITIES, 0, 1, 0, 0, 0, 0, 0, 0)),
]
CONTROL = [arm(), arm(0), set_mode(4), set_mode(9), takeoff(), velocity(), position(), param_set(),
           frame(ENC.command_long_encode(1, 1, m.MAV_CMD_CONDITION_YAW, 0, 0, 0, 1, 1, 0, 0, 0)),
           frame(ENC.rc_channels_override_encode(1, 1, *([1500] * 8))),
           frame(ENC.mission_count_encode(1, 1, 3))]


@pytest.fixture
def env():
    clock = Clock()
    logs = []
    guard = cg.CommandGuard(clock=clock, log=logs.append)
    snap = cg.Snapshot(connected=True, system_id=1, component_id=1, vehicle_type="2",
                       heartbeat_age_s=0.2, armed=False, mode="GUIDED", gps_fix=3, satellites=12)
    guard.set_snapshot_source(lambda: snap)
    return guard, clock, snap, logs


def authorize(guard):
    assert guard.authorize([True, True, True, True, True], "1")


def test_monitor_mode_blocks_every_control_message(env):
    guard, *_ = env
    assert guard.state == cg.MONITOR
    for data in CONTROL:
        assert guard.filter_bytes(data) == b""
    for data in READ_ONLY:
        assert guard.filter_bytes(data) == data
    assert guard.sent_control == []


def test_requests_are_rejected_without_session(env):
    guard, *_ = env
    for kind in (cg.ARM, cg.TAKEOFF, cg.LAND, cg.RTL, cg.VELOCITY):
        assert not guard.request(kind, altitude=5)


def test_authorization_requires_confirmations_and_matching_sysid(env):
    guard, _clock, snap, _ = env
    assert not guard.authorize([True, False], "1")
    assert not guard.authorize([True, True], "2")
    snap.heartbeat_age_s = 5.0
    assert not guard.authorize([True, True], "1")
    snap.heartbeat_age_s = 0.1
    assert guard.authorize([True, True], "1")
    assert guard.state == cg.AUTHORIZED


def test_permit_allows_exactly_one_matching_frame(env):
    guard, *_ = env
    authorize(guard)
    assert guard.request(cg.ARM)
    assert guard.filter_bytes(set_mode(4)) == b""      # different command: still blocked
    assert guard.filter_bytes(arm()) == arm()
    assert guard.filter_bytes(arm()) == b""            # permit consumed


def test_forced_arm_or_disarm_is_never_sent(env):
    guard, *_ = env
    authorize(guard)
    assert guard.request(cg.ARM)
    assert guard.filter_bytes(arm(1, cg.FORCE_ARM_MAGIC)) == b""
    assert guard.request(cg.DISARM)
    assert guard.filter_bytes(arm(0, cg.FORCE_ARM_MAGIC)) == b""


def test_mode_permit_only_matches_requested_mode(env):
    guard, *_ = env
    authorize(guard)
    assert guard.request(cg.LAND)
    assert guard.filter_bytes(set_mode(4)) == b""      # GUIDED, not LAND
    assert guard.filter_bytes(set_mode(9)) == set_mode(9)


def test_permits_expire(env):
    guard, clock, *_ = env
    authorize(guard)
    assert guard.request(cg.ARM)
    clock.t += cg.PERMIT_TTL_S + 0.1
    assert guard.filter_bytes(arm()) == b""


def test_duplicate_commands_are_rejected(env):
    guard, clock, *_ = env
    authorize(guard)
    assert guard.request(cg.MODE, mode="LOITER")
    assert not guard.request(cg.MODE, mode="LOITER")
    clock.t += cg.DUPLICATE_WINDOW_S + 0.1
    assert guard.request(cg.MODE, mode="LOITER")


def test_failed_land_can_be_retried_immediately(env):
    guard, _clock, snap, _ = env
    authorize(guard)
    assert guard.request(cg.LAND)
    assert guard.request(cg.LAND)          # vehicle still not in LAND: retry allowed
    snap.mode = "LAND"
    assert not guard.request(cg.LAND)      # already landing: redundant


def test_takeoff_preconditions(env):
    guard, _clock, snap, _ = env
    authorize(guard)
    assert not guard.request(cg.TAKEOFF, altitude=5)          # not armed
    snap.armed = True
    assert not guard.request(cg.TAKEOFF, altitude=50)         # above limit
    snap.mode = "LOITER"
    assert not guard.request(cg.TAKEOFF, altitude=5)          # not GUIDED
    snap.mode, snap.gps_fix = "GUIDED", 1
    assert not guard.request(cg.TAKEOFF, altitude=5)          # no 3D fix
    snap.gps_fix = 3
    assert guard.request(cg.TAKEOFF, altitude=5)
    assert guard.filter_bytes(takeoff()) == takeoff()


def test_stale_heartbeat_suspends_and_only_emergency_is_allowed(env):
    guard, clock, snap, _ = env
    authorize(guard)
    snap.armed = True
    snap.heartbeat_age_s = 3.0
    guard.tick()
    assert guard.state == cg.SUSPENDED
    assert not guard.request(cg.VELOCITY)
    assert not guard.request(cg.TAKEOFF, altitude=3)
    assert guard.request(cg.LAND)
    assert guard.filter_bytes(set_mode(9)) == set_mode(9)
    snap.heartbeat_age_s = 0.1
    guard.tick()
    assert guard.state == cg.SUSPENDED                        # recovery needs a new authorisation


def test_vehicle_identity_change_revokes_session(env):
    guard, _clock, snap, _ = env
    authorize(guard)
    snap.system_id = 2
    assert not guard.request(cg.RTL)
    guard.tick()
    assert guard.state == cg.MONITOR


def test_session_expires(env):
    guard, clock, *_ = env
    authorize(guard)
    clock.t += cg.SESSION_DURATION_S + 1
    guard.tick()
    assert guard.state == cg.MONITOR


def test_movement_requires_guided_and_armed(env):
    guard, _clock, snap, _ = env
    authorize(guard)
    assert not guard.request(cg.VELOCITY)
    snap.armed = True
    assert guard.request(cg.VELOCITY)
    assert guard.filter_bytes(velocity()) == velocity()
    assert guard.filter_bytes(velocity()) == b""


def test_parameter_writes_and_missions_are_never_permitted(env):
    guard, *_ = env
    authorize(guard)
    for kind in (cg.ARM, cg.LAND):
        guard.request(kind)
    assert guard.filter_bytes(param_set()) == b""
    assert guard.filter_bytes(frame(ENC.mission_count_encode(1, 1, 3))) == b""


def test_install_wraps_master_write(env):
    guard, *_ = env

    class Master:
        def __init__(self):
            self.out = []

        def write(self, buf):
            self.out.append(buf)

    master = Master()
    guard.install(master)
    master.write(arm())
    master.write(READ_ONLY[0])
    assert master.out == [READ_ONLY[0]]
