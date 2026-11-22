"""Video reception status for the VIDEO panel (pure logic, no Flet / PyAV).

The receiver thread reports what actually happens (attempt, stream opened,
frame decoded, failure); the UI asks for a snapshot. Each event carries the
source generation so that events of a previous source are ignored.

States: En directo, Conectando, Sin señal, Error de recepción (and Sin vídeo
when the profile has no video). The origin is only what the stream itself
*declares* in its metadata title (e.g. ``ffmpeg -metadata title=...`` before
MediaMTX); it is shown as declared, never as verified, and the profile name is
never used for it.
"""

from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

LIVE = "live"
CONNECTING = "connecting"
NO_SIGNAL = "no_signal"
ERROR = "error"
DISABLED = "disabled"

LABELS = {
    LIVE: "En directo",
    CONNECTING: "Conectando",
    NO_SIGNAL: "Sin señal",
    ERROR: "Error de recepción",
    DISABLED: "Sin vídeo",
}
COLORS = {LIVE: "#4ade80", CONNECTING: "#facc15", NO_SIGNAL: "#fb7185", ERROR: "#f97316", DISABLED: "#9ca3af"}

ORIGIN_TEST = "test"
ORIGIN_CAMERA = "camera"
ORIGIN_UNKNOWN = "unknown"

TEST_MARKERS = ("safeflight-test", "safeflight test", "test pattern", "testsrc")
CAMERA_MARKERS = ("imx", "rpicam", "libcamera", "raspberry pi camera", "siyi", "a8 mini", "zr10", "zr30")
DEFAULT_TITLES = ("", "no name")  # ffmpeg's default SDP session name says nothing

# A source that never produced a frame is "Conectando" for this many failed
# attempts, then "Sin señal".
CONNECTING_ATTEMPTS = 2
FPS_WINDOW_S = 2.0
# After (re)opening a stream the decoder drains buffered frames in a burst:
# those frames are not counted for the FPS figure.
FPS_WARMUP_S = 1.0


def classify_origin(title: Optional[str]) -> tuple:
    """(kind, text) from the title the stream declares. A title is not proof of the source."""
    clean = (title or "").strip()
    low = clean.lower()
    if low in DEFAULT_TITLES:
        return ORIGIN_UNKNOWN, "Origen desconocido (el flujo no se identifica)"
    if any(m in low for m in TEST_MARKERS):
        return ORIGIN_TEST, f"Origen declarado: fuente de prueba («{clean}»)"
    if any(m in low for m in CAMERA_MARKERS):
        return ORIGIN_CAMERA, f"Origen declarado: cámara («{clean}») · no verificado"
    return ORIGIN_UNKNOWN, f"Origen desconocido · título del flujo: «{clean}»"


def classify_error(exc: BaseException) -> tuple:
    """(state, short Spanish reason) for an exception of av.open / decode."""
    name = type(exc).__name__
    if name in ("ExitError", "TimeoutError", "EOFError") or isinstance(exc, (TimeoutError, EOFError)):
        return NO_SIGNAL, "sin datos dentro del tiempo de espera"
    if name == "ConnectionRefusedError" or isinstance(exc, ConnectionRefusedError):
        return ERROR, "conexión rechazada (¿servidor RTSP arrancado?)"
    if name == "HTTPNotFoundError":
        return ERROR, "ruta RTSP no encontrada en el servidor"
    if name in ("HTTPUnauthorizedError", "HTTPForbiddenError"):
        return ERROR, "el servidor RTSP exige credenciales"
    if name == "InvalidDataError":
        return ERROR, "datos no válidos (¿protocolo, puerto o SDP incorrectos?)"
    if isinstance(exc, OSError):
        return ERROR, f"error de red: {exc.strerror or exc}"
    return ERROR, f"{name}: {exc}"


@dataclass
class VideoSnapshot:
    state: str
    label: str
    color: str
    protocol: str
    resolution: Optional[str]
    fps: float
    age_ms: Optional[float]
    origin_kind: str
    origin_text: str
    reason: Optional[str]
    codec: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    frames: int = 0
    attempts: int = 0
    last_error: Optional[str] = None

    def summary(self) -> str:
        """Compact line: protocol · resolution · FPS · age (only what is known)."""
        parts = [self.protocol]
        if self.resolution:
            parts.append(self.resolution)
        if self.state == LIVE:
            parts.append(f"{self.fps:.1f} FPS")
            if self.age_ms is not None:
                parts.append(f"{self.age_ms:.0f} ms")
        return " · ".join(parts)


@dataclass
class _Session:
    generation: int = -1
    protocol: str = "—"
    source: Optional[str] = None
    attempts: int = 0
    failures_without_frame: int = 0
    opened: bool = False
    codec: Optional[str] = None
    title: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    frames: int = 0
    opened_at: Optional[float] = None
    last_frame_at: Optional[float] = None
    frame_times: collections.deque = field(default_factory=lambda: collections.deque(maxlen=120))
    error_state: Optional[str] = None
    reason: Optional[str] = None
    last_error: Optional[str] = None


class VideoStatusTracker:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._s = _Session()

    # -- events (receiver thread) -------------------------------------------
    def set_source(self, generation: int, protocol: Optional[str], source: Optional[str]) -> None:
        with self._lock:
            self._s = _Session(generation=generation, protocol=protocol or "—", source=source)

    def attempt_started(self, generation: int) -> None:
        with self._lock:
            if generation == self._s.generation:
                self._s.attempts += 1
                self._s.opened = False

    def stream_opened(self, generation: int, codec: Optional[str], title: Optional[str]) -> None:
        with self._lock:
            if generation == self._s.generation:
                self._s.opened = True
                self._s.opened_at = self._clock()
                self._s.frame_times.clear()  # the FPS window restarts with each stream
                self._s.codec = codec
                self._s.title = title

    def frame(self, generation: int, width: int, height: int, at: Optional[float] = None) -> None:
        with self._lock:
            s = self._s
            if generation != s.generation:
                return
            at = self._clock() if at is None else at
            s.width, s.height = width, height
            s.frames += 1
            s.last_frame_at = at
            s.frame_times.append(at)
            s.failures_without_frame = 0
            s.error_state = None
            s.reason = None

    def attempt_failed(self, generation: int, exc: BaseException) -> None:
        state, reason = classify_error(exc)
        with self._lock:
            s = self._s
            if generation != s.generation:
                return
            s.opened = False
            s.failures_without_frame += 1
            s.error_state = state
            s.reason = reason
            s.last_error = f"{type(exc).__name__}: {exc}"

    def stream_ended(self, generation: int) -> None:
        with self._lock:
            if generation == self._s.generation:
                self._s.opened = False
                self._s.reason = "el flujo se interrumpió"

    # -- query (UI) ----------------------------------------------------------
    def snapshot(self, stale_s: float = 2.0) -> VideoSnapshot:
        with self._lock:
            s = self._s
            now = self._clock()
            age = None if s.last_frame_at is None else max(0.0, now - s.last_frame_at)
            warm = (s.opened_at or float("-inf")) + FPS_WARMUP_S
            recent = [t for t in s.frame_times if now - t <= FPS_WINDOW_S and t >= warm]
            fps = (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) >= 2 and recent[-1] > recent[0] else 0.0

            if s.source is None:
                state = DISABLED
            elif age is not None and age <= stale_s:
                state = LIVE
            elif s.error_state == ERROR:
                state = ERROR
            elif s.frames > 0 or s.failures_without_frame >= CONNECTING_ATTEMPTS:
                state = NO_SIGNAL
            else:
                state = CONNECTING

            origin_kind, origin_text = classify_origin(s.title) if s.opened or s.frames else (
                ORIGIN_UNKNOWN, "Origen desconocido (sin flujo)")
            reason = None
            if state in (NO_SIGNAL, ERROR):
                reason = s.reason or ("no llegan fotogramas" if s.frames else None)
            return VideoSnapshot(
                state=state,
                label=LABELS[state],
                color=COLORS[state],
                protocol=s.protocol,
                resolution=f"{s.width}×{s.height}" if s.width and s.height else None,
                fps=fps if state == LIVE else 0.0,
                age_ms=None if age is None else age * 1000.0,
                origin_kind=origin_kind,
                origin_text=origin_text,
                reason=reason,
                codec=s.codec,
                title=s.title,
                source=s.source,
                frames=s.frames,
                attempts=s.attempts,
                last_error=s.last_error,
            )
