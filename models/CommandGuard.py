"""Central authorisation of every command sent to the vehicle.

SafeFlight Desktop starts in MONITOR mode: only telemetry-related messages
(heartbeats, parameter and stream requests) can leave the application. Any
message that can change the vehicle state (arming, mode changes, take-off,
position or velocity targets, parameter writes, missions...) is dropped at the
transport layer unless a permit issued by :meth:`CommandGuard.request` matches
it. Permits are only issued during an operator-authorised control session
whose preconditions are re-checked for every command.

The filter wraps ``write()`` of the pymavlink connection used by DroneKit, the
single point through which all outgoing bytes pass (DroneKit's output thread
and pymavlink after a MAVLink 2 switch). Legacy code paths that bypass the
guard (``vehicle.mode = ...``, ``vehicle.armed = ...``, ``send_mavlink``) are
therefore blocked as well.

States
------
MONITOR     default; no control command is ever sent.
AUTHORIZED  explicit operator session for one identified vehicle; expires.
SUSPENDED   link or identity problem during a session; only LAND/RTL requests
            (pilot-requested emergency actions) are accepted. A new
            authorisation is required to resume normal control.

The application never sends commands on its own: there is no automatic
LAND/RTL. Loss-of-link recovery is the job of the autopilot failsafes and of
the RC pilot.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from pymavlink.dialects.v20 import ardupilotmega as mavlink2

MONITOR = "MONITOR"
AUTHORIZED = "AUTHORIZED"
SUSPENDED = "SUSPENDED"

# Command kinds requested by the application.
ARM = "ARM"
DISARM = "DISARM"
MODE = "MODE"
TAKEOFF = "TAKEOFF"
LAND = "LAND"
RTL = "RTL"
VELOCITY = "VELOCITY"
POSITION = "POSITION"
YAW = "YAW"

EMERGENCY_KINDS = {LAND, RTL}
MOVEMENT_KINDS = {VELOCITY, POSITION, YAW}

ARDUCOPTER_MODES = {
    "STABILIZE": 0, "ACRO": 1, "ALT_HOLD": 2, "AUTO": 3, "GUIDED": 4, "LOITER": 5,
    "RTL": 6, "CIRCLE": 7, "LAND": 9, "DRIFT": 11, "SPORT": 13, "FLIP": 14,
    "AUTOTUNE": 15, "POSHOLD": 16, "BRAKE": 17, "THROW": 18, "AVOID_ADSB": 19,
    "GUIDED_NOGPS": 20, "SMART_RTL": 21, "FLOWHOLD": 22, "FOLLOW": 23, "ZIGZAG": 24,
    "SYSTEMID": 25, "AUTOROTATE": 26, "AUTO_RTL": 27,
}
# Modes the application may request explicitly.
REQUESTABLE_MODES = {"GUIDED", "LAND", "RTL", "LOITER", "ALT_HOLD", "STABILIZE"}

# Messages that never change the vehicle state.
READ_ONLY_MESSAGES = {
    "HEARTBEAT", "PARAM_REQUEST_LIST", "PARAM_REQUEST_READ", "REQUEST_DATA_STREAM",
    "MISSION_REQUEST_LIST", "MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK",
    "TIMESYNC", "SYSTEM_TIME", "AUTOPILOT_VERSION_REQUEST",
}
READ_ONLY_COMMANDS = {
    mavlink2.MAV_CMD_SET_MESSAGE_INTERVAL,              # 511
    mavlink2.MAV_CMD_REQUEST_MESSAGE,                   # 512
    mavlink2.MAV_CMD_REQUEST_PROTOCOL_VERSION,          # 519
    mavlink2.MAV_CMD_REQUEST_AUTOPILOT_CAPABILITIES,    # 520
}
FORCE_ARM_MAGIC = 21196  # forced arm/disarm bypasses autopilot checks: never allowed

# Limits and timings (seconds / metres).
HEARTBEAT_MAX_AGE_S = 2.0
DUPLICATE_WINDOW_S = 2.0
PERMIT_TTL_S = 3.0
SESSION_DURATION_S = 20 * 60
MAX_TAKEOFF_ALT_M = 10.0
MIN_TAKEOFF_ALT_M = 1.0
MIN_GPS_FIX = 3


@dataclass
class Snapshot:
    """Telemetry needed to decide on a command (from DroneKit)."""
    connected: bool = False
    system_id: Optional[int] = None
    component_id: Optional[int] = None
    vehicle_type: Optional[str] = None
    heartbeat_age_s: Optional[float] = None
    armed: Optional[bool] = None
    mode: Optional[str] = None
    gps_fix: Optional[int] = None
    satellites: Optional[int] = None


@dataclass
class Decision:
    allowed: bool
    reason: str
    kind: str = ""

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class Permit:
    kind: str
    predicate: Callable[[object], bool]
    expires_at: float
    description: str


@dataclass
class AuditEntry:
    at: float
    event: str
    detail: str


@dataclass
class Session:
    system_id: int
    component_id: int
    vehicle_type: Optional[str]
    started_at: float
    expires_at: float


def classify(msg) -> str:
    """Returns 'read_only' or 'control' for a decoded pymavlink message."""
    mtype = msg.get_type()
    if mtype in READ_ONLY_MESSAGES:
        return "read_only"
    if mtype == "COMMAND_LONG" and msg.command in READ_ONLY_COMMANDS:
        return "read_only"
    return "control"


def _mode_id(name: str) -> Optional[int]:
    return ARDUCOPTER_MODES.get(name)


def _matches_mode(msg, mode_id: int) -> bool:
    mtype = msg.get_type()
    if mtype == "SET_MODE":
        return int(msg.custom_mode) == mode_id
    if mtype == "COMMAND_LONG" and msg.command == mavlink2.MAV_CMD_DO_SET_MODE:
        return int(msg.param2) == mode_id
    return False


def _is_command(msg, command: int) -> bool:
    return msg.get_type() == "COMMAND_LONG" and msg.command == command


class CommandGuard:
    def __init__(self, clock: Callable[[], float] = time.monotonic, log: Callable[[str], None] = print):
        self._clock = clock
        self._log = log
        self._lock = threading.RLock()
        self.state = MONITOR
        self.session: Optional[Session] = None
        self.suspend_reason = ""
        self._permits: List[Permit] = []
        self._last_request: Dict[str, float] = {}
        self.audit: List[AuditEntry] = []
        self._blocked_counts: Dict[str, int] = {}
        self._last_block_log: Dict[str, float] = {}
        self._parser = mavlink2.MAVLink(None)
        self._parser.robust_parsing = True
        self._snapshot_fn: Callable[[], Snapshot] = Snapshot
        self.sent_control: List[str] = []

    # ------------------------------------------------------------------ audit
    def _record(self, event: str, detail: str) -> None:
        entry = AuditEntry(self._clock(), event, detail)
        with self._lock:
            self.audit.append(entry)
            if len(self.audit) > 500:
                self.audit = self.audit[-500:]
        self._log(f"[CMD] {event}: {detail}")

    # -------------------------------------------------------------- telemetry
    def set_snapshot_source(self, fn: Callable[[], Snapshot]) -> None:
        self._snapshot_fn = fn

    def snapshot(self) -> Snapshot:
        try:
            return self._snapshot_fn()
        except Exception as exc:  # telemetry access must never raise here
            self._log(f"[CMD] snapshot error: {exc}")
            return Snapshot()

    # ---------------------------------------------------------------- session
    def authorize(self, confirmations: List[bool], typed_system_id: str,
                  duration_s: float = SESSION_DURATION_S) -> Decision:
        """Operator-initiated control session (never automatic)."""
        snap = self.snapshot()
        if not confirmations or not all(confirmations):
            return self._deny("SESSION", "Faltan confirmaciones de la lista previa")
        if not snap.connected or snap.system_id is None:
            return self._deny("SESSION", "Sin vehículo identificado")
        if snap.heartbeat_age_s is None or snap.heartbeat_age_s > HEARTBEAT_MAX_AGE_S:
            return self._deny("SESSION", "Telemetría no vigente")
        if str(typed_system_id).strip() != str(snap.system_id):
            return self._deny("SESSION", "El SYSID escrito no coincide con el vehículo conectado")
        now = self._clock()
        with self._lock:
            self.session = Session(snap.system_id, snap.component_id or 0, snap.vehicle_type,
                                   now, now + duration_s)
            self.state = AUTHORIZED
            self.suspend_reason = ""
            self._permits.clear()
        self._record("SESIÓN AUTORIZADA",
                     f"SYSID {snap.system_id} COMPID {snap.component_id} tipo {snap.vehicle_type} "
                     f"durante {int(duration_s // 60)} min")
        return Decision(True, "Sesión de control autorizada", "SESSION")

    def revoke(self, reason: str = "Revocada por el operador") -> None:
        with self._lock:
            was = self.state
            self.state = MONITOR
            self.session = None
            self._permits.clear()
        if was != MONITOR:
            self._record("SESIÓN FINALIZADA", reason)

    def suspend(self, reason: str) -> None:
        with self._lock:
            if self.state != AUTHORIZED:
                return
            self.state = SUSPENDED
            self.suspend_reason = reason
            self._permits = [p for p in self._permits if p.kind in EMERGENCY_KINDS]
        self._record("SESIÓN SUSPENDIDA", reason)

    def tick(self) -> None:
        """Periodic supervision (called from the control loop)."""
        if self.state == MONITOR:
            return
        snap = self.snapshot()
        now = self._clock()
        session = self.session
        if session and now > session.expires_at:
            self.revoke("Sesión expirada")
            return
        if session and snap.system_id is not None and (
                snap.system_id != session.system_id or (snap.component_id or 0) != session.component_id):
            self.revoke(f"Cambio de vehículo (SYSID {snap.system_id})")
            return
        if self.state == AUTHORIZED and (
                not snap.connected or snap.heartbeat_age_s is None or snap.heartbeat_age_s > HEARTBEAT_MAX_AGE_S):
            self.suspend("Pérdida o retraso de heartbeat")

    def status_text(self) -> str:
        if self.state == AUTHORIZED and self.session:
            remaining = max(0, int(self.session.expires_at - self._clock()))
            return f"CONTROL AUTORIZADO · SYSID {self.session.system_id} · {remaining // 60:02d}:{remaining % 60:02d}"
        if self.state == SUSPENDED:
            return f"CONTROL SUSPENDIDO · {self.suspend_reason} · solo LAND/RTL"
        return "SOLO MONITORIZACIÓN · comandos bloqueados"

    # --------------------------------------------------------------- requests
    def _deny(self, kind: str, reason: str) -> Decision:
        # Movement setpoints are requested at up to 25 Hz: log rejections at most every 5 s.
        if kind in MOVEMENT_KINDS:
            now = self._clock()
            if now - self._last_block_log.get("deny:" + kind, -1e9) < 5.0:
                return Decision(False, reason, kind)
            self._last_block_log["deny:" + kind] = now
        self._record("RECHAZADO", f"{kind}: {reason}")
        return Decision(False, reason, kind)

    def request(self, kind: str, mode: Optional[str] = None, altitude: Optional[float] = None) -> Decision:
        """Validates a command and, if allowed, issues a one-shot permit."""
        label = f"{kind}{':' + mode if mode else ''}"
        self.tick()
        snap = self.snapshot()
        now = self._clock()
        if self.state == MONITOR:
            return self._deny(label, "Solo monitorización: no hay sesión de control autorizada")
        if self.state == SUSPENDED and kind not in EMERGENCY_KINDS:
            return self._deny(label, f"Sesión suspendida ({self.suspend_reason}); solo LAND/RTL")
        session = self.session
        if session is None or snap.system_id != session.system_id:
            return self._deny(label, "Vehículo no coincide con la sesión autorizada")
        if self.state == AUTHORIZED and (snap.heartbeat_age_s is None or snap.heartbeat_age_s > HEARTBEAT_MAX_AGE_S):
            return self._deny(label, "Telemetría no vigente")
        if kind in EMERGENCY_KINDS:
            # A failed LAND/RTL must be retryable at once: only a request for the
            # mode the vehicle already reports is redundant.
            if snap.mode == kind:
                return self._deny(label, f"El vehículo ya está en {kind}")
        elif kind not in MOVEMENT_KINDS:
            last = self._last_request.get(label)
            if last is not None and now - last < DUPLICATE_WINDOW_S:
                return self._deny(label, "Comando duplicado")

        predicate, reason = self._build_predicate(kind, mode, altitude, snap)
        if predicate is None:
            return self._deny(label, reason)

        with self._lock:
            self._permits.append(Permit(kind, predicate, now + PERMIT_TTL_S, label))
            if kind not in MOVEMENT_KINDS:
                self._last_request[label] = now
        if kind not in MOVEMENT_KINDS:
            self._record("AUTORIZADO", label + (f" {altitude:.1f} m" if altitude is not None else ""))
        return Decision(True, "Autorizado", label)

    def _build_predicate(self, kind, mode, altitude, snap: Snapshot):
        gps_ok = snap.gps_fix is not None and snap.gps_fix >= MIN_GPS_FIX
        if kind == ARM:
            if snap.armed:
                return None, "El vehículo ya está armado"
            if snap.mode not in ("GUIDED", "LOITER", "ALT_HOLD", "STABILIZE"):
                return None, f"Modo {snap.mode} no admitido para armar"
            if snap.mode in ("GUIDED", "LOITER") and not gps_ok:
                return None, "GPS sin fix 3D"
            return (lambda m: _is_command(m, mavlink2.MAV_CMD_COMPONENT_ARM_DISARM)
                    and int(m.param1) == 1 and int(m.param2) != FORCE_ARM_MAGIC), ""
        if kind == DISARM:
            return (lambda m: _is_command(m, mavlink2.MAV_CMD_COMPONENT_ARM_DISARM)
                    and int(m.param1) == 0 and int(m.param2) != FORCE_ARM_MAGIC), ""
        if kind in (MODE, LAND, RTL):
            name = mode if kind == MODE else kind
            if name not in REQUESTABLE_MODES:
                return None, f"Modo {name} no permitido"
            mode_id = _mode_id(name)
            return (lambda m: _matches_mode(m, mode_id)), ""
        if kind == TAKEOFF:
            if altitude is None or not MIN_TAKEOFF_ALT_M <= altitude <= MAX_TAKEOFF_ALT_M:
                return None, f"Altura fuera de rango ({MIN_TAKEOFF_ALT_M:g}-{MAX_TAKEOFF_ALT_M:g} m)"
            if not snap.armed:
                return None, "El vehículo no está armado"
            if snap.mode != "GUIDED":
                return None, "TAKEOFF requiere modo GUIDED"
            if not gps_ok:
                return None, "GPS sin fix 3D"
            return (lambda m: _is_command(m, mavlink2.MAV_CMD_NAV_TAKEOFF)), ""
        if kind in MOVEMENT_KINDS:
            if not snap.armed or snap.mode != "GUIDED":
                return None, "Movimiento solo en GUIDED y armado"
            if kind == POSITION and not gps_ok:
                return None, "GPS sin fix 3D"
            if kind == VELOCITY:
                return (lambda m: m.get_type() == "SET_POSITION_TARGET_LOCAL_NED"), ""
            if kind == POSITION:
                return (lambda m: m.get_type() == "SET_POSITION_TARGET_GLOBAL_INT"), ""
            return (lambda m: _is_command(m, mavlink2.MAV_CMD_CONDITION_YAW)), ""
        return None, f"Tipo de comando desconocido: {kind}"

    # ---------------------------------------------------------- transport
    def filter_bytes(self, buf: bytes) -> bytes:
        """Returns the subset of ``buf`` that may be transmitted."""
        with self._lock:
            messages = self._parser.parse_buffer(bytes(buf)) or []
            allowed = bytearray()
            now = self._clock()
            self._permits = [p for p in self._permits if p.expires_at >= now]
            for msg in messages:
                mtype = msg.get_type()
                if mtype == "BAD_DATA":
                    self._note_block("BAD_DATA")
                    continue
                if classify(msg) == "read_only":
                    allowed += msg.get_msgbuf()
                    continue
                permit = next((p for p in self._permits if self._safe(p.predicate, msg)), None)
                if permit is not None:
                    self._permits.remove(permit)
                    allowed += msg.get_msgbuf()
                    self.sent_control.append(mtype)
                    if permit.kind not in MOVEMENT_KINDS:
                        self._record("ENVIADO", f"{permit.description} ({mtype})")
                    continue
                self._note_block(mtype if mtype != "COMMAND_LONG" else f"COMMAND_LONG:{msg.command}")
            return bytes(allowed)

    @staticmethod
    def _safe(predicate, msg) -> bool:
        try:
            return bool(predicate(msg))
        except Exception:
            return False

    def _note_block(self, what: str) -> None:
        self._blocked_counts[what] = self._blocked_counts.get(what, 0) + 1
        now = self._clock()
        if now - self._last_block_log.get(what, -1e9) >= 5.0:
            self._last_block_log[what] = now
            self._record("BLOQUEADO", f"{what} (total {self._blocked_counts[what]})")

    @property
    def blocked_counts(self) -> Dict[str, int]:
        return dict(self._blocked_counts)

    def install(self, master) -> None:
        """Wraps ``master.write`` (pymavlink mavfile) with the filter."""
        if getattr(master, "_safeflight_guarded", False):
            return
        original_write = master.write

        def guarded_write(buf):
            data = self.filter_bytes(buf)
            if data:
                return original_write(data)
            return len(buf)

        master.write = guarded_write
        master._safeflight_guarded = True
        self._record("FILTRO INSTALADO", "Comandos de control bloqueados salvo permiso explícito")

    def on_command_ack(self, command: int, result: int) -> None:
        if command in READ_ONLY_COMMANDS:
            return
        names = {0: "ACEPTADO", 1: "TEMPORALMENTE RECHAZADO", 2: "DENEGADO", 3: "NO SOPORTADO",
                 4: "FALLIDO", 5: "EN PROGRESO", 6: "CANCELADO"}
        self._record("ACK", f"comando {command}: {names.get(result, result)}")
