class Point:
    def __init__(self, x, y, z, name = None):
        self.x = x
        self.y = y
        self.z = z
        self.name = name
    def __repr__(self):
        return f"Point({self.x}, {self.y}, {self.z}, name={self.name})"
    def get_coords(self):
        return (self.x, self.y, self.z)