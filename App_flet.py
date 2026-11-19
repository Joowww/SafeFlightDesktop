# SafeFlight Desktop v0.2.0 RC - video RTP/RTSP
import os
import sys
import json
import math
import time
import base64
import cv2
import av
import numpy as np
import asyncio
import threading
import traceback
import collections
import collections.abc
from urllib.parse import urlsplit
from io import BytesIO
from dataclasses import dataclass
from typing import List, Optional, Tuple

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "protocol_whitelist;file,crypto,data,udp,rtp,tcp"
)
print(f"DEBUG ENV VAR: {os.environ.get('OPENCV_FFMPEG_CAPTURE_OPTIONS')}")

if not hasattr(collections, "MutableMapping"):
    collections.MutableMapping = collections.abc.MutableMapping

import cv2
import numpy as np
import flet as ft
import flet_map as fmap
import flet_charts as fch
from PIL import Image, ImageDraw

from dronekit import VehicleMode

from models.DroneManager import DroneManager
from models.Trajectory import Trajectory
import argparse


_g_drone_manager = None
_g_frame_lock = threading.Lock()
_g_latest_frame = None
_g_video_thread_running = False
_g_video_thread = None
_g_video_frame_times = collections.deque(maxlen=120)
_g_video_last_frame_at = None



def _global_video_worker():
    global _g_latest_frame, _g_video_thread_running
    global _g_stream_sdp, _g_video_last_frame_at    

    print("[GLOBAL VIDEO] Iniciando receptor PyAV...", flush=True)

    options = {
        "protocol_whitelist": "file,crypto,data,udp,rtp,tcp",
    }

    while _g_video_thread_running:
        if not _g_stream_sdp:
            time.sleep(1)
            continue

        try:
            is_rtsp = _g_stream_sdp.startswith("rtsp://")
            source_type = "RTSP/TCP" if is_rtsp else "RTP/UDP"
            print(f"[GLOBAL VIDEO] Esperando señal {source_type}...", flush=True)
            source_options = {"rtsp_transport": "tcp"} if is_rtsp else options

            with av.open(
                _g_stream_sdp,
                mode="r",
                format="rtsp" if is_rtsp else "sdp",
                options=source_options,
                timeout=(5.0, 5.0),
            ) as container:

                first_frame_received = False

                for decoded_frame in container.decode(video=0):
                    if not _g_video_thread_running:
                        break

                    frame = decoded_frame.to_ndarray(format="bgr24")
                    received_at = time.monotonic()

                    with _g_frame_lock:
                        _g_latest_frame = frame
                        _g_video_last_frame_at = received_at
                        _g_video_frame_times.append(received_at)

                    if not first_frame_received:
                        print(
                            "[GLOBAL VIDEO] Señal recibida: "
                            f"{frame.shape[1]}x{frame.shape[0]}",
                            flush=True,
                        )
                        first_frame_received = True

                if _g_video_thread_running:
                    print(
                        "[GLOBAL VIDEO] Flujo interrumpido.",
                        flush=True,
                    )

        except Exception as exc:
            if _g_video_thread_running:
                print(
                    "[GLOBAL VIDEO] Sin señal o error: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )

        if _g_video_thread_running:
            time.sleep(1)

    print("[GLOBAL VIDEO] Receptor detenido.", flush=True)



def patch_dronekit_modes():
    """Parche para Dronekit: inyecta modos y evita bloqueos."""
    standard_modes = {
        0: "STABILIZE",
        1: "ACRO",
        2: "ALT_HOLD",
        3: "AUTO",
        4: "GUIDED",
        5: "LOITER",
        6: "RTL",
        7: "CIRCLE",
        9: "LAND",
        11: "DRIFT",
        13: "SPORT",
        14: "FLIP",
        15: "AUTOTUNE",
        16: "POSHOLD",
        17: "BRAKE",
        18: "THROW",
        19: "AVOID_ADSB",
        20: "GUIDED_NOGPS",
        21: "SMART_RTL",
        22: "FLOWHOLD",
        23: "FOLLOW",
        24: "ZIGZAG",
        25: "SYSTEMID",
        26: "AUTOROTATE",
        27: "AUTO_RTL",
    }

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env-mode", choices=["dev", "prod"])
    args, _ = parser.parse_known_args()

    env_mode = (args.env_mode or os.getenv("ENV_MODE", "dev")).lower()
    os.environ["ENV_MODE"] = env_mode
    try:
        if not hasattr(VehicleMode, "fixed_mode_map"):
            VehicleMode.fixed_mode_map = standard_modes
        else:
            VehicleMode.fixed_mode_map.update(standard_modes)
    except Exception as e:
        print(f"Nota: No se pudo actualizar fixed_mode_map (no crítico): {e}")

    original_init = VehicleMode.__init__

    def safe_init(self, name):
        if isinstance(name, int):
            name = standard_modes.get(name, f"UNKNOWN_{name}")
        elif name is None:
            name = "UNKNOWN"
        original_init(self, name)

    VehicleMode.__init__ = safe_init
    print("Dronekit Patch: interceptor de modos activado.")


patch_dronekit_modes()


@dataclass
class SimplePoint:
    x: float
    y: float
    z: float
    name: Optional[str] = None


class SafeFlightApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "SafeFlight Desktop"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.spacing = 0
        self.page.window_width = 1366
        self.page.window_height = 768
        self.page.window_min_width = 1100
        self.page.window_min_height = 650
        self.page.bgcolor = "#111111"
        self.page.on_close = self._on_page_close
        self.page.on_disconnect = self._on_page_disconnect
        
        self._shutdown_lock = threading.Lock()
        self._shutdown_done = False

        self.video_task = None
        self.ui_task = None
        self.video_cap = None
        self.session_id = f"{id(self)}"
        self.selected_control_mode = DroneManager.CONTROL_TRAJECTORY
        
        # ----------------------------------------------------
        # RECURSOS
        # ----------------------------------------------------
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.icon_path = os.path.join(self.assets_dir, "drone_icon.png")

        # La configuración del vídeo pertenece al usuario, no al ejecutable.
        # Esto también funciona con la distribución PyInstaller --onedir.
        self.video_config_dir = os.path.join(
            os.environ.get("APPDATA") or os.path.expanduser("~"),
            "SafeFlightDesktop",
        )
        self.video_config_path = os.path.join(
            self.video_config_dir, "video_settings.json"
        )
        self.video_udp_port = self._load_video_udp_port()
        self.video_mode, self.rtsp_url = self._load_video_stream_mode()
        self.stream_sdp = (
            self.rtsp_url
            if self.video_mode == "rtsp"
            else self._prepare_runtime_sdp(self.video_udp_port)
        )

        try:
            self.drone_img_raw = Image.open(self.icon_path).convert("RGBA")
        except Exception:
            self.drone_img_raw = Image.new("RGBA", (60, 60), color=(0, 255, 0, 160))

        # ----------------------------------------------------
        # ESTADO / MANAGERS
        # ----------------------------------------------------
        global _g_drone_manager
        if _g_drone_manager is None:
            _g_drone_manager = DroneManager()
        self.drone_manager = _g_drone_manager
        self.is_updating = False
        self.drone_marker = None
        self.drone_path_layer = None
        self.flight_start_time = None
        self.path_points: List[Tuple[float, float]] = []
        self.last_heading = -1
        self.altitude_history: List[float] = []
        self.is_video_main = False
        self.map_follow_drone = True
        self.map_initialized = False
        self.last_centered_pos = None
        self.drone_icon_container = None
        self.last_known_lat = 41.3874
        self.last_known_lon = 2.1686
        self._pressed_keys: set = set()
   
        
        self.vr_enabled = False
        self.current_trajectory = Trajectory("test_trajectory")
        self.trajectory_path = None
        self.trajectory_markers = []
        self.selected_waypoint_index = None
        self.is_creating_trajectory = False
        self.altitude_mode = "constant"

        self.placeholder_image_bytes = self._build_placeholder_image_bytes()

        self.sidebar_visible = False
        self.telemetry_visible = False

        # estado diálogos / picker
        self.pending_file_action = None  # "save_trajectory" | "load_trajectory"
        
        self.takeoff_thread = None
        self.takeoff_stop_event = threading.Event()
        
        self.connection_thread = None
        self.connection_stop_event = threading.Event()

        # vídeo
        self.frame_lock = threading.Lock()
        self.latest_frame = None
        self.video_thread_running = False  # No arranca hasta _start_background_services
        self.video_thread = None
        self.video_display_size = (1280, 720)
        self.latest_encoded_frame = None

        # sincronización UI
        self.ui_lock = threading.Lock()
        self.closing = False

        self.pressed_keys = set()
        

        # ----------------------------------------------------
        # FILE PICKER
        # ----------------------------------------------------
        self.file_picker = ft.FilePicker()
        self.file_picker.on_result = self._on_file_picker_result
        self.page.services.append(self.file_picker)

        # ----------------------------------------------------
        # SNACK / DIALOGS
        # ----------------------------------------------------
        self.snack = ft.SnackBar(content=ft.Text(""), open=False)
        self.page.overlay.append(self.snack)

        # diálogo altura variable waypoint
        self.pending_wp_coords = None

        self.wp_alt_field = ft.TextField(
            label="Altura relativa (m)",
            autofocus=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor="#1b1b1b",
            color="white",
        )

        self.wp_popup = ft.Container(
            visible=False,
            expand=True,
            bgcolor="#00000099",
            alignment=ft.Alignment(0,0),
            content=ft.Container(
                width=360,
                padding=20,
                border_radius=12,
                bgcolor="#202020",
                border=ft.Border.all(1, "#444444"),
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text("Waypoint", size=20, weight=ft.FontWeight.BOLD, color="white"),
                        ft.Text("Introduce la altura relativa del waypoint.", color="white"),
                        self.wp_alt_field,
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.TextButton("Cancelar", on_click=self._cancel_wp_alt_dialog),
                                ft.Button("Aceptar", on_click=self._confirm_wp_alt_dialog),
                            ],
                        ),
                    ],
                ),
            ),
        )

        # ----------------------------------------------------
        # CONTROLES PRINCIPALES
        # ----------------------------------------------------
        self._build_sidebar()
        self._build_main_area()
        self._build_telemetry_area()
        self._build_root()

        # Inicialmente paneles ocultos
        self.sidebar.visible = False
        self.telemetry_frame.visible = False
        self._safe_page_update()
        self._start_background_services()      
            
    
    def _kb_control_worker(self):
        """
        Inspirado en el updateuiloop de tkinter que llamaba dronemanager.tick()
        directamente en el hilo principal. Aquí usamos un hilo dedicado porque
        send_mavlink() es bloqueante y no puede correr en asyncio.
        """
        while self._kb_thread_running and not self.closing:
            try:
                if self.is_updating:
                    self.drone_manager.set_speed(self.speed_slider.value)
                    self.drone_manager.tick()
            except Exception as e:
                print(f"KB Worker error: {e}")
            time.sleep(0.04)  # 25Hz — ArduPilot GUIDED acepta 10-25Hz

    
    async def _auto_clear_key(self, key: str):
        await asyncio.sleep(0.15)
        self.pressed_keys.discard(key)
        self._push_keys_to_controller()
        
    async def _initialize_map_at_drone(self, lat, lon):
        await asyncio.sleep(0.3)
        try:
            await self.map_widget.center_on(
                point=fmap.MapLatitudeLongitude(lat, lon),
                zoom=19,
            )
            self.map_initialized = True
        except Exception:
            pass
        
        
    def _on_page_disconnect(self, e):
        self._on_closing("disconnect")

    def _on_page_close(self, e):
        self._on_closing("close")
        
    def _normalize_key(self, key: str) -> str:
        return (key or "").strip().lower()

    def _text_input_has_focus(self) -> bool:
        return (
            getattr(self.conn_entry, "focused", False)
            or getattr(self.wp_alt_field, "focused", False)
        )

    def _push_keys_to_controller(self):
        kb = getattr(self.drone_manager, "kb_controller", None)
        if kb:
            kb.set_pressed_keys(self._pressed_keys)

    def _clear_keyboard_state(self):
        self._pressed_keys.clear()
        kb = getattr(self.drone_manager, "kb_controller", None)
        if kb:
            kb.set_pressed_keys(set())
    def _map_event_fallback(self, e):
        try:
            print("MAP EVENT:", getattr(e, "event_type", None), getattr(e, "coordinates", None))

            event_type = getattr(e, "event_type", None)
            coords = getattr(e, "coordinates", None)

            if not self.is_creating_trajectory:
                return

            event_name = str(getattr(event_type, "value", event_type))
            if event_name not in ("tap", "MapEventType.TAP"):
                return

            if coords is None:
                return

            self._handle_new_map_point(coords.latitude, coords.longitude)
        except Exception as ex:
            print(f"[MAP EVENT FALLBACK] {ex}")

    # ========================================================
    # UI BUILDERS
    # ========================================================
    def _build_sidebar(self):
        self.conn_entry = ft.TextField(
            value="udpin:0.0.0.0:14560",
            read_only= True if self.page.web else False,
            dense=True,
            border_radius=10,
            bgcolor="#1b1b1b",
            color="white",
        )

        self.speed_value_text = ft.Text("1.0 m/s", color="#3b8ed0", size=13)
        self.alt_value_text = ft.Text("2 m", color="#3b8ed0", size=13)

        self.speed_slider = ft.Slider(
            min=0.1,
            max=5.0,
            value=0.5,
            divisions=49,
            on_change=self._on_speed_slider_change,
            autofocus=False,
            
        )

        self.alt_slider = ft.Slider(
            min=1,
            max=20,
            value=2.5,
            divisions=19,
            on_change=self._on_alt_slider_change,
            autofocus=False,
        )

        self.btn_connect = ft.Button(
            "CONNECT",
            bgcolor="#28a745",
            color="white",
            on_click=self._connect_action,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        )

        self.controlmode_radio = ft.RadioGroup(
            value=DroneManager.CONTROL_TRAJECTORY,
            on_change=self.on_control_mode_change,
            content=ft.Column(
                spacing=2,
                controls=[
                    ft.Radio(value=DroneManager.CONTROL_KEYBOARD, label="Keyboard"),
                    ft.Radio(value=DroneManager.CONTROL_TRAJECTORY, label="Trajectory"),
                ],
            ),
        )

        
        self.btn_takeoff = ft.Button(
            "TAKEOFF",
            disabled=True,
            height=40,
            on_click=self._takeoff_action,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            bgcolor = "#3b8ed0",
            color = "white",
        )

        self.btn_land = ft.Button(
            "LAND",
            disabled=True,
            bgcolor="#e67e22",
            color="white",
            on_click=self._land_action,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        )

        self.traj_switch = ft.Switch(
            label="Create trajectory",
            value=False,
            on_change=self._on_traj_switch_change,
        )
        self.radio_button_constant = ft.Radio(value="constant", label="Constant altitude TO", autofocus=False)
        self.radio_button_variable = ft.Radio(value="variable", label="Variable altitude", autofocus=False)
        self.alt_mode_radio = ft.RadioGroup(
            value="constant",
            on_change=self._on_altitude_mode_change,
            content=ft.Column(
                spacing=2,
                controls=[
                    self.radio_button_constant, self.radio_button_variable
                ],
            ),
        )

        self.btn_save_traj = ft.Button(
            "Save trajectory",
            bgcolor="#3b8ed0",
            color="white",
            on_click=self._save_trajectory_to_file,
        )
        self.btn_load_traj = ft.Button(
            "Import trajectory",
            on_click=self._load_trajectory_from_file,
        )
        self.btn_clear_traj = ft.Button(
            "Clear Trajectory",
            bgcolor="#e74c3c",
            color="white",
            on_click=self._clear_trajectory,
            
        )

        self.vr_switch = ft.Switch(
            label="VR Origen",
            value=False,
            on_change=self._on_vr_switch_change,
        )

        self.video_port_field = ft.TextField(
            label="Puerto RTP local (UDP)",
            value=str(self.video_udp_port),
            keyboard_type=ft.KeyboardType.NUMBER,
            dense=True,
            max_length=5,
            border_radius=10,
            bgcolor="#1b1b1b",
            color="white",
        )
        self.video_use_rtsp_switch = ft.Switch(
            label="Usar RTSP (MK32 / MediaMTX)",
            value=(self.video_mode == "rtsp"),
        )
        self.video_rtsp_url_field = ft.TextField(
            label="URL RTSP (servidor en Raspberry)",
            value=self.rtsp_url,
            dense=True,
            border_radius=10,
            bgcolor="#1b1b1b",
            color="white",
        )
        self.video_port_save_button = ft.Button(
            "Guardar vídeo (reiniciar)",
            on_click=self._save_video_port_setting,
        )
        current_video_source = (
            "RTSP: " + self.rtsp_url
            if self.video_mode == "rtsp"
            else f"RTP/UDP: {self.video_udp_port}"
        )
        self.video_port_info_text = ft.Text(
            f"Fuente en uso: {current_video_source}. Cambios al reiniciar.",
            color="#aaaaaa",
            size=11,
        )

        self.sidebar = ft.Container(
            width=260,
            bgcolor="#181818",
            padding=20,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                spacing=10,
                controls=[
                    ft.Text("SAFEFLIGHT", size=22, weight=ft.FontWeight.BOLD),
                    self.conn_entry,
                    self.btn_connect,
                    ft.Divider(color="#333333"),
                    ft.Text(
                        "MISSION SETTINGS",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color="gray",
                    ),
                    ft.Text("Speed:", size=13),
                    self.speed_slider,
                    self.speed_value_text,
                    ft.Text("Takeoff altitude(m):", size=13),
                    self.alt_slider,
                    self.alt_value_text,
                    ft.Divider(color="#333333"),
                    ft.Text(
                        "COMMANDMENTS",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color="gray",
                    ),
                    self.controlmode_radio,
                    self.btn_takeoff,
                    self.btn_land,
                    ft.Divider(color="#333333"),
                    ft.Text(
                        "TRAJECTORY COMMANDS",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color="gray",
                    ),
                    self.traj_switch,
                    ft.Text("Trajectory height:", size=13),
                    self.alt_mode_radio,
                    self.btn_save_traj,
                    self.btn_load_traj,
                    self.btn_clear_traj,
                    ft.Divider(color="#333333"),
                    ft.Text(
                        "APP SETTINGS",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color="gray",
                    ),
                    self.vr_switch,
                    ft.Divider(color="#333333"),
                    ft.Text(
                        "VIDEO INPUT (RTP / RTSP)",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color="gray",
                    ),
                    self.video_use_rtsp_switch,
                    self.video_port_field,
                    self.video_rtsp_url_field,
                    self.video_port_save_button,
                    self.video_port_info_text,
                ],
            ),
        )

    def on_control_mode_change(self, e):
        value = e.control.value
        ok = self.drone_manager.select_control_mode(value)
        if ok:
            self.selected_control_mode = value
        else:
            self.controlmode_radio.value = self.selected_control_mode
        self._safe_page_update()

    def _build_main_area(self):
        # VIDEO
        self.video_view = ft.Image(
            src=self.placeholder_image_bytes,
            fit="cover",
            gapless_playback=True,
            expand=True,
            width = float("inf"),
        )

        # Indicador independiente del fotograma: mantiene su tamaño en
        # la vista previa pequeña y en la vista principal.
        self.video_status_text = ft.Text(
            "● SIGNAL LOST",
            color="#fb7185",
            size=11,
            weight=ft.FontWeight.BOLD,
            no_wrap=True,
        )
        self.video_metrics_text = ft.Text(
            "RX -- FPS  |  AGE -- ms",
            color="#cbd5e1",
            size=10,
            no_wrap=True,
        )
        self.video_status_overlay = ft.Container(
            top=8,
            left=8,
            padding=ft.Padding.symmetric(horizontal=10, vertical=7),
            bgcolor="#111827",
            border_radius=8,
            content=ft.Column(
                tight=True,
                spacing=2,
                controls=[
                    self.video_status_text,
                    self.video_metrics_text,
                ],
            ),
        )
        self._video_status_last_update = 0.0
        self._video_status_live = False

        self.video_container_big = ft.Container(
            bgcolor="black",
            border_radius=12,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Stack(
                expand=True,
                controls=[
                    self.video_view,
                    self.video_status_overlay,
                ],
            ),
            expand=True,
        )

        # MAPA LEAFLET
        self.tile_layer = fmap.TileLayer(
            #url_template="https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}",
            url_template="https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            #url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            user_agent_package_name="safeflight_app",
        )
        self.drone_marker_layer = fmap.MarkerLayer(markers=[])
        
        self.drone_marker = None
        
        self.trajectory_marker_layer = fmap.MarkerLayer(markers=[])
        self.drone_path_layer = fmap.PolylineLayer(polylines=[])
        self.trajectory_path_layer = fmap.PolylineLayer(polylines=[])
        
        self.map_layers = [
            self.tile_layer,
            self.drone_path_layer,
            self.trajectory_path_layer,
            self.drone_marker_layer,
            self.trajectory_marker_layer,
        ]
        
        self.map_widget = fmap.Map(
            expand=True,
            initial_center=fmap.MapLatitudeLongitude(41.3874, 2.1686),
            initial_zoom=18,
            interaction_configuration=fmap.InteractionConfiguration(
                flags=fmap.InteractionFlag.ALL,
                keyboard_configuration=fmap.KeyboardConfiguration(autofocus=False, enable_arrow_keys_panning=False, enable_wasd_panning=False),
            ),
            on_tap=self._map_left_click_add_point,
            #on_event=self._map_event_fallback,
            layers=self.map_layers,
        )

        self.map_container_big = ft.Container(
            bgcolor="black",
            border_radius=12,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=self.map_widget,
            expand=True,
        )

        self.big_stack_content = ft.Stack(expand=True, controls=[])

        self.main_content_container = ft.Container(
            expand=True,
            content=self.big_stack_content,
        )

        self.mini_preview_container = ft.Container(
            width=320,
            height=190,
            right=16,
            bottom=70,
            border_radius=12,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            border= ft.Border.all(),
        )

        self.btn_swap = ft.Button(
            icon = ft.Icons.REPEAT_ROUNDED,
            width=50,
            height=50,
            style=ft.ButtonStyle(
                bgcolor="#2b2b2b",
                color="white",
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._toggle_view,
        )

        self.btn_toggle_sidebar = ft.Button(
            icon = ft.Icons.MENU_ROUNDED,
            width=50,
            height=50,
            style=ft.ButtonStyle(
                bgcolor="#1e1e2e",
                color="white",
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._toggle_sidebar,
        )

        self.btn_toggle_telemetry = ft.Button(
            icon = ft.Icons.BAR_CHART_ROUNDED,
            width=50,
            height=50,
            style=ft.ButtonStyle(
                bgcolor="#1e1e2e",
                color="white",
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._toggle_telemetry,
        )

        self.lbl_arm = ft.Text(
            "⬤", color="#e74c3c", size=12, weight=ft.FontWeight.BOLD
        )
        self.lbl_mode = ft.Text("MODE: ---", color="#aaaaaa", size=12, weight=ft.FontWeight.BOLD)
        self.lbl_alt_hud = ft.Text("H: 0.0m", color="#aaaaaa", size=12, weight=ft.FontWeight.BOLD)
        self.lbl_dist_hud = ft.Text("D: 0m", color="#aaaaaa", size=12, weight=ft.FontWeight.BOLD)
        self.lbl_speed = ft.Text("SPD: 0.0m/s", color="#aaaaaa", size=12, weight=ft.FontWeight.BOLD)
        self.lbl_batt = ft.Text("BAT: ---%", color="#aaaaaa", size=12, weight=ft.FontWeight.BOLD)
        self.lbl_time = ft.Text("T: 00:00", color="#aaaaaa", size=12, weight=ft.FontWeight.BOLD)
        self.lbl_sats = ft.Text("SAT: 0", color="#aaaaaa", size=12, weight=ft.FontWeight.BOLD)

        
        def sep():
            return ft.Text("|", color="#444444", size=12)

        self.hud_bar =ft.Column(
            horizontal_alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    alignment=ft.Alignment(0,0.8),
                    bgcolor="#1e1e2e",
                    border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    width=475,
                    content=ft.Row(
                        spacing=8,
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            self.lbl_arm,
                            sep(),
                            self.lbl_mode,
                            sep(),
                            self.lbl_alt_hud,
                            sep(),
                            self.lbl_dist_hud,
                            sep(),
                            self.lbl_speed,
                            #sep(),
                            #self.lbl_batt,
                            sep(),
                            self.lbl_time,
                            sep(),
                            self.lbl_sats,
                        ],
                    ),
                )
            ]
        )

        self.main_view = ft.Container(
            expand=True,
            margin=10,
            border_radius=15,
            bgcolor="#1a1a1a",
            clip_behavior=ft.ClipBehavior.NONE,
            content=ft.Stack(
                expand=True,
                controls=[
                    self.main_content_container,
                    self.mini_preview_container,
                    ft.Container(top=12, right=12, content=self.btn_swap),
                    ft.Container(bottom=10, left=10, content=self.btn_toggle_sidebar),
                    ft.Container(bottom = 20, left = 350, alignment = ft.Alignment(0,0.8), content=self.hud_bar),
                    ft.Container(bottom=10, right=10, content=self.btn_toggle_telemetry),
                    self.wp_popup,
                ],
            ),
        )

        self._arrange_views()

    def _build_telemetry_area(self):
        self.lbl_status = ft.Text(
            "DISARMED",
            color="#e74c3c",
            size=16,
            weight=ft.FontWeight.BOLD,
        )

        self.alt_chart = fch.LineChart(
            data_series=[
                fch.LineChartData(
                    data=[fch.LineChartDataPoint(0, 0)],
                    stroke_width=2,
                    color="#3498db",
                    curved=False,
                )
            ],
            border=ft.Border.all(1, "#2f2f2f"),
            horizontal_grid_lines=fch.ChartGridLines(color="#2a2a2a", width=1),
            vertical_grid_lines=fch.ChartGridLines(color="#2a2a2a", width=1),
            left_axis=fch.ChartAxis(label_size=40),
            bottom_axis=fch.ChartAxis(label_size=30),
            bgcolor="#1e1e1e",
            expand=True,
            min_y=-1,   
            max_y=10,
            min_x=0,    
            max_x=10,   
        )

        self.telemetry_frame = ft.Container(
            width=320,
            margin=10,
            padding=15,
            bgcolor="#181818",
            border_radius=0,
            content=ft.Column(
                expand=True,
                controls=[
                    self.lbl_status,
                    ft.Container(height=10),
                    self.alt_chart,
                ],
            ),
        )

    def _build_root(self):
        self._kb_listener = ft.KeyboardListener(
            autofocus = True,
            content=ft.Container(width=0, height=0),  # ← invisible, sin bloquear
            on_key_down=self._on_key_down,
            on_key_up=self._on_key_up,
        )
        self.page.overlay.append(self._kb_listener)  # ← overlay, NO el Stack

        self.root_content = ft.Row(
            expand=True,
            spacing=0,
            controls=[
                self.sidebar,
                self.main_view,
                self.telemetry_frame,
            ],
        )

        self.root = ft.Stack(
            expand=True,
            controls=[
                self.root_content,   # ← solo esto, sin el kb_listener aquí
            ],
        )

        self.page.add(self.root)


    def _start_background_services(self):
        if self.closing:
            return

        self.closing = False
        self._shutdown_done = False
        self._kb_thread_running = True

        global _g_stream_sdp, _g_video_thread_running, _g_video_thread
        _g_stream_sdp = self.stream_sdp
        if not _g_video_thread_running:
            _g_video_thread_running = True
            _g_video_thread = threading.Thread(target=_global_video_worker, daemon=True)
            _g_video_thread.start()

        self._kb_thread = threading.Thread(
            target=self._kb_control_worker,
            name=f"kb-worker-{self.session_id}",
            daemon=True,
        )
        self._kb_thread.start()

        self.video_task = self._safe_run_task(self._update_video_display_loop)
        self.ui_task = self._safe_run_task(self._update_ui_loop)

        print(f"Servicios en background iniciados [{self.session_id}]")



    # ========================================================
    # TOGGLES / LAYOUT
    # ========================================================
    def _toggle_sidebar(self, e=None):
        if self.closing:
            return
        self.sidebar_visible = not self.sidebar_visible
        self.sidebar.visible = self.sidebar_visible
        try:
            vehicle = self.drone_manager.link.vehicle if self.drone_manager.link else None
            if vehicle:
                loc = vehicle.location.global_relative_frame
                if loc and loc.lat is not None and loc.lon is not None:
                    self.last_known_lat = loc.lat
                    self.last_known_lon = loc.lon
        except Exception:
            pass 
        self.map_widget.initial_center = fmap.MapLatitudeLongitude(
            self.last_known_lat, self.last_known_lon
        )
        self.map_widget.initial_zoom = 19
        self.btn_toggle_sidebar.style = ft.ButtonStyle(
            bgcolor="#3b8ed0" if self.sidebar_visible else "#1e1e2e",
            color="white",
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        self._safe_page_update()

    def _toggle_telemetry(self, e=None):
        if self.closing:
            return
        self.telemetry_visible = not self.telemetry_visible
        self.telemetry_frame.visible = self.telemetry_visible
        try:
            vehicle = self.drone_manager.link.vehicle if self.drone_manager.link else None
            if vehicle:
                loc = vehicle.location.global_relative_frame
                if loc and loc.lat is not None and loc.lon is not None:
                    self.last_known_lat = loc.lat
                    self.last_known_lon = loc.lon
        except Exception:
            pass 
        self.map_widget.initial_center = fmap.MapLatitudeLongitude(
            self.last_known_lat, self.last_known_lon
        )
        self.map_widget.initial_zoom = 19
        self.btn_toggle_telemetry.style = ft.ButtonStyle(
            bgcolor="#3b8ed0" if self.telemetry_visible else "#1e1e2e",
            color="white",
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        self._safe_page_update()

    def _arrange_views(self):
        self.big_stack_content.controls.clear()

        if self.is_video_main:
            print("VISTA PRINCIPAL: VIDEO | MAPA EN PREVIEW")
            self.video_container_big.expand = True
            self.video_container_big.width = None
            self.video_container_big.height = None
            
            # Mapa → mini: tamaño fijo
            self.map_container_big.expand = False
            self.map_container_big.width = 320
            self.map_container_big.height = 190
            self.big_stack_content.controls.append(self.video_container_big)
            self.mini_preview_container.content = self.map_container_big
        else:
            print("VISTA PRINCIPAL: MAPA | VIDEO EN PREVIEW")
            self.map_container_big.expand = True
            self.map_container_big.width = None
            self.map_container_big.height = None
            
            # Video → mini: tamaño fijo
            self.video_container_big.expand = False
            self.video_container_big.width = 320
            self.video_container_big.height = 190
            self.big_stack_content.controls.append(self.map_container_big)
            self.mini_preview_container.content = self.video_container_big

        self._safe_page_update()

    def _toggle_view(self, e=None):
        if self.closing:
            return
        self.is_video_main = not self.is_video_main
        try:
            vehicle = self.drone_manager.link.vehicle if self.drone_manager.link else None
            if vehicle:
                loc = vehicle.location.global_relative_frame
                if loc and loc.lat is not None and loc.lon is not None:
                    self.last_known_lat = loc.lat
                    self.last_known_lon = loc.lon
        except Exception:
            pass 
        self.map_widget.initial_center = fmap.MapLatitudeLongitude(
            self.last_known_lat, self.last_known_lon
        )
        self.map_widget.initial_zoom = 19
        self._arrange_views()


        

    # ========================================================
    # EVENTOS CONTROLES
    # ========================================================
    def _on_key_down(self, e: ft.KeyDownEvent):
        if self._text_input_has_focus():
            return
        key = (e.key or "").strip().lower()
        self._pressed_keys.add(key)
        self._push_keys_to_controller()

    def _on_key_up(self, e: ft.KeyUpEvent):
        key = (e.key or "").strip().lower()
        self._pressed_keys.discard(key)
        self._push_keys_to_controller()

    
    def _on_speed_slider_change(self, e):
        if self.closing:
            return
        self.speed_value_text.value = f"{e.control.value:.1f} m/s"
        self._safe_page_update()

    def _on_alt_slider_change(self, e):
        if self.closing:
            return
        self.alt_value_text.value = f"{int(e.control.value)} m"
        self._safe_page_update()

    def _on_traj_switch_change(self, e):
        self.is_creating_trajectory = bool(e.control.value)
        print("TRAJ MODE:", self.is_creating_trajectory)

    def _on_altitude_mode_change(self, e):
        self.altitude_mode = e.control.value

    def _on_vr_switch_change(self, e):
        self.vr_enabled = bool(e.control.value)

    # ========================================================
    # VIDEO CONFIGURATION (WINDOWS DESKTOP)
    # ========================================================
    def _load_video_udp_port(self) -> int:
        """Carga el puerto RTP desde la configuración del usuario."""
        default_port = 5004
        try:
            with open(self.video_config_path, "r", encoding="utf-8") as config_file:
                settings = json.load(config_file)
            port = int(settings.get("rtp_udp_port", default_port))
            if 1024 <= port <= 65534:
                return port
            print("[VIDEO CONFIG] Puerto fuera de rango; usando 5004.")
        except FileNotFoundError:
            pass
        except Exception as exc:
            print(f"[VIDEO CONFIG] No se pudo leer configuración: {exc}")
        return default_port

    def _load_video_stream_mode(self) -> tuple[str, str]:
        """Carga el tipo de fuente sin alterar la configuración RTP previa."""
        default_url = "rtsp://192.168.144.30:8554/raspicam"
        try:
            with open(self.video_config_path, "r", encoding="utf-8") as handle:
                settings = json.load(handle)
            mode = settings.get("video_mode", "rtp")
            url = settings.get("rtsp_url", default_url)
            if mode not in ("rtp", "rtsp"):
                mode = "rtp"
            if not isinstance(url, str) or not self._valid_rtsp_url(url):
                url = default_url
            return mode, url
        except FileNotFoundError:
            return "rtp", default_url
        except Exception as exc:
            print(f"[VIDEO CONFIG] No se pudo leer modo: {exc}")
            return "rtp", default_url

    @staticmethod
    def _valid_rtsp_url(url: str) -> bool:
        if not isinstance(url, str) or len(url) > 1024:
            return False
        try:
            parts = urlsplit(url.strip())
            return (
                parts.scheme == "rtsp"
                and bool(parts.hostname)
                and (parts.port is None or 1 <= parts.port <= 65535)
                and not any(c in url for c in ("\n", "\r", "\t"))
            )
        except ValueError:
            return False

    def _prepare_runtime_sdp(self, port: int) -> str:
        """Escribe un SDP reproducible en AppData, no en la carpeta de la app."""
        sdp_path = os.path.join(self.video_config_dir, "stream_runtime.sdp")
        sdp_text = (
            "v=0\n"
            "o=- 0 0 IN IP4 0.0.0.0\n"
            "s=SafeFlight Desktop RTP receiver\n"
            "c=IN IP4 0.0.0.0\n"
            "t=0 0\n"
            "a=tool:SafeFlightDesktop\n"
            f"m=video {port} RTP/AVP 96\n"
            "a=rtpmap:96 H264/90000\n"
            "a=fmtp:96 packetization-mode=1\n"
            "a=recvonly\n"
        )
        try:
            os.makedirs(self.video_config_dir, exist_ok=True)
            with open(sdp_path, "w", encoding="ascii", newline="\n") as sdp_file:
                sdp_file.write(sdp_text)
            print(f"[VIDEO CONFIG] Escuchando RTP en UDP {port}")
            return sdp_path
        except OSError as exc:
            # No se intenta modificar el stream.sdp empaquetado.
            print(f"[VIDEO CONFIG] No se pudo crear SDP en AppData: {exc}")
            self.video_udp_port = 5004
            return os.path.join(self.base_dir, "stream.sdp")

    def _save_video_port_setting(self, e=None):
        """Guarda RTP o RTSP en AppData y pide reiniciar para aplicar cambios."""
        if self.closing:
            return
        raw = str(self.video_port_field.value or "").strip()
        try:
            port = int(raw)
        except ValueError:
            self._show_message("Introduce un puerto UDP numérico.", error=True)
            return
        if not 1024 <= port <= 65534:
            self._show_message("Puerto RTP fuera de rango (1024-65534).", error=True)
            return

        mode = "rtsp" if self.video_use_rtsp_switch.value else "rtp"
        url = str(self.video_rtsp_url_field.value or "").strip()
        if not self._valid_rtsp_url(url):
            self._show_message("URL RTSP inválida; usa rtsp://IP:PUERTO/ruta.", error=True)
            return

        settings = {
            "video_mode": mode,
            "rtp_udp_port": port,
            "rtsp_url": url,
        }
        try:
            os.makedirs(self.video_config_dir, exist_ok=True)
            temporary_path = self.video_config_path + ".tmp"
            with open(temporary_path, "w", encoding="utf-8") as config_file:
                json.dump(settings, config_file, indent=2)
            os.replace(temporary_path, self.video_config_path)
        except OSError as exc:
            self._show_message(f"No se pudo guardar el vídeo: {exc}", error=True)
            return

        source = f"RTSP {url}" if mode == "rtsp" else f"RTP UDP {port}"
        message = f"Guardado: {source}. Reinicia SafeFlight para aplicarlo."
        print(f"[VIDEO CONFIG] {message}")
        self._show_message(message)

    # ========================================================
    # VIDEO
    # ========================================================
    def _video_worker(self):
        """Hilo que lee OpenCV sin bloquear la app."""
        with self.frame_lock:
            self.latest_frame = None
        while self.video_thread_running and not self.closing:
            cap = None
            try:
                cap = cv2.VideoCapture(self.stream_sdp, cv2.CAP_FFMPEG)

                if not cap.isOpened():
                    print("[VIDEO] Esperando stream... (reintentando en 2s)")
                    time.sleep(2)
                    continue

                print("[VIDEO] Conexión establecida.")

                while self.video_thread_running and not self.closing and cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        with self.frame_lock:
                            self.latest_frame = frame
                    else:
                        print("[VIDEO] Stream perdido.")
                        break

            except Exception as e:
                print(f"VIDEO: Error en captura: {e}")
            finally:
                try:
                    if cap is not None:
                        cap.release()
                        print("VIDEO: cap.release() ejecutado")
                except Exception as e:
                    print(f"VIDEO: error en cap.release(): {e}")

                if self.video_cap is cap:
                    self.video_cap = None

                if self.video_thread_running and not self.closing:
                    time.sleep(1)

        print("VIDEO: thread finalizado limpiamente")
            

    def _update_video_status_overlay(self, live, rx_fps=0.0, frame_age_ms=None):
        """Actualiza el indicador a un máximo de dos veces por segundo."""
        now = time.monotonic()
        if (
            live == self._video_status_live
            and now - self._video_status_last_update < 0.5
        ):
            return

        self._video_status_live = live
        self._video_status_last_update = now

        if live:
            age_text = "--" if frame_age_ms is None else f"{frame_age_ms:.0f}"
            self.video_status_text.value = "● CAMERA LIVE"
            self.video_status_text.color = "#4ade80"
            self.video_metrics_text.value = (
                f"RX {rx_fps:.1f} FPS  |  AGE {age_text} ms"
            )
        else:
            self.video_status_text.value = "● SIGNAL LOST"
            self.video_status_text.color = "#fb7185"
            self.video_metrics_text.value = "RX 0.0 FPS  |  AGE -- ms"

        self._safe_control_update(
            self.video_status_overlay, "video_status_overlay.update"
        )

    #async def _update_video_display_loop(self):
    #    while not self.closing:
    async def _update_video_display_loop(self):
        last_frame_time = None
        black_visible = False

        while not self.closing:
            try:
                frame = None
                frame_received_at = None
                rx_times = ()

                global _g_frame_lock, _g_latest_frame

                with _g_frame_lock:
                    if _g_latest_frame is not None:
                        frame = _g_latest_frame.copy()
                        frame_received_at = _g_video_last_frame_at
                        _g_latest_frame = None

                    rx_times = tuple(_g_video_frame_times) 

                now = time.monotonic()

                if frame is not None:
                    last_frame_time = now
                    black_visible = False

                elif last_frame_time is not None and now - last_frame_time < 1.5:
                    await asyncio.sleep(0.05)
                    continue

                elif black_visible:
                    await asyncio.sleep(0.2)
                    continue

                if frame is not None:
                    target_w, target_h = self.video_display_size
                #if frame is not None:
                #    target_w, target_h = self.video_display_size
                    frame = cv2.resize(frame, (target_w, target_h))

                    try:
                        if self.drone_manager.link and self.drone_manager.link.vehicle:
                            vehicle = self.drone_manager.link.vehicle

                            # HOME VR
                            home_data = self.get_home_pixel_position(
                                vehicle,
                                self.drone_manager.home_location,
                                target_w,
                                target_h,
                            )

                            if home_data and self.vr_enabled:
                                x, y, pitch_deg = home_data
                                dist = self.get_distance_metres(
                                    vehicle.location.global_relative_frame,
                                    self.drone_manager.home_location,
                                )

                                y = max(10, min(target_h - 10, y))
                                base_scale = 700
                                calculated_radius = base_scale / max(1, dist)
                                radius_x = int(max(15, min(200, calculated_radius)))
                                squash_factor = abs(math.sin(math.radians(pitch_deg)))
                                radius_y = int(radius_x * squash_factor)
                                radius_y = max(3, radius_y)

                                cv2.ellipse(
                                    frame,
                                    (x, y),
                                    (radius_x, radius_y),
                                    0,
                                    0,
                                    360,
                                    (220, 220, 220),
                                    -1,
                                    lineType=cv2.LINE_AA,
                                )
                                cv2.ellipse(
                                    frame,
                                    (x, y),
                                    (radius_x, radius_y),
                                    0,
                                    0,
                                    360,
                                    (0, 0, 0),
                                    1,
                                    lineType=cv2.LINE_AA,
                                )

                                text_offset_y = y - radius_y - 12
                                cv2.putText(
                                    frame,
                                    "H",
                                    (x - 7, text_offset_y),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5,
                                    (0, 0, 0),
                                    2,
                                )
                                cv2.putText(
                                    frame,
                                    f"{int(dist)}m",
                                    (x - 10, y + 30),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5,
                                    (255, 255, 255),
                                    1,
                                )

                            # WAYPOINTS VR
                            if (
                                self.current_trajectory
                                and getattr(self.current_trajectory, "points", None)
                                and self.vr_enabled
                            ):
                                for idx, wp in enumerate(self.current_trajectory.points, start=1):
                                    pixdata = self.project_waypoint_to_pixel(
                                        vehicle, wp, target_w, target_h
                                    )
                                    if pixdata is None:
                                        continue

                                    x, y, pitch_deg, dist = pixdata
                                    y = max(10, min(target_h - 10, y))

                                    base_scale = 900
                                    calculated_radius = base_scale / max(1, dist)
                                    radius_x = int(max(20, min(250, calculated_radius)))
                                    squash_factor = abs(math.sin(math.radians(pitch_deg)))
                                    radius_y = int(radius_x * squash_factor)
                                    radius_y = max(5, radius_y)

                                    cv2.ellipse(
                                        frame,
                                        (x, y),
                                        (radius_x, radius_y),
                                        0,
                                        0,
                                        360,
                                        (0, 200, 0),
                                        -1,
                                        lineType=cv2.LINE_AA,
                                    )
                                    cv2.ellipse(
                                        frame,
                                        (x, y),
                                        (radius_x, radius_y),
                                        0,
                                        0,
                                        360,
                                        (0, 255, 0),
                                        3,
                                        lineType=cv2.LINE_AA,
                                    )
                                    cv2.ellipse(
                                        frame,
                                        (x, y),
                                        (radius_x + 2, radius_y + 2),
                                        0,
                                        0,
                                        360,
                                        (255, 255, 0),
                                        2,
                                        lineType=cv2.LINE_AA,
                                    )

                                    text_offset_y = y - radius_y - 15
                                    text = getattr(wp, "name", None) or f"P{idx}"

                                    cv2.putText(
                                        frame,
                                        text,
                                        (x - 20, text_offset_y),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.6,
                                        (0, 0, 0),
                                        2,
                                    )
                                    cv2.putText(
                                        frame,
                                        text,
                                        (x - 20, text_offset_y),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.6,
                                        (255, 255, 255),
                                        1,
                                    )
                                    cv2.putText(
                                        frame,
                                        f"{dist:.0f}m",
                                        (x - 15, y + radius_y + 15),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.5,
                                        (200, 255, 200),
                                        1,
                                    )
                    
                    except Exception as vr_err:
                        print(f"Error overlay VR: {vr_err}")

                    # FPS de recepción y antigüedad del fotograma decodificado.
                    if frame_received_at is not None:
                        current_time = time.monotonic()
                        recent_times = [
                            t for t in rx_times
                            if current_time - t <= 2.0
                        ]

                        rx_fps = 0.0
                        if len(recent_times) >= 2:
                            elapsed = recent_times[-1] - recent_times[0]
                            if elapsed > 0:
                                rx_fps = (len(recent_times) - 1) / elapsed

                        frame_age_ms = max(
                            0.0,
                            (current_time - frame_received_at) * 1000.0,
                        )
                        self._update_video_status_overlay(
                            live=True,
                            rx_fps=rx_fps,
                            frame_age_ms=frame_age_ms,
                        )

                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb)


                    buffer = BytesIO()
                    pil_img.save(buffer, format="JPEG", quality=82)

                    self.video_view.src = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    try:
                        self._safe_control_update(self.video_view, "video_view.update")
                    except Exception:
                        self.closing = True
                        break

                    await asyncio.sleep(0.05)
                    #try:
                    #    self._safe_control_update(self.video_view , "video_view.update")   
                    #except Exception:
                        # WebSocketDisconnect u otro error de sesión cerrada → salir
                    #    self.closing = True
                    #    break
                    #await asyncio.sleep(0.066)
                else:
                    self._update_video_status_overlay(live=False)
                    target_w, target_h = self.video_display_size
                    black = np.zeros((target_h, target_w, 3), dtype=np.uint8)

                    cv2.putText(
                        black,
                        "VIDEO SIGNAL LOST",
                        (max(10, target_w // 2 - 200), target_h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )

                    rgb = cv2.cvtColor(black, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb)

                    buffer = BytesIO()
                    pil_img.save(buffer, format="JPEG", quality=80)

                    self.video_view.src = base64.b64encode(
                        buffer.getvalue()
                    ).decode("utf-8")

                    try:
                        self._safe_control_update(
                            self.video_view, "video_view.update"
                        )
                    except Exception:
                        self.closing = True
                        break

                    black_visible = True
                    await asyncio.sleep(0.05)
                    
            except asyncio.CancelledError:
                return
            except Exception as e:
                if not self.closing:
                    print(f"Error Render Video: {e}")

            

    # ========================================================
    # LOOP UI / TELEMETRÍA
    # ========================================================
    async def _update_ui_loop(self):
        while not self.closing:
            if not self.is_updating:
                await asyncio.sleep(0.075)
                continue

            try:
                vehicle = self.drone_manager.link.vehicle if self.drone_manager.link else None
                if vehicle:
                    v_mode = vehicle.mode.name
                    is_active = vehicle.armed or v_mode in ["GUIDED", "TAKEOFF"]

                    if not is_active:
                        if self.btn_takeoff.disabled:
                            self.btn_takeoff.disabled = False
                            self.speed_slider.disabled = False
                            self.alt_slider.disabled = False
                            self.alt_mode_radio.disabled = False
                            self.radio_button_constant.disabled = False
                            self.radio_button_variable.disabled = False
                            self.btn_save_traj.disabled = False
                            self.btn_load_traj.disabled = False
                            self.traj_switch.disabled = False
                            self.controlmode_radio.disabled = False
                            self.btn_takeoff.text = "TAKEOFF"
                            self.btn_takeoff.bgcolor = "#3b8ed0"
                            self.btn_land.disabled = True
                            self.btn_land.text = "LAND"
                    else:
                        if self.btn_land.disabled and v_mode != "LAND":
                            self.btn_takeoff.disabled = True
                            self.speed_slider.disabled = True
                            self.alt_slider.disabled = True
                            self.alt_mode_radio.disabled = True
                            self.radio_button_constant.disabled = True
                            self.radio_button_variable.disabled = True
                            self.is_creating_trajectory = False
                            self.traj_switch.disabled = True
                            self.btn_save_traj.disabled = True
                            self.btn_load_traj.disabled = True
                            self.controlmode_radio.disabled = True
                            
                            self.traj_switch.disabled = True
                            self.btn_takeoff.text = "FLYING"
                            self.btn_takeoff.bgcolor = "gray"
                            self.btn_land.disabled = False
                            self.btn_land.text = "LAND"

                    status_text = f"MODE: {vehicle.mode.name}\nARMED: {vehicle.armed}"
                    self.lbl_status.value = status_text
                    self.lbl_status.color = "#2ecc71" if vehicle.armed else "#e74c3c"

                    lat = vehicle.location.global_relative_frame.lat
                    lon = vehicle.location.global_relative_frame.lon
                    heading = vehicle.heading or 0
                    #print("DRONE POS:", lat, lon)
                    if lat is not None and lon is not None:
                        self.last_known_lat = lat
                        self.last_known_lon = lon   
                        self._update_drone_on_map(lat, lon, heading)

                        if self.map_follow_drone:

                            # Primera posición GPS
                            if not self.map_initialized:
                                await self._initialize_map_at_drone(lat, lon)
                                self.last_centered_pos = (lat, lon)
                            else:
                                c_lat, c_lon = self.last_centered_pos
                                if abs(lat - c_lat) > 0.0006 or abs(lon - c_lon) > 0.0006:
                                    try:
                                        await self.map_widget.center_on(point = fmap.MapLatitudeLongitude(lat, lon), zoom = 19)
                                        self.last_centered_pos = (lat, lon)
                                    except Exception:
                                        pass

                    alt = max(0, vehicle.location.global_relative_frame.alt or 0)
                    self.altitude_history.append(alt)
                    if len(self.altitude_history) > 120:
                        self.altitude_history = self.altitude_history[-120:]
                    #print("ALT HIST:", self.altitude_history)
                    self._refresh_altitude_chart()

                    # HUD
                    if vehicle.armed:
                        self.lbl_arm.value = "⬤"
                        self.lbl_arm.color = "#2ecc71"
                        if self.flight_start_time is None:
                            self.flight_start_time = time.time()
                    else:
                        self.lbl_arm.value = "⬤"
                        self.lbl_arm.color = "#e74c3c"
                        self.flight_start_time = None

                    self.lbl_mode.value = f"MODE: {vehicle.mode.name}"
                    alt_hud = vehicle.location.global_relative_frame.alt or 0
                    self.lbl_alt_hud.value = f"H: {alt_hud:.1f}m"

                    if self.drone_manager.home_location:
                        dist_hud = self.get_distance_metres(
                            vehicle.location.global_relative_frame,
                            self.drone_manager.home_location,
                        )
                        self.lbl_dist_hud.value = f"D: {dist_hud:.0f}m"

                    try:
                        vx, vy, vz = vehicle.velocity
                        speed = math.sqrt(vx**2 + vy**2 + vz**2)
                    except Exception:
                        speed = 0.0

                    self.lbl_speed.value = f"SPD: {speed:.1f}m/s"

                    #batt = 0
                    #try:
                    #    batt = vehicle.battery.level if vehicle.battery.level is not None else 0
                    #except Exception:
                    #    batt = 0
                    #batt_color = "#aaaaaa" if batt > 50 else "#e67e22" if batt > 20 else "#e74c3c"
                    #self.lbl_batt.value = f"BAT: {batt}%"
                    #self.lbl_batt.color = batt_color

                    if self.flight_start_time:
                        elapsed = int(time.time() - self.flight_start_time)
                        mins, secs = divmod(elapsed, 60)
                        self.lbl_time.value = f"T: {mins:02d}:{secs:02d}"
                    else:
                        self.lbl_time.value = "T: 00:00"

                    sats = 0
                    try:
                        sats = vehicle.gps_0.satellites_visible if vehicle.gps_0 else 0
                        sats = sats or 0
                    except Exception:
                        sats = 0
                    sat_color = "#aaaaaa" if sats >= 8 else "#e67e22" if sats >= 5 else "#e74c3c"
                    self.lbl_sats.value = f"SAT: {sats}"
                    self.lbl_sats.color = sat_color

                    #self._safe_update_map()
                    try:
                        self._safe_page_update()
                    except Exception:
                        # WebSocketDisconnect u otro error de sesión cerrada → salir
                        self.closing = True
                        break
                    await asyncio.sleep(0.075)
            except asyncio.CancelledError:
                return
            except Exception as e:
                print(f"Error UI Loop: {e}")
                traceback.print_exc()

        

    # ========================================================
    # MAPA / DRON / TRAYECTORIA
    # ========================================================
    def _build_placeholder_image_bytes(self) -> bytes:
        img = Image.new("RGB", (1280, 720), color=(18, 18, 18))
        draw = ImageDraw.Draw(img)
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()

    def _safe_update_map(self):
        pass

    def _build_waypoint_marker(self, p, idx: int, selected: bool = False):
        bg = "#ffd400" if selected else "#00aa00"
        fg = "#111111" if selected else "white"
        return fmap.Marker(
            coordinates=fmap.MapLatitudeLongitude(p.x, p.y),
            width=44,
            height=44,
            content=ft.GestureDetector(
                data=idx,
                mouse_cursor=ft.MouseCursor.CLICK,
                on_tap=self._select_waypoint,
                content=ft.Container(
                    bgcolor=bg,
                    border_radius=20,
                    padding=6,
                    border=ft.Border.all(2, "#333333" if selected else "#0d5f0d"),
                    content=ft.Text(
                        p.name or f"P{idx + 1}",
                        size=11,
                        color=fg,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ),
            ),
        )

    def _rebuild_trajectory_layers(self):
        points = self.current_trajectory.obtain_points()
        coords = [fmap.MapLatitudeLongitude(p.x, p.y) for p in points]

        if coords:
            selected = self.selected_waypoint_index is not None
            self.trajectory_path = fmap.PolylineMarker(
                coordinates=coords,
                color="#ffff00" if selected else "#00ff00",
                border_color="#ff8800" if selected else "#003300",
                border_stroke_width=2 if selected else 1,
                stroke_width=6 if selected else 4,
            )
            self.trajectory_path_layer.polylines = [self.trajectory_path]
        else:
            self.trajectory_path = None
            self.trajectory_path_layer.polylines = []

        self.trajectory_markers = [
            self._build_waypoint_marker(
                p,
                idx,
                selected=(idx == self.selected_waypoint_index),
            )
            for idx, p in enumerate(points)
        ]
        self.trajectory_marker_layer.markers = list(self.trajectory_markers)

    def _select_waypoint(self, e):
        if self.closing:
            return
        try:
            self.selected_waypoint_index = int(e.control.data)
        except Exception:
            self.selected_waypoint_index = None

        self._rebuild_trajectory_layers()
        #self._safe_update_map()
        self._safe_page_update()

    def _update_drone_on_map(self, lat, lon, heading):
        #print("UPDATE DRONE MARKER", lat, lon)
        if self.drone_marker is None:
            self.drone_icon_container = ft.Container(
                alignment=ft.Alignment(0, 0),
                rotate=heading * math.pi / 180,   # ← heading en radianes
                content=ft.Icon(
                    ft.Icons.NAVIGATION,
                    color="#00ff99",
                    size=30,
                ),
            )
            self.drone_marker = fmap.Marker(
                coordinates=fmap.MapLatitudeLongitude(lat, lon),
                width=40,
                height=40,
                content=self.drone_icon_container,
            )
            self.drone_marker_layer.markers.append(self.drone_marker)
        else:
            self.drone_marker.coordinates = fmap.MapLatitudeLongitude(lat, lon)
            self.drone_icon_container.rotate = heading * math.pi / 180 
        if not self.path_points or self._has_moved_significantly(
            self.path_points[-1], (lat, lon)
        ):
            self.path_points.append((lat, lon))

            if len(self.path_points) > 1500:
                self.path_points = self.path_points[-1500:]

            self.drone_path_layer.polylines = [
                fmap.PolylineMarker(
                    coordinates=[
                        fmap.MapLatitudeLongitude(p[0], p[1]) for p in self.path_points
                    ],
                    color="#ff1500",
                    stroke_width=3,
                )
            ]
    
    def _clear_trajectory(self, e=None):
        self.current_trajectory = Trajectory("trayectoria_mapa")
        self.selected_waypoint_index = None
        self.trajectory_path = None
        self.trajectory_markers.clear()
        self.trajectory_path_layer.polylines = []
        self.trajectory_marker_layer.markers = []
        #self._safe_update_map()
        self._safe_page_update()

    def _map_left_click_add_point(self, e):
        if self.closing:
            return
        try:
            if not self.is_creating_trajectory:
                return

            coords = getattr(e, "coordinates", None)
            if coords is None:
                print("[MAP TAP] Evento sin coordinates")
                return

            self._handle_new_map_point(coords.latitude, coords.longitude)
            print("CLICK MAP:", e)
            print("COORDS:", getattr(e, "coordinates", None))
        except Exception as ex:
            print(f"[MAP TAP ERROR] {ex}")
            
    def _cancel_wp_alt_dialog(self, e):
        if self.closing:
            return
        self.pending_wp_coords = None
        self.wp_alt_field.value = ""
        self.wp_popup.visible = False
        self._safe_page_update()
        
    def _handle_new_map_point(self, lat, lon):
        mode = self.altitude_mode
        
        if mode == "constant":
            alt = float(self.alt_slider.value)
            self._add_trajectory_point(lat, lon, alt)
        else:
            self.pending_wp_coords = (lat, lon)
            self.wp_alt_field.value = ""
            self.wp_popup.visible = True
            self._safe_page_update()

    def _confirm_wp_alt_dialog(self, e):
        if self.closing:
            return
        try:
            if not self.pending_wp_coords:
                self.wp_popup.visible = False
                self._safe_page_update()
                return

            raw = (self.wp_alt_field.value or "").strip()
            if not raw:
                self._show_message("Introduce una altura.", error=True)
                return

            alt = float(raw)

            lat, lon = self.pending_wp_coords
            self.pending_wp_coords = None
            self.wp_alt_field.value = ""
            self.wp_popup.visible = False
            self._safe_page_update()

            print(f"[WP CONFIRM] lat={lat}, lon={lon}, alt={alt}")
            self._add_trajectory_point(lat, lon, alt)

        except Exception as ex:
            print(f"[WP CONFIRM ERROR] {ex}")
            self._show_message(f"Altura inválida: {ex}", error=True)
            
    def _add_trajectory_point(self, lat: float, lon: float, alt: float):
        self.current_trajectory.add_point(lat, lon, alt)
        self.selected_waypoint_index = len(self.current_trajectory.obtain_points()) - 1
        self._rebuild_trajectory_layers()
        #self._safe_update_map()
        self._safe_page_update()

    # ========================================================
    # CONEXIÓN / VUELO
    # ========================================================
    def _connect_action(self, e=None):
        if self.closing:
            return
        if self.connection_thread and self.connection_thread.is_alive():
            return
        self.btn_connect.text = "CONECTANDO..."
        self.btn_connect.disabled = True
        self._safe_page_update()

        conn_str = "udpin:0.0.0.0:14560" #if os.getenv('ENV_MODE', 'dev') == 'dev' else "host.docker.internal:14560"
        
        self.connection_stop_event.clear()
        self.connection_thread = threading.Thread(
            target=self._connection_worker,
            args=(conn_str,),
            name="connection-worker",
            daemon=False,
        )
        self.connection_thread.start()

    def _connection_worker(self, conn_string):  
        #os.environ["SIM_conn_str"] = "udpin:0.0.0.0:14560"  
        #os.environ["REAL_conn_str"] = "host.docker.internal:14560"  
        print(f"DEBUG ENV_MODE={os.getenv('ENV_MODE')}")
        print(f"DEBUG SIM_conn_str={os.getenv('SIM_conn_str')}")
        print(f"DEBUG REAL_conn_str={os.getenv('REAL_conn_str')}")
        print(f"DEBUG conn_str efectivo={conn_string}")

        try:
            if self.closing or self.connection_stop_event.is_set():
                return
            env_mode = os.getenv('ENV_MODE', 'dev').lower()
            mode = "REAL" if env_mode == 'prod' else "SIM"
            print(f"DEBUG: Modo {env_mode}, usando {mode}: {conn_string}")
            
            if self.closing or self.connection_stop_event.is_set():
                return
            
            if self.drone_manager.link and self.drone_manager.link.is_connected and self.drone_manager.health.is_alive:
                print("DEBUG: La conexión global ya está establecida.")
                self._safe_run_task(self._apply_connection_success)
                return

            if self.drone_manager.setup_drone(mode=mode):
                self._safe_run_task(self._apply_connection_success)
            else:
                self._safe_run_task(
                    self._apply_connection_error,
                    "No s'ha pogut establir la sessio Mavlink. Revisa la IP/Port.",
                )
        except Exception as e:
            self._safe_run_task(
                self._apply_connection_error,
                f"Error critic al connectar: {e}",
            )
        finally:
            try:
                current = threading.current_thread()
                if getattr(self, "connection_thread", None) is current:
                    self.connection_thread = None
            except Exception:
                print ("Error limpiando connection_thread:", sys.exc_info())
                pass


    async def _apply_connection_success(self):
        self.btn_connect.text = "ONLINE"
        self.btn_connect.bgcolor = "#3498db"
        self.btn_takeoff.disabled = False
        self.speed_slider.disabled = False
        self.alt_slider.disabled = False
        self.alt_mode_radio.disabled = False
        self.radio_button_constant.disabled = False
        self.radio_button_variable.disabled = False
        self.btn_save_traj.disabled = False
        self.traj_switch.disabled = False
        self.btn_load_traj.disabled = False
        self.controlmode_radio.disabled = False
        self.btn_land.disabled = True
        self.is_updating = True
        self._safe_page_update()

    async def _apply_connection_error(self, message: str):
        self._on_connection_error(message)


    
    def _takeoff_action(self, e=None):
        if (
            self.selected_control_mode == DroneManager.CONTROL_TRAJECTORY
            and (not self.current_trajectory or not self.current_trajectory.points)
        ):
            self._show_message("No hay trayectoria cargada para volar en modo trajectory.", error=True)
            return
        if self.takeoff_thread and self.takeoff_thread.is_alive():
            return
        self._reset_session_ui()
        self.btn_takeoff.disabled = True
        self.speed_slider.disabled = True
        self.alt_slider.disabled = True
        self.alt_mode_radio.disabled = True
        self.radio_button_constant.disabled = True
        self.radio_button_variable.disabled = True
        
        self.traj_switch.value = False
        self.takeoff_stop_event.clear()
        self.is_creating_trajectory = False
        self.traj_switch.disabled = True
        self.btn_save_traj.disabled = True
        self.btn_load_traj.disabled = True
        self.controlmode_radio.disabled = True
        self.btn_takeoff.text = "EN PROCESO..."
        self.btn_takeoff.bgcolor = "gray"
        self._safe_page_update()

        
        
        try:
            target_alt = float(self.alt_slider.value)
        except Exception:
            target_alt = 2.5

        def takeoff_sequence():
            try:
                if self.takeoff_stop_event.is_set() or self.closing:
                    return
                success = self.drone_manager.arm_and_takeoff_safe(target_alt, mode="GUIDED", stop_event=self.takeoff_stop_event, closing_checker=lambda: self.closing,)

                if self.takeoff_stop_event.is_set() or self.closing:
                    return
                
                async def apply_result():
                    if self.takeoff_stop_event.is_set() or self.closing:
                        return
                    if success:
                        try:
                            task = self.drone_manager.start_selected_controller(self.current_trajectory)
                            if task == False:
                                self._show_message(
                                    "No se pudo activar el modo de control seleccionado.",
                                    error=True,
                                )
                        except Exception as ex:
                            self._show_message(f"Error iniciando control: {ex}", error=True)
                        self.btn_land.disabled = False
                        self.btn_land.text = "LAND"
                        self.btn_takeoff.text = "FLYING"
                    else:
                        self.btn_takeoff.disabled = False
                        self.speed_slider.disabled = False
                        self.alt_slider.disabled = False
                        self.alt_mode_radio.disabled = False
                        self.radio_button_constant.disabled = False
                        self.radio_button_variable.disabled = False
                        self.btn_save_traj.disabled = False
                        self.btn_load_traj.disabled = False
                        self.controlmode_radio.disabled = False
                        self.traj_switch.disabled = False
                        self.btn_takeoff.text = "TAKEOFF"
                        self.btn_takeoff.bgcolor = "#3b8ed0"
                        self._show_message(
                            "El dron no pudo despegar. Revisa GPS y modo GUIDED.",
                            error=True,
                        )
                    self._safe_page_update()

                self._safe_run_task(apply_result)
            finally:
                pass

        self.takeoff_thread = threading.Thread(
            target=takeoff_sequence,
            name="takeoff-sequence",
            daemon=False,
        )
        self.takeoff_thread.start()

    def _land_action(self, e=None):
        if self.closing:
            return
        if self.takeoff_stop_event:
            self.takeoff_stop_event.set()
        if self.drone_manager.link and self.drone_manager.link.vehicle:
            self.btn_land.disabled = True
            self.btn_land.text = "LANDING..."
            self._safe_page_update()
            self.drone_manager.link.vehicle.mode = VehicleMode("LAND")
            self.drone_manager.current_mode = "IDLE"
            self._clear_keyboard_state()
        if self.takeoff_thread and self.takeoff_thread.is_alive():
            self.takeoff_thread.join(timeout=2.0)
           

    # ========================================================
    # ARCHIVOS
    # ========================================================
    async def _save_trajectory_to_file(self, e=None):
        if not self.current_trajectory or not self.current_trajectory.points:
            self._show_message("No hay puntos en la trayectoria actual.", error=True)
            return

        try:
            data = self.current_trajectory.to_dict()
            payload = json.dumps(data, indent=2).encode("utf-8")

            file_path = await self.file_picker.save_file(
                dialog_title="Guardar trayectoria",
                file_name="trajectory.json",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
                src_bytes=payload if self.page.web else None,
            )

            if self.page.web:
                self._show_message("Trayectoria descargada correctamente.")
                return

            if not file_path:
                self._show_message("Guardado cancelado.", error=True)
                return

            with open(file_path, "wb") as f:
                f.write(payload)

            self._show_message("Trayectoria guardada correctamente.")

        except Exception as ex:
            self._show_message(f"Error al guardar archivo: {ex}", error=True)

    async def _load_trajectory_from_file(self, e=None):
        if self.closing:
            return

        try:
            files = await self.file_picker.pick_files(
                dialog_title="Importar trayectoria",
                with_data=True,
                allow_multiple=False,
                allowed_extensions=["json"],
            )

            if not files:
                self._show_message("No se seleccionó ningún archivo.", error=True)
                return

            selected = files[0]

            if self.page.web:
                if not selected.bytes:
                    self._show_message("No se pudo leer el contenido del archivo.", error=True)
                    return
                data = json.loads(selected.bytes.decode("utf-8"))
            else:
                with open(selected.path, "r", encoding="utf-8") as f:
                    data = json.load(f)

            self.current_trajectory = Trajectory.from_dict(data)
            points = self.current_trajectory.obtain_points()
            self.selected_waypoint_index = len(points) - 1 if points else None
            self._rebuild_trajectory_layers()
            self._safe_page_update()
            self._show_message("Trayectoria importada correctamente.")

        except Exception as ex:
            self._show_message(f"Error de archivo: {ex}", error=True)

    def _on_file_picker_result(self, e):
        if self.closing:
            return
        action = self.pending_file_action
        self.pending_file_action = None

        try:
            print (f"File Picker Result: action={action}, e={e}")
            if action == "save_trajectory":
                if not getattr(e, "path", None):
                    self.showmessage("No se recibió ruta de guardado.", error=True)
                    return
                file_path = e.path
                data = self.current_trajectory.to_dict()
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                self._show_message("Trayectoria guardada correctamente.")

            elif action == "load_trajectory":
                if not e.files:
                    self.showmessage("No se seleccionó ningún archivo.", error=True)
                    return
                selected = e.files[0]
                if self.page.web:
                    if not selected.bytes:
                        self._show_message("No se pudo leer el contenido del archivo.", error=True)
                        return
                    data = json.loads(selected.bytes.decode("utf-8"))
                else:
                    with open(selected.path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                self.current_trajectory = Trajectory.from_dict(data)
                points = self.current_trajectory.obtain_points()
                self.selected_waypoint_index = len(points) - 1 if points else None
                self._rebuild_trajectory_layers()
                #self._safe_update_map()
                self._safe_page_update()
                self._show_message("Trayectoria importada correctamente.")

        except Exception as ex:
            self._show_message(f"Error de archivo: {ex}", error=True)

    # ========================================================
    # CIERRE / RESET
    # ========================================================
    def _reset_session_ui(self):
        self.path_points = []
        self.altitude_history = []
        self.drone_path_layer.polylines = []
        self.drone_marker_layer.markers = []
        self.drone_marker = None
        self._refresh_altitude_chart()
        #._safe_update_map()
        self._safe_page_update()

    def _on_connection_error(self, message):
        self.btn_connect.text = "CONNECTAR"
        self.btn_connect.disabled = False
        self.btn_connect.bgcolor = "#28a745"
        self._safe_page_update()
        self._show_message(message, error=True)
        print(f"DEBUG: {message}")
        self._clear_keyboard_state()



    def _on_closing(self, reason="unknown"):
        with self._shutdown_lock:
            if self._shutdown_done:
                return
            self._shutdown_done = True

        print(f"SESIÓN CERRADA ({reason}) - limpiando recursos...")
        self.closing = True
        self.is_updating = False
        self.video_thread_running = False
        self._kb_thread_running = False

        try:
            if getattr(self, "takeoff_stop_event", None):
                self.takeoff_stop_event.set()
        except Exception as e:
            print(f"Error takeoff_stop_event.set(): {e}")


        try:
            if getattr(self, "connection_stop_event", None):
                self.connection_stop_event.set()
        except Exception as e:
            print(f"Error connection_stop_event.set(): {e}")
            
        self._clear_keyboard_state()

        # 1) cancelar tasks async de Flet
        for task_name in ("video_task", "ui_task"):
            task = getattr(self, task_name, None)
            if task:
                try:
                    task.cancel()
                except Exception as e:
                    print(f"Error cancelando {task_name}: {e}")
                setattr(self, task_name, None)

        # 2) detener componentes del drone manager
        try:
            if getattr(self.drone_manager, "health", None):
                self.drone_manager.health._stop_event().set()
        except Exception as e:
            print(f"Error health.stop(): {e}")

        try:
            if getattr(self.drone_manager, "kb_controller", None):
                self.drone_manager.kb_controller.stop()
        except Exception as e:
            print(f"Error kb_controller.stop(): {e}")

        # 3) desconexión MAVLink completa
        print("Cerrando la interfaz y limpiando conexiones locales; no se envían comandos de vuelo.")

        # Cerrar la interfaz no debe enviar comandos de vuelo.
        # El control del vehículo y sus failsafes se gestionan
        # independientemente del cierre de SafeFlight Desktop.

        # 5) join threads
        try:
            if getattr(self, "_kb_thread", None) and self._kb_thread.is_alive():
                self._kb_thread.join(timeout=2)
        except Exception as e:
            print(f"Error join kb_thread: {e}")
            
        try:
            if getattr(self, "takeoff_thread", None) and self.takeoff_thread.is_alive():
                self.takeoff_thread.join(timeout=3)
        except Exception as e:
            print(f"Error join takeoff_thread: {e}")
            
        try:
            if getattr(self, "connection_thread", None) and self.connection_thread.is_alive():
                self.connection_thread.join(timeout=3)
        except Exception as e:
            print(f"Error join connection_thread: {e}")

        print("Cierre de la interfaz: limpiando recursos...")

        try:
            self.destroy_global_drone_manager()
        except Exception as e:
            print(f"Error limpiando DroneManager: {e}")

        print("Limpieza de DroneManager finalizada.")

    def destroy_global_drone_manager(self):
        global _g_drone_manager

        dm = _g_drone_manager
        if dm is None:
            return

        try:
            if getattr(dm, "kbcontroller", None):
                dm.kb_controller.stop()
        except Exception:
            print ("Error deteniendo kb_controller:", sys.exc_info())
            pass

        try:
            if getattr(dm, "link", None):
                try:
                    if getattr(dm.link, "vehicle", None):
                        dm.link.vehicle.close()
                except Exception:
                    print ("Error cerrando vehicle:", sys.exc_info())
                    pass

                try:
                    dm.link.close()
                except Exception:
                    print ("Error cerrando link:", sys.exc_info())
                    pass
        except Exception:
            print ("Error limpiando link:", sys.exc_info())
            pass

        try:
            dm.link = None
        except Exception:
            pass

        try:
            dm.homelocation = None
        except Exception:
            print ("Error limpiando home_location:", sys.exc_info())
            pass

        _g_drone_manager = None
        self.drone_manager = None
        self.is_updating = False
        self.drone_marker = None
        self.drone_path_layer = None
        self.flight_start_time = None
        self.path_points: List[Tuple[float, float]] = []
        self.last_heading = -1
        self.altitude_history: List[float] = []
        self.is_video_main = False
        self.map_follow_drone = True
        self.map_initialized = False
        self.last_centered_pos = None
        self.drone_icon_container = None
        self.last_known_lat = 41.3874
        self.last_known_lon = 2.1686
        print("✓ DroneManager global destruido")
    # UTILIDADES UI
    # ========================================================
    def _show_message(self, message: str, error: bool = False):
        self.snack.content = ft.Text(message, color="white")
        self.snack.bgcolor = "#c0392b" if error else "#2d89ef"
        self.snack.open = True
        self._safe_page_update()

    def _refresh_altitude_chart(self):
        if not self.altitude_history:
            points = [fch.LineChartDataPoint(0, 0)]
            min_y = -0.5
            max_y = 5
            max_x = 10
        else:
            sliced = self.altitude_history[-120:]
            points = [
                fch.LineChartDataPoint(i, float(v))
                for i, v in enumerate(sliced)
            ]
            data_min = min(sliced)
            data_max = max(sliced)
            margin = max(0.5, (data_max - data_min) * 0.15)
            min_y = data_min - margin
            max_y = data_max + margin
            max_x = max(1, len(sliced) - 1)

        self.alt_chart.data_series = [
            fch.LineChartData(
                points=points,           # ← "points" en vez de "data"
                stroke_width=3,          # ← más gruesa
                color="#3498db",
                curved=True,             # ← suavizada
                rounded_stroke_cap=True, # ← extremos redondeados
                point=fch.ChartCirclePoint(radius=1, color="#3498db"),  # ← puntos
            )
        ]
        self.alt_chart.min_y = min_y
        self.alt_chart.max_y = max_y
        self.alt_chart.min_x = 0
        self.alt_chart.max_x = max_x
        try:
            self._safe_control_update(self.alt_chart, "alt_chart.update")
        except Exception as e:
            print("UI update failed:", e)


    # ========================================================
    # CÁLCULOS / LÓGICA
    # ========================================================
    def _has_moved_significantly(self, p1, p2):
        return abs(p1[0] - p2[0]) > 0.000005 or abs(p1[1] - p2[1]) > 0.000005

    def get_distance_metres(self, loc1, loc2):
        dlat = loc2.lat - loc1.lat
        dlong = loc2.lon - loc1.lon
        return math.sqrt((dlat * 111319.5) ** 2 + (dlong * 111319.5) ** 2)

    def get_home_pixel_position(self, vehicle, home_loc, screen_width, screen_height):
        if not home_loc or not vehicle.location.global_relative_frame:
            return None

        current_loc = vehicle.location.global_relative_frame
        dist = self.get_distance_metres(current_loc, home_loc)
        if dist < 5.0:
            return None

        dlat = home_loc.lat - current_loc.lat
        dlon = home_loc.lon - current_loc.lon

        angle_to_home = math.atan2(dlon, dlat)
        angle_to_home_deg = math.degrees(angle_to_home) % 360
        diff_angle = (angle_to_home_deg - vehicle.heading + 180) % 360 - 180

        fov_x = 80

        if abs(diff_angle) < fov_x / 2:
            x_pos = (diff_angle / (fov_x / 2)) * (screen_width / 2) + (screen_width / 2)

            fov_y = 60
            rel_alt = current_loc.alt - home_loc.alt

            if dist > 0:
                pitch_angle = math.degrees(math.atan2(rel_alt, dist))
            else:
                pitch_angle = 90

            y_pos = (pitch_angle / (fov_y / 2)) * (screen_height / 2) + (screen_height / 2)

            return int(x_pos), int(y_pos), pitch_angle

        return None

    def project_waypoint_to_pixel(
        self,
        vehicle,
        waypoint,
        screen_w,
        screen_h,
        fovx_deg=80,
        fovy_deg=60,
    ):
        """
        Proyecta un waypoint 3D a coordenadas píxel.
        Retorna (x, y, pitch_deg, dist) o None si está fuera FOV.
        """
        drone_loc = vehicle.location.global_relative_frame
        if not drone_loc:
            return None

        dlat = waypoint.x - drone_loc.lat
        dlon = waypoint.y - drone_loc.lon
        dx = dlat * 111319.5
        dy = dlon * 111319.5 * math.cos(math.radians(drone_loc.lat))
        dz = waypoint.z - drone_loc.alt

        dist_xy = math.sqrt(dx**2 + dy**2)
        if dist_xy < 0.5:
            return None

        dist_3d = math.sqrt(dist_xy**2 + dz**2)

        angle_to_wp_rad = math.atan2(dy, dx)
        angle_to_wp_deg = math.degrees(angle_to_wp_rad)

        drone_heading_deg = vehicle.heading
        rel_angle_deg = angle_to_wp_deg - drone_heading_deg
        rel_angle_deg = (rel_angle_deg + 180) % 360 - 180

        if abs(rel_angle_deg) > fovx_deg / 2:
            return None

        x = int((rel_angle_deg / (fovx_deg / 2)) * (screen_w / 2) + screen_w / 2)

        pitch_angle_deg = math.degrees(math.atan2(dz, dist_xy))

        if abs(pitch_angle_deg) > fovy_deg / 2:
            return None

        y = int((pitch_angle_deg / (fovy_deg / 2)) * (screen_h / 2) + screen_h / 2)

        return (x, y, pitch_angle_deg, dist_3d)

    def _ui_gone(self, origin: str, exc: Exception | None = None):
        if self.closing:
            return False
        print(f"[UI CLOSED] {origin}: {exc}")
        self._on_closing(origin)
        return False

    def _safe_page_update(self):
        if self.closing:
            return False
        try:
            self.page.update()
            return True
        except Exception as e:
            return self._ui_gone("page.update", e)

    def _safe_control_update(self, control, name="control.update"):
        if self.closing:
            return False
        try:
            control.update()
            return True
        except Exception as e:
            return self._ui_gone(name, e)

    def _safe_run_task(self, coro, *args, **kwargs):
        if self.closing:
            return None
        try:
            return self.page.run_task(coro, *args, **kwargs)
        except Exception as e:
            self._ui_gone("page.run_task", e)
            return None


def main(page: ft.Page):
    
    SafeFlightApp(page)


if __name__ == "__main__":
    ft.context.disable_auto_update()
    ft.run(main)