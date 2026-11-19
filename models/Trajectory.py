import math

from models.Point import Point

class Trajectory:
    def __init__(self, name):
        self.name = name
        self.points = []
        
    def add_point(self, x, y, z = 0 , name=None):
        newpoint = Point(x,y,z,name)
        self.points.append(newpoint)
        print(f"Point added '{self.name}': {newpoint}")
        
    def calcular_distancia_total(self):
        distancia = 0
        for i in range (len(self.puntos)-1):
            p1 = self.puntos[i]
            p2 = self.puntos[i+1]
            distancia += math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2 + (p2.z - p1.z)**2)
        return distancia
    
    def obtain_points (self):
        return self.points
    
    def to_dict(self):
        return {
            "name": self.name,
            "points": [
                {"x": p.x, "y": p.y, "z": p.z, "name": p.name}
                for p in self.points
            ]
        }

    @classmethod
    def from_dict(cls, data):
        traj = cls(data.get("name", "trayectoria_importada"))
        for pd in data.get("points", []):
            traj.add_point(
                pd["x"],
                pd["y"],
                pd.get("z", 0),
                pd.get("name")
            )
        return traj
    
        