import math
import time
from pymavlink import mavutil


class TrajectoryController:
    def __init__(
        self,
        vehicle,
        acceptance_radius=1.5,
        altitude_tolerance=0.8,
        resend_interval=0.5,
        speed = 0.5,
    ):
        self.vehicle = vehicle
        self.acceptance_radius = acceptance_radius
        self.altitude_tolerance = altitude_tolerance
        self.resend_interval = resend_interval

        self.trajectory = None
        self.current_index = 0
        self.is_active = False
        self.finished = False
        self.speed = speed
        self.last_send_ts = 0.0

    def load_trajectory(self, trajectory):
        self.trajectory = trajectory
        self.current_index = 0
        self.finished = False
        self.last_send_ts = 0.0

    def start(self):
        if not self.vehicle:
            print("TrajectoryFollower: vehicle no disponible.")
            return False

        if not self.trajectory or not self.trajectory.points:
            print("TrajectoryFollower: trayectoria vacía.")
            return False

        if self.vehicle.mode.name != "GUIDED":
            print(f"TrajectoryFollower: modo inválido: {self.vehicle.mode.name}")
            return False

        self.is_active = True
        self.finished = False
        self._send_current_target(force=True)
        print("TrajectoryFollower activado.")
        return True

    def stop(self):
        self.is_active = False
        print("TrajectoryFollower detenido.")

    def update(self):
        if not self.is_active or not self.vehicle:
            return

        if not self.trajectory or not self.trajectory.points:
            self.stop()
            return

        if self.current_index >= len(self.trajectory.points):
            self.finished = True
            self.stop()
            return

        loc = self.vehicle.location.global_relative_frame
        if not loc or loc.lat is None or loc.lon is None:
            return

        wp = self.trajectory.points[self.current_index]
        dist_xy = self._distance_xy_m(loc.lat, loc.lon, wp.x, wp.y)
        alt_err = abs((loc.alt or 0.0) - (wp.z or 0.0))

        if dist_xy <= self.acceptance_radius and alt_err <= self.altitude_tolerance:
            print(f"Waypoint {self.current_index + 1} alcanzado.")
            self.current_index += 1

            if self.current_index >= len(self.trajectory.points):
                self.finished = True
                self.stop()
                print("Trayectoria completada.")
                return

            self._send_current_target(force=True)
            return

        self._send_current_target(force=False)

    def get_status(self):
        total = len(self.trajectory.points) if self.trajectory else 0
        return {
            "is_active": self.is_active,
            "finished": self.finished,
            "current_index": self.current_index,
            "total_points": total,
        }

    def _send_current_target(self, force=False):
        now = time.time()
        if not force and (now - self.last_send_ts) < self.resend_interval:
            return

        if not self.trajectory or self.current_index >= len(self.trajectory.points):
            return

        wp = self.trajectory.points[self.current_index]

        lat_int = int(wp.x * 1e7)
        lon_int = int(wp.y * 1e7)
        alt = float(wp.z)

        target_system = self.vehicle._master.target_system
        target_component = self.vehicle._master.target_component

        type_mask = (
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_VX_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_VY_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_VZ_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_IGNORE |
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
        )

        msg = self.vehicle.message_factory.set_position_target_global_int_encode(
            0,
            target_system,
            target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            type_mask,
            lat_int,
            lon_int,
            alt,
            0, 0, 0,
            0, 0, 0,
            0, 0
        )

        self.vehicle.send_mavlink(msg)
        self.last_send_ts = now

        print(
            f"Enviando WP {self.current_index + 1}: "
            f"lat={wp.x}, lon={wp.y}, alt={wp.z}"
        )

    def _distance_xy_m(self, lat1, lon1, lat2, lon2):
        dlat = (lat2 - lat1) * 111319.5
        dlon = (lon2 - lon1) * 111319.5 * math.cos(math.radians(lat1))
        return math.sqrt(dlat**2 + dlon**2)
    
    def set_speed(self, speed):
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            return

        self.speed = max(0.1, speed)
