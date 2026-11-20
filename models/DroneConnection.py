from dronekit import connect

class DroneConnection: 
    def __init__(self, connection_string, baud_rate=57600, heartbeat_timeout=30, timeout=90):
        self.connection_string = connection_string
        self.baud_rate = baud_rate
        self.heartbeat_timeout = heartbeat_timeout
        self.timeout = timeout
        self.vehicle = None
        self.is_connected = False
    def connect(self):
        try:
            print(f"Estableciendo enlace MAVLink en {self.connection_string}...")
            print(f"DEBUG DroneConnection.connect() conn_str={self.connection_string}")

            # wait_ready=True es fundamental para el Cube Orange
            # Le da tiempo a descargar los parámetros y entender el estado del dron
            self.vehicle = connect(
                self.connection_string, 
                baud=self.baud_rate, 
                wait_ready=False,
                heartbeat_timeout=self.heartbeat_timeout,
                timeout=self.timeout,
            )
            
            if self.vehicle:
                self.is_connected = True
                print("Conexión establecida con éxito.")
                return True
            return False
        except Exception as e:
            print(f"Error del enlace: {e}")
            return False
        
    def disconnect(self):
        if self.vehicle:
            self.vehicle.close()
            self.vehicle = None
            self.is_connected = False
    