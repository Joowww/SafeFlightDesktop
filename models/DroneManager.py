import time
import os
from .DroneConnection import DroneConnection
from .HeartbeatMonitor import HeartbeatMonitor
from .KeyboardController import KeyboardController
from .TrajectoryController import TrajectoryController 
from dronekit import VehicleMode
from dotenv import load_dotenv

load_dotenv() 
class DroneManager:
    """Capa superior que interactúa con la lógica de negocio y la GUI"""
    MODE_IDLE = "IDLE"
    MODE_GUIDED_STATIONARY = "GUIDED_STATIONARY"
    MODE_MANUAL_KEYBOARD = "MANUAL_KEYBOARD"
    MODE_FOLLOW_TRAJECTORY = "FOLLOW_TRAJECTORY"
    MODE_EMERGENCY = "EMERGENCY"
    CONTROL_KEYBOARD = "KEYBOARD"
    CONTROL_TRAJECTORY = "TRAJECTORY"
    
    def __init__(self):
        self.link = None
        self.health = None
        self.kb_controller = None
        self.trajectory_controller = None
        self.current_mode = self.MODE_IDLE
        self.selected_control_mode = self.CONTROL_TRAJECTORY
        self.home_location = None

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
            print(f"DEBUG: Usando conexión SIM: {conn_str}")
        elif mode == "REAL":
            conn_str = os.getenv("REAL_conn_str") or "udpin:0.0.0.0:14560"
        else:
            print(f"ERROR: Modo desconocido '{mode}'. Usa 'SIM' o 'REAL'.")
            return False
        self.link = DroneConnection(
            conn_str,
            baud_rate=baud_rate,
            heartbeat_timeout=heartbeat_timeout,
            timeout=connect_timeout,
        )
        print(f"DEBUG mode={mode}")
        print(f"DEBUG conn_str efectivo={conn_str}")
        if self.link.connect():
            self.health = HeartbeatMonitor(self.link)
            self.health.start(on_loss_callback=self._handle_emergency)
            self.kb_controller = KeyboardController(self.link.vehicle)
            self.trajectory_controller = TrajectoryController(self.link.vehicle)
            
            return True
        print("DEBUG: Falló la conexión en DroneConnection")
        return False
    def arm_and_takeoff_safe(self, altitude=3.0, mode = "LOITER", *, stop_event=None, closing_checker=None): #canviar modo a GUIDED para volar!
        vehicle = self.link.vehicle
        if not vehicle: 
            return False
        def should_stop():
            try:
                if stop_event is not None and stop_event.is_set():
                    return True
            except Exception:
                pass

            try:
                if closing_checker is not None and closing_checker():
                    return True
            except Exception:
                pass
            return False
        
        if should_stop():
            print ("Thread de despegue detenido")
            return False
            
        
        # --- REGISTRO DE HOME ---
        # Guardamos la posición actual como 'Home' antes de despegar
        # Esto es lo que usa tu HUD para calcular la distancia y la posición de la "H"
        self.home_location = vehicle.location.global_relative_frame
        print(f"--- Home registrado: Lat:{self.home_location.lat}, Lon:{self.home_location.lon} ---")

        # 1. FORZAR MODO GUIDED (Salida de LAND o cualquier otro modo)
        print("Cambiando a modo GUIDED...")
        vehicle.mode = VehicleMode(mode)
        
        timeout = 0
        while vehicle.mode.name != mode and timeout < 10:
            time.sleep(0.5)
            timeout += 1
            if timeout % 4 == 0: # Re-intentar si el Cube ignora el comando
                vehicle.mode = VehicleMode(mode)

        if vehicle.mode.name != mode:
            
            print("ERROR: El Cube rechazó GUIDED. ¿Tienes el mando en una posición fija?:" + vehicle.mode.name+ ""+ vehicle.system_status.state + ""+ str(vehicle.version))
            return False

        # 2. ESPERAR A QUE SEA ARMABLE (GPS y Sensores OK)
        # En el Cube Orange, esto puede tardar si acabas de encenderlo
        print("Esperando Pre-Arm Checks...")
        while not vehicle.is_armable:
            print(" Cube no listo: Revisa GPS Fix y nivelación...")
            time.sleep(1)

        # 3. ARMADO
        print("Armando motores...")
        vehicle.armed = True
        while not vehicle.armed:
            # Re-enviamos el comando de armado por si acaso
            vehicle.armed = True 
            time.sleep(0.5)
            print(" Confirmando armado...")

        # 4. DESPEGUE
        print(f"¡Despegando a {altitude}m!")
        vehicle.simple_takeoff(altitude)

        # Monitorizamos la subida para no devolver el control antes de tiempo
        while True:
            actual_alt = vehicle.location.global_relative_frame.alt
            if actual_alt >= altitude * 0.95:
                print("Altitud de seguridad alcanzada.")
                break
            time.sleep(0.5)
            
        self.current_mode = self.MODE_GUIDED_STATIONARY
        return True
    
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
        else:
            return False
    
    def set_mode_infantil(self):
        if self.link and self.link.is_connected:
            self.stop_active_controller()
            self.current_mode = self.MODE_MANUAL_KEYBOARD
            self.kb_controller.start()
            print("Modo infantil activado.")
     
    def set_mode_trajectory(self, trajectory):
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

        ok = self.trajectory_controller.start()
        if not ok:
            return False

        self.current_mode = self.MODE_FOLLOW_TRAJECTORY
        print("Modo seguimiento de trayectoria activado.")
        return True
            
    def _handle_emergency(self):
        print("EMERGÈNCIA: Conexió 5G perduda ")
        self.stop_active_controller()
        self.current_mode = self.MODE_EMERGENCY
        if self.link.vehicle:
            #Aterrizar
            self.link.vehicle.mode = VehicleMode("LAND")
            print("Comando LAND enviado por seguridad.")
            
        
    def tick(self):
        """Bucle principal de lógica de control."""
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

        if self.link and self.link.vehicle and self.link.vehicle.mode.name == "GUIDED":
            self.current_mode = self.MODE_GUIDED_STATIONARY
        else:
            self.current_mode = self.MODE_IDLE
    
    def set_speed(self, speed):
        if self.kb_controller:
            self.kb_controller.speed = speed

        if self.trajectory_controller:
            self.trajectory_controller.set_speed(speed)