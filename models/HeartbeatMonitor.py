
import threading
import time


class HeartbeatMonitor:
    def __init__(self, drone_connection, timeout=15.0):
        self.drone = drone_connection
        self.timeout = timeout
        self.last_heartbeat = time.time()
        self.latency = 0.0
        self.is_alive = True
        self._stop_event = threading.Event()

    def start(self, on_loss_callback):
        """Inicia el hilo de monitorización."""
        self.thread = threading.Thread(
            target=self._run,
            args=(on_loss_callback,),
            daemon=True,
        )
        self.thread.start()

    def _run(self, on_loss_callback):
        self.last_heartbeat = time.time()

        while not self._stop_event.is_set():
            if self.drone.vehicle is not None:
                # DroneKit devuelve los segundos transcurridos
                # desde el último heartbeat recibido.
                last_msg = self.drone.vehicle.last_heartbeat

                if last_msg is not None:
                    time_since_last = float(last_msg)
                    self.latency = time_since_last

                    if time_since_last > self.timeout:
                        print(
                            f"DEBUG: Latencia crítica: "
                            f"{time_since_last:.2f}s"
                        )
                        self.is_alive = False
                        on_loss_callback()
                        break

            self._stop_event.wait(1.0)

    def stop(self):
        """Detiene el monitor."""
        self._stop_event.set()
