"""Augmented-reality projection of HOME and mission waypoints onto the video.

Pinhole camera model:

* local east/north/up offsets from the vehicle (equirectangular, with
  cos(latitude) on the longitude axis);
* camera yaw = vehicle heading; camera pitch = mount/gimbal pitch
  (negative = looking down), from the camera configuration;
* focal lengths from the *effective* horizontal/vertical field of view of
  the video actually received (sensor mode and crop change it);
* image y grows downwards: a point above the camera axis is drawn higher.

A projection is flagged ``approximate`` (and the UI says so) when the camera
configuration is not calibrated, or when the camera orientation is not
reliable: a camera fixed to the frame (not stabilized) with unknown vehicle
attitude or with roll above ATTITUDE_TOLERANCE_DEG. The default FOV is the
nominal value of the Raspberry Pi Camera Module 3 (IMX708) standard lens in a
full-sensor 16:9 mode, and the default mount pitch is 0° (camera level).

Altitudes: vehicle, HOME and waypoints must share one reference. SafeFlight
uses altitude relative to HOME everywhere (``global_relative_frame`` and
MAV_FRAME_GLOBAL_RELATIVE_ALT for the mission), so HOME is altitude 0.

Configuration (optional): ``ar_camera.json`` in the user configuration
directory, e.g. ``{"hfov_deg": 66, "vfov_deg": 41, "mount_pitch_deg": -15,
"calibrated": false}``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from models.AppPaths import user_config_dir

FILE_NAME = "ar_camera.json"
EARTH_RADIUS_M = 6371000.0
MIN_FORWARD_M = 0.5     # points closer than this along the camera axis are not drawn
MIN_GROUND_M = 2.0      # HOME/waypoint under the vehicle: no meaningful projection
ATTITUDE_TOLERANCE_DEG = 5.0  # roll that a frame-fixed camera model does not account for


@dataclass(frozen=True)
class CameraModel:
    hfov_deg: float = 66.0
    vfov_deg: float = 41.0
    mount_pitch_deg: float = 0.0
    calibrated: bool = False
    stabilized: bool = False  # gimbal compensating vehicle pitch/roll
    name: str = "IMX708 estándar, 16:9 (valores nominales)"

    def validate(self) -> "CameraModel":
        if not (10.0 <= self.hfov_deg <= 170.0 and 10.0 <= self.vfov_deg <= 170.0):
            raise ValueError("FOV fuera de rango (10–170°)")
        if not -90.0 <= self.mount_pitch_deg <= 30.0:
            raise ValueError("inclinación de cámara fuera de rango (-90–30°)")
        return self

    def describe(self) -> str:
        state = "calibrada" if self.calibrated else "SIN CALIBRAR"
        mount = "con gimbal estabilizado" if self.stabilized else "fija al dron"
        return (f"Cámara {state}, {mount}: FOV {self.hfov_deg:.0f}×{self.vfov_deg:.0f}°, "
                f"inclinación {self.mount_pitch_deg:+.0f}° ({self.name})")


DEFAULT_CAMERA = CameraModel()


def load_camera(config_dir=None) -> tuple:
    """(CameraModel, warning or None). Missing file -> nominal, uncalibrated values."""
    path = Path(config_dir or user_config_dir()) / FILE_NAME
    if not path.exists():
        return DEFAULT_CAMERA, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cam = CameraModel(
            hfov_deg=float(data.get("hfov_deg", DEFAULT_CAMERA.hfov_deg)),
            vfov_deg=float(data.get("vfov_deg", DEFAULT_CAMERA.vfov_deg)),
            mount_pitch_deg=float(data.get("mount_pitch_deg", DEFAULT_CAMERA.mount_pitch_deg)),
            calibrated=bool(data.get("calibrated", False)),
            stabilized=bool(data.get("stabilized", False)),
            name=str(data.get("name", "configuración de usuario")),
        ).validate()
        return cam, None
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return DEFAULT_CAMERA, f"{FILE_NAME} ignorado ({exc}); se usan valores nominales"


@dataclass(frozen=True)
class Projection:
    x: int
    y: int
    distance_m: float        # 3D distance
    ground_m: float          # horizontal distance
    depression_deg: float    # angle below the horizon as seen from the camera (>0 = below)
    approximate: bool
    reason: Optional[str] = None  # why it is approximate


def enu_offset(lat0, lon0, alt0, lat1, lon1, alt1) -> tuple:
    """(east, north, up) metres from point 0 to point 1."""
    mean_lat = math.radians((lat0 + lat1) / 2.0)
    east = math.radians(lon1 - lon0) * math.cos(mean_lat) * EARTH_RADIUS_M
    north = math.radians(lat1 - lat0) * EARTH_RADIUS_M
    return east, north, (alt1 or 0.0) - (alt0 or 0.0)


def accuracy(camera: CameraModel, attitude) -> Optional[str]:
    """None when the projection can be presented as accurate, else the reason it is approximate.

    ``attitude`` is (pitch_deg, roll_deg) of the vehicle, or None when unknown.
    """
    if not camera.calibrated:
        return "cámara sin calibrar"
    if camera.stabilized:
        return None
    if attitude is None or None in attitude:
        return "actitud del vehículo desconocida"
    if abs(attitude[1]) > ATTITUDE_TOLERANCE_DEG:
        return "alabeo del vehículo no compensado"
    return None


def project(vehicle_lat, vehicle_lon, vehicle_alt, heading_deg, target_lat, target_lon, target_alt,
            width, height, camera: CameraModel = DEFAULT_CAMERA, attitude=None) -> Optional[Projection]:
    """Pixel position of the target, or None when it is behind the camera or out of frame.

    With a frame-fixed camera and known attitude, the vehicle pitch is added to the mount pitch.
    """
    if None in (vehicle_lat, vehicle_lon, heading_deg, target_lat, target_lon) or width <= 0 or height <= 0:
        return None
    east, north, up = enu_offset(vehicle_lat, vehicle_lon, vehicle_alt, target_lat, target_lon, target_alt)
    ground = math.hypot(east, north)
    if ground < MIN_GROUND_M:
        return None

    h = math.radians(heading_deg)
    forward = east * math.sin(h) + north * math.cos(h)
    right = east * math.cos(h) - north * math.sin(h)
    pitch = camera.mount_pitch_deg
    if not camera.stabilized and attitude is not None and attitude[0] is not None:
        pitch += attitude[0]
    p = math.radians(pitch)
    cam_forward = forward * math.cos(p) + up * math.sin(p)
    cam_up = -forward * math.sin(p) + up * math.cos(p)
    if cam_forward < MIN_FORWARD_M:
        return None

    fx = (width / 2.0) / math.tan(math.radians(camera.hfov_deg) / 2.0)
    fy = (height / 2.0) / math.tan(math.radians(camera.vfov_deg) / 2.0)
    x = width / 2.0 + fx * right / cam_forward
    y = height / 2.0 - fy * cam_up / cam_forward
    if not (0 <= x < width and 0 <= y < height):
        return None
    reason = accuracy(camera, attitude)
    return Projection(
        x=int(round(x)),
        y=int(round(y)),
        distance_m=math.sqrt(ground ** 2 + up ** 2),
        ground_m=ground,
        depression_deg=math.degrees(math.atan2(-up, ground)),
        approximate=reason is not None,
        reason=reason,
    )


def marker_radii(projection: Projection, base_scale: float, min_r: int, max_r: int, min_ry: int) -> tuple:
    """Ellipse radii of a ground marker: size by distance, flattened by the viewing angle."""
    rx = int(max(min_r, min(max_r, base_scale / max(1.0, projection.distance_m))))
    ry = max(min_ry, int(rx * abs(math.sin(math.radians(projection.depression_deg)))))
    return rx, ry


def distance_label(projection: Projection) -> str:
    return f"~{projection.distance_m:.0f} m" if projection.approximate else f"{projection.distance_m:.0f} m"
