import json
import math

import pytest

from models.ArProjection import (
    DEFAULT_CAMERA,
    CameraModel,
    distance_label,
    enu_offset,
    load_camera,
    marker_radii,
    project,
)

W, H = 1280, 720
LAT, LON = 41.2756, 1.9871      # any mid-latitude place
M_LAT = 1 / 111195.0             # degrees of latitude per metre (approx.)


def m_lon(lat=LAT):
    return M_LAT / math.cos(math.radians(lat))


def test_enu_uses_cos_latitude_for_longitude():
    east, north, up = enu_offset(LAT, LON, 10, LAT, LON + 100 * m_lon(), 0)
    assert abs(east - 100) < 0.5 and abs(north) < 0.01 and up == -10


def test_point_straight_ahead_is_on_the_centre_column():
    p = project(LAT, LON, 0, 0, LAT + 50 * M_LAT, LON, 0, W, H)   # heading north, target 50 m north
    assert p and abs(p.x - W // 2) <= 1 and abs(p.y - H // 2) <= 1


def test_heading_rotates_the_scene():
    # Target 50 m east: centred when heading east (90), out of frame when heading north (FOV 66°).
    target = (LAT, LON + 50 * m_lon(), 0)
    assert abs(project(LAT, LON, 0, 90, *target, W, H).x - W // 2) <= 1
    assert project(LAT, LON, 0, 0, *target, W, H) is None


def test_target_to_the_right_is_drawn_right():
    # 50 m north, 10 m east, heading north -> right of centre, pinhole: fx * 10 / 50
    p = project(LAT, LON, 0, 0, LAT + 50 * M_LAT, LON + 10 * m_lon(), 0, W, H)
    fx = (W / 2) / math.tan(math.radians(DEFAULT_CAMERA.hfov_deg / 2))
    assert abs(p.x - (W / 2 + fx * 10 / 50)) <= 2


def test_higher_waypoint_is_drawn_higher_and_ground_is_below():
    above = project(LAT, LON, 10, 0, LAT + 50 * M_LAT, LON, 20, W, H)   # waypoint 10 m above the drone
    ground = project(LAT, LON, 10, 0, LAT + 50 * M_LAT, LON, 0, W, H)   # HOME on the ground
    assert above.y < H / 2 < ground.y
    assert ground.depression_deg > 0 > above.depression_deg


def test_point_behind_is_not_drawn():
    assert project(LAT, LON, 0, 0, LAT - 50 * M_LAT, LON, 0, W, H) is None


def test_target_under_the_vehicle_is_not_drawn():
    assert project(LAT, LON, 30, 0, LAT + 0.5 * M_LAT, LON, 0, W, H) is None


def test_camera_tilted_down_brings_the_ground_up():
    level = project(LAT, LON, 20, 0, LAT + 40 * M_LAT, LON, 0, W, H)          # 26.6° below horizon
    tilted = project(LAT, LON, 20, 0, LAT + 40 * M_LAT, LON, 0, W, H,
                     CameraModel(mount_pitch_deg=-26.565))
    assert level is None or level.y > H / 2
    assert abs(tilted.y - H // 2) <= 1


def test_uncalibrated_projection_is_approximate():
    p = project(LAT, LON, 0, 0, LAT + 50 * M_LAT, LON, 0, W, H)
    assert p.approximate and distance_label(p) == "~50 m"
    q = project(LAT, LON, 0, 0, LAT + 50 * M_LAT, LON, 0, W, H, CameraModel(calibrated=True),
                attitude=(0.0, 0.0))
    assert not q.approximate and distance_label(q) == "50 m"


def test_missing_data_returns_none():
    assert project(None, LON, 0, 0, LAT, LON, 0, W, H) is None
    assert project(LAT, LON, 0, None, LAT + 50 * M_LAT, LON, 0, W, H) is None


def test_marker_radii_flatten_with_low_viewing_angle():
    near = project(LAT, LON, 10, 0, LAT + 15 * M_LAT, LON, 0, W, H, CameraModel(mount_pitch_deg=-30))
    far = project(LAT, LON, 10, 0, LAT + 60 * M_LAT, LON, 0, W, H, CameraModel(mount_pitch_deg=-10))
    rx_n, ry_n = marker_radii(near, 700, 15, 200, 3)
    rx_f, ry_f = marker_radii(far, 700, 15, 200, 3)
    assert rx_n > rx_f and ry_n / rx_n > ry_f / rx_f


def test_camera_config_file(tmp_path):
    assert load_camera(tmp_path) == (DEFAULT_CAMERA, None)
    (tmp_path / "ar_camera.json").write_text(json.dumps(
        {"hfov_deg": 102, "vfov_deg": 67, "mount_pitch_deg": -20, "calibrated": True, "name": "IMX708 wide"}),
        encoding="utf-8")
    cam, warning = load_camera(tmp_path)
    assert warning is None and cam.calibrated and cam.hfov_deg == 102 and cam.mount_pitch_deg == -20
    assert "calibrada" in cam.describe()


@pytest.mark.parametrize("content", ["{bad", json.dumps({"hfov_deg": 5}), json.dumps({"mount_pitch_deg": 80})])
def test_invalid_camera_config_falls_back_to_nominal(tmp_path, content):
    (tmp_path / "ar_camera.json").write_text(content, encoding="utf-8")
    cam, warning = load_camera(tmp_path)
    assert cam == DEFAULT_CAMERA and warning and not cam.calibrated
    assert "SIN CALIBRAR" in cam.describe()


def test_calibrated_but_unreliable_orientation_is_approximate():
    cal = CameraModel(calibrated=True)
    target = (LAT + 50 * M_LAT, LON, 0)
    unknown = project(LAT, LON, 0, 0, *target, W, H, cal, attitude=None)
    rolled = project(LAT, LON, 0, 0, *target, W, H, cal, attitude=(0.0, 12.0))
    assert unknown.approximate and unknown.reason == "actitud del vehículo desconocida"
    assert rolled.approximate and "alabeo" in rolled.reason
    stabilized = project(LAT, LON, 0, 0, *target, W, H, CameraModel(calibrated=True, stabilized=True))
    assert not stabilized.approximate


def test_vehicle_pitch_tilts_a_frame_fixed_camera():
    target = (LAT + 50 * M_LAT, LON, 0)
    level = project(LAT, LON, 0, 0, *target, W, H, attitude=(0.0, 0.0))
    nose_down = project(LAT, LON, 0, 0, *target, W, H, attitude=(-10.0, 0.0))
    gimbal = project(LAT, LON, 0, 0, *target, W, H, CameraModel(stabilized=True), attitude=(-10.0, 0.0))
    assert nose_down.y < level.y          # camera looks down: horizon objects move up
    assert gimbal.y == level.y            # stabilized camera ignores vehicle pitch


def test_home_is_altitude_zero_in_the_relative_frame():
    # Vehicle 20 m above HOME (relative frame): HOME 40 m ahead is below the horizon.
    p = project(LAT, LON, 20.0, 0, LAT + 40 * M_LAT, LON, 0.0, W, H, CameraModel(mount_pitch_deg=-30))
    assert abs(p.depression_deg - math.degrees(math.atan2(20, 40))) < 0.5
