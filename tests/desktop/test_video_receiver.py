"""Desktop video reception driven by connection profiles.

Exercises the real receiver thread of App_flet (PyAV) with:
  * RTP/UDP H.264 described by the runtime SDP (5G/VPN profile path);
  * a live source switch between profiles without restarting the app;
  * an RTSP server, when the optional test server is running
    (scripts/rtsp-test-server, port 18554); otherwise that case is skipped.
"""

import socket
import sys
import threading
import time

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
from rtp_test_sender import RtpTestSender  # noqa: E402

import App_flet  # noqa: E402
from models.ConnectionProfiles import write_runtime_sdp  # noqa: E402

RTSP_TEST_URL = "rtsp://127.0.0.1:18554/test"


def _free_rtp_port(start=5600):
    """Even port whose RTCP neighbour (port + 1) is also free.

    Ephemeral ports are avoided: on Windows, Hyper-V/WSL reserve dynamic UDP
    ranges and FFmpeg must bind both the RTP and the RTCP port.
    """
    for port in range(start, start + 200, 2):
        sockets = []
        try:
            for p in (port, port + 1):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sockets.append(s)
                s.bind(("0.0.0.0", p))
            return port
        except OSError:
            continue
        finally:
            for s in sockets:
                s.close()
    raise RuntimeError("no free RTP port pair")


def _wait_frame(after_generation, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with App_flet._g_frame_lock:
            frame = App_flet._g_latest_frame
            generation = App_flet._g_stream_generation
        if frame is not None and generation == after_generation:
            return frame
        time.sleep(0.1)
    return None


@pytest.fixture
def receiver():
    App_flet._set_global_video_source(None)
    App_flet._g_video_thread_running = True
    thread = threading.Thread(target=App_flet._global_video_worker, daemon=True)
    thread.start()
    yield
    App_flet._g_video_thread_running = False
    App_flet._set_global_video_source(None)
    thread.join(timeout=10)


def _rtsp_server_available():
    try:
        with socket.create_connection(("127.0.0.1", 18554), timeout=1):
            return True
    except OSError:
        return False


@pytest.mark.integration
def test_rtp_udp_profile_and_live_switch(receiver, tmp_path):
    port_a = _free_rtp_port(5600)
    port_b = _free_rtp_port(port_a + 2)
    sender_a = RtpTestSender(port=port_a).start()
    sender_b = RtpTestSender(port=port_b).start()
    try:
        App_flet._set_global_video_source(str(write_runtime_sdp(tmp_path / "a", port_a)), "tcp", 0.5)
        frame = _wait_frame(App_flet._g_stream_generation, 20)
        assert sender_a.error is None, sender_a.error
        assert frame is not None, "no RTP frame decoded"
        assert frame.shape == (360, 640, 3)

        # Profile change: new port applied without restarting the receiver thread.
        App_flet._set_global_video_source(str(write_runtime_sdp(tmp_path / "b", port_b)), "tcp", 0.5)
        generation = App_flet._g_stream_generation
        assert App_flet._g_latest_frame is None  # stale frame cleared on switch
        assert _wait_frame(generation, 20) is not None

        # Profile without video: frames stop.
        App_flet._set_global_video_source(None)
        time.sleep(1.5)
        assert App_flet._g_latest_frame is None
    finally:
        sender_a.stop()
        sender_b.stop()


@pytest.mark.integration
@pytest.mark.skipif(not _rtsp_server_available(), reason="RTSP test server not running on port 18554")
def test_rtsp_profile(receiver):
    App_flet._set_global_video_source(RTSP_TEST_URL, "tcp", 0.5)
    frame = _wait_frame(App_flet._g_stream_generation, 30)
    assert frame is not None, "no RTSP frame decoded"
    assert frame.shape[2] == 3
