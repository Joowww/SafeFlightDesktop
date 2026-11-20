#!/usr/bin/env python3
"""Synthetic H.264 RTP/UDP video source (test fixture, no hardware).

Encodes a moving test pattern with libx264 (bundled with PyAV) and sends it
as RTP payload type 96, the format SafeFlight Desktop receives through its
SDP description (profiles with video mode ``rtp_udp``)::

    python scripts/rtp_test_sender.py --port 5004 --duration 60

It reproduces the transport used by the Raspberry Pi pipeline over 5G/VPN
(H.264 over RTP/UDP) without touching the drone.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

import av
import numpy as np


class RtpTestSender:
    def __init__(self, host: str = "127.0.0.1", port: int = 5004, width: int = 640,
                 height: int = 360, fps: int = 25):
        self.url = f"rtp://{host}:{port}"
        self.width, self.height, self.fps = width, height, fps
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="rtp-test-sender", daemon=True)
        self.frames_sent = 0
        self.error = None

    def start(self) -> "RtpTestSender":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            with av.open(self.url, mode="w", format="rtp") as container:
                stream = container.add_stream("libx264", rate=self.fps)
                stream.width, stream.height = self.width, self.height
                stream.pix_fmt = "yuv420p"
                stream.options = {"preset": "ultrafast", "tune": "zerolatency", "g": str(self.fps),
                                  "profile": "baseline", "x264-params": "repeat-headers=1"}
                ys, xs = np.mgrid[0:self.height, 0:self.width]
                start = time.monotonic()
                while not self._stop.is_set():
                    shift = self.frames_sent * 4
                    img = np.stack([(xs + shift) % 256, (ys + shift) % 256,
                                    np.full_like(xs, (self.frames_sent * 3) % 256)], axis=-1).astype(np.uint8)
                    frame = av.VideoFrame.from_ndarray(img, format="rgb24")
                    for packet in stream.encode(frame):
                        container.mux(packet)
                    self.frames_sent += 1
                    delay = start + self.frames_sent / self.fps - time.monotonic()
                    if delay > 0:
                        self._stop.wait(delay)
        except Exception as exc:  # reported to the caller/test
            self.error = f"{type(exc).__name__}: {exc}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5004)
    parser.add_argument("--duration", type=float, default=0, help="seconds (0 = until Ctrl+C)")
    args = parser.parse_args(argv)
    sender = RtpTestSender(args.host, args.port).start()
    print(f"Sending H.264 RTP test pattern to {sender.url}", flush=True)
    try:
        deadline = time.monotonic() + args.duration if args.duration else None
        while deadline is None or time.monotonic() < deadline:
            time.sleep(0.5)
            if sender.error:
                print(sender.error, file=sys.stderr)
                return 1
    except KeyboardInterrupt:
        pass
    finally:
        sender.stop()
    print(f"Stopped after {sender.frames_sent} frames.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
