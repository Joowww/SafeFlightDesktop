import json

import pytest

from models.ConnectionProfiles import (
    ConnectionProfile,
    MavlinkEndpoint,
    ProfileStore,
    ProfileValidationError,
    VideoSource,
    default_profiles,
    parse_connection_string,
    redact_url,
    valid_rtsp_url,
    validate_profile,
    write_runtime_sdp,
)


@pytest.fixture
def store(tmp_path):
    return ProfileStore(config_dir=tmp_path, environ={}).load()


# -- defaults ------------------------------------------------------------------
def test_defaults_contain_required_profiles(store):
    ids = [p.id for p in store.profiles]
    assert ids == ["siyi-local", "cellular-vpn", "raspberry-lab", "sitl"]
    assert all(p.builtin for p in store.profiles)
    for profile in store.profiles:
        validate_profile(profile)


def test_default_active_profile_preserves_previous_behaviour(store):
    # v0.2 used udpin:0.0.0.0:14560 in development mode.
    assert store.active.id == "sitl"
    assert store.active.mavlink_connection_string() == "udpin:0.0.0.0:14560"


def test_env_mode_prod_selects_cellular_profile(tmp_path):
    s = ProfileStore(config_dir=tmp_path, environ={"ENV_MODE": "prod"}).load()
    assert s.active.id == "cellular-vpn"


# -- persistence ---------------------------------------------------------------
def test_roundtrip_persistence(tmp_path, store):
    profile = store.get("cellular-vpn").copy()
    profile.mavlink.local_port = 14555
    profile.video.mode = "rtsp"
    profile.video.rtsp_url = "rtsp://10.8.0.5:8554/cam"
    store.upsert(profile)
    store.select("cellular-vpn")
    store.save()

    reloaded = ProfileStore(config_dir=tmp_path, environ={}).load()
    assert reloaded.active.id == "cellular-vpn"
    assert reloaded.active.mavlink_connection_string() == "udpin:0.0.0.0:14555"
    assert reloaded.active.video.rtsp_url == "rtsp://10.8.0.5:8554/cam"
    assert reloaded.warnings == []


def test_file_is_valid_json_with_schema_version(tmp_path, store):
    data = json.loads((tmp_path / "connection_profiles.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["active_profile_id"] == "sitl"
    assert len(data["profiles"]) == 4


def test_corrupt_file_is_quarantined_and_defaults_restored(tmp_path):
    path = tmp_path / "connection_profiles.json"
    path.write_text("{ not json", encoding="utf-8")
    s = ProfileStore(config_dir=tmp_path, environ={}).load()
    assert [p.id for p in s.profiles] == ["siyi-local", "cellular-vpn", "raspberry-lab", "sitl"]
    assert any("ilegibles" in w for w in s.warnings)
    assert list(tmp_path.glob("connection_profiles.json.corrupt-*"))
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_future_schema_version_is_not_silently_accepted(tmp_path):
    (tmp_path / "connection_profiles.json").write_text(
        json.dumps({"schema_version": 99, "profiles": []}), encoding="utf-8")
    s = ProfileStore(config_dir=tmp_path, environ={}).load()
    assert any("ilegibles" in w for w in s.warnings)


def test_invalid_profile_is_skipped_and_builtins_restored(tmp_path):
    good = next(p for p in default_profiles() if p.id == "sitl").to_dict()
    bad = dict(good, id="broken", builtin=False)
    bad["mavlink"] = dict(good["mavlink"], local_port=80)
    incomplete = {"id": "partial", "name": "Partial", "kind": "custom"}  # defaults fill the rest
    (tmp_path / "connection_profiles.json").write_text(json.dumps({
        "schema_version": 1, "active_profile_id": "broken",
        "profiles": [good, bad, incomplete],
    }), encoding="utf-8")
    s = ProfileStore(config_dir=tmp_path, environ={}).load()
    ids = [p.id for p in s.profiles]
    assert "broken" not in ids and "partial" in ids
    assert {"siyi-local", "cellular-vpn", "sitl"} <= set(ids)
    assert s.active.id == "sitl"  # active id was invalid -> first profile
    assert any("broken" not in w and "ignorado" in w for w in s.warnings)


def test_unknown_fields_are_ignored(tmp_path):
    data = default_profiles()[0].to_dict()
    data["future_field"] = 1
    data["video"]["future_codec"] = "h265"
    profile = ConnectionProfile.from_dict(data)
    assert profile.id == "siyi-local"


# -- migration -----------------------------------------------------------------
def test_legacy_video_settings_are_migrated(tmp_path):
    (tmp_path / "video_settings.json").write_text(json.dumps({
        "video_mode": "rtsp", "rtp_udp_port": 5600, "rtsp_url": "rtsp://192.168.144.40:8554/cam",
    }), encoding="utf-8")
    s = ProfileStore(config_dir=tmp_path, environ={}).load()
    cell = s.get("cellular-vpn")
    assert cell.video.mode == "rtsp"
    assert cell.video.rtp_udp_port == 5600
    assert cell.video.rtsp_url == "rtsp://192.168.144.40:8554/cam"
    assert (tmp_path / "video_settings.json").exists()  # legacy file left untouched


def test_env_connection_strings_are_migrated(tmp_path):
    s = ProfileStore(config_dir=tmp_path, environ={
        "SIM_conn_str": "tcp:127.0.0.1:5760",
        "REAL_conn_str": "udpin:0.0.0.0:14570",
    }).load()
    assert s.get("sitl").mavlink_connection_string() == "tcp:127.0.0.1:5760"
    assert s.get("cellular-vpn").mavlink_connection_string() == "udpin:0.0.0.0:14570"


def test_unparseable_env_string_becomes_custom(tmp_path):
    s = ProfileStore(config_dir=tmp_path, environ={"REAL_conn_str": "host.docker.internal:14560"}).load()
    m = s.get("cellular-vpn").mavlink
    assert m.transport == "custom"
    assert s.get("cellular-vpn").mavlink_connection_string() == "host.docker.internal:14560"


# -- editing -------------------------------------------------------------------
def test_duplicate_restore_delete(store):
    clone = store.duplicate("siyi-local")
    assert not clone.builtin and clone.id == "siyi-local-copy"
    clone.mavlink.local_port = 14600
    store.upsert(clone)
    assert store.get("siyi-local").mavlink.local_port == 14560  # source untouched

    modified = store.get("siyi-local").copy()
    modified.video.rtsp_url = "rtsp://1.2.3.4:8554/x"
    store.upsert(modified)
    store.restore_builtin("siyi-local")
    assert store.get("siyi-local").video.rtsp_url == "rtsp://192.168.144.30:8554/raspicam"
    assert store.get("siyi-local-copy").mavlink.local_port == 14600  # other profile untouched

    with pytest.raises(ValueError):
        store.delete("sitl")
    store.select("siyi-local-copy")
    store.delete("siyi-local-copy")
    assert store.get("siyi-local-copy") is None
    assert store.active.id == "siyi-local"


def test_upsert_cannot_promote_custom_profile_to_builtin(store):
    p = ConnectionProfile(id="lab", name="Lab", builtin=True)
    stored = store.upsert(p)
    assert stored.builtin is False


# -- validation ----------------------------------------------------------------
@pytest.mark.parametrize("mavlink,ok", [
    (MavlinkEndpoint(transport="udp_listen", local_host="0.0.0.0", local_port=14550), True),
    (MavlinkEndpoint(transport="udp_listen", local_host="0.0.0.0", local_port=80), False),
    (MavlinkEndpoint(transport="udp_connect", remote_host="192.168.144.20", remote_port=14550), True),
    (MavlinkEndpoint(transport="udp_connect", remote_host="", remote_port=14550), False),
    (MavlinkEndpoint(transport="udp_connect", remote_host="bad host", remote_port=14550), False),
    (MavlinkEndpoint(transport="tcp_client", remote_host="raspberrypi.local", remote_port=5760), True),
    (MavlinkEndpoint(transport="serial", serial_device="/dev/ttyACM0", baud_rate=115200), True),
    (MavlinkEndpoint(transport="serial", serial_device="COM5", baud_rate=12345), False),
    (MavlinkEndpoint(transport="custom", connection_string="udpin:0.0.0.0:14560"), True),
    (MavlinkEndpoint(transport="custom", connection_string="a\nb"), False),
    (MavlinkEndpoint(transport="telepathy"), False),
])
def test_mavlink_validation(mavlink, ok):
    profile = ConnectionProfile(id="t", name="T", mavlink=mavlink)
    if ok:
        validate_profile(profile)
    else:
        with pytest.raises(ProfileValidationError):
            validate_profile(profile)


def test_rtsp_and_rtp_are_validated_separately():
    p = ConnectionProfile(id="t", name="T", video=VideoSource(mode="rtsp", rtsp_url="udp://1.2.3.4:5004"))
    with pytest.raises(ProfileValidationError):
        validate_profile(p)
    # An invalid RTSP URL does not matter while RTP is selected.
    p.video.mode = "rtp_udp"
    validate_profile(p)


def test_form_strings_are_coerced_or_rejected():
    p = ConnectionProfile(id="t", name="T", mavlink=MavlinkEndpoint(local_port="14570"))
    p.normalise()
    assert p.mavlink.local_port == 14570
    p2 = ConnectionProfile(id="t", name="T", mavlink=MavlinkEndpoint(local_port="abc"))
    with pytest.raises(ProfileValidationError):
        p2.normalise()


def test_timeouts_are_bounded():
    p = ConnectionProfile(id="t", name="T")
    p.timeouts.telemetry_stale_s = 0.0
    with pytest.raises(ProfileValidationError):
        validate_profile(p)


# -- helpers -------------------------------------------------------------------
def test_parse_connection_string():
    assert parse_connection_string("udpin:0.0.0.0:14560").transport == "udp_listen"
    assert parse_connection_string("udp:0.0.0.0:14550").local_port == 14550
    assert parse_connection_string("udpout:10.0.0.2:14550").remote_host == "10.0.0.2"
    assert parse_connection_string("tcp:127.0.0.1:5760").transport == "tcp_client"
    assert parse_connection_string("/dev/ttyACM0") is None
    assert parse_connection_string("udpin:0.0.0.0:99999") is None


def test_rtsp_url_helpers():
    assert valid_rtsp_url("rtsp://192.168.144.30:8554/raspicam")
    assert not valid_rtsp_url("http://x/y")
    assert not valid_rtsp_url("rtsp://host:99999/x")
    assert redact_url("rtsp://user:secret@10.0.0.1:8554/cam") == "rtsp://user:***@10.0.0.1:8554/cam"
    assert "secret" not in ConnectionProfile(
        id="t", name="T", video=VideoSource(mode="rtsp", rtsp_url="rtsp://u:secret@h/p")).video_summary()


def test_runtime_sdp(tmp_path):
    path = write_runtime_sdp(tmp_path, 5600)
    text = path.read_text(encoding="ascii")
    assert "m=video 5600 RTP/AVP 96" in text and "H264/90000" in text
    with pytest.raises(ValueError):
        write_runtime_sdp(tmp_path, 80)


def test_shared_example_matches_factory_profiles(tmp_path):
    """shared/examples must reflect the current Desktop factory profiles."""
    from conftest import ROOT
    example = json.loads((ROOT / "shared" / "examples" / "connection-profiles.example.json").read_text(encoding="utf-8"))
    current = ProfileStore(config_dir=tmp_path, environ={}).load().to_dict()
    assert example == current, "regenerate shared/examples/connection-profiles.example.json"
