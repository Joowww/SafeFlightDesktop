"""Platform-aware locations for resources, user configuration and logs.

The application must never write next to its executable: on macOS the
``.app`` bundle is read-only once signed, on Linux the package may live in
``/opt`` and on Windows in ``Program Files``. User data therefore goes to
the directory conventionally used by each operating system.

Windows keeps the historical location (``%APPDATA%\\SafeFlightDesktop``)
so that existing ``video_settings.json`` files remain readable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

APP_DIR_NAME = "SafeFlightDesktop"
CONFIG_DIR_ENV = "SAFEFLIGHT_CONFIG_DIR"
LOG_DIR_ENV = "SAFEFLIGHT_LOG_DIR"


def platform_key() -> str:
    """Return ``windows``, ``macos`` or ``linux`` (other POSIX -> linux)."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def resource_dir() -> Path:
    """Directory holding bundled read-only resources (assets, SDP template).

    In a PyInstaller build the resources are unpacked under ``sys._MEIPASS``;
    in development they live at the repository root.
    """
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir)
    return Path(__file__).resolve().parent.parent


def user_config_dir() -> Path:
    """Writable per-user configuration directory (not created here)."""
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()

    key = platform_key()
    home = Path.home()
    if key == "windows":
        base = os.environ.get("APPDATA")
        return Path(base) / APP_DIR_NAME if base else home / APP_DIR_NAME
    if key == "macos":
        return home / "Library" / "Application Support" / APP_DIR_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg) if xdg else home / ".config"
    return base_dir / APP_DIR_NAME


def user_log_dir() -> Path:
    """Writable per-user log directory (not created here)."""
    override = os.environ.get(LOG_DIR_ENV)
    if override:
        return Path(override).expanduser()

    key = platform_key()
    home = Path.home()
    if key == "windows":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return (Path(base) if base else home) / APP_DIR_NAME / "logs"
    if key == "macos":
        return home / "Library" / "Logs" / APP_DIR_NAME
    state = os.environ.get("XDG_STATE_HOME")
    base_dir = Path(state) if state else home / ".local" / "state"
    return base_dir / APP_DIR_NAME / "logs"


def legacy_config_dirs() -> List[Path]:
    """Locations used by earlier versions, consulted only for migration.

    Before v0.3.0 the configuration directory was ``%APPDATA%`` or, when
    that variable did not exist (macOS/Linux), ``~/SafeFlightDesktop``.
    """
    candidates: List[Path] = []
    if os.environ.get(CONFIG_DIR_ENV):
        return candidates
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / APP_DIR_NAME)
    candidates.append(Path.home() / APP_DIR_NAME)
    current = user_config_dir()
    unique: List[Path] = []
    for path in candidates:
        if path != current and path not in unique:
            unique.append(path)
    return unique
