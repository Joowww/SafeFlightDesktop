import collections
import collections.abc
collections.MutableMapping = collections.abc.MutableMapping

import time
import os
from models.DroneManager import DroneManager
from dronekit import VehicleMode
import keyboard

def main():
    manager = DroneManager()

    # 1. Conexión 5G (Se hace una sola vez al encender la app)
    if not manager.setup_drone(mode="REAL"):
        print("ERROR CRÍTICO: No hay comunicación con el dron.")
        return

    while True:
        print("\n--- MENÚ PRINCIPAL ---")
        print("1. Despegar y Control Manual")
        print("2. Salir de la aplicación")
        opcion = input("Selecciona una opción: ")

        if opcion == "1":
            try:
                # --- CHEQUEO DE SEGURIDAD PRE-VUELO ---
                v = manager.link.vehicle
                print(f"Estado: Batería: {v.battery.voltage}V | GPS: {v.gps_0.fix_type} | Modo: {v.mode.name}")
                
                #if v.battery.level is not None and v.battery.level < 20:
                #   print("¡ALERTA! Batería demasiado baja para volar.")
                #   continue

                # 2. Despegue (El nuevo método limpia el modo LAND automáticamente)
                manager.arm_and_takeoff_safe(altitude=2.5)
                manager.set_mode_infantil()

                print("\nVOLANDO. Pulsa 'ESC' para aterrizar.")
                
                # 3. Bucle de control activo
                while manager.current_mode != "EMERGENCY":
                    manager.tick()
                    time.sleep(0.1)
                    
                    if keyboard.is_pressed('esc'):
                        print("\nAterrizaje manual solicitado...")
                        break
                
                # 4. Fase de aterrizaje (Sin cerrar conexión)
                v.mode = VehicleMode("LAND")
                while v.location.global_relative_frame.alt > 0.3:
                    print(f"Descendiendo... Altitud: {v.location.global_relative_frame.alt:.2f}m")
                    time.sleep(1)
                
                print("Dron en tierra. Motores desarmados.")
                manager.current_mode = "IDLE" # Reset de estado para permitir re-vuelo

            except Exception as e:
                print(f"Excepción en vuelo: {e}")
                # Si algo falla gravemente, intentamos aterrizar
                manager.link.vehicle.mode = VehicleMode("LAND")
        
        elif opcion == "2":
            print("Cerrando enlace 5G...")
            break

    if manager.link and manager.link.vehicle:
        manager.link.disconnect()

if __name__ == "__main__":
    main()