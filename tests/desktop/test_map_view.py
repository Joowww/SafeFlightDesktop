import json

import pytest

from models.MapView import (
    FOLLOW_ZOOM,
    WORLD_VIEW,
    MapFollower,
    MapViewStore,
    distance_m,
    valid_coordinates,
    vehicle_position,
)


# -- trustworthy vehicle position ---------------------------------------------
def test_recent_3d_fix_is_accepted():
    assert vehicle_position(41.27, 1.98, fix_type=3, position_age_s=0.4) == (41.27, 1.98)


@pytest.mark.parametrize("lat,lon,fix,age", [
    (None, 1.0, 3, 0.1),          # no position yet
    (41.0, 1.0, 2, 0.1),          # 2D fix
    (41.0, 1.0, None, 0.1),       # fix unknown
    (41.0, 1.0, 3, 5.0),          # stale position messages
    (41.0, 1.0, 3, None),         # position messages not received yet
    (95.0, 1.0, 3, 0.1),          # out of range
    (float("nan"), 1.0, 3, 0.1),
])
def test_untrustworthy_positions_are_rejected(lat, lon, fix, age):
    assert vehicle_position(lat, lon, fix, age) is None


def test_zero_zero_is_not_rejected_by_itself():
    assert valid_coordinates(0.0, 0.0)
    assert vehicle_position(0.0, 0.0, 3, 0.1) == (0.0, 0.0)


def test_distance():
    assert distance_m((41.0, 2.0), (41.0, 2.0)) == 0
    assert 105 < distance_m((41.0, 2.0), (41.001, 2.0)) < 116


# -- initial view ---------------------------------------------------------------
def test_without_saved_view_the_map_opens_on_world_view(tmp_path):
    store = MapViewStore(tmp_path).load()
    assert store.initial_view() == WORLD_VIEW
    assert WORLD_VIEW.zoom <= 3


def test_saved_view_roundtrip(tmp_path):
    MapViewStore(tmp_path).load().save_view(41.2756, 1.9871, 17.5)
    view = MapViewStore(tmp_path).load().initial_view()
    assert (view.lat, view.lon, view.zoom, view.source) == (41.2756, 1.9871, 17.5, "saved")


def test_clear_returns_to_world_view(tmp_path):
    store = MapViewStore(tmp_path).load()
    store.save_view(41.0, 2.0, 15)
    store.clear()
    assert MapViewStore(tmp_path).load().initial_view() == WORLD_VIEW


@pytest.mark.parametrize("content", [
    "{ not json",
    json.dumps({"schema_version": 99, "initial_view": {"lat": 1, "lon": 1, "zoom": 5}}),
    json.dumps({"schema_version": 1, "initial_view": {"lat": 200, "lon": 1, "zoom": 5}}),
    json.dumps({"schema_version": 1, "initial_view": {"lat": 1}}),
])
def test_invalid_file_falls_back_to_world_view(tmp_path, content):
    (tmp_path / "map_view.json").write_text(content, encoding="utf-8")
    store = MapViewStore(tmp_path).load()
    assert store.initial_view() == WORLD_VIEW
    assert store.warning


def test_invalid_view_is_not_saved(tmp_path):
    with pytest.raises(ValueError):
        MapViewStore(tmp_path).load().save_view(None, 2.0, 10)
    assert not (tmp_path / "map_view.json").exists()


# -- follow ---------------------------------------------------------------------
def test_first_trustworthy_position_centres_once_even_without_follow():
    f = MapFollower(follow=False)
    assert f.update(None) is None
    view = f.update((41.0, 2.0))
    assert (view.lat, view.lon, view.zoom, view.source) == (41.0, 2.0, FOLLOW_ZOOM, "vehicle")
    assert f.update((41.01, 2.0)) is None  # follow off: the map stays


def test_follow_recentres_only_after_significant_movement():
    f = MapFollower(follow=True)
    f.update((41.0, 2.0))
    assert f.update((41.0001, 2.0)) is None       # ~11 m
    assert f.update((41.0005, 2.0)) is not None   # ~55 m


def test_manual_gesture_stops_follow_and_reenabling_recentres():
    f = MapFollower(follow=True)
    f.update((41.0, 2.0))
    assert f.user_moved_map() is True
    assert f.update((41.01, 2.0)) is None
    view = f.set_follow(True)
    assert (view.lat, view.lon) == (41.01, 2.0)


def test_enabling_follow_without_position_does_nothing():
    assert MapFollower(follow=False).set_follow(True) is None


def test_reset_forgets_previous_vehicle():
    f = MapFollower()
    f.update((41.0, 2.0))
    f.reset()
    assert f.update((10.0, 10.0)) is not None


# -- position age comes from the position messages, not from the heartbeat -------
def test_position_age_ignores_heartbeat(monkeypatch):
    import models.DroneManager as dm_module
    from models.DroneManager import DroneManager

    now = [100.0]
    monkeypatch.setattr(dm_module.time, "monotonic", lambda: now[0])
    dm = DroneManager()
    assert dm.gps_position_age_s() is None
    dm._on_position_message(None, "GLOBAL_POSITION_INT", None)
    assert dm.gps_position_age_s() is None          # GPS_RAW_INT (fix) still missing
    dm._on_position_message(None, "GPS_RAW_INT", None)
    now[0] = 101.0
    assert dm.gps_position_age_s() == 1.0
    # Heartbeats keep arriving but the position stops: the age keeps growing.
    now[0] = 110.0
    age = dm.gps_position_age_s()
    assert age == 10.0
    assert vehicle_position(41.0, 2.0, 3, age) is None
