bl_info = {
    "name": "Spaceship Generator",
    "author": "Michael Davies",
    "version": (2, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Add > Mesh",
    "description": "Procedurally generate 3D spaceships from a random seed.",
    "wiki_url": "https://github.com/PuKoren/SpaceshipGenerator/blob/master/README.md",
    "tracker_url": "https://github.com/PuKoren/SpaceshipGenerator/issues",
    "category": "Add Mesh"
}

if "bpy" in locals():
    # reload logic (magic)
    import importlib
    importlib.reload(spaceship_generator)
else:
    from . import spaceship_generator

import bpy
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty, EnumProperty
from bpy.types import Operator

class GenerateSpaceship(Operator):
    """Procedurally generate 3D spaceships from a random seed."""
    bl_idname = "mesh.generate_spaceship"
    bl_label = "Spaceship"
    bl_options = {'REGISTER', 'UNDO'}

    random_seed : StringProperty(default='', name='Seed')
    num_hull_segments_min      : IntProperty (default=3, min=0, soft_max=16, name='Min. Hull Segments')
    num_hull_segments_max      : IntProperty (default=6, min=0, soft_max=16, name='Max. Hull Segments')
    create_asymmetry_segments  : BoolProperty(default=True, name='Create Asymmetry Segments')
    num_asymmetry_segments_min : IntProperty (default=1, min=1, soft_max=16, name='Min. Asymmetry Segments')
    num_asymmetry_segments_max : IntProperty (default=5, min=1, soft_max=16, name='Max. Asymmetry Segments')
    create_face_detail         : BoolProperty(default=True,  name='Create Face Detail')
    allow_horizontal_symmetry  : BoolProperty(default=True,  name='Allow Horizontal Symmetry')
    allow_vertical_symmetry    : BoolProperty(default=False, name='Allow Vertical Symmetry')
    apply_bevel_modifier       : BoolProperty(default=True,  name='Apply Bevel Modifier')
    archetype                  : EnumProperty(default='wedge', name='Archetype', items=(
        ('classic', 'Classic', 'A chain of extruded boxes, as the generator always drew'),
        ('wedge', 'Wedge', 'One flat arrowhead over a stern engine row'),
        ('fighter', 'Fighter', 'A slender fuselage with swept wings'),
        ('freighter', 'Freighter', 'A cab, a spine and a train of containers'),
        ('saucer', 'Saucer', 'A lens with mandibles and a cockpit bump'),
        ('spine', 'Spine', 'Modules hung along a boom'),
        ('pod', 'Pod', 'A short tug on two engine pods')))
    taper                      : FloatProperty(default=0.5, min=0, max=1, name='Taper')
    wing_span                  : FloatProperty(default=0.5, min=0, max=1, name='Wing Span')
    fuselage_roundness         : FloatProperty(default=0.5, min=0, max=1, name='Fuselage Roundness')
    assign_materials           : BoolProperty(default=True,  name='Assign Materials')
    nose_taper                 : FloatProperty(default=0, min=0, max=0.95, name='Nose Taper')
    min_slenderness            : FloatProperty(default=0, min=0, soft_max=8, name='Min. Slenderness')
    asymmetry_chance           : FloatProperty(default=0.15, min=0, max=1, name='Asymmetry Chance')
    horizontal_symmetry_chance : FloatProperty(default=1, min=0, max=1, name='Horizontal Symmetry Chance')
    antenna_density            : FloatProperty(default=0.1, min=0, max=1, name='Antenna Density')
    create_weapons             : BoolProperty(default=True,  name='Create Weapons')

    def execute(self, context):
        spaceship_generator.generate_spaceship(
            self.random_seed,
            self.num_hull_segments_min,
            self.num_hull_segments_max,
            self.create_asymmetry_segments,
            self.num_asymmetry_segments_min,
            self.num_asymmetry_segments_max,
            self.create_face_detail,
            self.allow_horizontal_symmetry,
            self.allow_vertical_symmetry,
            self.apply_bevel_modifier,
            self.assign_materials,
            nose_taper=self.nose_taper,
            min_slenderness=self.min_slenderness,
            asymmetry_chance=self.asymmetry_chance,
            horizontal_symmetry_chance=self.horizontal_symmetry_chance,
            antenna_density=self.antenna_density,
            create_weapons=self.create_weapons,
            archetype=self.archetype,
            taper=self.taper,
            wing_span=self.wing_span,
            fuselage_roundness=self.fuselage_roundness)
        return {'FINISHED'}

def menu_func(self, context):
    self.layout.operator(GenerateSpaceship.bl_idname, text="Spaceship")

def register():
    bpy.utils.register_class(GenerateSpaceship)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)

def unregister():
    bpy.utils.unregister_class(GenerateSpaceship)
    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)

if __name__ == "__main__":
    register()
