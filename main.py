import collections
import collections.abc
collections.MutableMapping = collections.abc.MutableMapping
import time
from models.DroneManager import DroneManager
from dronekit import VehicleMode
import keyboard

def main():
    manager = DroneManager()

    if not manager.setup_drone():
        print("Error: No se pudo conectar.")
        return

    while True: # Bucle principal de la aplicación
        print("\n--- MENÚ PRINCIPAL ---")
        print("1. Despegar y Control Manual")
        print("2. Salir de la aplicación")
        opcion = input("Selecciona una opción: ")

        if opcion == "1":
            try:
                manager.arm_and_takeoff_safe(altitude=5, mode = "STABILIZE")
                manager.set_mode_infantil()

                print("\nVOLANDO. Pulsa 'ESC' para aterrizar y volver al menú.")
                while manager.current_mode != "EMERGENCY":
                    manager.tick()
                    time.sleep(0.1)
                    
                    if keyboard.is_pressed('esc'):
                        print("Aterrizaje solicitado por usuario...")
                        break
                
                manager.link.vehicle.mode = VehicleMode("LAND")
                print("Esperando a que el dron toque suelo...")
                while manager.link.vehicle.location.global_relative_frame.alt > 2.0:
                    time.sleep(1)
                print("Dron en tierra.")
                
                manager.current_mode = "IDLE"

            except Exception as e:
                print(f"Error durante el ciclo de vuelo: {e}")
        
        elif opcion == "2":
            break

    # 3. Limpieza final al salir de verdad
    if manager.link.vehicle:
        manager.link.disconnect()
if __name__ == "__main__":
    main()