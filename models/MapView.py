"""Initial map view and "follow the vehicle" decisions.

The map is centred only from *vehicle* telemetry (a recent 3D GPS fix) or a
view the operator saved explicitly. There is no fixed city default and the
computer's own approximate location is never used: with neither source the
map opens on a world view.

Pure logic (no Flet), so it can be unit-tested.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from models.AppPaths import user_config_dir

FILE_NAME = "map_view.json"
SCHEMA_VERSION = 1

MIN_FIX_TYPE = 3            # 3D fix or better (GPS_RAW_INT.fix_type)
MAX_POSITION_AGE_S = 3.0    # age of the position messages themselves (not the heartbeat)
FOLLOW_ZOOM = 19.0
RECENTER_DISTANCE_M = 30.0  # follow mode re-centres when the vehicle moved this far


@dataclass(frozen=True)
class MapView:
    lat: float
    lon: float
    zoom: float
    source: str  # "world", "saved" or "vehicle"


WORLD_VIEW = MapView(lat=20.0, lon=0.0, zoom=2.0, source="world")


def _finite(*values) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def valid_coordinates(lat, lon) -> bool:
    """Range check only: (0, 0) is a real place and is not rejected here."""
    return _finite(lat, lon) and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def vehicle_position(lat, lon, fix_type, position_age_s) -> Optional[tuple]:
    """(lat, lon) when the vehicle position is trustworthy for centring the map, else None."""
    if not valid_coordinates(lat, lon):
        return None
    if fix_type is None or fix_type < MIN_FIX_TYPE:
        return None
    if position_age_s is None or not _finite(position_age_s) or position_age_s > MAX_POSITION_AGE_S:
        return None
    return float(lat), float(lon)


def distance_m(a: tuple, b: tuple) -> float:
    """Equirectangular approximation, adequate for the short distances used here."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    x = (lon2 - lon1) * math.cos((lat1 + lat2) / 2)
    y = lat2 - lat1
    return 6371000.0 * math.hypot(x, y)


class MapViewStore:
    """Persists the operator's saved initial view in the user configuration directory."""

    def __init__(self, config_dir: Optional[os.PathLike] = None):
        self.path = Path(config_dir or user_config_dir()) / FILE_NAME
        self.saved: Optional[MapView] = None
        self.warning: Optional[str] = None

    def load(self) -> "MapViewStore":
        self.saved = None
        self.warning = None
        if not self.path.exists():
            return self
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("versión de esquema no soportada")
            view = data.get("initial_view")
            if view is not None:
                lat, lon, zoom = view["lat"], view["lon"], view["zoom"]
                if not valid_coordinates(lat, lon) or not _finite(zoom) or not 1 <= zoom <= 22:
                    raise ValueError("vista inicial fuera de rango")
                self.saved = MapView(float(lat), float(lon), float(zoom), "saved")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.warning = f"Vista inicial del mapa ignorada ({exc}); se usa la vista mundial."
        return self

    def save_view(self, lat, lon, zoom) -> MapView:
        if not valid_coordinates(lat, lon) or not _finite(zoom):
            raise ValueError("vista del mapa no válida")
        view = MapView(float(lat), float(lon), float(min(max(zoom, 1.0), 22.0)), "saved")
        self._write({"schema_version": SCHEMA_VERSION,
                     "initial_view": {"lat": view.lat, "lon": view.lon, "zoom": view.zoom}})
        self.saved = view
        return view

    def clear(self) -> None:
        self._write({"schema_version": SCHEMA_VERSION, "initial_view": None})
        self.saved = None

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".map_view-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp, self.path)

    def initial_view(self) -> MapView:
        return self.saved or WORLD_VIEW


class MapFollower:
    """Decides when the map should move to the vehicle.

    * First trustworthy position: centre once (even with follow disabled), so
      the operator does not have to find the vehicle on a world map.
    * Follow enabled: re-centre when the vehicle moved RECENTER_DISTANCE_M.
    * A manual pan/zoom disables follow; the operator re-enables it.
    """

    def __init__(self, follow: bool = True):
        self.follow = follow
        self.centred_on: Optional[tuple] = None
        self.last_position: Optional[tuple] = None

    def update(self, position: Optional[tuple]) -> Optional[MapView]:
        """Returns the view to move to, or None to leave the map where it is."""
        if position is None:
            return None
        self.last_position = position
        if self.centred_on is None or (
            self.follow and distance_m(self.centred_on, position) >= RECENTER_DISTANCE_M
        ):
            self.centred_on = position
            return MapView(position[0], position[1], FOLLOW_ZOOM, "vehicle")
        return None

    def set_follow(self, enabled: bool) -> Optional[MapView]:
        """Enabling follow moves immediately to the last trustworthy position, if any."""
        self.follow = enabled
        if enabled and self.last_position is not None:
            self.centred_on = self.last_position
            return MapView(self.last_position[0], self.last_position[1], FOLLOW_ZOOM, "vehicle")
        return None

    def user_moved_map(self) -> bool:
        """Manual gesture: stop following. Returns True when follow was on."""
        was = self.follow
        self.follow = False
        return was

    def reset(self) -> None:
        self.centred_on = None
        self.last_position = None
