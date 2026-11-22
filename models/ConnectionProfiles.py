"""Persistent connection profiles for SafeFlight Desktop.

A connection profile groups every network parameter that changes when the
physical link changes (SIYI local link, 5G/VPN, SITL): the MAVLink endpoint,
the video source and the supervision timeouts. Profiles are stored as JSON
in the per-user configuration directory, so IP addresses and ports can be
modified from the user interface without editing Python code or rebuilding.

The JSON layout follows ``shared/schemas/connection-profiles.schema.json``,
which is also implemented by SafeFlight Android.

This module has no GUI dependency and is covered by ``tests/desktop``.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from .AppPaths import legacy_config_dirs, user_config_dir

SCHEMA_VERSION = 1
PROFILES_FILE_NAME = "connection_profiles.json"
LEGACY_VIDEO_FILE_NAME = "video_settings.json"

PROFILE_KINDS = ("siyi_local", "cellular_vpn", "sitl", "custom")
MAVLINK_TRANSPORTS = ("udp_listen", "udp_connect", "tcp_client", "serial", "custom")
VIDEO_MODES = ("rtp_udp", "rtsp", "none")
RTSP_TRANSPORTS = ("tcp", "udp")

# Historical default used by SafeFlight Desktop up to v0.2 (SITL and 5G).
LEGACY_MAVLINK_PORT = 14560
LEGACY_RTP_PORT = 5004
LEGACY_RTSP_URL = "rtsp://192.168.144.30:8554/raspicam"

_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*$")
_CONTROL_CHARS = ("\n", "\r", "\t", "\x00")

# Numeric limits (min, max) for every timeout field.
TIMEOUT_LIMITS: Dict[str, Tuple[float, float]] = {
    "connect_timeout_s": (5.0, 300.0),
    "heartbeat_timeout_s": (5.0, 120.0),
    "telemetry_stale_s": (0.5, 60.0),
    "video_stale_s": (0.5, 60.0),
    "video_reconnect_interval_s": (0.2, 30.0),
}


class ProfileValidationError(ValueError):
    """Raised when a profile contains invalid values. ``errors`` lists them."""

    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class MavlinkEndpoint:
    transport: str = "udp_listen"
    local_host: str = "0.0.0.0"
    local_port: int = LEGACY_MAVLINK_PORT
    remote_host: str = ""
    remote_port: int = 14550
    serial_device: str = ""
    baud_rate: int = 57600
    connection_string: str = ""


@dataclass
class VideoSource:
    mode: str = "rtp_udp"
    rtp_udp_port: int = LEGACY_RTP_PORT
    rtsp_url: str = LEGACY_RTSP_URL
    rtsp_transport: str = "tcp"


@dataclass
class Timeouts:
    connect_timeout_s: float = 90.0
    heartbeat_timeout_s: float = 30.0
    telemetry_stale_s: float = 3.0
    video_stale_s: float = 2.0
    video_reconnect_interval_s: float = 1.0


@dataclass
class Diagnostics:
    verbose_logging: bool = False


@dataclass
class ConnectionProfile:
    id: str
    name: str
    kind: str = "custom"
    builtin: bool = False
    notes: str = ""
    mavlink: MavlinkEndpoint = field(default_factory=MavlinkEndpoint)
    video: VideoSource = field(default_factory=VideoSource)
    timeouts: Timeouts = field(default_factory=Timeouts)
    diagnostics: Diagnostics = field(default_factory=Diagnostics)

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "builtin": self.builtin,
            "notes": self.notes,
            "mavlink": dict(vars(self.mavlink)),
            "video": dict(vars(self.video)),
            "timeouts": dict(vars(self.timeouts)),
            "diagnostics": dict(vars(self.diagnostics)),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectionProfile":
        """Build a profile from JSON data, ignoring unknown keys.

        Missing keys take their defaults, which keeps files written by
        newer versions (with additional fields) readable. The result is
        validated; :class:`ProfileValidationError` is raised on bad data.
        """
        if not isinstance(data, dict):
            raise ProfileValidationError(["profile must be a JSON object"])

        def section(name: str, klass):
            raw = data.get(name) or {}
            if not isinstance(raw, dict):
                raise ProfileValidationError([f"{name} must be a JSON object"])
            known = {k: raw[k] for k in vars(klass()) if k in raw}
            return klass(**known)

        profile = cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            kind=str(data.get("kind", "custom")),
            builtin=bool(data.get("builtin", False)),
            notes=str(data.get("notes", "")),
            mavlink=section("mavlink", MavlinkEndpoint),
            video=section("video", VideoSource),
            timeouts=section("timeouts", Timeouts),
            diagnostics=section("diagnostics", Diagnostics),
        )
        profile.normalise()
        validate_profile(profile)
        return profile

    def copy(self) -> "ConnectionProfile":
        return copy.deepcopy(self)

    def normalise(self) -> None:
        """Coerce numeric fields and strip whitespace (raises on bad types)."""
        errors: List[str] = []
        m = self.mavlink
        for attr in ("local_port", "remote_port", "baud_rate"):
            try:
                setattr(m, attr, int(getattr(m, attr)))
            except (TypeError, ValueError):
                errors.append(f"mavlink.{attr} must be an integer")
        for attr in ("transport", "local_host", "remote_host", "serial_device", "connection_string"):
            setattr(m, attr, str(getattr(m, attr) or "").strip())
        v = self.video
        try:
            v.rtp_udp_port = int(v.rtp_udp_port)
        except (TypeError, ValueError):
            errors.append("video.rtp_udp_port must be an integer")
        v.mode = str(v.mode or "").strip()
        v.rtsp_url = str(v.rtsp_url or "").strip()
        v.rtsp_transport = str(v.rtsp_transport or "tcp").strip().lower()
        for attr in TIMEOUT_LIMITS:
            try:
                setattr(self.timeouts, attr, float(getattr(self.timeouts, attr)))
            except (TypeError, ValueError):
                errors.append(f"timeouts.{attr} must be a number")
        self.diagnostics.verbose_logging = bool(self.diagnostics.verbose_logging)
        self.id = self.id.strip()
        self.name = self.name.strip()
        if errors:
            raise ProfileValidationError(errors)

    # -- derived values -----------------------------------------------------
    def mavlink_connection_string(self) -> str:
        """Connection string understood by pymavlink/DroneKit."""
        m = self.mavlink
        if m.transport == "udp_listen":
            return f"udpin:{m.local_host}:{m.local_port}"
        if m.transport == "udp_connect":
            return f"udpout:{m.remote_host}:{m.remote_port}"
        if m.transport == "tcp_client":
            return f"tcp:{m.remote_host}:{m.remote_port}"
        if m.transport == "serial":
            return m.serial_device
        return m.connection_string

    def video_summary(self) -> str:
        v = self.video
        if v.mode == "rtsp":
            return f"RTSP {redact_url(v.rtsp_url)} ({v.rtsp_transport.upper()})"
        if v.mode == "rtp_udp":
            return f"RTP/UDP :{v.rtp_udp_port}"
        return "Sin vídeo"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _valid_port(value: Any, low: int = 1) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= 65535


def valid_host(host: str) -> bool:
    if not host or any(c in host for c in _CONTROL_CHARS) or " " in host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return bool(_HOSTNAME_RE.match(host))


def valid_rtsp_url(url: str) -> bool:
    if not isinstance(url, str) or not url or len(url) > 1024:
        return False
    if any(c in url for c in _CONTROL_CHARS):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return parts.scheme in ("rtsp", "rtsps") and bool(parts.hostname) and (port is None or 1 <= port <= 65535)


def redact_url(url: str) -> str:
    """Hide the password of ``rtsp://user:pass@host`` URLs in logs and UI."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if parts.password:
        netloc = f"{parts.username}:***@{parts.hostname}"
        if parts.port:
            netloc += f":{parts.port}"
        return parts._replace(netloc=netloc).geturl()
    return url


def validate_profile(profile: ConnectionProfile) -> None:
    errors: List[str] = []
    if not _PROFILE_ID_RE.match(profile.id or ""):
        errors.append("id must use lowercase letters, digits, '-' or '_' (max 48)")
    if not profile.name or len(profile.name) > 64:
        errors.append("name is required (max 64 characters)")
    if profile.kind not in PROFILE_KINDS:
        errors.append(f"kind must be one of {', '.join(PROFILE_KINDS)}")

    m = profile.mavlink
    if m.transport not in MAVLINK_TRANSPORTS:
        errors.append(f"mavlink.transport must be one of {', '.join(MAVLINK_TRANSPORTS)}")
    elif m.transport == "udp_listen":
        if not valid_host(m.local_host):
            errors.append("mavlink.local_host must be an IP address or hostname")
        if not _valid_port(m.local_port, 1024):
            errors.append("mavlink.local_port must be between 1024 and 65535")
    elif m.transport in ("udp_connect", "tcp_client"):
        if not valid_host(m.remote_host):
            errors.append("mavlink.remote_host must be an IP address or hostname")
        if not _valid_port(m.remote_port):
            errors.append("mavlink.remote_port must be between 1 and 65535")
    elif m.transport == "serial":
        if not m.serial_device or any(c in m.serial_device for c in _CONTROL_CHARS):
            errors.append("mavlink.serial_device is required for serial transport")
        if m.baud_rate not in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 1500000):
            errors.append("mavlink.baud_rate is not a standard rate")
    elif m.transport == "custom":
        if not m.connection_string or any(c in m.connection_string for c in _CONTROL_CHARS):
            errors.append("mavlink.connection_string is required for custom transport")

    v = profile.video
    if v.mode not in VIDEO_MODES:
        errors.append(f"video.mode must be one of {', '.join(VIDEO_MODES)}")
    if not _valid_port(v.rtp_udp_port, 1024):
        errors.append("video.rtp_udp_port must be between 1024 and 65535")
    if v.mode == "rtsp" and not valid_rtsp_url(v.rtsp_url):
        errors.append("video.rtsp_url must look like rtsp://host:port/path")
    if v.rtsp_transport not in RTSP_TRANSPORTS:
        errors.append("video.rtsp_transport must be tcp or udp")

    for attr, (low, high) in TIMEOUT_LIMITS.items():
        value = getattr(profile.timeouts, attr)
        if not isinstance(value, (int, float)) or not low <= value <= high:
            errors.append(f"timeouts.{attr} must be between {low:g} and {high:g}")

    if errors:
        raise ProfileValidationError(errors)


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------
def default_profiles() -> List[ConnectionProfile]:
    """Factory profiles. Values marked as provisional must be verified."""
    return [
        ConnectionProfile(
            id="siyi-local",
            name="SIYI LOCAL",
            kind="siyi_local",
            builtin=True,
            notes=(
                "Enlace local a través de SIYI (red 192.168.144.0/24). "
                "Valores PROVISIONALES: verificar la IP de la Raspberry y el "
                "reenvío MAVLink en la red SIYI antes de usar."
            ),
            mavlink=MavlinkEndpoint(transport="udp_listen", local_host="0.0.0.0", local_port=LEGACY_MAVLINK_PORT),
            video=VideoSource(mode="rtsp", rtp_udp_port=LEGACY_RTP_PORT, rtsp_url=LEGACY_RTSP_URL, rtsp_transport="tcp"),
            timeouts=Timeouts(),
        ),
        ConnectionProfile(
            id="cellular-vpn",
            name="5G / VPN",
            kind="cellular_vpn",
            builtin=True,
            notes=(
                "Configuración vigente hasta v0.2: MAVProxy en la Raspberry "
                "reenvía MAVLink a este equipo (UDP 14560) y el vídeo H.264 "
                "llega por RTP/UDP 5004."
            ),
            mavlink=MavlinkEndpoint(transport="udp_listen", local_host="0.0.0.0", local_port=LEGACY_MAVLINK_PORT),
            video=VideoSource(mode="rtp_udp", rtp_udp_port=LEGACY_RTP_PORT, rtsp_url=LEGACY_RTSP_URL),
            timeouts=Timeouts(),
        ),
        ConnectionProfile(
            id="raspberry-lab",
            name="RASPBERRY / CUBE (LAB)",
            kind="custom",
            builtin=True,
            notes=(
                "Raspberry Pi del laboratorio (172.16.15.85) con Cube Orange en /dev/ttyACM0 a 57600. MAVProxy reenvía MAVLink a este equipo. Verificar la IP del equipo antes de conectar; primera conexión siempre en SOLO MONITORIZACIÓN. Vídeo: RTP/UDP 5004 desde rpicam-vid; alternativa RTSP "
                "(MediaMTX en la Raspberry) en rtsp://172.16.15.85:8554/cam."
            ),
            mavlink=MavlinkEndpoint(transport="udp_listen", local_host="0.0.0.0", local_port=LEGACY_MAVLINK_PORT),
            video=VideoSource(mode="rtp_udp", rtp_udp_port=LEGACY_RTP_PORT,
                              rtsp_url="rtsp://172.16.15.85:8554/cam", rtsp_transport="tcp"),
            timeouts=Timeouts(),
        ),
        ConnectionProfile(
            id="sitl",
            name="SITL / SIMULACIÓN",
            kind="sitl",
            builtin=True,
            notes=(
                "ArduPilot SITL o el generador de pruebas "
                "scripts/mavlink_test_sender.py enviando a UDP 14560."
            ),
            mavlink=MavlinkEndpoint(transport="udp_listen", local_host="0.0.0.0", local_port=LEGACY_MAVLINK_PORT),
            video=VideoSource(mode="rtp_udp", rtp_udp_port=LEGACY_RTP_PORT, rtsp_url=LEGACY_RTSP_URL),
            timeouts=Timeouts(),
        ),
    ]


def builtin_default(profile_id: str) -> Optional[ConnectionProfile]:
    for profile in default_profiles():
        if profile.id == profile_id:
            return profile
    return None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
class ProfileStore:
    """Load, edit and atomically persist the profile collection."""

    def __init__(self, config_dir: Optional[Path] = None, environ: Optional[Dict[str, str]] = None):
        self.config_dir = Path(config_dir) if config_dir else user_config_dir()
        self.path = self.config_dir / PROFILES_FILE_NAME
        self._environ = dict(os.environ if environ is None else environ)
        self.profiles: List[ConnectionProfile] = []
        self.active_profile_id: str = ""
        self.warnings: List[str] = []

    # -- loading -------------------------------------------------------------
    def load(self) -> "ProfileStore":
        """Load profiles; create defaults (with migration) when absent.

        A corrupt file is preserved as ``*.corrupt-<timestamp>`` and replaced
        by defaults so that the application can still start.
        """
        self.warnings = []
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                self._load_data(data)
                return self
            except (OSError, ValueError) as exc:
                backup = self._quarantine_corrupt_file()
                self.warnings.append(
                    f"Perfiles ilegibles ({exc}); se restauran los valores por defecto. "
                    f"Copia conservada en {backup}"
                )
        self._create_defaults_with_migration()
        try:
            self.save()
        except OSError as exc:
            self.warnings.append(f"No se pudo guardar la configuración inicial: {exc}")
        return self

    def _load_data(self, data: Any) -> None:
        if not isinstance(data, dict):
            raise ValueError("root must be a JSON object")
        version = data.get("schema_version", SCHEMA_VERSION)
        if not isinstance(version, int) or version > SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {version!r}")
        raw_profiles = data.get("profiles")
        if not isinstance(raw_profiles, list):
            raise ValueError("profiles must be a list")

        profiles: List[ConnectionProfile] = []
        seen = set()
        for index, raw in enumerate(raw_profiles):
            try:
                profile = ConnectionProfile.from_dict(raw)
            except ProfileValidationError as exc:
                self.warnings.append(f"Perfil #{index} ignorado: {exc}")
                continue
            if profile.id in seen:
                self.warnings.append(f"Perfil duplicado ignorado: {profile.id}")
                continue
            seen.add(profile.id)
            profiles.append(profile)

        # Built-in profiles that were removed from the file are restored.
        for builtin in default_profiles():
            if builtin.id not in seen:
                profiles.append(builtin)
                seen.add(builtin.id)

        self.profiles = profiles
        active = data.get("active_profile_id")
        self.active_profile_id = active if active in seen else profiles[0].id

    def _quarantine_corrupt_file(self) -> Optional[Path]:
        backup = self.path.with_name(f"{self.path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            os.replace(self.path, backup)
            return backup
        except OSError:
            return None

    def _create_defaults_with_migration(self) -> None:
        profiles = default_profiles()
        by_id = {p.id: p for p in profiles}

        legacy_video = self._read_legacy_video_settings()
        if legacy_video is not None:
            target = by_id["cellular-vpn"]
            mode, port, url = legacy_video
            target.video.rtp_udp_port = port
            if url:
                target.video.rtsp_url = url
                by_id["siyi-local"].video.rtsp_url = url
            target.video.mode = "rtsp" if mode == "rtsp" else "rtp_udp"
            self.warnings.append("Configuración de vídeo anterior migrada al perfil 5G / VPN.")

        # Connection strings previously supplied through .env are kept.
        for env_name, profile_id in (("SIM_conn_str", "sitl"), ("REAL_conn_str", "cellular-vpn")):
            value = (self._environ.get(env_name) or "").strip()
            if value and not any(c in value for c in _CONTROL_CHARS):
                endpoint = by_id[profile_id].mavlink
                parsed = parse_connection_string(value)
                if parsed is not None:
                    by_id[profile_id].mavlink = parsed
                else:
                    endpoint.transport = "custom"
                    endpoint.connection_string = value
                self.warnings.append(f"{env_name} migrado al perfil {by_id[profile_id].name}.")

        env_mode = (self._environ.get("ENV_MODE") or "dev").strip().lower()
        self.profiles = profiles
        self.active_profile_id = "cellular-vpn" if env_mode == "prod" else "sitl"

    def _read_legacy_video_settings(self) -> Optional[Tuple[str, int, str]]:
        for directory in [self.config_dir, *legacy_config_dirs()]:
            path = Path(directory) / LEGACY_VIDEO_FILE_NAME
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                port = int(data.get("rtp_udp_port", LEGACY_RTP_PORT))
                if not 1024 <= port <= 65535:
                    port = LEGACY_RTP_PORT
                url = data.get("rtsp_url", "")
                url = url if valid_rtsp_url(url) else ""
                mode = data.get("video_mode", "rtp")
                return (mode if mode in ("rtp", "rtsp") else "rtp", port, url)
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        return None

    # -- saving --------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "active_profile_id": self.active_profile_id,
            "profiles": [p.to_dict() for p in self.profiles],
        }

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    # -- queries -------------------------------------------------------------
    def get(self, profile_id: str) -> Optional[ConnectionProfile]:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        return None

    @property
    def active(self) -> ConnectionProfile:
        profile = self.get(self.active_profile_id)
        if profile is None:
            profile = self.profiles[0]
            self.active_profile_id = profile.id
        return profile

    # -- mutations (callers persist with save()) ------------------------------
    def select(self, profile_id: str) -> ConnectionProfile:
        profile = self.get(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        self.active_profile_id = profile_id
        return profile

    def upsert(self, profile: ConnectionProfile) -> ConnectionProfile:
        profile = profile.copy()
        profile.normalise()
        validate_profile(profile)
        existing = self.get(profile.id)
        if existing is not None:
            profile.builtin = existing.builtin
            self.profiles[self.profiles.index(existing)] = profile
        else:
            profile.builtin = False
            self.profiles.append(profile)
        return profile

    def duplicate(self, profile_id: str, new_name: Optional[str] = None) -> ConnectionProfile:
        source = self.get(profile_id)
        if source is None:
            raise KeyError(profile_id)
        clone = source.copy()
        clone.builtin = False
        clone.kind = source.kind
        clone.name = (new_name or f"{source.name} (copia)")[:64]
        clone.id = self._unique_id(source.id + "-copy")
        self.profiles.append(clone)
        return clone

    def delete(self, profile_id: str) -> None:
        profile = self.get(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        if profile.builtin:
            raise ValueError("built-in profiles cannot be deleted; use restore instead")
        self.profiles.remove(profile)
        if self.active_profile_id == profile_id:
            self.active_profile_id = self.profiles[0].id

    def restore_builtin(self, profile_id: str) -> ConnectionProfile:
        default = builtin_default(profile_id)
        if default is None:
            raise ValueError("only built-in profiles can be restored")
        existing = self.get(profile_id)
        if existing is None:
            self.profiles.append(default)
        else:
            self.profiles[self.profiles.index(existing)] = default
        return default

    def new_profile_id(self, base: str = "custom") -> str:
        return self._unique_id(base)

    def _unique_id(self, base: str) -> str:
        base = re.sub(r"[^a-z0-9_-]", "-", base.lower())[:40] or "profile"
        candidate = base
        counter = 2
        while self.get(candidate) is not None:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate


# ---------------------------------------------------------------------------
# Connection string parsing (migration from .env and legacy strings)
# ---------------------------------------------------------------------------
def parse_connection_string(value: str) -> Optional[MavlinkEndpoint]:
    """Translate ``udpin:``, ``udpout:``, ``udp:`` or ``tcp:`` strings.

    Returns ``None`` for strings that cannot be represented by structured
    fields (they are then stored as ``custom``).
    """
    match = re.match(r"^(udpin|udpout|udp|tcp):([^:]+):(\d{1,5})$", value.strip())
    if not match:
        return None
    scheme, host, port_text = match.groups()
    port = int(port_text)
    if not 1 <= port <= 65535 or not valid_host(host):
        return None
    if scheme in ("udpin", "udp"):
        if port < 1024:
            return None
        return MavlinkEndpoint(transport="udp_listen", local_host=host, local_port=port)
    if scheme == "udpout":
        return MavlinkEndpoint(transport="udp_connect", remote_host=host, remote_port=port)
    return MavlinkEndpoint(transport="tcp_client", remote_host=host, remote_port=port)


def write_runtime_sdp(directory: Path, port: int) -> Path:
    """Write the SDP description used by FFmpeg/PyAV to receive RTP H.264."""
    if not 1024 <= int(port) <= 65535:
        raise ValueError("RTP port out of range")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "stream_runtime.sdp"
    sdp_text = (
        "v=0\n"
        "o=- 0 0 IN IP4 0.0.0.0\n"
        "s=SafeFlight Desktop RTP receiver\n"
        "c=IN IP4 0.0.0.0\n"
        "t=0 0\n"
        "a=tool:SafeFlightDesktop\n"
        f"m=video {int(port)} RTP/AVP 96\n"
        "a=rtpmap:96 H264/90000\n"
        "a=fmtp:96 packetization-mode=1\n"
        "a=recvonly\n"
    )
    with open(path, "w", encoding="ascii", newline="\n") as handle:
        handle.write(sdp_text)
    return path
