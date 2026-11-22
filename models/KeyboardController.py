import math
from pymavlink import mavutil

class KeyboardController:
    def __init__(self, vehicle, max_speed=1, max_yaw_rate=15, guard=None):
        self.vehicle = vehicle
        # CommandGuard: every setpoint needs a permit; without it nothing is sent.
        self.guard = guard
        self.max_speed = max_speed
        self.speed = max_speed
        self.is_active = False
        self.max_yaw_rate = max_yaw_rate
        self.height_locked = 1.5
        self.pressed_keys = set()

    def start(self):
        self.is_active = True
        print("Control por teclado activado.")
        self._setup_yaw_control()

    def stop(self):
        was_active = self.is_active
        self.is_active = False
        self.pressed_keys.clear()
        if was_active:
            self._send_velocity(0, 0, 0, 0)

    def set_pressed_keys(self, keys):
        self.pressed_keys = set(keys)

    def _send_velocity(self, vx, vy, vz, yaw_rate):
        if self.guard is not None and not self.guard.request("VELOCITY"):
            return
        yaw_rate_rad = math.radians(yaw_rate)
        target_system = self.vehicle._master.target_system
        target_comp = self.vehicle._master.target_component

        msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
            0,
            target_system,
            target_comp,
            mavutil.mavlink.MAV_FRAME_BODY_NED,
            0b0000011111000111,
            0, 0, 0,
            vx, vy, vz,
            0, 0, 0,
            0, yaw_rate_rad
        )
        self.vehicle.send_mavlink(msg)

    def update(self):
        if not self.is_active:
            return


        vx, vy, vz = 0, 0, 0
        yaw_rate = 0

        if "arrow up" in self.pressed_keys or "up" in self.pressed_keys:
            vx = self.speed
        if "arrow down" in self.pressed_keys or "down" in self.pressed_keys:
            vx = -self.speed
        if "arrow left" in self.pressed_keys or "left" in self.pressed_keys:
            vy = -self.speed
        if "arrow right" in self.pressed_keys or "right" in self.pressed_keys:
            vy = self.speed

        if "a" in self.pressed_keys:
            yaw_rate = -self.max_yaw_rate
        if "d" in self.pressed_keys:
            yaw_rate = self.max_yaw_rate

        if "w" in self.pressed_keys:
            vz = -0.2
        if "s" in self.pressed_keys:
            vz = 0.1

        self._send_velocity(vx, vy, vz, yaw_rate)

    def _setup_yaw_control(self):
        if self.guard is not None and not self.guard.request("YAW"):
            return
        target_system = self.vehicle._master.target_system
        target_comp = self.vehicle._master.target_component
        msg = self.vehicle.message_factory.command_long_encode(
            target_system,
            target_comp,
            mavutil.mavlink.MAV_CMD_CONDITION_YAW,
            0,
            0,
            0,
            1,
            1,
            0, 0, 0
        )
        self.vehicle.send_mavlink(msg)