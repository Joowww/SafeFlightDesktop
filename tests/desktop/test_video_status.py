import pytest

from models import VideoStatus as vs


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def tracker(clock):
    t = vs.VideoStatusTracker(clock=clock)
    t.set_source(1, "RTSP/TCP", "rtsp://127.0.0.1:18554/test")
    return t


def test_no_source_is_disabled(clock):
    t = vs.VideoStatusTracker(clock=clock)
    t.set_source(1, None, None)
    assert t.snapshot().state == vs.DISABLED


def test_connecting_until_first_frame(tracker):
    tracker.attempt_started(1)
    tracker.stream_opened(1, "h264", None)
    snap = tracker.snapshot()
    assert snap.state == vs.CONNECTING and snap.label == "Conectando"


def test_live_with_resolution_fps_and_age(tracker, clock):
    tracker.attempt_started(1)
    tracker.stream_opened(1, "h264", "SafeFlight test pattern")
    clock.t += vs.FPS_WARMUP_S
    for i in range(31):
        tracker.frame(1, 1280, 720, at=clock.t + i / 30)
    clock.t += 1.0 + 0.016
    snap = tracker.snapshot(stale_s=2.0)
    assert snap.state == vs.LIVE and snap.label == "En directo"
    assert snap.resolution == "1280×720"
    assert 29.0 < snap.fps < 31.0
    assert 10 < snap.age_ms < 30
    assert snap.summary().startswith("RTSP/TCP · 1280×720 · ")
    assert snap.origin_kind == vs.ORIGIN_TEST


def test_frames_stop_means_no_signal(tracker, clock):
    tracker.frame(1, 640, 360)
    clock.t += 5
    snap = tracker.snapshot(stale_s=2.0)
    assert snap.state == vs.NO_SIGNAL and snap.fps == 0.0
    assert snap.reason == "no llegan fotogramas"


def test_timeouts_without_frames_become_no_signal(tracker):
    tracker.attempt_started(1)
    tracker.attempt_failed(1, TimeoutError("timed out"))
    assert tracker.snapshot().state == vs.CONNECTING
    tracker.attempt_started(1)
    tracker.attempt_failed(1, TimeoutError("timed out"))
    snap = tracker.snapshot()
    assert snap.state == vs.NO_SIGNAL and "tiempo de espera" in snap.reason


def test_refused_connection_is_reception_error(tracker):
    tracker.attempt_started(1)
    tracker.attempt_failed(1, ConnectionRefusedError(10061, "refused"))
    snap = tracker.snapshot()
    assert snap.state == vs.ERROR and snap.label == "Error de recepción"
    assert "rechazada" in snap.reason
    assert snap.last_error.startswith("ConnectionRefusedError")


def test_frame_clears_error(tracker):
    tracker.attempt_failed(1, ConnectionRefusedError(10061, "refused"))
    tracker.frame(1, 640, 360)
    assert tracker.snapshot().state == vs.LIVE


def test_events_of_previous_source_are_ignored(tracker):
    tracker.set_source(2, "RTP/UDP", "stream.sdp")
    tracker.frame(1, 1280, 720)
    tracker.attempt_failed(1, ConnectionRefusedError(10061, "refused"))
    snap = tracker.snapshot()
    assert snap.state == vs.CONNECTING and snap.frames == 0 and snap.protocol == "RTP/UDP"


@pytest.mark.parametrize("title,kind", [
    (None, vs.ORIGIN_UNKNOWN),
    ("No Name", vs.ORIGIN_UNKNOWN),          # ffmpeg default session name
    ("SafeFlight-test-pattern", vs.ORIGIN_TEST),
    ("rpicam-vid IMX708", vs.ORIGIN_CAMERA),
    ("SIYI A8 mini", vs.ORIGIN_CAMERA),
    ("Stream", vs.ORIGIN_UNKNOWN),
])
def test_origin_only_from_stream_metadata(title, kind):
    assert vs.classify_origin(title)[0] == kind


def test_origin_unknown_without_stream(tracker):
    assert tracker.snapshot().origin_kind == vs.ORIGIN_UNKNOWN


@pytest.mark.parametrize("name,state", [
    ("ExitError", vs.NO_SIGNAL),
    ("HTTPNotFoundError", vs.ERROR),
    ("InvalidDataError", vs.ERROR),
])
def test_pyav_error_names(name, state):
    exc = type(name, (Exception,), {})("x")
    assert vs.classify_error(exc)[0] == state


def test_reconnection_burst_does_not_inflate_fps(tracker, clock):
    tracker.stream_opened(1, "h264", None)
    clock.t += 2.0
    for i in range(60):                       # 30 FPS before the outage
        tracker.frame(1, 1280, 720, at=clock.t + i / 30)
    clock.t += 2.0
    tracker.stream_ended(1)
    tracker.stream_opened(1, "h264", None)    # reconnection
    for i in range(20):                       # buffered frames drained in 0.2 s
        tracker.frame(1, 1280, 720, at=clock.t + i / 100)
    clock.t += 0.3
    assert tracker.snapshot().fps == 0.0      # burst ignored (warm-up)
    for i in range(45):                       # steady 30 FPS afterwards
        tracker.frame(1, 1280, 720, at=clock.t + 0.7 + i / 30)
    clock.t += 0.7 + 45 / 30
    assert 28.0 < tracker.snapshot().fps < 32.0


def test_declared_camera_is_not_presented_as_verified():
    kind, text = vs.classify_origin("rpicam-vid IMX708")
    assert kind == vs.ORIGIN_CAMERA
    assert text.startswith("Origen declarado") and "no verificado" in text
    assert "física" not in text
