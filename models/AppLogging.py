"""Session log files for diagnostics on every platform.

SafeFlight Desktop reports its activity through ``print``. A packaged
macOS ``.app`` or a Linux desktop launcher has no visible console, so this
module duplicates standard output and standard error into a per-session log
file in the user log directory. The original streams are preserved, so the
Windows console build keeps its current behaviour.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Optional, TextIO

from .AppPaths import user_log_dir

MAX_SESSION_LOGS = 10


class _TeeStream:
    def __init__(self, original: Optional[TextIO], log_file: TextIO, lock: threading.Lock):
        self._original = original
        self._log_file = log_file
        self._lock = lock

    def write(self, text: str) -> int:
        if self._original is not None:
            try:
                self._original.write(text)
            except Exception:
                pass
        with self._lock:
            try:
                self._log_file.write(text)
                if "\n" in text:
                    self._log_file.flush()
            except Exception:
                pass
        return len(text)

    def flush(self) -> None:
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass
        with self._lock:
            try:
                self._log_file.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return bool(self._original is not None and getattr(self._original, "isatty", lambda: False)())

    @property
    def encoding(self) -> str:
        return getattr(self._original, "encoding", "utf-8") or "utf-8"


_active_log_path: Optional[Path] = None


def start_session_log(log_dir: Optional[Path] = None) -> Optional[Path]:
    """Start mirroring stdout/stderr to a new log file. Idempotent."""
    global _active_log_path
    if _active_log_path is not None:
        return _active_log_path
    directory = Path(log_dir) if log_dir else user_log_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        _prune_old_logs(directory)
        path = directory / f"safeflight-{time.strftime('%Y%m%d-%H%M%S')}.log"
        log_file = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    lock = threading.Lock()
    sys.stdout = _TeeStream(sys.stdout, log_file, lock)
    sys.stderr = _TeeStream(sys.stderr, log_file, lock)
    _active_log_path = path
    print(f"[LOG] Registro de sesión: {path}", flush=True)
    return path


def active_log_path() -> Optional[Path]:
    return _active_log_path


def _prune_old_logs(directory: Path) -> None:
    logs = sorted(directory.glob("safeflight-*.log"))
    for old in logs[: max(0, len(logs) - (MAX_SESSION_LOGS - 1))]:
        try:
            old.unlink()
        except OSError:
            pass
