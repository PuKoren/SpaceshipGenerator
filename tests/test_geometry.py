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


class HardwareTest(unittest.TestCase):
    def build(self, **fittings):
        mesh = bmesh.new()
        bmesh.ops.create_cube(mesh, size=2)
        mesh.normal_update()
        generator.add_archetype_detail(mesh, max_segments=8, **fittings)
        return mesh

    def test_fittings_are_drawn_on_the_half_the_mirror_keeps(self):
        mesh = self.build(pipes=1.0, armour=1.0, intakes=1.0, hubs=1.0, mounts=1.0, ladders=1.0, lattice=1.0)
        try:
            bmesh.ops.symmetrize(mesh, input=mesh.verts[:] + mesh.edges[:] + mesh.faces[:], direction="Y")
            seen = {(round(v.co.x, 4), round(v.co.y, 4), round(v.co.z, 4)) for v in mesh.verts}
            mirrored = sum((-x, y, z) in seen for x, y, z in seen)
            self.assertGreater(mirrored, 0.97 * len(seen))
        finally:
            mesh.free()

    def test_a_hull_lights_only_when_its_lights_are_asked_for(self):
        lit = self.build(lights=1.0)
        dark = self.build(lights=0.0)
        try:
            self.assertTrue(any(face.material_index == generator.Material.light for face in lit.faces))
            self.assertFalse(any(face.material_index == generator.Material.light for face in dark.faces))
        finally:
            lit.free()
            dark.free()


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
