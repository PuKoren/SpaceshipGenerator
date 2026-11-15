#
# spaceship_generator.py
#
# This is a Blender script that uses procedural generation to create
# textured 3D spaceship models. Written for Blender 2.77, kept working on Blender 4.2 and later.
#
# michael@spaceduststudios.com
# https://github.com/a1studmuffin/SpaceshipGenerator
#

import os
import os.path
import bpy
import bmesh
from math import sqrt, radians, cos, sin
from mathutils import Vector, Matrix
from random import random, seed, uniform, randint, randrange, getstate, setstate
from enum import IntEnum
from colorsys import hls_to_rgb

DIR = os.path.dirname(os.path.abspath(__file__))

def resource_path(*path_components):
    return os.path.join(DIR, *path_components)

# Deletes all existing spaceships and unused materials from the scene
def reset_scene():
    for item in bpy.data.objects:
        item.select_set(item.name.startswith('Spaceship'))
    bpy.ops.object.delete()
    for material in bpy.data.materials:
        if not material.users:
            bpy.data.materials.remove(material)
    for texture in bpy.data.textures:
        if not texture.users:
            bpy.data.textures.remove(texture)

# Extrudes a face along its normal by translate_forwards units.
# Returns the new face, and optionally fills out extruded_face_list
# with all the additional side faces created from the extrusion.
def extrude_face(bm, face, translate_forwards=0.0, extruded_face_list=None):
    new_faces = bmesh.ops.extrude_discrete_faces(bm, faces=[face])['faces']
    if extruded_face_list != None:
        extruded_face_list += new_faces[:]
    new_face = new_faces[0]
    bmesh.ops.translate(bm,
                        vec=new_face.normal * translate_forwards,
                        verts=new_face.verts)
    return new_face

# Similar to extrude_face, except corrigates the geometry to create "ribs".
# Returns the new face.
def ribbed_extrude_face(bm, face, translate_forwards, num_ribs=3, rib_scale=0.9):
    translate_forwards_per_rib = translate_forwards / float(num_ribs)
    new_face = face
    for i in range(num_ribs):
        new_face = extrude_face(bm, new_face, translate_forwards_per_rib * 0.25)
        new_face = extrude_face(bm, new_face, 0.0)
        scale_face(bm, new_face, rib_scale, rib_scale, rib_scale)
        new_face = extrude_face(bm, new_face, translate_forwards_per_rib * 0.5)
        new_face = extrude_face(bm, new_face, 0.0)
        scale_face(bm, new_face, 1 / rib_scale, 1 / rib_scale, 1 / rib_scale)
        new_face = extrude_face(bm, new_face, translate_forwards_per_rib * 0.25)
    return new_face

# Scales a face in local face space. Ace!
def scale_face(bm, face, scale_x, scale_y, scale_z):
    face_space = get_face_matrix(face)
    face_space.invert()
    bmesh.ops.scale(bm,
                    vec=Vector((scale_x, scale_y, scale_z)),
                    space=face_space,
                    verts=face.verts)

# Returns a rough 4x4 transform matrix for a face (doesn't handle
# distortion/shear) with optional position override.
def get_face_matrix(face, pos=None):
    x_axis = (face.verts[1].co - face.verts[0].co).normalized()
    z_axis = -face.normal
    y_axis = z_axis.cross(x_axis)
    if not pos:
        pos = face.calc_center_bounds()

    # Construct a 4x4 matrix from axes + position:
    # http://i.stack.imgur.com/3TnQP.png
    mat = Matrix()
    mat[0][0] = x_axis.x
    mat[1][0] = x_axis.y
    mat[2][0] = x_axis.z
    mat[3][0] = 0
    mat[0][1] = y_axis.x
    mat[1][1] = y_axis.y
    mat[2][1] = y_axis.z
    mat[3][1] = 0
    mat[0][2] = z_axis.x
    mat[1][2] = z_axis.y
    mat[2][2] = z_axis.z
    mat[3][2] = 0
    mat[0][3] = pos.x
    mat[1][3] = pos.y
    mat[2][3] = pos.z
    mat[3][3] = 1
    return mat

# Returns the rough length and width of a quad face.
# Assumes a perfect rectangle, but close enough.
def get_face_width_and_height(face):
    if not face.is_valid or len(face.verts[:]) < 4:
        return -1, -1
    width = (face.verts[0].co - face.verts[1].co).length
    height = (face.verts[2].co - face.verts[1].co).length
    return width, height

# Returns the rough aspect ratio of a face. Always >= 1.
def get_aspect_ratio(face):
    if not face.is_valid:
        return 1.0
    face_aspect_ratio = max(0.01, face.edges[0].calc_length() / face.edges[1].calc_length())
    if face_aspect_ratio < 1.0:
        face_aspect_ratio = 1.0 / face_aspect_ratio
    return face_aspect_ratio

# Returns true if this face is pointing behind the ship
def is_rear_face(face):
    return face.normal.x < -0.95

# Primary forms first; the classic face-detail pass remains available separately.

ARCHETYPES = ('classic', 'wedge', 'fighter', 'freighter', 'saucer', 'spine', 'pod')

# How one archetype's forms are arranged: its own balanced form, one solid tight
# form, two forms split across the beam, or forms tiered one over the other.
LAYOUTS = ('balanced', 'compact', 'split', 'stacked')


def _ring_points(width, height, roundness, sides=8):
    # A ring of half-extents `width` x `height`: at roundness 0 a crisply
    # chamfered rectangle, at 1 an octagon of the ellipse. Other side counts
    # always draw the ellipse.
    points = []
    flat = 1.0 / cos(radians(180.0 / sides))
    blend = min(max(roundness, 0.0), 1.0)
    for step in range(sides):
        angle = radians(360.0 * (step + 0.5) / sides)
        ca, sa = cos(angle), sin(angle)
        px, py = ca * flat, sa * flat
        if sides == 8:
            if abs(ca) >= abs(sa):
                bx, by = (1.0 if ca > 0 else -1.0), 0.7 * (1.0 if sa > 0 else -1.0)
            else:
                bx, by = 0.7 * (1.0 if ca > 0 else -1.0), (1.0 if sa > 0 else -1.0)
            px, py = bx * (1.0 - blend) + px * blend, by * (1.0 - blend) + py * blend
        points.append((px * width, py * height))
    return points

def _bridge_rings(bm, rings):
    faces = []
    for near, far in zip(rings, rings[1:]):
        count = len(near)
        for i in range(count):
            faces.append(bm.faces.new((near[i], far[i], far[(i + 1) % count], near[(i + 1) % count])))
    faces.append(bm.faces.new(rings[0]))
    faces.append(bm.faces.new(tuple(reversed(rings[-1]))))
    return faces

def _loft(bm, sections, sides=8, shift=0.0):
    # A volume through cross-sections (x, half_width, half_height, lift,
    # roundness), nose first, capped at both ends, centred on y = `shift`.
    rings = []
    for x, width, height, lift, roundness in sections:
        points = _ring_points(width, height, roundness, sides)
        rings.append([bm.verts.new((x, shift + py, lift + pz)) for py, pz in points])
    return _bridge_rings(bm, rings)

def _canopy(bm, sections):
    faces = _loft(bm, sections)
    for face in faces:
        face.material_index = Material.hull_dark
    roof, windshield = faces[1], faces[-2]
    roof.material_index = windshield.material_index = Material.glass

def _disc(bm, sections, sides=12, shift=0.0):
    # A volume stacked down Z through sections (z, radius_x, radius_y): a
    # saucer's language. Centred on y = `shift`.
    rings = []
    for z, radius_x, radius_y in sections:
        points = _ring_points(radius_x, radius_y, 1.0, sides)
        rings.append([bm.verts.new((px, shift + py, z)) for px, py in points])
    _bridge_rings(bm, rings)

def _wings(bm, root, span, chord, tip_chord, at_x, sweep, lift, rise, thickness):
    # A mirrored pair of thin tapered slabs, swept back by `sweep` and raised
    # by `rise` at the tip.
    for side in (1.0, -1.0):
        rings = []
        for y, half_chord, x, z in (
            (side * root, chord * 0.5, at_x, lift),
            (side * (root + span), tip_chord * 0.5, at_x - sweep, lift + rise),
        ):
            points = _ring_points(half_chord, thickness, 0.2)
            rings.append([bm.verts.new((x + px, y, z + pz)) for px, pz in points])
        _bridge_rings(bm, rings)

def _box(bm, matrix, size, material):
    # A block of `size`, placed by a frame and named by its material.
    result = bmesh.ops.create_cube(bm, size=1.0,
                                   matrix=matrix @ Matrix.Diagonal((size[0], size[1], size[2], 1.0)))
    for vert in result['verts']:
        for face in vert.link_faces:
            face.material_index = material

def _tube(bm, start, end, radius, material, segments=8):
    # A capped cylinder from one point to another.
    run = end - start
    turn = Vector((0.0, 0.0, 1.0)).rotation_difference(run.normalized()).to_matrix().to_4x4()
    result = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=max(4, segments),
                                   radius1=radius, radius2=radius, depth=run.length,
                                   matrix=Matrix.Translation((start + end) * 0.5) @ turn)
    for vert in result['verts']:
        for face in vert.link_faces:
            face.material_index = material

def _quad(bm, matrix, size, material):
    # A flat panel of `size` in a frame, facing the way the frame's own front does.
    corners = ((0.5, 0.5), (0.5, -0.5), (-0.5, -0.5), (-0.5, 0.5))
    face = bm.faces.new([bm.verts.new(matrix @ Vector((x * size[0], y * size[1], 0.0))) for x, y in corners])
    face.material_index = material


# The rings of one drive, per nozzle shape: (x, half-width, half-height, roundness), the last one
# closed and wearing the exhaust material. `bell` is the shape every hull had before shapes.
_NOZZLE_ROWS = {
    'bell': lambda x, r: (
        (x + r * 0.8, 1.0, 1.0, 1.0),
        (x - r * 0.55, 1.0, 1.0, 1.0),
        (x - r * 0.55, 0.72, 0.72, 1.0),
        (x - r * 0.12, 0.6, 0.6, 1.0),
    ),
    'round': lambda x, r: (
        (x + r * 0.7, 1.0, 1.0, 1.0),
        (x - r * 0.5, 1.0, 1.0, 1.0),
        (x - r * 0.5, 0.78, 0.78, 1.0),
        (x - r * 0.32, 0.78, 0.78, 1.0),
    ),
    'square': lambda x, r: (
        (x + r * 0.7, 1.0, 1.0, 0.0),
        (x - r * 0.5, 1.0, 1.0, 0.0),
        (x - r * 0.5, 0.8, 0.8, 0.0),
        (x - r * 0.3, 0.8, 0.8, 0.0),
    ),
    'slot': lambda x, r: (
        (x + r * 0.7, 1.0, 0.45, 0.25),
        (x - r * 0.5, 1.0, 0.45, 0.25),
        (x - r * 0.5, 0.84, 0.32, 0.25),
        (x - r * 0.3, 0.84, 0.32, 0.25),
    ),
    'grille': lambda x, r: (
        (x + r * 0.6, 1.0, 0.9, 0.0),
        (x - r * 0.45, 1.0, 0.9, 0.0),
        (x - r * 0.5, 0.92, 0.8, 0.0),
        (x - r * 0.62, 0.7, 0.58, 0.0),
    ),
}
# The shape a drive is drawn in, set once per hull by `generate_spaceship`.
_NOZZLE = 'bell'

def _engine_bell(bm, x, y, z, radius, shape=None):
    # A drive on the stern plane `x`, looking down -X: a bell or another of
    # the shapes a hull may be given, proud of the hull, its throat closed by
    # a floor that wears the exhaust material — the shape the classic
    # exhausts leave, so a reader of the mesh finds the same thing.
    shape = shape or _NOZZLE
    # A drive reads as one: the stern gives it a throat, and a hull's own scale is no reason to shrink it
    # to a rivet, so every shape is drawn a little wider than the throat it replaces.
    radius = radius * 1.3
    if shape == 'cluster':
        for offset_y, offset_z in ((0.0, radius * 0.26), (radius * 0.22, -radius * 0.13), (-radius * 0.22, -radius * 0.13)):
            _engine_bell(bm, x, y + offset_y, z + offset_z, radius * 0.5, 'round')
        return
    rings = []
    for ring_x, half_width, half_height, roundness in _NOZZLE_ROWS[shape](x, radius):
        points = _ring_points(radius * half_width, radius * half_height, roundness)
        rings.append([bm.verts.new((ring_x, y + py, z + pz)) for py, pz in points])
    faces = _bridge_rings(bm, rings)
    for face in faces:
        face.material_index = Material.hull_dark
    faces[-1].material_index = Material.exhaust_burn
    if shape == 'grille':
        # the bars that make a recessed mouth a grille rather than a hole
        for step in (-1, 1):
            _box(bm, Matrix.Translation((x - radius * 0.42, y, z + step * radius * 0.26)),
                 (radius * 0.14, radius * 1.7, radius * 0.1), Material.hull_dark)

def _engine_row(bm, x, z, count, radius, spread):
    if count > 1:
        radius = min(radius, spread / (count - 1) * 0.8)
    for i in range(count):
        y = 0.0 if count == 1 else spread * (2.0 * i / (count - 1) - 1.0)
        _engine_bell(bm, x, y, z, radius)

def _round_of(base, bias):
    return min(1.0, max(0.0, base + (bias - 0.5) * 0.6))

def _slab(bm, fore, aft, half_width, half_height, center_z, shift=0.0, r=0.08, taper=0.92):
    # A block from `fore` aft to `aft`, its section shrinking to `taper`. Laid
    # across the ship, fore and aft close together, it is a crossbeam.
    return _loft(bm, ((fore, half_width, half_height, center_z, r),
                      (aft, half_width * taper, half_height * taper, center_z, r)), shift=shift)

def _bridge(bm, fore, aft, half_width, half_height, center_z, r=0.15, glass=0.66):
    # A command block centred on `center_z` with a glazed canopy on its roof.
    # Returns the roof's height.
    _slab(bm, fore, aft, half_width, half_height, center_z, r=r, taper=0.94)
    roof = center_z + half_height
    canopy_h = half_height * 0.42
    inset = (fore - aft) * 0.10
    _canopy(bm, ((fore - inset, half_width * glass, canopy_h, roof + canopy_h * 0.55, 0.3),
                 (aft + inset * 1.3, half_width * glass * 0.88, canopy_h, roof + canopy_h * 0.55, 0.3)))
    return roof + canopy_h

def _build_wedge(bm, span_scale, round_bias, layout):
    # A variable arrowhead with a stepped bridge, deck tiers and flank trenches.
    if layout == 'compact':
        return _wedge_compact(bm, span_scale, round_bias)
    if layout == 'split':
        return _wedge_split(bm, span_scale, round_bias)
    if layout == 'stacked':
        return _wedge_stacked(bm, span_scale, round_bias)
    length = uniform(2.9, 3.9)
    nose, stern = length * 0.5, -length * 0.5
    beam = length * uniform(0.18, 0.40) * (0.9 + 0.2 * span_scale)
    hz = beam * uniform(0.10, 0.21)
    r = _round_of(0.08, round_bias)
    shoulder = uniform(0.42, 0.68)
    shoulder_x = nose - length * shoulder
    aft_w = uniform(0.86, 0.98)
    deck_z = hz * 2.0
    _loft(bm, (
        (nose, beam * 0.05, hz * 0.16, hz * 0.16, r),
        (nose - length * shoulder * 0.34, beam * 0.30, hz * 0.44, hz * 0.44, r),
        (nose - length * shoulder * 0.70, beam * 0.62, hz * 0.76, hz * 0.76, r),
        (shoulder_x, beam, hz, hz, r),
        ((shoulder_x + stern) * 0.5, beam * (1.0 + aft_w) * 0.5, hz, hz, r),
        (stern, beam * aft_w, hz * 0.86, hz * 1.14, r),
    ))

    tower_fore = shoulder_x - length * uniform(0.01, 0.05)
    tower_len = length * uniform(0.09, 0.14)
    tower_aft = tower_fore - tower_len
    deck_fore = tower_aft + tower_len * uniform(0.18, 0.30)
    deck_aft = stern + length * 0.01
    deck_span = deck_fore - deck_aft
    tiers = randint(1, 3)
    half = beam * uniform(0.24, 0.32)
    half_wide = half
    top = deck_z
    for tier in range(tiers):
        h = hz * uniform(0.16, 0.28)
        _loft(bm, (
            (deck_fore - deck_span * 0.18 * tier, half, h, top + h * 0.35, r),
            (deck_aft + deck_span * 0.05 * tier, half * 0.94, h, top + h * 0.35, r),
        ))
        top += h * 1.35
        half *= uniform(0.68, 0.84)

    base_h = max(hz * uniform(0.45, 0.72), (top - deck_z) / 1.35 + hz * uniform(0.18, 0.30))
    base_hw = beam * uniform(0.18, 0.25)
    _loft(bm, (
        (tower_fore, base_hw, base_h, deck_z + base_h * 0.35, r),
        (tower_aft, base_hw * 0.94, base_h, deck_z + base_h * 0.35, r),
    ))
    upper_h = hz * uniform(0.34, 0.52)
    upper_hw = base_hw * uniform(0.62, 0.80)
    upper_fore = tower_fore - tower_len * uniform(0.08, 0.16)
    upper_aft = tower_aft + tower_len * uniform(0.10, 0.18)
    upper_top = deck_z + base_h * 1.35
    _loft(bm, (
        (upper_fore, upper_hw, upper_h, upper_top + upper_h * 0.35, r),
        (upper_aft, upper_hw * 0.94, upper_h, upper_top + upper_h * 0.35, r),
    ))
    canopy_h = hz * uniform(0.20, 0.30)
    canopy_lift = upper_top + upper_h * 1.35 + canopy_h * 0.5
    _canopy(bm, (
        (upper_fore - tower_len * 0.06, upper_hw * 0.80, canopy_h, canopy_lift, 0.35),
        (upper_aft + tower_len * 0.14, upper_hw * 0.72, canopy_h, canopy_lift, 0.35),
    ))

    rail_x_fore = shoulder_x - length * 0.01
    rail_x_aft = stern + length * 0.03
    rail_hw = beam * uniform(0.024, 0.032)
    rail_h = hz * uniform(0.10, 0.16)
    strip_hw = beam * uniform(0.038, 0.052)
    strip_h = rail_h * 0.5
    rail_y = beam * 0.47
    rail_lift = deck_z - rail_h * 0.20
    strip_shift = max(rail_y - rail_hw * 0.85 - strip_hw, half_wide + strip_hw * 1.10)
    strip_lift = deck_z - strip_h * 0.10
    for side in (1.0, -1.0):
        _loft(bm, (
            (rail_x_fore, rail_hw, rail_h, rail_lift, 0.15),
            (rail_x_aft, rail_hw, rail_h, rail_lift, 0.15),
        ), shift=side * rail_y)
        trench_faces = _loft(bm, (
            (rail_x_fore, strip_hw, strip_h, strip_lift, 0.1),
            (rail_x_aft, strip_hw, strip_h, strip_lift, 0.1),
        ), shift=side * strip_shift)
        for face in trench_faces:
            face.material_index = Material.hull_dark

    _engine_row(bm, stern, hz * 1.12, randint(3, 4), hz * uniform(0.55, 0.75),
                beam * aft_w * uniform(0.58, 0.72))

def _wedge_compact(bm, span_scale, round_bias):
    # A long narrow dagger: a low bridge amidships and blades ahead of it.
    length = uniform(3.8, 4.6)
    nose, stern = length * 0.5, -length * 0.5
    beam = length * uniform(0.085, 0.125) * (0.9 + 0.2 * span_scale)
    hz = beam * uniform(0.14, 0.24)
    r = _round_of(0.12, round_bias)
    waist_x = nose - length * uniform(0.62, 0.74)
    aft_w = uniform(0.80, 0.92)
    _loft(bm, (
        (nose, beam * 0.04, hz * 0.14, hz * 0.14, r),
        (nose - length * 0.12, beam * 0.17, hz * 0.34, hz * 0.32, r),
        (nose - length * 0.32, beam * 0.46, hz * 0.62, hz * 0.54, r),
        (waist_x, beam, hz, hz, r),
        (stern + length * 0.14, beam * 0.91, hz * 0.94, hz * 1.02, r),
        (stern, beam * aft_w, hz * 0.74, hz * 1.12, r),
    ))
    deck_z = hz * 1.90
    bridge_fore = waist_x - length * 0.02
    bridge_h = hz * uniform(0.40, 0.56)
    _bridge(bm, bridge_fore, bridge_fore - length * uniform(0.16, 0.22),
            beam * uniform(0.42, 0.56), bridge_h, deck_z + bridge_h, r, glass=0.78)
    # Blades swept back off the shoulders, ahead of the bridge.
    fin_span = beam * uniform(1.4, 2.2) * (0.9 + 0.2 * span_scale)
    fin_x = nose - length * uniform(0.26, 0.34)
    _wings(bm, beam * uniform(0.26, 0.38), fin_span, length * uniform(0.20, 0.28),
           length * uniform(0.06, 0.10), fin_x, length * uniform(0.06, 0.14),
           hz * uniform(0.10, 0.40), fin_span * uniform(0.0, 0.08),
           length * uniform(0.006, 0.010))
    ridge_h = hz * uniform(0.16, 0.28)
    _slab(bm, bridge_fore + length * 0.03, stern + length * 0.12, beam * uniform(0.08, 0.12),
          ridge_h, deck_z + ridge_h * 0.6, r=0.2, taper=0.70)
    _engine_row(bm, stern, hz * 1.05, randint(2, 3), hz * uniform(0.50, 0.66),
                beam * aft_w * uniform(0.52, 0.68))

def _wedge_split(bm, span_scale, round_bias):
    # Twin slim arrow bodies either side of a command block, tied by a crosspiece.
    length = uniform(3.4, 4.2)
    nose, stern = length * 0.5, -length * 0.5
    body_w = length * uniform(0.095, 0.140) * (0.9 + 0.2 * span_scale)
    hz = body_w * uniform(0.32, 0.48)
    r = _round_of(0.10, round_bias)
    offset = body_w * uniform(1.30, 1.70)
    for side in (1.0, -1.0):
        _loft(bm, (
            (nose, body_w * 0.05, hz * 0.14, hz, r),
            (nose - length * 0.18, body_w * 0.34, hz * 0.44, hz, r),
            (nose - length * 0.44, body_w * 0.78, hz * 0.86, hz, r),
            (nose - length * 0.70, body_w, hz, hz, r),
            (stern, body_w * 0.86, hz * 0.90, hz, r),
        ), shift=side * offset)
    cross_x = nose - length * uniform(0.44, 0.52)
    cross_len = length * uniform(0.10, 0.16)
    cross_h = hz * uniform(0.55, 0.90)
    _slab(bm, cross_x + cross_len * 0.5, cross_x - cross_len * 0.5, offset + body_w * 0.70,
          cross_h, hz, r=0.12, taper=0.97)
    cmd_len = length * uniform(0.16, 0.24)
    bridge_h = hz * uniform(0.85, 1.15)
    _bridge(bm, cross_x + cmd_len * 0.55, cross_x - cmd_len * 0.45, body_w * uniform(0.60, 0.78),
            bridge_h, hz + cross_h + bridge_h, r)
    _slab(bm, cross_x - cmd_len * 0.45, stern + length * 0.04, body_w * 0.26, hz * 0.34,
          hz * 1.30, r=0.2, taper=0.85)
    _slab(bm, stern + length * 0.09, stern, offset + body_w * 0.62, hz * 0.46, hz, r=0.15, taper=0.90)
    for side in (1.0, -1.0):
        _engine_bell(bm, stern, side * offset, hz, body_w * 0.60)

def _wedge_stacked(bm, span_scale, round_bias):
    # A broad low arrow under a stepped block superstructure and a ventral keel.
    length = uniform(3.0, 3.9)
    nose, stern = length * 0.5, -length * 0.5
    beam = length * uniform(0.30, 0.46) * (0.9 + 0.2 * span_scale)
    hz = beam * uniform(0.09, 0.15)
    r = _round_of(0.06, round_bias)
    shoulder_x = nose - length * uniform(0.46, 0.60)
    aft_w = uniform(0.84, 0.94)
    _loft(bm, (
        (nose, beam * 0.05, hz * 0.20, hz * 0.20, r),
        (nose - length * 0.16, beam * 0.30, hz * 0.44, hz * 0.44, r),
        (nose - length * 0.32, beam * 0.62, hz * 0.74, hz * 0.74, r),
        (shoulder_x, beam, hz, hz, r),
        (stern + length * 0.16, beam * 0.98, hz, hz, r),
        (stern, beam * aft_w, hz * 0.86, hz * 1.10, r),
    ))
    deck = hz * 2.0
    tier_fore = shoulder_x - length * uniform(0.02, 0.06)
    tier_len = length * uniform(0.26, 0.34)
    tier_hw = beam * uniform(0.30, 0.38)
    tier_h = hz * uniform(0.55, 0.75)
    for tier in range(3):
        _slab(bm, tier_fore - tier_len * 0.10 * tier, tier_fore - tier_len * (1.0 - 0.16 * tier),
              tier_hw, tier_h, deck + tier_h, r=0.12, taper=0.94)
        deck += tier_h * 2.0
        tier_hw *= uniform(0.70, 0.82)
        tier_h *= uniform(0.62, 0.78)
    canopy_h = tier_h * uniform(1.0, 1.4)
    _canopy(bm, ((tier_fore - tier_len * 0.60, tier_hw * 0.90, canopy_h, deck + canopy_h * 0.5, 0.35),
                 (tier_fore - tier_len * 0.88, tier_hw * 0.80, canopy_h, deck + canopy_h * 0.5, 0.35)))
    keel_h = hz * uniform(1.6, 2.6)
    keel_hw = beam * uniform(0.05, 0.09)
    keel_fore = shoulder_x - length * 0.03
    _loft(bm, (
        (keel_fore, keel_hw, keel_h, -keel_h * 0.55, 0.15),
        (keel_fore - length * 0.14, keel_hw * 1.6, keel_h * 1.05, -keel_h * 0.55, 0.15),
        (stern + length * 0.10, keel_hw * 1.1, keel_h * 0.70, -keel_h * 0.45, 0.15),
    ))
    rail_y = beam * 0.62
    rail_hw = beam * uniform(0.022, 0.032)
    rail_h = hz * uniform(0.10, 0.18)
    for side in (1.0, -1.0):
        _slab(bm, shoulder_x - length * 0.02, stern + length * 0.05, rail_hw, rail_h,
              hz * 1.05, shift=side * rail_y, r=0.15, taper=1.0)
    _engine_row(bm, stern, hz * 1.15, randint(3, 4), hz * 0.62, beam * aft_w * 0.55)

def _build_fighter(bm, span_scale, round_bias, layout):
    # Swept or forward-swept wings, with canards, intakes or stern fairings.
    if layout == 'compact':
        return _fighter_compact(bm, span_scale, round_bias)
    if layout == 'split':
        return _fighter_split(bm, span_scale, round_bias)
    if layout == 'stacked':
        return _fighter_stacked(bm, span_scale, round_bias)
    length = uniform(3.0, 3.9)
    nose, stern = length * 0.5, -length * 0.5
    r = _round_of(0.72, round_bias)
    w = length * uniform(0.050, 0.095)
    h = w * uniform(0.85, 1.30)
    _loft(bm, (
        (nose, w * 0.18, h * 0.20, h * 0.14, r),
        (nose - length * 0.14, w * 0.60, h * 0.58, h * 0.30, r),
        (nose - length * 0.30, w * 0.95, h * 0.98, h * 0.36, r),
        (nose - length * 0.55, w, h * 1.12, h * 0.30, r),
        (stern + length * 0.24, w * 0.90, h * 1.00, h * 0.10, r),
        (stern, w * 0.70, h * 0.70, 0.0, r),
    ))
    canopy_fore = nose - length * uniform(0.32, 0.36)
    canopy_aft = canopy_fore - length * uniform(0.10, 0.16)
    canopy_h = h * uniform(0.20, 0.30)
    _canopy(bm, (
        (canopy_fore, w * 0.52, canopy_h, h * 1.32 + canopy_h * 0.5, 0.4),
        (canopy_aft, w * 0.44, canopy_h, h * 1.32 + canopy_h * 0.5, 0.4),
    ))

    span = (length * uniform(0.26, 0.34) * uniform(0.65, 1.35)
            * (0.9 + 0.2 * span_scale))
    chord = length * uniform(0.18, 0.32)
    tip_chord = chord * uniform(0.28, 0.62)
    at_x = stern + length * uniform(0.26, 0.48)
    sweep = length * uniform(-0.14, 0.28)
    wing_lift = h * uniform(-0.05, 0.25)
    thickness = length * uniform(0.008, 0.014)
    _wings(bm, w * uniform(0.55, 0.85), span, chord, tip_chord, at_x, sweep,
           wing_lift, span * uniform(-0.03, 0.16), thickness)

    config = randint(0, 2)
    if config == 0:
        canard_span = span * uniform(0.22, 0.38)
        _wings(bm, w * 0.45, canard_span, chord * uniform(0.20, 0.34),
               chord * uniform(0.08, 0.16), nose - length * uniform(0.24, 0.32),
               length * uniform(-0.02, 0.05), wing_lift,
               canard_span * uniform(0.0, 0.10), thickness * 0.85)
    elif config == 1:
        intake_len = length * uniform(0.10, 0.16)
        intake_hw = w * uniform(0.16, 0.26)
        intake_h = h * uniform(0.30, 0.44)
        intake_fore = at_x + chord * 0.30
        for side in (1.0, -1.0):
            _loft(bm, (
                (intake_fore, intake_hw, intake_h, h * 0.04, 0.25),
                (intake_fore - intake_len, intake_hw * 0.88, intake_h * 0.9, h * 0.04, 0.25),
            ), shift=side * (w * 0.80 + intake_hw * 0.80))
    else:
        fair_len = length * uniform(0.20, 0.30)
        fair_hw = w * uniform(0.18, 0.28)
        fair_h = h * uniform(0.34, 0.50)
        fair_aft = stern - length * 0.02
        for side in (1.0, -1.0):
            _loft(bm, (
                (fair_aft + fair_len, fair_hw * 0.66, fair_h * 0.70, h * 0.06, 0.5),
                (fair_aft + fair_len * 0.28, fair_hw, fair_h, h * 0.06, 0.5),
                (fair_aft, fair_hw * 0.84, fair_h * 0.88, h * 0.06, 0.5),
            ), shift=side * (w * 0.70 + fair_hw * 0.70))

    if random() < 0.55:
        fin_hw = w * uniform(0.07, 0.12)
        _loft(bm, (
            (nose - length * uniform(0.48, 0.56), fin_hw * 0.80, h * 0.40, h * 1.22, 0.1),
            (stern + length * uniform(0.10, 0.18), fin_hw, h * 0.60, h * 1.30, 0.1),
        ))

    count = randint(1, 2)
    _engine_row(bm, stern, h * 0.02, count, w * (0.62 if count == 1 else 0.44), w * 0.54)

def _fighter_compact(bm, span_scale, round_bias):
    # A delta flying wing: one blended lifting body, no separate fuselage.
    length = uniform(2.8, 3.6)
    nose, stern = length * 0.5, -length * 0.5
    half_span = length * uniform(0.36, 0.48) * (0.9 + 0.2 * span_scale)
    hz = length * uniform(0.022, 0.032)
    r = _round_of(0.5, round_bias)
    _loft(bm, (
        (nose, half_span * 0.04, hz * 0.50, 0.0, r),
        (nose - length * 0.18, half_span * 0.30, hz * 1.10, 0.0, r),
        (nose - length * 0.38, half_span * 0.68, hz * 1.50, 0.0, r),
        (stern + length * 0.18, half_span, hz * 1.40, 0.0, r),
        (stern, half_span * 0.86, hz * 0.90, 0.0, r),
    ))
    canopy_fore = nose - length * uniform(0.10, 0.16)
    canopy_aft = nose - length * uniform(0.28, 0.36)
    ch = hz * uniform(1.6, 2.4)
    _canopy(bm, ((canopy_fore, half_span * 0.16, ch, hz * 1.5 + ch * 0.6, 0.45),
                 (canopy_aft, half_span * 0.12, ch * 0.9, hz * 1.5 + ch * 0.5, 0.45)))
    fin_hw = length * uniform(0.012, 0.020)
    fin_h = hz * uniform(3.0, 4.6)
    fin_x = stern + length * uniform(0.18, 0.28)
    fin_y = half_span * uniform(0.72, 0.86)
    for side in (1.0, -1.0):
        _loft(bm, ((fin_x + length * 0.05, fin_hw, fin_h, hz * 1.2 + fin_h, 0.1),
                   (fin_x - length * 0.05, fin_hw * 0.8, fin_h * 0.7, hz * 1.2 + fin_h * 0.8, 0.1)),
              shift=side * fin_y)
    _engine_row(bm, stern, 0.0, 2, hz * 2.2, half_span * 0.34)

def _fighter_split(bm, span_scale, round_bias):
    # Twin slim booms carrying one wing, joined by a cockpit pod at the bow.
    length = uniform(3.0, 3.8)
    nose, stern = length * 0.5, -length * 0.5
    boom_w = length * uniform(0.035, 0.055)
    boom_h = boom_w * uniform(1.0, 1.5)
    r = _round_of(0.7, round_bias)
    offset = length * uniform(0.10, 0.14) * (0.9 + 0.2 * span_scale)
    for side in (1.0, -1.0):
        _loft(bm, (
            (nose - length * 0.06, boom_w * 0.35, boom_h * 0.40, 0.0, r),
            (nose - length * 0.20, boom_w, boom_h, 0.0, r),
            (stern + length * 0.16, boom_w * 0.92, boom_h * 0.92, 0.0, r),
            (stern, boom_w * 0.70, boom_h * 0.70, 0.0, r),
        ), shift=side * offset)
    wing_fore = nose - length * uniform(0.20, 0.26)
    wing_root = boom_w * 0.90
    _wings(bm, wing_root, offset + boom_w * 2.2 - wing_root, length * uniform(0.30, 0.40),
           length * uniform(0.12, 0.18), wing_fore, length * uniform(0.06, 0.14),
           0.0, 0.0, length * uniform(0.010, 0.016))
    _loft(bm, ((nose, boom_w * 0.60, boom_h * 0.60, 0.0, r),
               (nose - length * 0.10, boom_w * 1.50, boom_h * 1.30, 0.0, r),
               (wing_fore + length * 0.04, boom_w * 1.60, boom_h * 1.20, 0.0, r)))
    ch = boom_h * uniform(0.50, 0.80)
    _canopy(bm, ((nose - length * 0.13, boom_w * 0.85, ch, boom_h * 1.30 + ch * 0.5, 0.4),
                 (nose - length * 0.21, boom_w * 0.72, ch * 0.9, boom_h * 1.30 + ch * 0.5, 0.4)))
    _slab(bm, stern + length * 0.11, stern + length * 0.05, offset + boom_w, boom_h * 0.40, 0.0,
          r=0.2, taper=0.90)
    for side in (1.0, -1.0):
        _engine_bell(bm, stern, side * offset, 0.0, boom_w * 0.85)

def _fighter_stacked(bm, span_scale, round_bias):
    # A slim fuselage between two wing planes, their tips and roots finned together.
    length = uniform(3.0, 3.9)
    nose, stern = length * 0.5, -length * 0.5
    w = length * uniform(0.045, 0.075)
    h = w * uniform(1.0, 1.4)
    r = _round_of(0.65, round_bias)
    _loft(bm, (
        (nose, w * 0.22, h * 0.26, 0.0, r),
        (nose - length * 0.16, w * 0.70, h * 0.72, 0.0, r),
        (nose - length * 0.40, w, h, 0.0, r),
        (stern + length * 0.20, w * 0.85, h * 0.88, 0.0, r),
        (stern, w * 0.55, h * 0.60, 0.0, r),
    ))
    ch = h * uniform(0.28, 0.42)
    _canopy(bm, ((nose - length * 0.26, w * 0.52, ch, h * 1.05 + ch * 0.5, 0.4),
                 (nose - length * 0.38, w * 0.44, ch * 0.9, h * 1.05 + ch * 0.5, 0.4)))
    span = length * uniform(0.24, 0.34) * (0.9 + 0.2 * span_scale)
    chord = length * uniform(0.24, 0.34)
    tip = chord * uniform(0.34, 0.55)
    upper_at = stern + length * uniform(0.42, 0.55)
    lower_at = stern + length * uniform(0.26, 0.36)
    thick = length * uniform(0.007, 0.011)
    gap = h * uniform(1.6, 2.4)
    upper_sweep = length * uniform(0.02, 0.10)
    upper_rise = span * uniform(0.02, 0.12)
    _wings(bm, w * 0.7, span, chord, tip, upper_at, upper_sweep, gap, upper_rise, thick)
    _wings(bm, w * 0.7, span * uniform(0.86, 1.0), chord * 0.86, tip * 0.80, lower_at,
           length * uniform(0.10, 0.20), -gap, -span * uniform(0.02, 0.10), thick)
    # Diagonal struts join the staggered roots; fins sit on the upper tips.
    strut_hw = w * uniform(0.18, 0.28)
    for side in (1.0, -1.0):
        _loft(bm, ((upper_at, strut_hw, thick * 2, gap, 0.15),
                   (lower_at, strut_hw, thick * 2, -gap, 0.15)),
              shift=side * w * 0.70)
    fin_hw = length * uniform(0.010, 0.016)
    fin_tip = span + w * 0.70 - fin_hw * 0.5
    tip_x = upper_at - upper_sweep
    tip_z = gap + upper_rise
    for side in (1.0, -1.0):
        _loft(bm, ((tip_x + tip * 0.15, fin_hw, h * 0.55, tip_z + h * 0.50, 0.1),
                   (tip_x - tip * 0.25, fin_hw * 0.75, h * 0.35, tip_z + h * 0.30, 0.1)),
              shift=side * fin_tip)
    _engine_row(bm, stern, 0.0, 2, w * 0.55, w * 0.50)

def _build_freighter(bm, span_scale, round_bias, layout):
    # Cargo modules on a continuous spine, with a raised forward bridge.
    if layout == 'compact':
        return _freighter_compact(bm, span_scale, round_bias)
    if layout == 'split':
        return _freighter_split(bm, span_scale, round_bias)
    if layout == 'stacked':
        return _freighter_stacked(bm, span_scale, round_bias)
    length = uniform(3.2, 4.6)
    nose, stern = length * 0.5, -length * 0.5
    r = _round_of(0.1, round_bias)
    beam = 0.85 + 0.3 * span_scale
    squat = randint(0, 1)
    if squat:
        w = length * uniform(0.108, 0.14) * beam
        h = w * uniform(0.52, 0.72)
    else:
        w = length * uniform(0.058, 0.078) * beam
        h = w * uniform(1.28, 1.75)
    cab_aft = nose - length * uniform(0.16, 0.22)
    _loft(bm, (
        (nose, w * 0.6, h * 0.62, h * 0.15, r),
        (nose - length * 0.045, w, h, h * 0.05, r),
        (cab_aft, w * 0.95, h * 0.93, 0.0, r),
    ))
    tower_fore = nose - length * uniform(0.055, 0.075)
    tower_aft = max(tower_fore - length * uniform(0.07, 0.11), cab_aft + length * 0.005)
    tower_len = tower_fore - tower_aft
    tower_h = h * uniform(0.28, 0.42)
    deck = h * 0.86
    _loft(bm, (
        (tower_fore, w * 0.44, tower_h, deck, 0.15),
        (tower_aft, w * 0.5, tower_h, deck, 0.15),
    ))
    roof = deck + tower_h
    ch = h * uniform(0.16, 0.26)
    _canopy(bm, (
        (tower_fore - tower_len * 0.1, w * 0.3, ch, roof + ch * 0.5, 0.12),
        (tower_aft + tower_len * 0.12, w * 0.38, ch, roof + ch * 0.5, 0.12),
    ))
    block_fore = stern + length * uniform(0.13, 0.18)
    block_len = block_fore - stern
    _loft(bm, ((cab_aft + 0.01, w * 0.3, w * 0.3, 0.0, 0.2),
               (block_fore, w * 0.3, w * 0.3, 0.0, 0.2)))
    count = randint(2, 4)
    room = cab_aft - block_fore
    gap = room * uniform(0.03, 0.05)
    weights = [uniform(0.75, 1.35) for _ in range(count)]
    share = (room - gap * (count + 1)) / sum(weights)
    cursor = cab_aft - gap
    spans = []
    girths = []
    for i in range(count):
        each = share * weights[i]
        cw = w * uniform(1.15, 1.5) * beam
        mh = cw * (uniform(0.5, 0.8) if squat else uniform(0.95, 1.4))
        _loft(bm, ((cursor, cw, mh, 0.0, 0.06), (cursor - each, cw, mh, 0.0, 0.06)))
        spans.append((cursor, cursor - each))
        girths.append((cw, mh))
        cursor -= each + gap
    for i in range(min(count, randint(1, 2))):
        cw, mh = girths[i]
        fore, aft = spans[i]
        cx = fore - (fore - aft) * 0.42
        half = (fore - aft) * 0.11
        _loft(bm, ((cx + half, cw * 1.07, mh * 1.07, 0.0, 0.06),
                   (cx - half, cw * 1.07, mh * 1.07, 0.0, 0.06)))
    if randint(0, 1):
        fin_span = min(w * uniform(1.4, 2.4) * beam, length * 0.22)
        fin_chord = block_len * uniform(0.45, 0.6)
        _wings(bm, w * 0.72, fin_span, fin_chord, fin_chord * 0.62,
               block_fore - block_len * uniform(0.5, 0.6),
               fin_chord * uniform(0.2, 0.45), 0.0, 0.0, length * 0.007)
    else:
        housing_x = block_fore - block_len * uniform(0.25, 0.4)
        housing_l = block_len * uniform(0.3, 0.45)
        housing_w = w * uniform(0.3, 0.45)
        housing_h = h * uniform(0.28, 0.42)
        housing_z = h * uniform(0.3, 0.45)
        for side in (1.0, -1.0):
            _loft(bm, (
                (housing_x, housing_w, housing_h, housing_z, 0.12),
                (housing_x - housing_l, housing_w * 0.85, housing_h * 0.85, housing_z, 0.12),
            ), shift=side * w * 0.95)
    _loft(bm, (
        (block_fore, w * 1.02, h * 1.02, 0.0, r),
        (stern, w * 0.9, h * 0.9, 0.0, r),
    ))
    drives = randint(2, 4)
    spread = w * (0.45 if drives == 2 else 0.5)
    _engine_row(bm, stern, 0.0, drives, min(h * 0.62, spread * 0.85), spread)

def _freighter_compact(bm, span_scale, round_bias):
    # A broad low barge: one wide hull, a squat cab forward, crates on the deck.
    length = uniform(2.8, 3.6)
    nose, stern = length * 0.5, -length * 0.5
    r = _round_of(0.1, round_bias)
    w = length * uniform(0.20, 0.28) * (0.9 + 0.3 * span_scale)
    h = w * uniform(0.34, 0.50)
    _loft(bm, (
        (nose, w * 0.72, h * 0.62, 0.0, r),
        (nose - length * 0.06, w, h, 0.0, r),
        (stern + length * 0.12, w * 1.02, h * 0.98, 0.0, r),
        (stern, w * 0.90, h * 0.90, 0.0, r),
    ))
    cab_fore = nose - length * 0.05
    tower_h = h * uniform(0.50, 0.72)
    _bridge(bm, cab_fore, cab_fore - length * uniform(0.12, 0.17), w * uniform(0.40, 0.52),
            tower_h, h + tower_h, r, glass=0.62)
    for i in range(randint(2, 3)):
        crate_x = cab_fore - length * (0.20 + 0.16 * i)
        crate_w = w * uniform(0.28, 0.42)
        crate_h = h * uniform(0.45, 0.75)
        _slab(bm, crate_x + length * 0.05, crate_x - length * 0.05, crate_w, crate_h,
              h + crate_h * 0.35, r=0.06, taper=0.90)
    _engine_row(bm, stern, 0.0, randint(2, 3), min(h * 0.60, w * 0.30), w * 0.42)

def _freighter_split(bm, span_scale, round_bias):
    # Two parallel cargo rails, tied by a bow pilot house and crossbeams.
    length = uniform(3.6, 4.6)
    nose, stern = length * 0.5, -length * 0.5
    r = _round_of(0.12, round_bias)
    rail_w = length * uniform(0.045, 0.065) * (0.9 + 0.3 * span_scale)
    rail_h = rail_w * uniform(0.9, 1.3)
    offset = rail_w * uniform(3.0, 4.2)
    for side in (1.0, -1.0):
        _loft(bm, ((nose - length * 0.05, rail_w * 0.80, rail_h * 0.80, 0.0, r),
                   (nose - length * 0.18, rail_w, rail_h, 0.0, r),
                   (stern, rail_w * 0.90, rail_h * 0.90, 0.0, r)),
              shift=side * offset)
    # Cargo pods clamp onto each rail, in the same spans on both sides.
    spans = []
    cursor = nose - length * 0.26
    for i in range(randint(2, 3)):
        each = length * uniform(0.14, 0.22)
        spans.append((cursor, cursor - each))
        cursor -= each + length * uniform(0.03, 0.05)
    crate_w = rail_w * uniform(1.6, 2.4)
    crate_h = rail_h * uniform(1.4, 2.0)
    for fore, aft in spans:
        for side in (1.0, -1.0):
            _slab(bm, fore, aft, crate_w, crate_h, 0.0, shift=side * offset, r=0.06, taper=0.88)
    _bridge(bm, nose, nose - length * 0.12, rail_w * uniform(2.4, 3.2), rail_h * uniform(1.6, 2.2),
            rail_h * 1.9, r, glass=0.55)
    for x in (nose - length * 0.13, spans[-1][1] - length * 0.02):
        _slab(bm, x + length * 0.02, x - length * 0.02, offset + rail_w * 0.90, rail_h * 0.45,
              rail_h, r=0.15, taper=0.95)
    _engine_row(bm, stern, 0.0, 2, rail_h * 0.75, offset)

def _freighter_stacked(bm, span_scale, round_bias):
    # Cargo stacked above and below one boom, the bridge high at the bow.
    length = uniform(3.4, 4.4)
    nose, stern = length * 0.5, -length * 0.5
    r = _round_of(0.1, round_bias)
    w = length * uniform(0.075, 0.100) * (0.9 + 0.3 * span_scale)
    h = w * uniform(0.80, 1.10)
    _loft(bm, ((nose, w * 0.55, h * 0.50, h * 0.10, r),
               (nose - length * 0.04, w * 0.90, h * 0.85, 0.0, r),
               (nose - length * 0.16, w, h, 0.0, r)))
    tower_h = h * uniform(0.70, 1.00)
    _bridge(bm, nose - length * 0.05, nose - length * 0.15, w * 0.55, tower_h, h * 0.75 + tower_h, r,
            glass=0.70)
    _slab(bm, nose - length * 0.15, stern, w * 0.42, h * 0.42, 0.0, r=r, taper=0.88)
    for i in range(randint(2, 3)):
        crate_x = nose - length * (0.30 + 0.17 * i)
        crate_w = w * uniform(1.5, 2.2)
        crate_h = h * uniform(0.55, 0.90)
        above = i % 2 == 0
        _slab(bm, crate_x + length * 0.07, crate_x - length * 0.07, crate_w, crate_h,
              (h * 0.35 + crate_h) if above else -(h * 0.35 + crate_h), r=0.06, taper=0.90)
    _engine_row(bm, stern, 0.0, randint(2, 3), min(h * 0.55, w * 0.55), w * 0.50)

def _build_saucer(bm, span_scale, round_bias, layout):
    # An oval lens with paired mandibles and a raised glazed command module.
    if layout == 'compact':
        return _saucer_compact(bm, span_scale, round_bias)
    if layout == 'split':
        return _saucer_split(bm, span_scale, round_bias)
    if layout == 'stacked':
        return _saucer_stacked(bm, span_scale, round_bias)
    radius = uniform(1.05, 1.45) * (0.85 + 0.30 * span_scale)
    thick = radius * uniform(0.09, 0.16) * (0.80 + 0.40 * round_bias)
    rx = radius * uniform(0.92, 1.22)
    ry = radius * uniform(0.70, 1.00)
    top_h = thick * 0.85
    _disc(bm, (
        (-thick, rx * 0.52, ry * 0.52),
        (-thick * 0.40, rx, ry),
        (thick * 0.42, rx * 0.97, ry * 0.97),
        (top_h, rx * 0.55, ry * 0.55),
    ))

    prong = rx * uniform(0.32, 0.70)
    mand_y = ry * uniform(0.18, 0.42)
    mand_hw = ry * uniform(0.07, 0.11)
    mand_h = thick * uniform(0.30, 0.50)
    for side in (1.0, -1.0):
        _loft(bm, (
            (rx + prong, mand_hw * 0.60, mand_h * 0.55, 0.0, 0.2),
            (rx + prong * 0.55, mand_hw, mand_h * 0.88, 0.0, 0.2),
            (rx * 0.80, mand_hw * 1.15, mand_h, 0.0, 0.2),
        ), shift=side * mand_y)

    cmd_h = thick * uniform(0.80, 1.30)
    _disc(bm, (
        (top_h - cmd_h * 0.55, rx * 0.34, ry * 0.34),
        (top_h + cmd_h * 0.55, rx * 0.27, ry * 0.27),
        (top_h + cmd_h, rx * 0.20, ry * 0.20),
    ), sides=8)
    canopy_h = cmd_h * uniform(0.40, 0.65)
    canopy_lift = top_h + cmd_h + canopy_h * 0.5
    _canopy(bm, (
        (rx * 0.06, rx * 0.085, canopy_h, canopy_lift, 0.4),
        (-rx * 0.10, rx * 0.080, canopy_h, canopy_lift, 0.4),
    ))

    plate_h = thick * uniform(0.22, 0.40)
    plate_fore = -rx * uniform(0.18, 0.26)
    plate_lift = top_h + plate_h * 0.30
    if randint(0, 1) == 0:
        plate_hw = ry * uniform(0.12, 0.16)
        _loft(bm, (
            (plate_fore, plate_hw, plate_h, plate_lift, 0.2),
            (-rx * uniform(0.44, 0.52), plate_hw * 0.80, plate_h, plate_lift, 0.2),
        ))
    else:
        plate_hw = ry * uniform(0.055, 0.085)
        plate_aft = -rx * uniform(0.34, 0.42)
        for side in (1.0, -1.0):
            _loft(bm, (
                (plate_fore, plate_hw, plate_h, plate_lift, 0.2),
                (plate_aft, plate_hw * 0.85, plate_h, plate_lift, 0.2),
            ), shift=side * plate_hw * 1.60)

    vent_y = ry * uniform(0.28, 0.38)
    vent_hw = ry * uniform(0.030, 0.050)
    vent_h = thick * uniform(0.60, 1.00)
    vent_fore = -rx * uniform(0.42, 0.52)
    vent_aft = vent_fore - rx * uniform(0.16, 0.26)
    for side in (1.0, -1.0):
        _loft(bm, (
            (vent_fore, vent_hw, vent_h * 0.55, thick * 0.30 + vent_h * 0.55, 0.15),
            (vent_aft, vent_hw * 0.82, vent_h * 0.42, thick * 0.30 + vent_h * 0.42, 0.15),
        ), shift=side * vent_y)

    block_aft = -rx * uniform(1.00, 1.10)
    block_hw = ry * uniform(0.34, 0.44)
    block_h = thick * uniform(0.42, 0.55)
    _loft(bm, (
        (-rx * 0.70, block_hw, block_h, 0.0, 0.3),
        (block_aft, block_hw * 0.86, block_h * 0.92, 0.0, 0.3),
    ))
    _engine_row(bm, block_aft, 0.0, randint(2, 4), thick * 0.42, block_hw * 0.55)

def _saucer_compact(bm, span_scale, round_bias):
    # One solid oval lens: no mandibles, a squat dome and a low glazed crown.
    radius = uniform(1.05, 1.40) * (0.85 + 0.30 * span_scale)
    thick = radius * uniform(0.14, 0.22) * (0.80 + 0.40 * round_bias)
    rx = radius * uniform(1.00, 1.18)
    ry = radius * uniform(0.86, 1.02)
    top = thick * 0.96
    _disc(bm, (
        (-thick, rx * 0.44, ry * 0.44),
        (-thick * 0.42, rx * 0.96, ry * 0.96),
        (thick * 0.30, rx, ry),
        (thick * 0.78, rx * 0.80, ry * 0.80),
        (top, rx * 0.42, ry * 0.42),
    ))
    dome = thick * uniform(0.60, 1.00)
    _disc(bm, ((top - dome * 0.20, rx * 0.34, ry * 0.34),
               (top + dome, rx * 0.20, ry * 0.20)), sides=8)
    ch = dome * uniform(0.50, 0.80)
    _canopy(bm, ((rx * 0.14, rx * 0.11, ch, top + dome + ch * 0.4, 0.5),
                 (-rx * 0.06, rx * 0.10, ch, top + dome + ch * 0.4, 0.5)))
    _slab(bm, -rx * 0.30, -rx * 1.02, ry * 0.34, thick * 0.42, 0.0, r=0.3)
    _engine_row(bm, -rx * 1.02, 0.0, randint(2, 3), thick * 0.40, ry * 0.50)

def _saucer_split(bm, span_scale, round_bias):
    # Two lens pods either side of a wide command hull, joined at the waist.
    radius = uniform(0.80, 1.05) * (0.85 + 0.30 * span_scale)
    thick = radius * uniform(0.14, 0.22) * (0.80 + 0.40 * round_bias)
    rx = radius * uniform(0.95, 1.15)
    ry = radius * uniform(0.78, 0.95)
    offset = ry * uniform(1.25, 1.55)
    pods = (
        (-thick, rx * 0.50, ry * 0.50),
        (-thick * 0.36, rx, ry),
        (thick * 0.36, rx * 0.96, ry * 0.96),
        (thick * 0.86, rx * 0.52, ry * 0.52),
    )
    for side in (1.0, -1.0):
        _disc(bm, pods, shift=side * offset)
    _slab(bm, rx * 0.52, -rx * 0.62, offset + ry * 0.55, thick * 0.34, 0.0, r=0.2, taper=0.92)
    tower_h = thick * uniform(0.80, 1.20)
    _bridge(bm, rx * 0.30, -rx * 0.36, offset * 0.62, tower_h, thick * 0.34 + tower_h, 0.2)
    for side in (1.0, -1.0):
        _engine_bell(bm, -rx, side * offset, 0.0, thick * 0.42)

def _saucer_stacked(bm, span_scale, round_bias):
    # A heavy lens with a nested deck ring, a tall stepped bridge and four drives.
    radius = uniform(1.35, 1.80) * (0.85 + 0.30 * span_scale)
    thick = radius * uniform(0.16, 0.24) * (0.80 + 0.40 * round_bias)
    rx = radius * uniform(1.00, 1.16)
    ry = radius * uniform(0.84, 1.00)
    rim = thick * uniform(0.30, 0.42)
    _disc(bm, (
        (-thick, rx * 0.40, ry * 0.40),
        (-thick * 0.55, rx * 0.90, ry * 0.90),
        (-rim, rx, ry),
        (rim, rx * 0.98, ry * 0.98),
        (rim * 1.90, rx * 0.72, ry * 0.72),
        (rim * 2.30, rx * 0.34, ry * 0.34),
    ))
    deck = rim * 2.30
    deck_h = thick * uniform(0.22, 0.34)
    _disc(bm, ((deck, rx * 0.46, ry * 0.46), (deck + deck_h, rx * 0.40, ry * 0.40)), sides=8)
    deck += deck_h
    step_fore = rx * 0.26
    step_hw = ry * 0.26
    step_h = thick * uniform(0.34, 0.50)
    for widen in (1.0, 0.76, 0.52):
        _slab(bm, step_fore * widen, -step_fore * widen * 0.92, step_hw * widen, step_h,
              deck + step_h, r=0.12, taper=0.90)
        deck += step_h * 2.0
        step_h *= 0.82
    ch = step_h * 1.10
    _canopy(bm, ((step_fore * 0.42, step_hw * 0.60, ch, deck + ch * 0.5, 0.35),
                 (step_fore * 0.10, step_hw * 0.50, ch, deck + ch * 0.5, 0.35)))
    block_aft = -rx * uniform(1.02, 1.10)
    block_hw = ry * uniform(0.40, 0.52)
    _slab(bm, -rx * 0.66, block_aft, block_hw, thick * 0.36, 0.0, r=0.3)
    _engine_row(bm, block_aft, 0.0, 4, thick * 0.30, block_hw * 0.70)

def _build_spine(bm, span_scale, round_bias, layout):
    # Mixed tanks and cargo modules on struts off an exposed boom.
    if layout == 'compact':
        return _spine_compact(bm, span_scale, round_bias)
    if layout == 'split':
        return _spine_split(bm, span_scale, round_bias)
    if layout == 'stacked':
        return _spine_stacked(bm, span_scale, round_bias)
    length = uniform(3.0, 4.6)
    nose, stern = length * 0.5, -length * 0.5
    r = _round_of(0.3, round_bias)
    beam = 0.8 + 0.4 * span_scale
    w = length * uniform(0.045, 0.072)
    pod_scale = uniform(0.85, 1.35)
    pod_aft = nose - length * uniform(0.13, 0.2)
    _loft(bm, (
        (nose, w * 0.5 * pod_scale, w * 0.5 * pod_scale, w * 0.08, r),
        (nose - length * 0.035, w * pod_scale, w * 0.95 * pod_scale, w * 0.04, r),
        (pod_aft, w * 0.9 * pod_scale, w * 0.82 * pod_scale, 0.0, r),
    ))
    pod_len = nose - pod_aft
    ch = w * uniform(0.22, 0.3) * pod_scale
    _canopy(bm, (
        (nose - pod_len * 0.22, w * 0.34 * pod_scale, ch, w * 0.9 * pod_scale + ch * 0.5, 0.12),
        (nose - pod_len * 0.62, w * 0.44 * pod_scale, ch, w * 0.9 * pod_scale + ch * 0.5, 0.12),
    ))
    block_fore = stern + length * uniform(0.12, 0.18)
    block_len = block_fore - stern
    bw = w * uniform(0.45, 0.62)
    _loft(bm, ((pod_aft + length * 0.02, bw, bw * 1.08, 0.0, 0.2),
               (block_fore, bw, bw * 1.08, 0.0, 0.2)))
    stations = randint(2, 4)
    step = (pod_aft - block_fore) / stations
    for i in range(stations):
        x = pod_aft - step * (i + 0.5)
        reach = bw * uniform(0.8, 1.8) * beam
        girth = uniform(0.85, 1.25)
        span_len = step * uniform(0.5, 0.68)
        if randint(0, 1):
            tank_r = w * uniform(0.5, 0.75) * girth
            offset = bw + reach + tank_r * 0.8
            _wings(bm, bw * 0.6, offset - tank_r * 0.55 - bw * 0.6, span_len * 0.3, span_len * 0.22,
                   x, 0.0, 0.0, 0.0, bw * 0.16)
            for side in (1.0, -1.0):
                _loft(bm, (
                    (x + span_len * 0.5, tank_r * 0.72, tank_r * 0.72, 0.0, 1.0),
                    (x + span_len * 0.28, tank_r, tank_r, 0.0, 1.0),
                    (x - span_len * 0.28, tank_r, tank_r, 0.0, 1.0),
                    (x - span_len * 0.5, tank_r * 0.72, tank_r * 0.72, 0.0, 1.0),
                ), shift=side * offset)
        else:
            mod_w = w * uniform(0.45, 0.7) * girth
            mod_h = mod_w * uniform(0.8, 1.4)
            offset = bw + reach + mod_w * 0.85
            _wings(bm, bw * 0.6, offset - mod_w * 0.55 - bw * 0.6, span_len * 0.26, span_len * 0.2,
                   x, 0.0, 0.0, 0.0, bw * 0.15)
            for side in (1.0, -1.0):
                _loft(bm, ((x + span_len * 0.5, mod_w, mod_h, 0.0, 0.08),
                           (x - span_len * 0.5, mod_w, mod_h, 0.0, 0.08)),
                      shift=side * offset)
    rad_span = w * uniform(1.8, 3.0) * beam
    rad_chord = block_len * uniform(0.4, 0.55)
    _wings(bm, bw, rad_span, rad_chord, rad_chord * 0.66,
           block_fore - block_len * uniform(0.5, 0.62), rad_chord * uniform(0.1, 0.3),
           0.0, rad_span * uniform(0.0, 0.1), length * 0.007)
    _loft(bm, (
        (block_fore, w * 1.05, w, 0.0, r),
        (stern, w * 0.92, w * 0.86, 0.0, r),
    ))
    count = randint(2, 3)
    spread = w * 0.45
    _engine_row(bm, stern, 0.0, count, min(w * 0.5, spread * 0.95), spread)

def _spine_compact(bm, span_scale, round_bias):
    # A short thick core with a tight cluster of modules pressed against it.
    length = uniform(2.4, 3.0)
    nose, stern = length * 0.5, -length * 0.5
    r = _round_of(0.4, round_bias)
    w = length * uniform(0.10, 0.14) * (0.85 + 0.30 * span_scale)
    h = w * uniform(0.85, 1.15)
    _loft(bm, (
        (nose, w * 0.50, h * 0.55, h * 0.10, r),
        (nose - length * 0.06, w, h, 0.0, r),
        (stern + length * 0.16, w * 0.95, h * 0.95, 0.0, r),
        (stern, w * 0.68, h * 0.68, 0.0, r),
    ))
    tower_h = h * uniform(0.35, 0.50)
    _bridge(bm, nose - length * 0.10, nose - length * 0.22, w * 0.60, tower_h, h + tower_h, r,
            glass=0.60)
    for i in range(randint(2, 3)):
        module_x = nose - length * (0.26 + 0.16 * i)
        module_w = w * uniform(0.50, 0.75)
        module_h = module_w * uniform(0.70, 1.10)
        module_y = w + module_w * 0.80
        for side in (1.0, -1.0):
            _slab(bm, module_x + module_w * 0.90, module_x - module_w * 0.90, module_w, module_h,
                  0.0, shift=side * module_y, r=0.2, taper=0.88)
    tank_fore = nose - length * 0.30
    _loft(bm, ((tank_fore, w * 0.50, h * 0.40, h * 1.10, 1.0),
               (tank_fore - length * 0.14, w * 0.62, h * 0.50, h * 1.20, 1.0),
               (tank_fore - length * 0.28, w * 0.44, h * 0.36, h * 1.05, 1.0)))
    _engine_row(bm, stern, 0.0, randint(2, 3), min(w * 0.50, h * 0.45), w * 0.50)

def _spine_split(bm, span_scale, round_bias):
    # Two structural rails carrying modules, bound by crossbeams and a bow pod.
    length = uniform(3.4, 4.4)
    nose, stern = length * 0.5, -length * 0.5
    r = _round_of(0.25, round_bias)
    w = length * uniform(0.035, 0.055)
    h = w * uniform(0.90, 1.20)
    offset = w * uniform(2.6, 3.6) * (0.8 + 0.4 * span_scale)
    for side in (1.0, -1.0):
        _loft(bm, ((nose - length * 0.14, w * 0.70, h * 0.70, 0.0, r),
                   (nose - length * 0.26, w, h, 0.0, r),
                   (stern, w * 0.90, h * 0.90, 0.0, r)), shift=side * offset)
    _loft(bm, ((nose, w * 0.50, h * 0.50, h * 0.05, r),
               (nose - length * 0.04, w * 1.10, h * 1.00, 0.0, r),
               (nose - length * 0.16, w * 1.05, h * 0.90, 0.0, r)))
    ch = h * uniform(0.40, 0.60)
    _canopy(bm, ((nose - length * 0.05, w * 0.72, ch, h * 0.95 + ch * 0.5, 0.3),
                 (nose - length * 0.13, w * 0.62, ch * 0.9, h * 0.95 + ch * 0.5, 0.3)))
    for i in range(randint(2, 3)):
        module_x = nose - length * (0.28 + 0.18 * i)
        module_w = w * uniform(0.55, 0.80)
        module_h = module_w * uniform(0.90, 1.40)
        module_l = length * uniform(0.06, 0.10)
        for side in (1.0, -1.0):
            _slab(bm, module_x + module_l, module_x - module_l, module_w, module_h, 0.0,
                  shift=side * offset, r=0.08, taper=0.92)
    for x in (nose - length * 0.14, nose - length * 0.44, stern + length * 0.06):
        _slab(bm, x + length * 0.015, x - length * 0.015, offset + w * 0.90, h * 0.40, 0.0,
              r=0.2, taper=0.95)
    _engine_row(bm, stern, 0.0, 2, min(w * 0.70, h * 0.60), offset)

def _spine_stacked(bm, span_scale, round_bias):
    # One boom with modules hung above and below it, the bridge high at the bow.
    length = uniform(3.2, 4.2)
    nose, stern = length * 0.5, -length * 0.5
    r = _round_of(0.3, round_bias)
    w = length * uniform(0.045, 0.065)
    h = w * uniform(0.85, 1.10)
    _loft(bm, ((nose, w * 0.55, h * 0.50, h * 0.08, r),
               (nose - length * 0.05, w * 1.20, h * 1.10, 0.0, r),
               (nose - length * 0.17, w * 0.95, h * 0.90, 0.0, r)))
    tower_h = h * uniform(0.90, 1.30)
    _bridge(bm, nose - length * 0.07, nose - length * 0.17, w * 0.80, tower_h, h * 0.90 + tower_h,
            r, glass=0.55)
    _slab(bm, nose - length * 0.16, stern, w * 0.42, h * 0.42, 0.0, r=r, taper=0.88)
    for i in range(randint(2, 3)):
        module_x = nose - length * (0.30 + 0.17 * i)
        module_w = w * uniform(0.80, 1.20)
        module_h = module_w * uniform(0.90, 1.40)
        module_l = length * uniform(0.07, 0.11)
        above = i % 2 == 0
        _slab(bm, module_x + module_l, module_x - module_l, module_w, module_h,
              (h * 0.35 + module_h) if above else -(h * 0.35 + module_h), r=0.1, taper=0.90)
    _engine_row(bm, stern, 0.0, randint(2, 3), min(h * 0.55, w * 0.80), w * 0.50)

def _build_pod(bm, span_scale, round_bias, layout):
    # A raised command section and ribbed nacelles on straight or swept wings.
    if layout == 'compact':
        return _pod_compact(bm, span_scale, round_bias)
    if layout == 'split':
        return _pod_split(bm, span_scale, round_bias)
    if layout == 'stacked':
        return _pod_stacked(bm, span_scale, round_bias)
    beam = 0.8 + 0.4 * span_scale
    long_body = randint(0, 1)
    if long_body:
        length = uniform(2.7, 3.4)
        w = length * uniform(0.085, 0.11) * beam
        h = w * uniform(1.0, 1.3)
        r = _round_of(0.6, round_bias)
    else:
        length = uniform(2.0, 2.5)
        w = length * uniform(0.16, 0.2) * beam
        h = w * uniform(0.72, 0.95)
        r = _round_of(0.85, round_bias)
    nose, stern = length * 0.5, -length * 0.5
    _loft(bm, (
        (nose, w * 0.42, h * 0.45, h * 0.12, r),
        (nose - length * 0.3, w, h, h * 0.08, r),
        (stern + length * 0.3, w * 0.95, h * 0.95, 0.0, r),
        (stern + length * 0.06, w * 0.6, h * 0.6, 0.0, r),
    ))
    tower_fore = nose - length * uniform(0.1, 0.15)
    tower_aft = tower_fore - length * uniform(0.14, 0.2)
    tower_len = tower_fore - tower_aft
    tower_h = h * uniform(0.3, 0.45)
    deck = h * 0.82
    _loft(bm, (
        (tower_fore, w * 0.42, tower_h, deck, 0.15),
        (tower_aft, w * 0.5, tower_h, deck, 0.15),
    ))
    ch = h * uniform(0.15, 0.22)
    _canopy(bm, (
        (tower_fore - tower_len * 0.08, w * 0.28, ch, deck + tower_h + ch * 0.5, 0.12),
        (tower_aft + tower_len * 0.1, w * 0.36, ch, deck + tower_h + ch * 0.5, 0.12),
    ))
    for i in range(randint(1, 2)):
        step_x = nose - length * uniform(0.22, 0.36)
        step_l = length * uniform(0.06, 0.12)
        step_w = w * uniform(0.2, 0.3)
        step_h = h * uniform(0.2, 0.3)
        step_z = h * uniform(0.25, 0.5)
        for side in (1.0, -1.0):
            _loft(bm, (
                (step_x, step_w, step_h, step_z, 0.1),
                (step_x - step_l, step_w * 0.9, step_h * 0.9, step_z, 0.1),
            ), shift=side * w * 0.78)
    pod_r = w * uniform(0.42, 0.68)
    clearance = w * uniform(0.12, 0.45)
    offset = w + clearance + pod_r * (1.0 + 0.4 * span_scale)
    nac_fore = nose - length * uniform(0.3, 0.42)
    nac_aft = stern - length * uniform(0.02, 0.12)
    nac_len = nac_fore - nac_aft
    nac_z = h * uniform(-0.05, 0.2)
    for side in (1.0, -1.0):
        _loft(bm, (
            (nac_fore, pod_r * 0.5, pod_r * 0.5, nac_z, 1.0),
            (nac_fore - length * 0.08, pod_r, pod_r, nac_z, 1.0),
            (nac_aft + length * 0.08, pod_r, pod_r, nac_z, 1.0),
            (nac_aft, pod_r * 0.88, pod_r * 0.88, nac_z, 1.0),
        ), shift=side * offset)
    swept = randint(0, 1)
    sweep = length * uniform(0.05, 0.13) if swept else 0.0
    _wings(bm, w * 0.5, offset - pod_r * 0.65 - w * 0.5,
           length * uniform(0.13, 0.19), length * uniform(0.1, 0.15),
           (nac_fore + nac_aft) * 0.5 + sweep, sweep, nac_z * 0.5, nac_z * 0.5,
           length * uniform(0.009, 0.013))
    bands = randint(2, 3)
    for i in range(bands):
        band_x = nac_fore - nac_len * (0.34 + 0.2 * i)
        band_w = pod_r * 0.22
        for side in (1.0, -1.0):
            _loft(bm, (
                (band_x + band_w, pod_r * 1.1, pod_r * 1.1, nac_z, 1.0),
                (band_x - band_w, pod_r * 1.1, pod_r * 1.1, nac_z, 1.0),
            ), shift=side * offset)
    if randint(0, 1):
        fin_x = nac_fore - nac_len * 0.55
        fin_h = pod_r * uniform(0.5, 0.8)
        for side in (1.0, -1.0):
            _loft(bm, (
                (fin_x + length * 0.035, pod_r * 0.18, fin_h * 0.5, nac_z + pod_r * 0.9, 0.1),
                (fin_x - length * 0.035, pod_r * 0.12, fin_h * 0.32, nac_z + pod_r * 0.9, 0.1),
            ), shift=side * offset)
    for side in (1.0, -1.0):
        _engine_bell(bm, nac_aft, side * offset, nac_z, pod_r * 0.8)

def _pod_compact(bm, span_scale, round_bias):
    # One fat tug: a single dominant body, no pods afloat beside it.
    length = uniform(2.3, 2.9)
    w = length * uniform(0.20, 0.26) * (0.8 + 0.4 * span_scale)
    h = w * uniform(0.82, 1.15)
    r = _round_of(0.9, round_bias)
    nose, stern = length * 0.5, -length * 0.5
    _loft(bm, (
        (nose, w * 0.30, h * 0.32, h * 0.10, r),
        (nose - length * 0.12, w * 0.72, h * 0.70, h * 0.06, r),
        (nose - length * 0.34, w, h, 0.0, r),
        (stern + length * 0.22, w * 0.92, h * 0.90, 0.0, r),
        (stern, w * 0.58, h * 0.56, 0.0, r),
    ))
    tower_fore = nose - length * uniform(0.20, 0.28)
    tower_h = h * uniform(0.34, 0.50)
    _bridge(bm, tower_fore, tower_fore - length * uniform(0.14, 0.20), w * uniform(0.42, 0.55),
            tower_h, h * 0.85 + tower_h, r, glass=0.62)
    _slab(bm, nose - length * 0.16, stern + length * 0.10, w * uniform(0.45, 0.60), h * 0.22,
          -h * 0.95, r=0.25, taper=0.90)
    for side in (1.0, -1.0):
        _slab(bm, nose - length * 0.30, stern + length * 0.16, w * 0.22, h * 0.30, -h * 0.15,
              shift=side * w * 0.92, r=0.3, taper=0.85)
    _engine_row(bm, stern, 0.0, randint(1, 2), h * 0.30, w * 0.36)

def _pod_split(bm, span_scale, round_bias):
    # Two full bodies either side of a command pod, bridged by beams and a wing.
    length = uniform(2.8, 3.6)
    w = length * uniform(0.085, 0.115) * (0.8 + 0.4 * span_scale)
    h = w * uniform(0.85, 1.10)
    r = _round_of(0.8, round_bias)
    offset = w * uniform(2.1, 2.8)
    nose, stern = length * 0.5, -length * 0.5
    for side in (1.0, -1.0):
        _loft(bm, (
            (nose, w * 0.45, h * 0.45, h * 0.08, r),
            (nose - length * 0.16, w * 0.92, h * 0.90, 0.0, r),
            (stern + length * 0.20, w, h, 0.0, r),
            (stern, w * 0.68, h * 0.68, 0.0, r),
        ), shift=side * offset)
    cmd_w = w * 0.85
    _loft(bm, ((nose, cmd_w * 0.45, h * 0.42, h * 0.08, r),
               (nose - length * 0.14, cmd_w, h * 0.85, 0.0, r),
               (nose - length * 0.26, cmd_w * 0.90, h * 0.72, 0.0, r)))
    ch = h * uniform(0.28, 0.40)
    _canopy(bm, ((nose - length * 0.10, cmd_w * 0.48, ch, h * 0.85 + ch * 0.4, 0.4),
                 (nose - length * 0.19, cmd_w * 0.42, ch * 0.9, h * 0.85 + ch * 0.4, 0.4)))
    for x in (nose - length * 0.18, stern + length * 0.30):
        _slab(bm, x + length * 0.02, x - length * 0.02, offset + w * 0.80, h * 0.34, 0.0,
              r=0.2, taper=0.95)
    span = offset + w * 1.20
    _wings(bm, w * 0.80, span - w * 0.80, length * uniform(0.20, 0.28),
           length * uniform(0.10, 0.15), stern + length * uniform(0.22, 0.34),
           length * uniform(0.02, 0.10), 0.0, span * uniform(0.0, 0.08),
           length * uniform(0.008, 0.012))
    for side in (1.0, -1.0):
        _engine_bell(bm, stern, side * offset, 0.0, w * 0.72)

def _pod_stacked(bm, span_scale, round_bias):
    # A long heavy lower hull under a shorter upper one, the bridge on the upper.
    length = uniform(2.9, 3.7)
    w = length * uniform(0.10, 0.14) * (0.8 + 0.4 * span_scale)
    h = w * uniform(0.55, 0.75)
    r = _round_of(0.8, round_bias)
    nose, stern = length * 0.5, -length * 0.5
    lower = -h * 1.15
    _loft(bm, (
        (nose - length * 0.08, w * 0.50, h * 0.60, lower, r),
        (nose - length * 0.26, w, h, lower, r),
        (stern + length * 0.26, w * 0.96, h * 0.94, lower, r),
        (stern, w * 0.62, h * 0.60, lower, r),
    ))
    upper = h * 1.05
    upper_aft = nose - length * uniform(0.36, 0.46)
    _loft(bm, ((nose, w * 0.45, h * 0.50, upper, r),
               (nose - length * 0.10, w * 0.85, h * 0.85, upper, r),
               (upper_aft, w * 0.78, h * 0.78, upper, r)))
    _slab(bm, nose - length * 0.10, upper_aft + length * 0.04, w * 0.34, h * 1.20, 0.0,
          r=0.25, taper=0.85)
    ch = h * uniform(0.30, 0.45)
    _canopy(bm, ((nose - length * 0.08, w * 0.55, ch, upper + h * 0.85 + ch * 0.4, 0.4),
                 (nose - length * 0.18, w * 0.50, ch * 0.9, upper + h * 0.85 + ch * 0.4, 0.4)))
    pylon_fore = upper_aft + length * 0.05
    for side in (1.0, -1.0):
        _slab(bm, pylon_fore, pylon_fore - length * 0.08, w * 0.16, h * 1.05, -h * 0.10,
              shift=side * w * 0.55, r=0.2, taper=0.85)
    _engine_row(bm, stern, lower, 2, h * 0.42, w * 0.42)

_BUILDERS = {'wedge': _build_wedge, 'fighter': _build_fighter, 'freighter': _build_freighter,
             'saucer': _build_saucer, 'spine': _build_spine, 'pod': _build_pod}

def _build_archetype(bm, archetype, wing_span, fuselage_roundness, layout):
    _BUILDERS[archetype](bm, min(max(wing_span, 0.0), 1.0), min(max(fuselage_roundness, 0.0), 1.0),
                         layout)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

# Given a face, splits it into a uniform grid and extrudes each grid face
# out and back in again, making an exhaust shape.
def add_exhaust_to_face(bm, face):
    if not face.is_valid:
        return

    # A stern face is told by where it points; any other face a drive is put on, by pointing where it does
    if is_rear_face(face):
        is_exhaust_face = is_rear_face
    else:
        direction = face.normal.copy()
        is_exhaust_face = lambda grid_face: grid_face.normal.dot(direction) > 0.95

    # The more square the face is, the more grid divisions it might have
    num_cuts = randint(1, max(1, int(4 - get_aspect_ratio(face))))
    result = bmesh.ops.subdivide_edges(bm,
                                    edges=face.edges[:],
                                    cuts=num_cuts,
                                    fractal=0.02,
                                    use_grid_fill=True)

    exhaust_length = uniform(0.1, 0.2)
    scale_outer = 1 / uniform(1.3, 1.6)
    scale_inner = 1 / uniform(1.05, 1.1)
    for face in result['geom']:
        if isinstance(face, bmesh.types.BMFace):
            if is_exhaust_face(face):
                face.material_index = Material.hull_dark
                face = extrude_face(bm, face, exhaust_length)
                scale_face(bm, face, scale_outer, scale_outer, scale_outer)
                extruded_face_list = []
                face = extrude_face(bm, face, -exhaust_length * 0.9, extruded_face_list)
                for extruded_face in extruded_face_list:
                    extruded_face.material_index = Material.exhaust_burn
                scale_face(bm, face, scale_inner, scale_inner, scale_inner)

# Given a face, splits it up into a smaller uniform grid and extrudes each grid cell
# by a length drawn between the two values of depth.
def add_grid_to_face(bm, face, depth=(0.025, 0.15), cuts=None, fractal=0.02):
    if not face.is_valid:
        return
    result = bmesh.ops.subdivide_edges(bm,
                                    edges=face.edges[:],
                                    cuts=randint(2, 4) if cuts is None else cuts,
                                    fractal=fractal,
                                    use_grid_fill=True,
                                    use_single_edge=False)
    grid_length = uniform(*depth)
    scale = 0.8
    # `geom` also contains neighbouring faces whose shared edges were split.
    for grid_face in (face, *result['geom_inner']):
        if isinstance(grid_face, bmesh.types.BMFace) and grid_face.is_valid:
            material_index = Material.hull_lights if random() > 0.5 else Material.hull
            extruded_face_list = []
            grid_face = extrude_face(bm, grid_face, grid_length, extruded_face_list)
            for extruded_face in extruded_face_list:
                if abs(grid_face.normal.z) < 0.707: # side face
                    extruded_face.material_index = material_index
            scale_face(bm, grid_face, scale, scale, scale)

# Given a face, adds some cylinders along it in a grid pattern.
def add_cylinders_to_face(bm, face, max_segments=32):
    if not face.is_valid or len(face.verts[:]) < 4:
        return
    horizontal_step = randint(1, 3)
    vertical_step = randint(1, 3)
    num_segments = min(randint(6, 12), max_segments)
    face_width, face_height = get_face_width_and_height(face)
    cylinder_depth = 1.3 * min(face_width / (horizontal_step + 2),
                               face_height / (vertical_step + 2))
    cylinder_size = cylinder_depth * 0.5
    for h in range(horizontal_step):
        top = face.verts[0].co.lerp(
            face.verts[1].co, (h + 1) / float(horizontal_step + 1))
        bottom = face.verts[3].co.lerp(
            face.verts[2].co, (h + 1) / float(horizontal_step + 1))
        for v in range(vertical_step):
            pos = top.lerp(bottom, (v + 1) / float(vertical_step + 1))
            cylinder_matrix = get_face_matrix(face, pos) @ \
                Matrix.Rotation(radians(90), 3, 'X').to_4x4()
            bmesh.ops.create_cone(bm,
                                  cap_ends=True,
                                  cap_tris=False,
                                  segments=num_segments,
                                  radius1=cylinder_size,
                                  radius2=cylinder_size,
                                  depth=cylinder_depth,
                                  matrix=cylinder_matrix)

# Given a face, adds some weapon turrets to it in a grid pattern.
# Each turret will have a random orientation.
def add_weapons_to_face(bm, face, max_segments=32):
    if not face.is_valid or len(face.verts[:]) < 4:
        return
    horizontal_step = randint(1, 2)
    vertical_step = randint(1, 2)
    num_segments = min(16, max_segments)
    face_width, face_height = get_face_width_and_height(face)
    weapon_size = 0.5 * min(face_width / (horizontal_step + 2),
                            face_height / (vertical_step + 2))
    weapon_depth = weapon_size * 0.2
    for h in range(horizontal_step):
        top = face.verts[0].co.lerp(
            face.verts[1].co, (h + 1) / float(horizontal_step + 1))
        bottom = face.verts[3].co.lerp(
            face.verts[2].co, (h + 1) / float(horizontal_step + 1))
        for v in range(vertical_step):
            pos = top.lerp(bottom, (v + 1) / float(vertical_step + 1))
            face_matrix = get_face_matrix(face, pos + face.normal * weapon_depth * 0.5) @ \
                Matrix.Rotation(radians(uniform(0, 90)), 3, 'Z').to_4x4()

            # Turret foundation
            bmesh.ops.create_cone(bm,
                                  cap_ends=True,
                                  cap_tris=False,
                                  segments=num_segments,
                                  radius1=weapon_size * 0.9,
                                  radius2=weapon_size,
                                  depth=weapon_depth,
                                  matrix=face_matrix)

            # Turret left guard
            left_guard_mat = face_matrix @ \
                Matrix.Rotation(radians(90), 3, 'Y').to_4x4() @ \
                Matrix.Translation(Vector((0, 0, weapon_size * 0.6))).to_4x4()
            bmesh.ops.create_cone(bm,
                                  cap_ends=True,
                                  cap_tris=False,
                                  segments=num_segments,
                                  radius1=weapon_size * 0.6,
                                  radius2=weapon_size * 0.5,
                                  depth=weapon_depth * 2,
                                  matrix=left_guard_mat)

            # Turret right guard
            right_guard_mat = face_matrix @ \
                Matrix.Rotation(radians(90), 3, 'Y').to_4x4() @ \
                Matrix.Translation(Vector((0, 0, weapon_size * -0.6))).to_4x4()
            bmesh.ops.create_cone(bm,
                                  cap_ends=True,
                                  cap_tris=False,
                                  segments=num_segments,
                                  radius1=weapon_size * 0.5,
                                  radius2=weapon_size * 0.6,
                                  depth=weapon_depth * 2,
                                  matrix=right_guard_mat)

            # Turret housing
            upward_angle = uniform(0, 45)
            turret_house_mat = face_matrix @ \
                Matrix.Rotation(radians(upward_angle), 3, 'X').to_4x4() @ \
                Matrix.Translation(Vector((0, weapon_size * -0.4, 0))).to_4x4()
            bmesh.ops.create_cone(bm,
                                  cap_ends=True,
                                  cap_tris=False,
                                  segments=min(8, max_segments),
                                  radius1=weapon_size * 0.4,
                                  radius2=weapon_size * 0.4,
                                  depth=weapon_depth * 5,
                                  matrix=turret_house_mat)

            # Turret barrels L + R
            bmesh.ops.create_cone(bm,
                                  cap_ends=True,
                                  cap_tris=False,
                                  segments=min(8, max_segments),
                                  radius1=weapon_size * 0.1,
                                  radius2=weapon_size * 0.1,
                                  depth=weapon_depth * 6,
                                  matrix=turret_house_mat @ \
                                         Matrix.Translation(Vector((weapon_size * 0.2, 0, -weapon_size))).to_4x4())
            bmesh.ops.create_cone(bm,
                                  cap_ends=True,
                                  cap_tris=False,
                                  segments=min(8, max_segments),
                                  radius1=weapon_size * 0.1,
                                  radius2=weapon_size * 0.1,
                                  depth=weapon_depth * 6,
                                  matrix=turret_house_mat @ \
                                         Matrix.Translation(Vector((weapon_size * -0.2, 0, -weapon_size))).to_4x4())

# Given a face, adds a sphere on the surface, partially inset.
def add_sphere_to_face(bm, face, subdivisions=3):
    if not face.is_valid:
        return
    face_width, face_height = get_face_width_and_height(face)
    sphere_size = uniform(0.4, 1.0) * min(face_width, face_height)
    sphere_matrix = get_face_matrix(face,
                                    face.calc_center_bounds() - face.normal * \
                                    uniform(0, sphere_size * 0.5))
    result = bmesh.ops.create_icosphere(bm,
                                        subdivisions=subdivisions,
                                        radius=sphere_size,
                                        matrix=sphere_matrix)
    for vert in result['verts']:
        for face in vert.link_faces:
            face.material_index = Material.hull

# Given a face, adds some pointy intimidating antennas: density is the chance
# that each point of a grid laid over the face carries one.
def add_surface_antenna_to_face(bm, face, density=0.1, max_segments=32):
    if not face.is_valid or len(face.verts[:]) < 4:
        return
    horizontal_step = randint(4, 10)
    vertical_step = randint(4, 10)
    for h in range(horizontal_step):
        top = face.verts[0].co.lerp(
            face.verts[1].co, (h + 1) / float(horizontal_step + 1))
        bottom = face.verts[3].co.lerp(
            face.verts[2].co, (h + 1) / float(horizontal_step + 1))
        for v in range(vertical_step):
            if random() > 1 - density:
                pos = top.lerp(bottom, (v + 1) / float(vertical_step + 1))
                face_size = sqrt(face.calc_area())
                depth = uniform(0.1, 1.5) * face_size
                depth_short = depth * uniform(0.02, 0.15)
                base_diameter = uniform(0.005, 0.05)

                material_index = Material.hull if random() > 0.5 else Material.hull_dark

                # Spire
                num_segments = min(int(uniform(3, 6)), max_segments)
                result = bmesh.ops.create_cone(bm,
                                               cap_ends=False,
                                               cap_tris=False,
                                               segments=num_segments,
                                               radius1=0,
                                               radius2=base_diameter,
                                               depth=depth,
                                               matrix=get_face_matrix(face, pos + face.normal * depth * 0.5))
                for vert in result['verts']:
                    for vert_face in vert.link_faces:
                        vert_face.material_index = material_index

                # Base
                result = bmesh.ops.create_cone(bm,
                                               cap_ends=True,
                                               cap_tris=False,
                                               segments=num_segments,
                                               radius1=base_diameter * uniform(1, 1.5),
                                               radius2=base_diameter * uniform(1.5, 2),
                                               depth=depth_short,
                                               matrix=get_face_matrix(face, pos + face.normal * depth_short * 0.45))
                for vert in result['verts']:
                    for vert_face in vert.link_faces:
                        vert_face.material_index = material_index

# Given a face, adds a glowing "landing pad" style disc.
def add_disc_to_face(bm, face, max_segments=32):
    if not face.is_valid:
        return
    face_width, face_height = get_face_width_and_height(face)
    depth = 0.125 * min(face_width, face_height)
    bmesh.ops.create_cone(bm,
                          cap_ends=True,
                          cap_tris=False,
                          segments=min(32, max_segments),
                          radius1=depth * 3,
                          radius2=depth * 4,
                          depth=depth,
                          matrix=get_face_matrix(face, face.calc_center_bounds() + face.normal * depth * 0.5))
    result = bmesh.ops.create_cone(bm,
                                   cap_ends=False,
                                   cap_tris=False,
                                   segments=min(32, max_segments),
                                   radius1=depth * 1.25,
                                   radius2=depth * 2.25,
                                   depth=0.0,
                                   matrix=get_face_matrix(face, face.calc_center_bounds() + face.normal * depth * 1.05))
    for vert in result['verts']:
        for face in vert.link_faces:
            face.material_index = Material.glow_disc

# The rest of a hull's hardware: fittings laid on the bare forms, on the half the mirror keeps
# (y >= 0), so the symmetrize that follows gives each one its pair.

def _dressable(bm, direction):
    # Quad hull faces pointing `direction` on the kept half, largest first, and the hull's length.
    length = max(v.co.x for v in bm.verts) - min(v.co.x for v in bm.verts)
    faces = [face for face in bm.faces
             if len(face.verts) == 4 and face.material_index == Material.hull
             and face.normal.dot(direction) > 0.75
             and face.calc_center_median().y > -1e-5
             and get_aspect_ratio(face) < 3
             and face.calc_area() > length * length * 0.0015]
    faces.sort(key=lambda face: -face.calc_area())
    return faces, length

def _share(faces, amount, most):
    # A fitting's own faces: up to `most` of them, fewer as `amount` falls, none at zero.
    if amount <= 0:
        return []
    count = max(1, int(round(amount * most)))
    return [face for face in faces if face.is_valid and random() < 0.55 + 0.45 * amount][:count]

def _coat(result, material):
    for vert in result['verts']:
        for face in vert.link_faces:
            face.material_index = material

# Tubes nose to stern along a plate, sitting half in the plating.
def add_pipes_to_face(bm, face, length, amount=0.3, max_segments=32):
    # a tube on a wing's edge is a strut, not pipework: it goes on a plate wide enough to carry it
    if not face.is_valid or len(face.verts) != 4 or get_aspect_ratio(face) > 2.4:
        return
    rails = [sorted(edge.verts, key=lambda vert: vert.co.x) for edge in face.edges
             if abs(edge.verts[1].co.x - edge.verts[0].co.x) > length * 0.02]
    if len(rails) < 2:
        return
    rails.sort(key=lambda rail: rail[0].co.y + rail[1].co.y)
    near, far = rails[0], rails[-1]
    radius = length * (0.006 + 0.008 * amount)
    count = 1 + int(round(amount * 2))
    for step in range(count):
        across = (step + 1) / (count + 1.0)
        head = near[0].co.lerp(near[1].co, 0.1).lerp(far[0].co.lerp(far[1].co, 0.1), across)
        tail = near[0].co.lerp(near[1].co, 0.92).lerp(far[0].co.lerp(far[1].co, 0.92), across)
        lift = face.normal * radius * 0.6
        _tube(bm, head + lift, tail + lift, radius, Material.hull_dark, min(6, max_segments))

# A plate standing proud of the hull, its edge left to the bevel that follows.
def add_armour_to_face(bm, face, length, amount=0.3):
    if not face.is_valid:
        return
    rise = length * (0.005 + 0.010 * amount)
    plate = extrude_face(bm, face, rise)
    scale_face(bm, plate, 0.94, 0.94, 1.0)
    plate = extrude_face(bm, plate, rise * 0.6)
    scale_face(bm, plate, 0.9, 0.9, 1.0)
    plate.material_index = Material.hull

# A recess sunk into a plate, its mouth barred: a ship's one real hole.
def add_intakes_to_face(bm, face, length, amount=0.3, max_segments=32):
    if not face.is_valid:
        return
    width, height = get_face_width_and_height(face)
    depth = length * (0.010 + 0.015 * amount)
    mouth = extrude_face(bm, face, -depth)
    for vert in mouth.verts:
        for wall in vert.link_faces:
            if wall is not mouth:
                wall.material_index = Material.hull_dark
    mouth.material_index = Material.hull_dark
    bars = 2 if amount < 0.6 else 3
    frame = get_face_matrix(mouth, mouth.calc_center_bounds())
    for step in range(bars):
        across = (step - (bars - 1) / 2.0) * height * 0.34
        _box(bm, frame @ Matrix.Translation((0.0, across, 0.0)),
             (width * 0.8, max(length * 0.002, 0.0015), max(length * 0.003, 0.002)), Material.hull_dark)

# A coupling standing proud of the hull, where a hose or a boom would lock on.
def add_hub_to_face(bm, face, length, amount=0.3, max_segments=32):
    if not face.is_valid:
        return
    width, height = get_face_width_and_height(face)
    across = min(width, height) * 0.36
    rise = max(length * 0.006, 0.002)
    _coat(bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=min(12, max_segments),
                                radius1=across, radius2=across * 0.82, depth=rise,
                                matrix=get_face_matrix(face, face.calc_center_bounds() + face.normal * rise * 0.5)),
          Material.hull_dark)
    _coat(bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=min(12, max_segments),
                                radius1=across * 0.55, radius2=across * 0.45, depth=rise * 0.8,
                                matrix=get_face_matrix(face, face.calc_center_bounds() + face.normal * rise * 1.3)),
          Material.hull_dark)

# Flat pads where a turret or a piece of equipment would sit: bare metal, and empty (ART 4.2).
def add_mounts_to_face(bm, face, length, amount=0.3):
    if not face.is_valid:
        return
    width, height = get_face_width_and_height(face)
    pad = min(width, height) * 0.34
    rise = max(length * 0.005, 0.002)
    count = 1 + int(round(amount * 3))
    frame = get_face_matrix(face, face.calc_center_bounds())
    for step in range(count):
        across = (step - (count - 1) / 2.0) * pad * 1.5
        _box(bm, frame @ Matrix.Translation((across, 0.0, -rise * 0.5)), (pad, pad, rise), Material.glow_disc)

# Rails and rungs down a flank, from the top of the plate to its bottom.
def add_ladder_to_face(bm, face, length, amount=0.3):
    # a ladder needs a plate with some height to it, and reads as scrap on a wing's edge
    if not face.is_valid or get_aspect_ratio(face) > 2.4:
        return
    width, height = get_face_width_and_height(face)
    frame = get_face_matrix(face, face.calc_center_bounds())
    across = min(width, height) * 0.22
    bar = max(length * 0.0045, 0.002)
    rungs = 3 + int(round(amount * 4))
    for side in (-1.0, 1.0):
        _box(bm, frame @ Matrix.Translation((side * across, 0.0, -bar * 0.5)),
             (bar, height * 0.74, bar), Material.hull_dark)
    for step in range(rungs):
        along = (step / (rungs - 1.0) - 0.5) * height * 0.66
        _box(bm, frame @ Matrix.Translation((0.0, along, -bar * 0.5)),
             (across * 2.0, bar * 0.8, bar), Material.hull_dark)

# A frame of bars standing off the belly: where a miner's tools and cables would bolt on.
def add_lattice_to_face(bm, face, length, amount=0.3, max_segments=32):
    if not face.is_valid:
        return
    width, height = get_face_width_and_height(face)
    stand = length * (0.010 + 0.012 * amount)
    bar = max(length * 0.007, 0.002)
    frame = get_face_matrix(face, face.calc_center_bounds() + face.normal * length * 0.001)
    brace = get_face_matrix(face, face.calc_center_bounds() + face.normal * stand * 0.5)
    for side in (-1.0, 1.0):
        _box(bm, brace @ Matrix.Translation((0.0, side * height * 0.3, 0.0)),
             (width * 0.82, bar, bar), Material.hull_dark)
        _box(bm, brace @ Matrix.Translation((side * width * 0.3, 0.0, 0.0)),
             (bar, height * 0.62, bar), Material.hull_dark)
        for corner in (-1.0, 1.0):
            _box(bm, frame @ Matrix.Translation((corner * width * 0.3, side * height * 0.3, -stand * 0.5)),
                 (bar, bar, stand), Material.hull_dark)

# Quarter lights: rows of panes standing in the plating, the one thing on a hull that lights it.
def add_windows_to_face(bm, face, length, amount=0.3):
    if not face.is_valid:
        return
    width, height = get_face_width_and_height(face)
    frame = get_face_matrix(face, face.calc_center_bounds())
    rows = 1 + int(round(amount * 2))
    panes = 2 + int(round(amount * 3))
    pane = width * 0.13
    tall = max(length * 0.006, 0.0025)
    for row in range(rows):
        along = (row - (rows - 1) / 2.0) * height * 0.16
        for step in range(panes):
            across = (step - (panes - 1) / 2.0) * pane * 1.7
            _quad(bm, frame @ Matrix.Translation((across, along, -length * 0.0025)),
                  (pane, tall * 1.8), Material.light)

# A docking bay: the plate sunk in behind a lit mouth, so a hull carrying one is seen at night.
def add_bay_to_face(bm, face, length, max_segments=32):
    if not face.is_valid:
        return
    width, height = get_face_width_and_height(face)
    lip = get_face_matrix(face, face.calc_center_bounds() + face.normal * length * 0.001)
    depth = length * 0.05
    mouth = extrude_face(bm, face, -depth)
    for vert in mouth.verts:
        for wall in vert.link_faces:
            if wall is not mouth:
                wall.material_index = Material.hull_dark
    mouth.material_index = Material.hull_dark
    scale_face(bm, mouth, 0.86, 0.66, 1.0)
    _quad(bm, lip @ Matrix.Translation((0.0, height * 0.28, -length * 0.0025)),
          (width * 0.7, max(length * 0.010, 0.004)), Material.light)

# The hardware of one archetype hull, in the order the fittings need the mesh: the armour and the
# recesses first, since they cut the faces the rest are laid on.
def add_archetype_detail(bm, pipes=0.0, armour=0.0, intakes=0.0, hubs=0.0, mounts=0.0,
                         ladders=0.0, lattice=0.0, lights=0.0, max_segments=32):
    top, length = _dressable(bm, Vector((0.0, 0.0, 1.0)))
    flank, _ = _dressable(bm, Vector((0.0, 1.0, 0.0)))
    belly, _ = _dressable(bm, Vector((0.0, 0.0, -1.0)))

    for face in _share(top[:2] + belly[:2], armour, 4):
        add_armour_to_face(bm, face, length, armour)
    for face in _share(flank, intakes, 2):
        add_intakes_to_face(bm, face, length, intakes, max_segments)
    for face in _share(flank[1:], min(lights, 1.0) * 0.6, 1):
        add_bay_to_face(bm, face, length, max_segments)
    for face in _share(flank, pipes, 3):
        add_pipes_to_face(bm, face, length, pipes, max_segments)
    for face in _share(top, min(lights, 1.0), 3):
        add_windows_to_face(bm, face, length, lights)
    for face in _share(flank[1:], min(lights, 1.0), 3):
        add_windows_to_face(bm, face, length, lights * 0.7)
    for face in _share(top[1:], hubs, 1):
        add_hub_to_face(bm, face, length, hubs, max_segments)
    for face in _share(top[2:], mounts, 3):
        add_mounts_to_face(bm, face, length, mounts)
    for face in _share(flank[2:], ladders, 1):
        add_ladder_to_face(bm, face, length, ladders)
    for face in _share(belly, lattice, 2):
        add_lattice_to_face(bm, face, length, lattice, max_segments)

class Material(IntEnum):
    hull = 0            # Plain spaceship hull
    hull_lights = 1     # Spaceship hull with emissive windows
    hull_dark = 2       # Plain Spaceship hull, darkened
    exhaust_burn = 3    # Emissive engine burn material
    glow_disc = 4       # Emissive landing pad disc material
    glass = 5           # Cockpit glazing: dark, smooth, opaque, never lit from inside
    light = 6           # A lamp: a quarter light, a docking bay's mouth. The one face on a hull that emits


# Returns shader node
def getShaderNode(mat):
    ntree = mat.node_tree
    node_out = ntree.get_output_node('EEVEE')
    shader_node = node_out.inputs['Surface'].links[0].from_node
    return shader_node

def getShaderInput(mat, name):
    shaderNode = getShaderNode(mat)
    return shaderNode.inputs[name]

# Adds a hull normal map texture slot to a material.
def add_hull_normal_map(mat, hull_normal_map):
    ntree = mat.node_tree
    shader = getShaderNode(mat)
    links = ntree.links

    teximage_node = ntree.nodes.new('ShaderNodeTexImage')
    teximage_node.image = hull_normal_map
    teximage_node.image.colorspace_settings.name = 'Non-Color'
    teximage_node.projection ='BOX'
    tex_coords_node = ntree.nodes.new('ShaderNodeTexCoord')
    links.new(tex_coords_node.outputs['Object'], teximage_node.inputs['Vector'])
    normalMap_node = ntree.nodes.new('ShaderNodeNormalMap')
    links.new(teximage_node.outputs[0], normalMap_node.inputs['Color'])
    links.new(normalMap_node.outputs['Normal'], shader.inputs['Normal'])
    return tex_coords_node



# Sets some basic properties for a hull material.
def set_hull_mat_basics(mat, color, hull_normal_map):
    shader_node = getShaderNode(mat)
    shader_node.inputs["Specular IOR Level"].default_value = 0.1
    shader_node.inputs["Base Color"].default_value = color

    return add_hull_normal_map(mat, hull_normal_map)

# Creates all our materials and returns them as a list.
def create_materials():
    ret = []

    for material in Material:
        mat = bpy.data.materials.new(name=material.name)
        if bpy.app.version < (5, 0, 0):
            mat.use_nodes = True  # every material has nodes from 5.0 on, and asking is deprecated
        ret.append(mat)

    # Choose a base color for the spaceship hull
    hull_base_color = hls_to_rgb(
        random(), uniform(0.05, 0.5), uniform(0, 0.25))
    hull_base_color = (hull_base_color[0], hull_base_color[1], hull_base_color[2], 1.0)

    # Load up the hull normal map
    hull_normal_map = bpy.data.images.load(resource_path('textures', 'hull_normal.png'), check_existing=True)


    # Build the hull texture
    mat = ret[Material.hull]
    set_hull_mat_basics(mat, hull_base_color, hull_normal_map)

    # Build the hull_lights texture
    mat = ret[Material.hull_lights]
    tex_coords_node = set_hull_mat_basics(mat, hull_base_color, hull_normal_map)
    ntree = mat.node_tree
    shader_node = getShaderNode(mat)
    links = ntree.links

    # Add a diffuse layer that sets the window color
    hull_lights_diffuse_map = bpy.data.images.load(resource_path('textures', 'hull_lights_diffuse.png'), check_existing=True)
    teximage_diff_node = ntree.nodes.new('ShaderNodeTexImage')
    teximage_diff_node.image = hull_lights_diffuse_map
    teximage_diff_node.projection ='BOX'
    links.new(tex_coords_node.outputs['Object'], teximage_diff_node.inputs['Vector'])
    RGB_node = ntree.nodes.new('ShaderNodeRGB')
    RGB_node.outputs[0].default_value = hull_base_color
    mix_node = ntree.nodes.new('ShaderNodeMixRGB')
    links.new(RGB_node.outputs[0], mix_node.inputs[1])
    links.new(teximage_diff_node.outputs[0], mix_node.inputs[2])
    links.new(teximage_diff_node.outputs[1], mix_node.inputs[0])
    links.new(mix_node.outputs[0], shader_node.inputs["Base Color"])



    # Add an emissive layer that lights up the windows
    hull_lights_emessive_map = bpy.data.images.load(resource_path('textures', 'hull_lights_emit.png'), check_existing=True)
    teximage_emit_node = ntree.nodes.new('ShaderNodeTexImage')
    teximage_emit_node.image = hull_lights_emessive_map
    teximage_emit_node.projection ='BOX'
    links.new(tex_coords_node.outputs['Object'], teximage_emit_node.inputs['Vector'])
    links.new(teximage_emit_node.outputs[0], shader_node.inputs["Emission Color"])
    shader_node.inputs["Emission Strength"].default_value = 1.0



    # Build the hull_dark texture
    mat = ret[Material.hull_dark]
    set_hull_mat_basics(mat, [0.3 * x for x in hull_base_color[:3]] + [1.0], hull_normal_map)

    # Choose a glow color for the exhaust + glow discs
    glow_color = hls_to_rgb(random(), uniform(0.5, 1), 1)
    glow_color = (glow_color[0], glow_color[1], glow_color[2], 1.0)

    # # Build the exhaust_burn texture
    mat = ret[Material.exhaust_burn]
    shader_node = getShaderNode(mat)
    shader_node.inputs["Emission Color"].default_value = glow_color
    shader_node.inputs["Emission Strength"].default_value = 1.0

    # # Build the glow_disc texture
    mat = ret[Material.glow_disc]
    shader_node = getShaderNode(mat)
    shader_node.inputs["Emission Color"].default_value = glow_color
    shader_node.inputs["Emission Strength"].default_value = 1.0

    # Build the glass canopy: dark and reflective, with no light of its own
    mat = ret[Material.glass]
    shader_node = getShaderNode(mat)
    shader_node.inputs["Base Color"].default_value = (0.018, 0.026, 0.040, 1.0)
    shader_node.inputs["Roughness"].default_value = 0.12
    shader_node.inputs["Metallic"].default_value = 0.30
    shader_node.inputs["Specular IOR Level"].default_value = 0.9
    shader_node.inputs["Emission Strength"].default_value = 0.0

    return ret

# Generates a textured spaceship mesh and returns the object.
# Just uses global cube texture coordinates rather than generating UVs.
# Takes an optional random seed value to generate a specific spaceship.
#
# The default is a symmetric wedge. `classic` selects the original extrusion machinery.
# Archetypes use one primary form, attached secondary forms and sparse surface detail.
#
#   archetype                      wedge, fighter, freighter, saucer, spine, pod, or classic
#   layout                         how that archetype's forms are arranged: balanced (the form
#                                  above), compact (one tight solid form), split (two forms either
#                                  side of the centre line) or stacked (forms tiered over each
#                                  other). Classic leaves this alone.
#   wing_span                      spread of wings, pods or beam: 0 narrow, 1 wide
#   fuselage_roundness             bias towards round sections (saucer: thickness), 0..1
#   taper                          front-half scale: 0 wider, 0.5 neutral, 1 narrower
#   num_hull_segments_min/max       how many sections each end of the hull is extruded by
#                                   (max is exclusive, as it always was; equal to min means exactly min)
#   hull_scale_x/y/z                the starting block's length, width and height: (low, high)
#   hull_segment_lengths            the length of one section: (low, high)
#   hull_taper_chance               how often a section narrows or widens
#   hull_step_chance                how often a section steps up or down
#   hull_tilt_chance                how often a section tilts five degrees
#   hull_ribbed_chance              how often a section is ribbed instead
#   min_slenderness                 stretch the bare hull until it is at least this many times
#                                   as long as it is wide or tall (0 leaves it alone)
#   nose_taper                      draw the nose in towards a point: 0 none, 0.95 the most
#   create_asymmetry_segments       grow blocks out of the hull's faces...
#   asymmetry_chance                ...this often a face...
#   num_asymmetry_segments_min/max  ...by this many sections (max exclusive)
#   create_face_detail              dress the faces at all; then, kind by kind:
#   create_grids, create_antennas, create_weapons, create_spheres, create_discs, create_cylinders
#   grid_depth                      how far a grid's cells stand out: (low, high)
#   antenna_density                 the chance of an antenna at each point of an antenna face
#   max_round_segments              the most sides any round part is given
#   sphere_subdivisions             how finely a sphere is divided
#   allow_horizontal_symmetry       mirror the ship left to right...
#   horizontal_symmetry_chance      ...this often (1 always)
#   allow_vertical_symmetry, vertical_symmetry_chance   the same, top to bottom
#   apply_bevel_modifier            add the broad bevel modifier
#   assign_materials                build the textured hull materials and opaque glass; otherwise six empty slots
def generate_spaceship(random_seed='',
                       num_hull_segments_min=3,
                       num_hull_segments_max=6,
                       create_asymmetry_segments=True,
                       num_asymmetry_segments_min=1,
                       num_asymmetry_segments_max=5,
                       create_face_detail=True,
                       allow_horizontal_symmetry=True,
                       allow_vertical_symmetry=False,
                       apply_bevel_modifier=True,
                       assign_materials=True,
                       *,
                       hull_scale_x=(0.75, 2.0),
                       hull_scale_y=(0.75, 2.0),
                       hull_scale_z=(0.75, 2.0),
                       hull_segment_lengths=(0.3, 1.0),
                       hull_taper_chance=0.5,
                       hull_step_chance=0.5,
                       hull_tilt_chance=0.5,
                       hull_ribbed_chance=0.1,
                       min_slenderness=0.0,
                       nose_taper=0.0,
                       asymmetry_chance=0.15,
                       create_grids=True,
                       create_antennas=True,
                       create_weapons=True,
                       create_spheres=True,
                       create_discs=True,
                       create_cylinders=True,
                       grid_depth=(0.025, 0.15),
                       antenna_density=0.1,
                       max_round_segments=32,
                       sphere_subdivisions=3,
                       horizontal_symmetry_chance=1.0,
                       vertical_symmetry_chance=0.5,
                       archetype='wedge',
                       wing_span=0.5,
                       fuselage_roundness=0.5,
                       layout='balanced',
                       taper=0.5,
                       pipes=0.0,
                       armour=0.0,
                       intakes=0.0,
                       hubs=0.0,
                       mounts=0.0,
                       ladders=0.0,
                       lattice=0.0,
                       lights=0.0,
                       nozzle='bell'):
    if random_seed:
        seed(random_seed)
    max_round_segments = max(3, int(max_round_segments))
    if archetype not in ARCHETYPES:
        raise ValueError("Unknown archetype: " + archetype)
    if layout not in LAYOUTS:
        raise ValueError("Unknown layout: " + layout)
    if nozzle not in _NOZZLE_ROWS and nozzle != 'cluster':
        raise ValueError("Unknown nozzle: " + nozzle)
    global _NOZZLE
    _NOZZLE = nozzle

    bm = bmesh.new()
    if archetype == 'classic':
        bmesh.ops.create_cube(bm, size=1)
        scale_vector = Vector(
            (uniform(*hull_scale_x), uniform(*hull_scale_y), uniform(*hull_scale_z)))
        bmesh.ops.scale(bm, vec=scale_vector, verts=bm.verts)
    else:
        _build_archetype(bm, archetype, wing_span, fuselage_roundness, layout)
        front = max(v.co.x for v in bm.verts)
        back = min(v.co.x for v in bm.verts)
        for vert in bm.verts:
            along = max(0.0, (vert.co.x - (front + back) * 0.5) / ((front - back) * 0.5))
            scale = 1.0 + along * (0.3 - 0.6 * min(max(taper, 0.0), 1.0))
            vert.co.y *= scale
            vert.co.z *= scale
        bm.normal_update()

    nose_face = None
    for face in (bm.faces[:] if archetype == 'classic' else []):
        if abs(face.normal.x) > 0.5:
            is_nose = face.normal.x > 0
            hull_segment_length = uniform(*hull_segment_lengths)
            num_hull_segments = randrange(num_hull_segments_min, max(num_hull_segments_max, num_hull_segments_min + 1))
            hull_segment_range = range(num_hull_segments)
            for i in hull_segment_range:
                is_last_hull_segment = i == hull_segment_range[-1]
                val = random()
                if val > hull_ribbed_chance:
                    # Most of the time, extrude out the face with some random deviations
                    face = extrude_face(bm, face, hull_segment_length)
                    if random() > 0.75:
                        face = extrude_face(
                            bm, face, hull_segment_length * 0.25)

                    # Maybe apply some scaling
                    if random() > 1 - hull_taper_chance:
                        sy = uniform(1.2, 1.5)
                        sz = uniform(1.2, 1.5)
                        if is_last_hull_segment or random() > 0.5:
                            sy = 1 / sy
                            sz = 1 / sz
                        scale_face(bm, face, 1, sy, sz)

                    # Maybe apply some sideways translation
                    if random() > 1 - hull_step_chance:
                        sideways_translation = Vector(
                            (0, 0, uniform(0.1, 0.4) * scale_vector.z * hull_segment_length))
                        if random() > 0.5:
                            sideways_translation = -sideways_translation
                        bmesh.ops.translate(bm,
                                            vec=sideways_translation,
                                            verts=face.verts)

                    # Maybe add some rotation around Y axis
                    if random() > 1 - hull_tilt_chance:
                        angle = 5
                        if random() > 0.5:
                            angle = -angle
                        bmesh.ops.rotate(bm,
                                         verts=face.verts,
                                         cent=(0, 0, 0),
                                         matrix=Matrix.Rotation(radians(angle), 3, 'Y'))
                else:
                    # Rarely, create a ribbed section of the hull
                    rib_scale = uniform(0.75, 0.95)
                    face = ribbed_extrude_face(
                        bm, face, hull_segment_length, randint(2, 4), rib_scale)
            if is_nose:
                nose_face = face

    # Stretch a stubby hull along its length, before anything is built on it
    if min_slenderness > 0:
        low = [min(v.co[axis] for v in bm.verts) for axis in range(3)]
        high = [max(v.co[axis] for v in bm.verts) for axis in range(3)]
        length = high[0] - low[0]
        wanted = min_slenderness * max(high[1] - low[1], high[2] - low[2])
        if 0 < length < wanted:
            bmesh.ops.scale(bm, vec=Vector((wanted / length, 1, 1)), verts=bm.verts)

    # Draw the nose in towards a point
    if nose_taper > 0 and nose_face is not None and nose_face.is_valid:
        nose_scale = 1 - min(nose_taper, 0.95)
        scale_face(bm, nose_face, nose_scale, nose_scale, nose_scale)

    # Add some large asymmetrical sections of the hull that stick out
    if create_asymmetry_segments and archetype == 'classic':
        for face in bm.faces[:]:
            # Skip any long thin faces as it'll probably look stupid
            if get_aspect_ratio(face) > 4:
                continue
            if random() > 1 - asymmetry_chance:
                hull_piece_length = uniform(0.1, 0.4)
                for i in range(randrange(num_asymmetry_segments_min, max(num_asymmetry_segments_max, num_asymmetry_segments_min + 1))):
                    face = extrude_face(bm, face, hull_piece_length)

                    # Maybe apply some scaling
                    if random() > 0.25:
                        s = 1 / uniform(1.1, 1.5)
                        scale_face(bm, face, s, s, s)

    # Now the basic hull shape is built, let's categorize + add detail to all the faces
    if create_face_detail and archetype != 'classic':
        if create_grids:
            length = max(v.co.x for v in bm.verts) - min(v.co.x for v in bm.verts)
            panels = [face for face in bm.faces
                      if len(face.verts) == 4 and face.material_index == Material.hull
                      and face.normal.z > 0.5 and get_aspect_ratio(face) < 3
                      and face.calc_area() < length * length * 0.04 and random() < 0.18]
            for face in panels[:6]:
                add_grid_to_face(bm, face, (length * 0.002, length * 0.004), cuts=1, fractal=0)
        add_archetype_detail(bm, pipes, armour, intakes, hubs, mounts, ladders, lattice, lights, max_round_segments)
    if create_face_detail and archetype == 'classic':
        engine_faces = []
        grid_faces = []
        antenna_faces = []
        weapon_faces = []
        sphere_faces = []
        disc_faces = []
        cylinder_faces = []
        for face in bm.faces[:]:
            # Skip any long thin faces as it'll probably look stupid
            if get_aspect_ratio(face) > 3:
                continue

            # Spin the wheel! Let's categorize + assign some materials
            val = random()
            if is_rear_face(face):  # rear face
                if not engine_faces or val > 0.75:
                    engine_faces.append(face)
                elif val > 0.5:
                    cylinder_faces.append(face)
                elif val > 0.25:
                    grid_faces.append(face)
                else:
                    face.material_index = Material.hull_lights
            elif face.normal.x > 0.9:  # front face
                if face.normal.dot(face.calc_center_bounds()) > 0 and val > 0.7:
                    antenna_faces.append(face)  # front facing antenna
                    face.material_index = Material.hull_lights
                elif val > 0.4:
                    grid_faces.append(face)
                else:
                    face.material_index = Material.hull_lights
            elif face.normal.z > 0.9:  # top face
                if face.normal.dot(face.calc_center_bounds()) > 0 and val > 0.7:
                    antenna_faces.append(face)  # top facing antenna
                elif val > 0.6:
                    grid_faces.append(face)
                elif val > 0.3:
                    cylinder_faces.append(face)
            elif face.normal.z < -0.9:  # bottom face
                if val > 0.75:
                    disc_faces.append(face)
                elif val > 0.5:
                    grid_faces.append(face)
                elif val > 0.25:
                    weapon_faces.append(face)
            elif abs(face.normal.y) > 0.9:  # side face
                if not weapon_faces or val > 0.75:
                    weapon_faces.append(face)
                elif val > 0.6:
                    grid_faces.append(face)
                elif val > 0.4:
                    sphere_faces.append(face)
                else:
                    face.material_index = Material.hull_lights

        # Now we've categorized, let's actually add the detail
        for face in engine_faces:
            add_exhaust_to_face(bm, face)

        if create_grids:
            for face in grid_faces:
                add_grid_to_face(bm, face, grid_depth)

        if create_antennas:
            for face in antenna_faces:
                add_surface_antenna_to_face(bm, face, antenna_density, max_round_segments)

        if create_weapons:
            for face in weapon_faces:
                add_weapons_to_face(bm, face, max_round_segments)

        if create_spheres:
            for face in sphere_faces:
                add_sphere_to_face(bm, face, sphere_subdivisions)

        if create_discs:
            for face in disc_faces:
                add_disc_to_face(bm, face, max_round_segments)

        if create_cylinders:
            for face in cylinder_faces:
                add_cylinders_to_face(bm, face, max_round_segments)

    # Apply horizontal symmetry sometimes
    if archetype != 'classic' or (allow_horizontal_symmetry and random() > 1 - horizontal_symmetry_chance):
        bmesh.ops.symmetrize(bm, input=bm.verts[:] + bm.edges[:] + bm.faces[:], direction="Y")

    # Apply vertical symmetry sometimes - this can cause spaceship "islands", so disabled by default
    if allow_vertical_symmetry and random() > 1 - vertical_symmetry_chance:
        bmesh.ops.symmetrize(bm, input=bm.verts[:] + bm.edges[:] + bm.faces[:], direction="Z")

    # Every dressed ship gets a drive. One can be missing: no stern face was square enough to be given
    # one, or the only one stood on the half a mirror threw away. It then goes on the largest of the
    # faces that point furthest aft, and on each of them alike where a mirror made two.
    if create_face_detail and not any(face.material_index == Material.exhaust_burn for face in bm.faces):
        faces = [face for face in bm.faces if face.is_valid and len(face.verts) == 4]
        if faces:
            aft = min(face.normal.x for face in faces)
            rear = [face for face in faces if face.normal.x < aft + 0.05]
            largest = max(face.calc_area() for face in rear)
            state = getstate()
            for face in [face for face in rear if face.calc_area() > largest * 0.999]:
                setstate(state)
                add_exhaust_to_face(bm, face)

    if archetype != 'classic':
        bm.normal_update()
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = (edge.is_manifold and edge.calc_face_angle(0) < radians(50)
                           and edge.link_faces[0].material_index == edge.link_faces[1].material_index)

    # Finish up, write the bmesh into a new mesh
    me = bpy.data.meshes.new('Mesh')
    bm.to_mesh(me)
    if archetype != 'classic':
        me["rounded"] = True
    bm.free()

    # Add the mesh to the scene
    scene = bpy.context.scene
    obj = bpy.data.objects.new('Spaceship', me)
    scene.collection.objects.link(obj)

    # Select and make active
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Recenter the object to its center of mass
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    ob = bpy.context.object
    ob.location = (0, 0, 0)

    # Add a fairly broad bevel modifier to angularize shape
    if apply_bevel_modifier:
        bevel_modifier = ob.modifiers.new('Bevel', 'BEVEL')
        bevel_modifier.width = uniform(5, 20) if archetype == 'classic' else 3
        bevel_modifier.offset_type = 'PERCENT'
        bevel_modifier.segments = 2
        bevel_modifier.profile = 0.25 if archetype == 'classic' else 0.5
        bevel_modifier.limit_method = 'NONE' if archetype == 'classic' else 'ANGLE'

    # Keep face-zone indices stable, with or without textured materials.
    me = ob.data
    if assign_materials:
        for mat in create_materials():
            me.materials.append(mat)
    else:
        for material in Material:
            me.materials.append(bpy.data.materials.new(name="Material"))

    return obj

if __name__ == "__main__":
    # Reset the scene, generate a single spaceship and focus on it
    reset_scene()
    customseed = '' # add anything here to generate the same spaceship
    obj = generate_spaceship(customseed)

    # View the selected object in all views (there are none when Blender runs in the background)
    screen = bpy.context.screen
    for area in (screen.areas if screen else []):
        if area.type == 'VIEW_3D':
            with bpy.context.temp_override(area=area, region=area.regions[-1]):
                bpy.ops.view3d.view_selected()
