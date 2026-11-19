# --- PARCHE DE COMPATIBILIDAD DRONEKIT ---
import os
import sys
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "protocol_whitelist;file,rtp,udp,tcp|fflags;nobuffer|flags;low_delay|strict;-2"
print(f"DEBUG ENV VAR: {os.environ.get('OPENCV_FFMPEG_CAPTURE_OPTIONS')}")
import collections
import collections.abc
if not hasattr(collections, 'MutableMapping'):
    collections.MutableMapping = collections.abc.MutableMapping
from dronekit import VehicleMode


def patch_dronekit_modes():
    """Parche definitivo para Dronekit: Inyecta modos y evita bloqueos."""
    standard_modes = {
        0: 'STABILIZE', 1: 'ACRO', 2: 'ALT_HOLD', 3: 'AUTO',
        4: 'GUIDED', 5: 'LOITER', 6: 'RTL', 7: 'CIRCLE',
        9: 'LAND', 11: 'DRIFT', 13: 'SPORT', 14: 'FLIP',
        15: 'AUTOTUNE', 16: 'POSHOLD', 17: 'BRAKE', 18: 'THROW',
        19: 'AVOID_ADSB', 20: 'GUIDED_NOGPS', 21: 'SMART_RTL',
        22: 'FLOWHOLD', 23: 'FOLLOW', 24: 'ZIGZAG', 25: 'SYSTEMID',
        26: 'AUTOROTATE', 27: 'AUTO_RTL'
    }

    try:
        if not hasattr(VehicleMode, 'fixed_mode_map'):
            VehicleMode.fixed_mode_map = standard_modes
        else:
            VehicleMode.fixed_mode_map.update(standard_modes)
    except Exception as e:
        print(f"Nota: No se pudo actualizar fixed_mode_map (no critico): {e}")

    original_init = VehicleMode.__init__

    def safe_init(self, name):
        if isinstance(name, int):
            name = standard_modes.get(name, f"UNKNOWN_{name}")
        elif name is None:
            name = "UNKNOWN"
        original_init(self, name)

    VehicleMode.__init__ = safe_init
    print("Dronekit Patch: Interceptor de modos activado.")

patch_dronekit_modes()

import ctypes
import json
import customtkinter as ctk
from tkintermapview import TkinterMapView
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from models.DroneManager import DroneManager
import threading
import time
import tkinter as tk
from tkinter import filedialog, simpledialog
from tkinter import messagebox
import cv2
import subprocess
import numpy as np
from PIL import Image, ImageTk
import math
from models.Trajectory import Trajectory


class SafeFlightApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SafeFlight App")
        self.geometry("1366x768")
        my_app_id = "safe_flight_app.safeflight.v1"
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(my_app_id)
        except:
            pass
        icon_path_logo = os.path.join(os.path.dirname(__file__), "assets", "safe_flight_2.ico")
        if os.path.exists(icon_path_logo):
            self.iconbitmap(icon_path_logo)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # 1. GESTION DE RECURSOS E ICONOS
        self.icon_path = os.path.join(os.path.dirname(__file__), "assets", "drone_icon.png")
        try:
            self.drone_img_raw = Image.open(self.icon_path).convert("RGBA")
        except:
            self.drone_img_raw = Image.new('RGBA', (60, 60), color=(0, 255, 0, 150))

        # 2. ESTADOS Y MANAGERS
        self.drone_manager = DroneManager()
        self.is_updating = False
        self.drone_marker = None
        self.drone_path = None
        self.flight_start_time = None
        self.path_points = []
        self.last_heading = -1
        self.altitude_history = []
        self.is_video_main = True
        self.vr_enabled = tk.BooleanVar(value=True)

        self.current_trajectory = Trajectory("test_trajectory")
        self.trajectory_path = None
        self.trajectory_markers = []

        self.is_creating_trajectory = tk.BooleanVar(value=False)
        self.altitude_mode = tk.StringVar(value="constant")

        # ── CAMBIO 1: columna central ocupa TODO al inicio ──────────────────
        # Las columnas 0 y 2 arrancan ocultas (weight=0, minsize=0)
        self.grid_columnconfigure(0, weight=0, minsize=0)
        self.grid_columnconfigure(1, weight=4)
        self.grid_columnconfigure(2, weight=0, minsize=0)
        self.grid_rowconfigure(0, weight=1)

        # Estado de visibilidad de los paneles laterales
        self.sidebar_visible = False
        self.telemetry_visible = False
        # ────────────────────────────────────────────────────────────────────

        self._build_sidebar()
        self._build_main_area()        # Contiene Video, Mapa y botones toggle
        self._build_telemetry_area()

        # ── CAMBIO 2: ocultar paneles despues de construirlos ───────────────
        self.sidebar.grid_remove()
        self.telemetry_frame.grid_remove()
        # ────────────────────────────────────────────────────────────────────

        # 4. CAMARA Y PROTOCOLOS
        self.frame_lock = threading.Lock()
        self.latest_frame = None
        self.video_thread_running = True

        self.video_thread = threading.Thread(target=self._video_worker, daemon=True)
        self.video_thread.start()

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Iniciar bucles
        self._update_video_display_loop()
        self.update()

    # ──────────────────────────────────────────────────────────────────────────
    # CAMBIO 3: metodos toggle para mostrar/ocultar paneles laterales
    # ──────────────────────────────────────────────────────────────────────────
    def _toggle_sidebar(self):
        if self.sidebar_visible:
            self.sidebar.grid_remove()
            self.grid_columnconfigure(0, weight=0, minsize=0)
            self.btn_toggle_sidebar.configure(fg_color="#1e1e2e")
        else:
            self.sidebar.grid()
            self.grid_columnconfigure(0, weight=1)
            self.btn_toggle_sidebar.configure(fg_color="#3b8ed0")
        self.sidebar_visible = not self.sidebar_visible

    def _toggle_telemetry(self):
        if self.telemetry_visible:
            self.telemetry_frame.grid_remove()
            self.grid_columnconfigure(2, weight=0, minsize=0)
            self.btn_toggle_telemetry.configure(fg_color="#1e1e2e")
        else:
            self.telemetry_frame.grid()
            self.grid_columnconfigure(2, weight=1)
            self.btn_toggle_telemetry.configure(fg_color="#3b8ed0")
        self.telemetry_visible = not self.telemetry_visible

    # ──────────────────────────────────────────────────────────────────────────

    def _video_worker(self):
        """Este hilo se encarga de leer OpenCV sin bloquear la App"""
        sdp_file = os.path.join(os.path.dirname(__file__), "stream.sdp")

        while self.video_thread_running:
            cap = cv2.VideoCapture(sdp_file, cv2.CAP_FFMPEG)

            if not cap.isOpened():
                print("[VIDEO] Esperando stream... (reintentando en 2s)")
                cap.release()
                time.sleep()
                continue

            print("[VIDEO] Conexion establecida.")

            while self.video_thread_running and cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    with self.frame_lock:
                        self.latest_frame = frame
                else:
                    print("[VIDEO] Stream perdido.")
                    break

            cap.release()
            time.sleep(1)

    def _build_sidebar(self):
        self.sidebar = ctk.CTkScrollableFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(self.sidebar, text="SAFEFLIGHT", font=ctk.CTkFont(size=22, weight="bold")).pack(pady=20)

        # CONEXION
        self.conn_entry = ctk.CTkEntry(self.sidebar)
        self.conn_entry.insert(0, "udpin:0.0.0.0:14560")
        self.conn_entry.pack(padx=20, pady=5, fill="x")
        self.btn_connect = ctk.CTkButton(self.sidebar, text="CONNECTAR", fg_color="#28a745", command=self._connect_action)
        self.btn_connect.pack(padx=20, pady=10, fill="x")

        # AJUSTES
        ctk.CTkLabel(self.sidebar, text="CONFIGURACIO DE MISSIO", font=("Arial", 12, "bold"), text_color="gray").pack(pady=(20, 5))

        self.speed_val_str = ctk.StringVar(value="1 m/s")
        ctk.CTkLabel(self.sidebar, text="Velocitat:").pack(padx=20, anchor="w")
        self.speed_slider = ctk.CTkSlider(self.sidebar, from_=0.1, to=5.0, command=lambda v: self.speed_val_str.set(f"{v:.1f} m/s"))
        self.speed_slider.set(0.5)
        self.speed_slider.pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(self.sidebar, textvariable=self.speed_val_str, text_color="#3b8ed0").pack()

        self.alt_val_str = ctk.StringVar(value="2.5 m")
        ctk.CTkLabel(self.sidebar, text="Altutitud de takeoff (m):").pack(padx=20, pady=(15, 0), anchor="w")
        self.alt_slider = ctk.CTkSlider(self.sidebar, from_=1, to=20, number_of_steps=19, command=lambda v: self.alt_val_str.set(f"{int(v)} m"))
        self.alt_slider.set(2.5)
        self.alt_slider.pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(self.sidebar, textvariable=self.alt_val_str, text_color="#3b8ed0").pack()

        # COMANDOS
        ctk.CTkLabel(self.sidebar, text="COMANDAMENTS", font=("Arial", 12, "bold"), text_color="gray").pack(pady=(30, 5))
        self.btn_takeoff = ctk.CTkButton(self.sidebar, text="TAKEOFF", command=self._takeoff_action, state="disabled", height=40)
        self.btn_takeoff.pack(padx=20, pady=10, fill="x")

        self.btn_land = ctk.CTkButton(self.sidebar, text="LAND", fg_color="#e67e22", command=self._land_action, state="disabled")
        self.btn_land.pack(padx=20, pady=5, fill="x")

        # TRAJECTORY SETTINGS
        ctk.CTkLabel(self.sidebar, text="TRAJECTORY COMMANDS", font=("Arial", 12, "bold"), text_color="gray").pack(pady=(30, 5))

        self.traj_switch = ctk.CTkSwitch(self.sidebar, text="Crear trayectoria", variable=self.is_creating_trajectory)
        self.traj_switch.pack(padx=20, pady=5, anchor="w")
        ctk.CTkLabel(self.sidebar, text="Altura trayectoria:").pack(padx=20, anchor="w")
        self.alt_radio_const = ctk.CTkRadioButton(self.sidebar, text="Altura constante TO", variable=self.altitude_mode, value="constant")
        self.alt_radio_const.pack(padx=20, pady=2, anchor="w")

        self.alt_radio_var = ctk.CTkRadioButton(self.sidebar, text="Altura variable", variable=self.altitude_mode, value="variable")
        self.alt_radio_var.pack(padx=20, pady=2, anchor="w")

        self.btn_save_traj = ctk.CTkButton(self.sidebar, text="Save trajectory", fg_color="#3b8ed0", command=self._save_trajectory_to_file)
        self.btn_save_traj.pack(padx=20, pady=5, fill="x")

        self.btn_load_traj = ctk.CTkButton(self.sidebar, text="Import trajectory", command=self._load_trajectory_from_file)
        self.btn_load_traj.pack(padx=20, pady=5, fill="x")

        self.btn_clear_traj = ctk.CTkButton(self.sidebar, text="Clear Trajectory", fg_color="#e74c3c", command=self._clear_trajectory)
        self.btn_clear_traj.pack(padx=20, pady=10, fill="x")

        # APP SETTINGS
        ctk.CTkLabel(self.sidebar, text="APP SETTINGS", font=("Arial", 12, "bold"), text_color="gray").pack(pady=(30, 5))
        self.vr_switch = ctk.CTkSwitch(self.sidebar, text="VR Origen", variable=self.vr_enabled)
        self.vr_switch.pack(padx=20, pady=10, anchor="w")

    def _build_main_area(self):
        self.main_view = ctk.CTkFrame(self, corner_radius=15, fg_color="#1a1a1a")
        self.main_view.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        # 1. Contenedor de VIDEO
        self.video_container = ctk.CTkFrame(self.main_view, corner_radius=12, fg_color="black")
        self.video_canvas = tk.Canvas(self.video_container, bg="black", highlightthickness=0)
        self.video_canvas.pack(fill="both", expand=True)

        # 2. Contenedor de MAPA
        self.map_container = ctk.CTkFrame(self.main_view, corner_radius=12, fg_color="black")
        self.map_widget = TkinterMapView(self.map_container, corner_radius=12)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}")
        self.map_widget.add_left_click_map_command(self._map_left_click_add_point)

        # 3. Boton de Swap (sin cambios, identico al original)
        self.btn_swap = ctk.CTkButton(
            self.main_view, text="🔁", width=40, height=30,
            font=ctk.CTkFont(size=25), fg_color="#2b2b2b", hover_color="#3a3a3a",
            command=self._toggle_view
        )
        self.btn_swap.place(relx=0.98, rely=0.02, anchor="ne")

        # ── CAMBIO 4: botones toggle en la parte inferior del main_view ─────
        self.btn_toggle_sidebar = ctk.CTkButton(
            self.main_view, text="☰  CONTROLES", width=140, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1e1e2e", hover_color="#2b2b3b", corner_radius=10,
            command=self._toggle_sidebar
        )
        self.btn_toggle_sidebar.place(relx=0.01, rely=0.97, anchor="sw")
        self.hud_bar = tk.Frame(self.main_view, bg="#1e1e2e", bd=0, highlightthickness=0)
                
        self.hud_bar.place(relx=0.5, rely=0.96, anchor="s", width=950)

        # ARM/DISARM status
        self.lbl_arm = ctk.CTkLabel(self.hud_bar, text="⬤ DISARMED",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#e74c3c")
        self.lbl_arm.pack(side="left", padx=10)

        # Separador
        ctk.CTkLabel(self.hud_bar, text="|", text_color="#444").pack(side="left")

        # Modo de vuelo
        self.lbl_mode = ctk.CTkLabel(self.hud_bar, text="MODE: ---",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
        self.lbl_mode.pack(side="left", padx=8)

        ctk.CTkLabel(self.hud_bar, text="|", text_color="#444").pack(side="left")

        # Altura
        self.lbl_alt_hud = ctk.CTkLabel(self.hud_bar, text="H: 0.0m",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
        self.lbl_alt_hud.pack(side="left", padx=8)

        ctk.CTkLabel(self.hud_bar, text="|", text_color="#444").pack(side="left")

        # Distancia al origen
        self.lbl_dist_hud = ctk.CTkLabel(self.hud_bar, text="D: 0m",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
        self.lbl_dist_hud.pack(side="left", padx=8)

        ctk.CTkLabel(self.hud_bar, text="|", text_color="#444").pack(side="left")

        # Velocidad
        self.lbl_speed = ctk.CTkLabel(self.hud_bar, text="SPD: 0.0m/s",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
        self.lbl_speed.pack(side="left", padx=8)

        ctk.CTkLabel(self.hud_bar, text="|", text_color="#444").pack(side="left")

        # Batería
        self.lbl_batt = ctk.CTkLabel(self.hud_bar, text="BAT: ---%",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
        self.lbl_batt.pack(side="left", padx=8)

        ctk.CTkLabel(self.hud_bar, text="|", text_color="#444").pack(side="left")

        # Tiempo de vuelo
        self.lbl_time = ctk.CTkLabel(self.hud_bar, text="T: 00:00",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
        self.lbl_time.pack(side="left", padx=8)

        ctk.CTkLabel(self.hud_bar, text="|", text_color="#444").pack(side="left")

        # Satélites
        self.lbl_sats = ctk.CTkLabel(self.hud_bar, text="SAT: 0",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
        self.lbl_sats.pack(side="left", padx=8)

        self.btn_toggle_telemetry = ctk.CTkButton(
            self.main_view, text="📊  TELEMETRIA", width=140, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1e1e2e", hover_color="#2b2b3b", corner_radius=10,
            command=self._toggle_telemetry
        )
        self.btn_toggle_telemetry.place(relx=0.99, rely=0.97, anchor="se")
        # ────────────────────────────────────────────────────────────────────

        self._arrange_views()

    def _clear_trajectory(self):
        self.current_trajectory = Trajectory("trayectoria_mapa")
        if self.trajectory_path:
            self.trajectory_path.delete()
            self.trajectory_path = None
        for m in self.trajectory_markers:
            m.delete()
        self.trajectory_markers.clear()

    def _arrange_views(self):
        """Sin cambios: logica original de swap video/mapa intacta."""
        self.video_container.place_forget()
        self.map_container.place_forget()

        if self.is_video_main:
            self.video_container.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.map_container.place(relx=0.74, rely=0.74, relwidth=0.24, relheight=0.24)
            self.map_container.lift()
        else:
            self.map_container.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.video_container.place(relx=0.74, rely=0.74, relwidth=0.24, relheight=0.24)
            self.video_container.lift()

        # Los tres botones flotantes siempre encima de video/mapa
        self.btn_swap.lift()
        self.btn_toggle_sidebar.lift()
        self.hud_bar.lift()  
        self.btn_toggle_telemetry.lift()
        self.update()

    def _toggle_view(self):
        self.is_video_main = not self.is_video_main
        self._arrange_views()
        self.after(50, lambda: self.map_widget.update())

    def _build_telemetry_area(self):
        self.telemetry_frame = ctk.CTkFrame(self, width=100, corner_radius=0)
        self.telemetry_frame.grid(row=0, column=2, sticky="nsew", padx=10, pady=10)

        self.lbl_status = ctk.CTkLabel(self.telemetry_frame, text="DISARMED", text_color="#e74c3c", font=("Arial", 16, "bold"))
        self.lbl_status.pack(pady=20)

        self.fig, self.ax = plt.subplots(figsize=(4, 5), dpi=80)
        self.fig.patch.set_facecolor('#2b2b2b')
        self.ax.set_facecolor('#1e1e1e')
        self.canvas_plt = FigureCanvasTkAgg(self.fig, master=self.telemetry_frame)
        self.canvas_plt.get_tk_widget().pack(fill="both", expand=True)

    def _map_left_click_add_point(self, coords_tuple):
        if not self.is_creating_trajectory.get():
            return

        lat, lon = coords_tuple

        mode = self.altitude_mode.get()
        if mode == "constant":
            alt = float(self.alt_slider.get())
        else:
            dialog = ctk.CTkInputDialog(
                title="Waypoint",
                text=f"Altura relativa del waypoint (m):\n(lat={lat:.5f}, lon={lon:.5f})"
            )
            result = dialog.get_input()

            if result is None or result == "":
                return

            try:
                alt = float(result)
            except ValueError:
                return

        self.current_trajectory.add_point(lat, lon, alt)

        position_list = [(p.x, p.y) for p in self.current_trajectory.obtain_points()]

        if self.trajectory_path is None:
            self.trajectory_path = self.map_widget.set_path(
                position_list,
                color="#00ff00",
                width=3,
                name="trayectoria_mapa"
            )
        else:
            self.trajectory_path.set_position_list(position_list)

        marker = self.map_widget.set_marker(lat, lon, text=f"P{len(position_list)}")
        self.trajectory_markers.append(marker)

    def _update_video_display_loop(self):
        if not self.winfo_exists(): return

        frame = None
        with self.frame_lock:
            if self.latest_frame is not None:
                frame = self.latest_frame.copy()

        if frame is not None:
            w = self.video_canvas.winfo_width()
            h = self.video_canvas.winfo_height()

            if w > 10 and h > 10:
                try:
                    frame = cv2.resize(frame, (w, h))

                    if self.drone_manager.link and self.drone_manager.link.vehicle:
                        vehicle = self.drone_manager.link.vehicle
                        home_data = self.get_home_pixel_position(vehicle, self.drone_manager.home_location, w, h)

                        if home_data and self.vr_enabled.get():
                            x, y, pitch_deg = home_data
                            dist = self.get_distance_metres(vehicle.location.global_relative_frame, self.drone_manager.home_location)

                            y = max(10, min(h - 10, y))
                            base_scale = 700
                            calculated_radius = base_scale / max(1, dist)
                            radius_x = int(max(15, min(200, calculated_radius)))
                            squash_factor = abs(math.sin(math.radians(pitch_deg)))
                            radius_y = int(radius_x * squash_factor)
                            radius_y = max(3, radius_y)

                            cv2.ellipse(frame, (x, y), (radius_x, radius_y), 0, 0, 360, (220, 220, 220), -1, lineType=cv2.LINE_AA)
                            cv2.ellipse(frame, (x, y), (radius_x, radius_y), 0, 0, 360, (0, 0, 0), 1, lineType=cv2.LINE_AA)

                            text_offset_y = y - radius_y - 12
                            cv2.putText(frame, "H", (x - 7, text_offset_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                            cv2.putText(frame, f"{int(dist)}m", (x - 10, y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                            if (self.currenttrajectory and 
                                self.currenttrajectory.points and 
                                self.vrenabled.get()):
                                
                                for wp in self.currenttrajectory.points:
                                    pixdata = self.project_waypoint_to_pixel(vehicle, wp, w, h)
                                    if pixdata is None:
                                        continue
                                        
                                    x, y, pitch_deg, dist = pixdata
                                    y = max(10, min(h - 10, y))  # límites pantalla
                                    
                                    # Radio escalado por distancia (como HOME)
                                    basescale = 900  # un poco más grande que HOME
                                    calculatedradius = basescale / max(1, dist)
                                    radiusx = int(max(20, min(250, calculatedradius)))
                                    squashfactor = abs(math.sin(math.radians(pitch_deg)))
                                    radiusy = int(radiusx * squashfactor)
                                    radiusy = max(5, radiusy)
                                    
                                    # Círculo relleno VERDE (estilo videojuego)
                                    cv2.ellipse(frame, (x, y), (radiusx, radiusy), 0, 0, 360, (0, 200, 0), -1, lineType=cv2.LINE_AA)
                                    cv2.ellipse(frame, (x, y), (radiusx, radiusy), 0, 0, 360, (0, 255, 0), 3, lineType=cv2.LINE_AA)
                                    
                                    # Borde brillante
                                    cv2.ellipse(frame, (x, y), (radiusx+2, radiusy+2), 0, 0, 360, (255, 255, 0), 2, lineType=cv2.LINE_AA)
                                    
                                    # Texto del waypoint
                                    textoffsety = y - radiusy - 15
                                    text = wp.name if wp.name else f"P{len(self.currenttrajectory.points)}"
                                    cv2.putText(frame, text, (x - 20, textoffsety), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                                    cv2.putText(frame, text, (x - 20, textoffsety), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                                    
                                    # Distancia
                                    cv2.putText(frame, f"{dist:.0f}m", (x - 15, y + radiusy + 15), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 255, 200), 1)
                            

                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame)
                    self.img_tk = ImageTk.PhotoImage(image=img)
                    self.video_canvas.create_image(0, 0, anchor="nw", image=self.img_tk)
                except Exception as e:
                    print(f"Error Render Video: {e}")

        self.after(10, self._update_video_display_loop)

    def _update_ui_loop(self):
        if not self.is_updating: return
        try:
            vehicle = self.drone_manager.link.vehicle
            if vehicle:
                v_mode = vehicle.mode.name
                is_active = vehicle.armed or v_mode in ["GUIDED", "TAKEOFF"]

                if not is_active and vehicle.location.global_relative_frame.alt < 0.3:
                    if self.btn_takeoff.cget("state") == "disabled":
                        self.btn_takeoff.configure(state="normal", text="TAKEOFF", fg_color="#3b8ed0")
                        self.btn_land.configure(state="disabled", text="LAND")
                else:
                    if self.btn_land.cget("state") == "disabled" and v_mode != "LAND":
                        self.btn_takeoff.configure(state="disabled", text="FLYING", fg_color="gray")
                        self.btn_land.configure(state="normal", text="LAND")

                if self.drone_manager.kb_controller:
                    self.drone_manager.kb_controller.speed = self.speed_slider.get()
                self.drone_manager.tick()

                status_text = f"MODE: {vehicle.mode.name}\nARMED: {vehicle.armed}"
                self.lbl_status.configure(text=status_text, text_color="#2ecc71" if vehicle.armed else "#e74c3c")

                lat, lon = vehicle.location.global_relative_frame.lat, vehicle.location.global_relative_frame.lon
                heading = vehicle.heading

                if lat and lon:
                    if abs(self.last_heading - heading) > 3 or self.drone_marker is None:
                        if self.drone_marker: self.drone_marker.delete()
                        rotated = self.drone_img_raw.rotate(-heading, resample=Image.BICUBIC)
                        self.drone_icon = ImageTk.PhotoImage(rotated.resize((45, 45)))
                        self.drone_marker = self.map_widget.set_marker(lat, lon, icon=self.drone_icon)
                        self.last_heading = heading
                    else:
                        self.drone_marker.set_position(lat, lon)

                    if not self.path_points or self._has_moved_significantly(self.path_points[-1], (lat, lon)):
                        self.path_points.append((lat, lon))
                        if not self.drone_path:
                            self.drone_path = self.map_widget.set_path(self.path_points, color="#ff1500", width=2)
                        else:
                            self.drone_path.set_position_list(self.path_points)

                    c_lat, c_lon = self.map_widget.get_position()
                    if abs(lat - c_lat) > 0.0006 or abs(lon - c_lon) > 0.0006:
                        self.map_widget.set_position(lat, lon)

                alt = max(0, vehicle.location.global_relative_frame.alt)
                self.altitude_history.append(alt)

                self.ax.clear()
                self.ax.plot(self.altitude_history, color="#3498db", linewidth=2)
                current_max = max(10, max(self.altitude_history) * 1.2)
                self.ax.set_ylim(0, current_max)
                self.ax.set_title(f"ALT: {alt:.1f} m", color="white")
                self.canvas_plt.draw_idle()
                
                # ── ACTUALIZAR HUD CENTRAL ───────────────────────────────────────────────
                # ARM / DISARM
                if vehicle.armed:
                    self.lbl_arm.configure(text="⬤ ARMED", text_color="#2ecc71")
                    if self.flight_start_time is None:
                        self.flight_start_time = time.time()
                else:
                    self.lbl_arm.configure(text="⬤ DISARMED", text_color="#e74c3c")
                    self.flight_start_time = None

                # Modo
                self.lbl_mode.configure(text=f"MODE: {vehicle.mode.name}")

                # Altura
                alt_hud = vehicle.location.global_relative_frame.alt
                self.lbl_alt_hud.configure(text=f"H: {alt_hud:.1f}m")

                # Distancia al origen
                if self.drone_manager.home_location:
                    dist_hud = self.get_distance_metres(
                        vehicle.location.global_relative_frame,
                        self.drone_manager.home_location
                    )
                    self.lbl_dist_hud.configure(text=f"D: {dist_hud:.0f}m")

                # Velocidad (módulo del vector velocidad 3D)
                vx = vehicle.velocity[0]
                vy = vehicle.velocity[1]
                vz = vehicle.velocity[2]
                speed = math.sqrt(vx**2 + vy**2 + vz**2)
                self.lbl_speed.configure(text=f"SPD: {speed:.1f}m/s")

                # Batería
                batt = vehicle.battery.level if vehicle.battery.level is not None else 0
                batt_color = "#aaaaaa" if batt > 50 else "#e67e22" if batt > 20 else "#e74c3c"
                self.lbl_batt.configure(text=f"BAT: {batt}%", text_color=batt_color)

                # Tiempo de vuelo
                if self.flight_start_time:
                    elapsed = int(time.time() - self.flight_start_time)
                    mins, secs = divmod(elapsed, 60)
                    self.lbl_time.configure(text=f"T: {mins:02d}:{secs:02d}")

                # Satélites
                sats = vehicle.gps_0.satellites_visible if vehicle.gps_0 else 0
                sat_color = "#aaaaaa" if sats >= 8 else "#e67e22" if sats >= 5 else "#e74c3c"
                self.lbl_sats.configure(text=f"SAT: {sats}", text_color=sat_color)
                # ─────────────────────────────────────────────────────────────────────────
                

        except Exception as e:
            print(f"Error UI Loop: {e}")

        self.after(75, self._update_ui_loop)

    def _connect_action(self):
        self.btn_connect.configure(text="CONECTANDO...", state="disabled")
        threading.Thread(target=self._connection_worker, args=(self.conn_entry.get(),), daemon=True).start()

    def _connection_worker(self, conn_string):
        os.environ["SIM_conn_str"] = conn_string
        try:
            if self.drone_manager.setup_drone(mode="SIM"):
                self.btn_connect.configure(text="ONLINE", fg_color="#3498db")
                self.btn_takeoff.configure(state="normal")
                self.btn_land.configure(state="disabled")
                self.is_updating = True
                self._update_ui_loop()
            else:
                self._on_connection_error("No s'ha pogut establir la sessio Mavlink. Revisa la IP/Port.")
        except Exception as e:
            self._on_connection_error(f"Error critic al connectar: {e}")

    def _takeoff_action(self):
        """Un sol click arma i s'enlaira immediatament"""
        self._reset_session_ui()
        self.btn_takeoff.configure(state="disabled", text="EN PROCESO...", fg_color="gray")

        try:
            target_alt = float(self.alt_slider.get())
        except:
            target_alt = 2.5

        def takeoff_sequence():
            success = self.drone_manager.arm_and_takeoff_safe(target_alt, mode="GUIDED")

            if success:
                self.drone_manager.set_mode_infantil()
                self.btn_land.configure(state="normal", text="LAND")
                self.btn_takeoff.configure(text="FLYING")
            else:
                self.btn_takeoff.configure(state="normal", text="TAKEOFF", fg_color="#3b8ed0")
                messagebox.showwarning("Fallo de Despegue", "El dron no pudo despegar. Revisa GPS y modo GUIDED.")

        threading.Thread(target=takeoff_sequence, daemon=True).start()

    def _land_action(self):
        if self.drone_manager.link.vehicle:
            self.btn_land.configure(state="disabled", text="LANDING...")
            self.drone_manager.link.vehicle.mode = VehicleMode("LAND")
            self.drone_manager.current_mode = "IDLE"

    def _has_moved_significantly(self, p1, p2):
        return abs(p1[0] - p2[0]) > 0.000005 or abs(p1[1] - p2[1]) > 0.000005

    def _on_closing(self):
        self.is_updating = False
        self.video_thread_running = False

        try:
            if self.drone_manager.link and self.drone_manager.link.vehicle:
                vehicle = self.drone_manager.link.vehicle
                if vehicle.armed or vehicle.location.global_relative_frame.alt > 0.3:
                    vehicle.mode = VehicleMode("LAND")
                    time.sleep(0.5)
                self.drone_manager.link.disconnect()
        except Exception as e:
            print(f"Error cierre: {e}")

        self.destroy()
        os._exit(0)

    def _reset_session_ui(self):
        self.path_points = []
        self.altitude_history = []
        if self.drone_path:
            self.drone_path.delete()
            self.drone_path = None
        self.ax.clear()
        self.canvas_plt.draw()

    def _on_connection_error(self, message):
        self.btn_connect.configure(text="CONNECTAR", state="normal", fg_color="#28a745")
        messagebox.showerror("Error de Conexion", message)
        print(f"DEBUG: {message}")

    def get_distance_metres(self, loc1, loc2):
        dlat = loc2.lat - loc1.lat
        dlong = loc2.lon - loc1.lon
        return math.sqrt((dlat * 111319.5) ** 2 + (dlong * 111319.5) ** 2)
    

    def _save_trajectory_to_file(self):
        if not self.current_trajectory or not self.current_trajectory.points:
            messagebox.showinfo("Guardar trayectoria", "No hay puntos en la trayectoria actual.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            data = self.current_trajectory.to_dict()
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Guardar trayectoria", "Trayectoria guardada correctamente.")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def _load_trajectory_from_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.current_trajectory = Trajectory.from_dict(data)

            if self.trajectory_path:
                self.trajectory_path.delete()
                self.trajectory_path = None

            points = self.current_trajectory.obtain_points()
            position_list = [(p.x, p.y) for p in points]
            if position_list:
                self.trajectory_path = self.map_widget.set_path(
                    position_list,
                    color="#00ff00",
                    width=3,
                    name=self.current_trajectory.name
                )
                for idx, p in enumerate(points, start=1):
                    marker = self.map_widget.set_marker(
                        p.x, p.y,
                        text=p.name or f"P{idx}"
                    )
                    self.trajectory_markers.append(marker)

            messagebox.showinfo("Importar trayectoria", "Trayectoria importada correctamente.")
        except Exception as e:
            messagebox.showerror("Error al importar", str(e))

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
    
    def project_waypoint_to_pixel(self, vehicle, waypoint, screen_w, screen_h, fovx_deg=80, fovy_deg=60):
        """
        Proyecta un waypoint 3D (Point) a coordenadas píxel en la imagen.
        Retorna (x, y, pitch_deg, dist) o None si está fuera FOV.
        """
        drone_loc = vehicle.location.global_relative_frame
        if not drone_loc:
            return None
        
        # 1. Diferencia en metros (extensión de tu get_distance_metres)
        dlat = waypoint.x - drone_loc.lat
        dlon = waypoint.y - drone_loc.lon
        dx = dlat * 111319.5  # metros
        dy = dlon * 111319.5 * math.cos(math.radians(drone_loc.lat))
        dz = waypoint.z - drone_loc.alt  # altura relativa
        
        dist_xy = math.sqrt(dx**2 + dy**2)
        if dist_xy < 0.5:  # waypoint muy cerca
            return None
        
        dist_3d = math.sqrt(dist_xy**2 + dz**2)
        
        # 2. Ángulo relativo en horizontal (como tu get_home_pixel_position)
        angle_to_wp_rad = math.atan2(dy, dx)
        angle_to_wp_deg = math.degrees(angle_to_wp_rad)
        
        # 3. Rotar por heading del dron (como ya haces)
        drone_heading_deg = vehicle.heading
        rel_angle_deg = angle_to_wp_deg - drone_heading_deg
        rel_angle_deg = (rel_angle_deg + 180) % 360 - 180  # normalizar [-180,180]
        
        # 4. Si fuera del FOV horizontal
        if abs(rel_angle_deg) > fovx_deg / 2:
            return None
        
        # 5. Posición X en píxel (exacto como tu código actual)
        x = int((rel_angle_deg / (fovx_deg / 2)) * (screen_w / 2) + screen_w / 2)
        
        # 6. Pitch relativo (ángulo vertical del waypoint)
        pitch_angle_deg = math.degrees(math.atan2(dz, dist_xy))
        
        # 7. Si fuera del FOV vertical
        if abs(pitch_angle_deg) > fovy_deg / 2:
            return None
        
        # 8. Posición Y en píxel (invertido, centro arriba)
        y = int((pitch_angle_deg / (fovy_deg / 2)) * (screen_h / 2) + screen_h / 2)
        
        return (x, y, pitch_angle_deg, dist_3d)



if __name__ == "__main__":
    app = SafeFlightApp()
    app.mainloop()