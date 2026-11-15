import sys
import unittest
from pathlib import Path

import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spaceship_generator as generator


class GridGeometryTest(unittest.TestCase):
    def test_grid_does_not_extrude_neighbouring_hull_faces(self):
        mesh = bmesh.new()
        try:
            bmesh.ops.create_cube(mesh, size=2)
            mesh.normal_update()
            roof = next(face for face in mesh.faces if face.normal.z > 0.9)
            generator.add_grid_to_face(mesh, roof, depth=(0.1, 0.1), cuts=1, fractal=0)
            for axis in (0, 1):
                self.assertAlmostEqual(min(v.co[axis] for v in mesh.verts), -1, places=5)
                self.assertAlmostEqual(max(v.co[axis] for v in mesh.verts), 1, places=5)
            self.assertAlmostEqual(min(v.co.z for v in mesh.verts), -1, places=5)
            self.assertAlmostEqual(max(v.co.z for v in mesh.verts), 1.1, places=5)
        finally:
            mesh.free()


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
