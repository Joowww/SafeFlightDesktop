import time
import os
from .DroneConnection import DroneConnection
from .HeartbeatMonitor import HeartbeatMonitor
from .KeyboardController import KeyboardController
from .TrajectoryController import TrajectoryController
from . import CommandGuard as cg
from dronekit import VehicleMode
from dotenv import load_dotenv

load_dotenv()


class DroneManager:
    """Capa superior que interactúa con la lógica de negocio y la GUI.

    Todos los comandos al vehículo pasan por ``self.guard`` (CommandGuard):
    sin una sesión de control autorizada por el operador no sale ningún
    comando, aunque se invoquen estos métodos o se use DroneKit directamente.
    """
    MODE_IDLE = "IDLE"
    MODE_GUIDED_STATIONARY = "GUIDED_STATIONARY"
    MODE_MANUAL_KEYBOARD = "MANUAL_KEYBOARD"
    MODE_FOLLOW_TRAJECTORY = "FOLLOW_TRAJECTORY"
    MODE_EMERGENCY = "EMERGENCY"
    CONTROL_KEYBOARD = "KEYBOARD"
    CONTROL_TRAJECTORY = "TRAJECTORY"

    MODE_CHANGE_TIMEOUT_S = 6.0
    ARMABLE_TIMEOUT_S = 60.0
    ARM_TIMEOUT_S = 8.0

    def __init__(self):
        self.link = None
        self.health = None
        self.kb_controller = None
        self.trajectory_controller = None
        self.current_mode = self.MODE_IDLE
        self.selected_control_mode = self.CONTROL_TRAJECTORY
        self.home_location = None
        self.guard = cg.CommandGuard()
        self.guard.set_snapshot_source(self.snapshot)
        self.identity = None  # (sysid, compid, type) of the autopilot heartbeat
        self.last_error = ""

    # ------------------------------------------------------------------ link
    def setup_drone(self, mode="SIM", connection_string=None, baud_rate=57600,
                    heartbeat_timeout=30, connect_timeout=90):
        """Open the MAVLink link.

        ``connection_string`` comes from the active connection profile.
        When it is omitted (CLI scripts ``main.py`` / ``main_production.py``)
        the historical behaviour is kept: ``SIM_conn_str`` / ``REAL_conn_str``
        environment variables or ``udpin:0.0.0.0:14560``.
        """
        if connection_string:
            conn_str = connection_string
        elif mode == "SIM":
            conn_str = os.getenv("SIM_conn_str") or "udpin:0.0.0.0:14560"
        elif mode == "REAL":
            conn_str = os.getenv("REAL_conn_str") or "udpin:0.0.0.0:14560"
        else:
            print(f"ERROR: Modo desconocido '{mode}'. Usa 'SIM' o 'REAL'.")
            return False
        self.guard.revoke("Nueva conexión")
        self.identity = None
        self.link = DroneConnection(
            conn_str,
            baud_rate=baud_rate,
            heartbeat_timeout=heartbeat_timeout,
            timeout=connect_timeout,
        )
        print(f"[LINK] Conectando: {conn_str}")
        if self.link.connect():
            vehicle = self.link.vehicle
            # The command filter is installed before any controller exists.
            self.guard.install(vehicle._master)
            vehicle.add_message_listener("HEARTBEAT", self._on_heartbeat)
            vehicle.add_message_listener("COMMAND_ACK", self._on_command_ack)
            self.health = HeartbeatMonitor(self.link)
            self.health.start(on_loss_callback=self._handle_link_loss)
            self.kb_controller = KeyboardController(vehicle, guard=self.guard)
            self.trajectory_controller = TrajectoryController(vehicle, guard=self.guard)
            return True
        print("[LINK] Falló la conexión en DroneConnection")
        return False

    def _on_heartbeat(self, _vehicle, _name, msg):
        # Autopilot heartbeats only (GCS/companion heartbeats use MAV_AUTOPILOT_INVALID).
        if msg.autopilot == 8:
            return
        identity = (msg.get_srcSystem(), msg.get_srcComponent(), int(msg.type))
        if self.identity is None:
            self.identity = identity
        elif identity[:2] != self.identity[:2] and msg.get_srcComponent() == 1:
            print(f"[LINK] Heartbeat de otro autopiloto: SYSID {identity[0]} (sesión: {self.identity[0]})")
            self.identity = identity

    def _on_command_ack(self, _vehicle, _name, msg):
        self.guard.on_command_ack(int(msg.command), int(msg.result))

    def snapshot(self) -> cg.Snapshot:
        vehicle = self.link.vehicle if self.link else None
        if vehicle is None or not self.link.is_connected:
            return cg.Snapshot()
        gps = getattr(vehicle, "gps_0", None)
        try:
            mode = vehicle.mode.name
        except Exception:
            mode = None
        ident = self.identity or (None, None, None)
        return cg.Snapshot(
            connected=True,
            system_id=ident[0],
            component_id=ident[1],
            vehicle_type=str(ident[2]) if ident[2] is not None else None,
            heartbeat_age_s=vehicle.last_heartbeat,
            armed=bool(vehicle.armed),
            mode=mode,
            gps_fix=getattr(gps, "fix_type", None),
            satellites=getattr(gps, "satellites_visible", None),
        )

    # -------------------------------------------------------------- commands
    def _fail(self, reason):
        self.last_error = reason
        print(f"[CMD] Secuencia detenida: {reason}")
        return False

    def _wait(self, predicate, timeout, should_stop, period=0.25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if should_stop():
                return False
            try:
                if predicate():
                    return True
            except Exception:
                pass
            time.sleep(period)
        return False

    def set_vehicle_mode(self, name, should_stop=lambda: False):
        vehicle = self.link.vehicle if self.link else None
        if vehicle is None:
            return self._fail("Sin vehículo")
        kind = name if name in (cg.LAND, cg.RTL) else cg.MODE
        decision = self.guard.request(kind, mode=None if kind != cg.MODE else name)
        if not decision:
            return self._fail(decision.reason)
        vehicle.mode = VehicleMode(name)
        if not self._wait(lambda: vehicle.mode.name == name, self.MODE_CHANGE_TIMEOUT_S, should_stop):
            return self._fail(f"El autopiloto no confirmó el modo {name} (modo actual {vehicle.mode.name})")
        return True

    def arm_and_takeoff_safe(self, altitude=3.0, mode="GUIDED", *, stop_event=None, closing_checker=None):
        """GUIDED → ARM → TAKEOFF with confirmations and timeouts.

        Never bypasses autopilot pre-arm checks. Returns True only when the
        vehicle reports the target altitude.
        """
        vehicle = self.link.vehicle if self.link else None
        if not vehicle:
            return self._fail("Sin vehículo")
        self.last_error = ""

        def should_stop():
            try:
                if stop_event is not None and stop_event.is_set():
                    return True
                if closing_checker is not None and closing_checker():
                    return True
            except Exception:
                pass
            return False

        if self.guard.state != cg.AUTHORIZED:
            return self._fail("Sesión de control no autorizada (solo monitorización)")

        self.home_location = vehicle.location.global_relative_frame
        if vehicle.mode.name != "GUIDED" and not self.set_vehicle_mode("GUIDED", should_stop):
            return False

        if not self._wait(lambda: vehicle.is_armable, self.ARMABLE_TIMEOUT_S, should_stop, 0.5):
            return self._fail("El autopiloto no está listo para armar (pre-arm, GPS o EKF)")

        decision = self.guard.request(cg.ARM)
        if not decision:
            return self._fail(decision.reason)
        vehicle.armed = True
        if not self._wait(lambda: vehicle.armed, self.ARM_TIMEOUT_S, should_stop):
            return self._fail("El autopiloto no confirmó el armado (revisar mensajes PreArm)")

        decision = self.guard.request(cg.TAKEOFF, altitude=float(altitude))
        if not decision:
            return self._fail(decision.reason)
        vehicle.simple_takeoff(float(altitude))
        climb_timeout = 15.0 + float(altitude) * 4.0

        def reached():
            alt = vehicle.location.global_relative_frame.alt
            return alt is not None and alt >= altitude * 0.95

        if not self._wait(reached, climb_timeout, should_stop, 0.5):
            return self._fail(f"No se alcanzó {altitude:.1f} m en {climb_timeout:.0f} s")
        print(f"[CMD] Altitud alcanzada: {vehicle.location.global_relative_frame.alt:.1f} m")
        self.current_mode = self.MODE_GUIDED_STATIONARY
        return True

    def land(self):
        """Pilot-requested landing (allowed also while the session is suspended)."""
        self.stop_active_controller()
        ok = self.set_vehicle_mode("LAND")
        if ok:
            self.current_mode = self.MODE_IDLE
        return ok

    def return_to_launch(self):
        self.stop_active_controller()
        ok = self.set_vehicle_mode("RTL")
        if ok:
            self.current_mode = self.MODE_IDLE
        return ok

    # ------------------------------------------------------------ controllers
    def select_control_mode(self, control_mode):
        if control_mode not in (self.CONTROL_KEYBOARD, self.CONTROL_TRAJECTORY):
            print(f"Modo de control desconocido: {control_mode}")
            return False
        self.selected_control_mode = control_mode
        print(f"Modo de control seleccionado: {control_mode}")
        return True

    def start_selected_controller(self, trajectory=None):
        if self.selected_control_mode == self.CONTROL_KEYBOARD:
            return self.set_mode_infantil()
        if self.selected_control_mode == self.CONTROL_TRAJECTORY:
            return self.set_mode_trajectory(trajectory)
        return False

    def set_mode_infantil(self):
        if self.guard.state != cg.AUTHORIZED:
            return self._fail("Control por teclado bloqueado: sesión no autorizada")
        if self.link and self.link.is_connected:
            self.stop_active_controller()
            self.current_mode = self.MODE_MANUAL_KEYBOARD
            self.kb_controller.start()
            print("Control por teclado activado.")
            return True
        return False

    def set_mode_trajectory(self, trajectory):
        if self.guard.state != cg.AUTHORIZED:
            return self._fail("Trayectoria bloqueada: sesión no autorizada")
        vehicle = self.link.vehicle if self.link else None
        if not vehicle or not self.trajectory_controller:
            return False
        if vehicle.mode.name != "GUIDED":
            print(f"No se puede activar trayectoria en modo {vehicle.mode.name}")
            return False
        if trajectory is None or not getattr(trajectory, "points", None):
            print("No hay trayectoria válida para seguir.")
            return False
        self.stop_active_controller()
        self.trajectory_controller.load_trajectory(trajectory)
        if not self.trajectory_controller.start():
            return False
        self.current_mode = self.MODE_FOLLOW_TRAJECTORY
        print("Modo seguimiento de trayectoria activado.")
        return True

    def _handle_link_loss(self):
        """Heartbeat lost for a long time: never sends commands.

        Earlier versions sent LAND here. A command sent over a lost or
        degraded link is unreliable and could arrive late; recovery is left to
        the autopilot failsafes and to the RC pilot. The session is suspended
        so that only pilot-requested LAND/RTL can be sent.
        """
        print("[LINK] Pérdida de enlace: controladores detenidos, sin comandos automáticos.")
        self.guard.suspend("Pérdida de enlace")
        self._stop_controllers_silently()
        self.current_mode = self.MODE_EMERGENCY

    # Kept for compatibility with older callers.
    _handle_emergency = _handle_link_loss

    def _stop_controllers_silently(self):
        if self.kb_controller:
            self.kb_controller.is_active = False
            self.kb_controller.pressed_keys.clear()
        if self.trajectory_controller:
            self.trajectory_controller.is_active = False

    def tick(self):
        """Bucle principal de lógica de control."""
        self.guard.tick()
        if self.guard.state != cg.AUTHORIZED:
            if self.current_mode in (self.MODE_MANUAL_KEYBOARD, self.MODE_FOLLOW_TRAJECTORY):
                self._stop_controllers_silently()
                self.current_mode = self.MODE_IDLE
            return
        if self.current_mode == self.MODE_MANUAL_KEYBOARD:
            if self.kb_controller and self.kb_controller.is_active:
                self.kb_controller.update()
        elif self.current_mode == self.MODE_FOLLOW_TRAJECTORY:
            if self.trajectory_controller and self.trajectory_controller.is_active:
                self.trajectory_controller.update()
                if getattr(self.trajectory_controller, "finished", False):
                    print("Trayectoria finalizada. Quedando en GUIDED_STATIONARY.")
                    self.current_mode = self.MODE_GUIDED_STATIONARY

    def stop_active_controller(self):
        if self.kb_controller:
            self.kb_controller.stop()
        if self.trajectory_controller:
            self.trajectory_controller.stop()
        try:
            guided = self.link and self.link.vehicle and self.link.vehicle.mode.name == "GUIDED"
        except Exception:
            guided = False
        self.current_mode = self.MODE_GUIDED_STATIONARY if guided else self.MODE_IDLE

    def set_speed(self, speed):
        if self.kb_controller:
            self.kb_controller.speed = speed
        if self.trajectory_controller:
            self.trajectory_controller.set_speed(speed)
