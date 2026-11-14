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
    roof.material_index = windshield.material_index = Material.hull_lights

def _disc(bm, sections, sides=12):
    # A volume stacked down Z through sections (z, radius_x, radius_y): a
    # saucer's language.
    rings = []
    for z, radius_x, radius_y in sections:
        points = _ring_points(radius_x, radius_y, 1.0, sides)
        rings.append([bm.verts.new((px, py, z)) for px, py in points])
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

def _engine_bell(bm, x, y, z, radius):
    # A drive on the stern plane `x`, looking down -X: a bell proud of the
    # hull, a rim, and a recessed throat whose floor wears the exhaust
    # material — the shape the classic exhausts leave, so a reader of the
    # mesh finds the same thing.
    rows = (
        (x + radius * 0.8, 1.0),
        (x - radius * 0.55, 1.0),
        (x - radius * 0.55, 0.72),
        (x - radius * 0.12, 0.6),
    )
    rings = []
    for ring_x, scale in rows:
        points = _ring_points(radius * scale, radius * scale, 1.0)
        rings.append([bm.verts.new((ring_x, y + py, z + pz)) for py, pz in points])
    faces = _bridge_rings(bm, rings)
    for face in faces:
        face.material_index = Material.hull_dark
    faces[-1].material_index = Material.exhaust_burn

def _engine_row(bm, x, z, count, radius, spread):
    if count > 1:
        radius = min(radius, spread / (count - 1) * 0.8)
    for i in range(count):
        y = 0.0 if count == 1 else spread * (2.0 * i / (count - 1) - 1.0)
        _engine_bell(bm, x, y, z, radius)

def _round_of(base, bias):
    return min(1.0, max(0.0, base + (bias - 0.5) * 0.6))

def _build_wedge(bm, span_scale, round_bias):
    # A variable arrowhead with a stepped bridge, deck tiers and flank trenches.
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

def _build_fighter(bm, span_scale, round_bias):
    # Swept or forward-swept wings, with canards, intakes or stern fairings.
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

def _build_freighter(bm, span_scale, round_bias):
    # Cargo modules on a continuous spine, with a raised forward bridge.
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

def _build_saucer(bm, span_scale, round_bias):
    # An oval lens with paired mandibles and a raised glazed command module.
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

def _build_spine(bm, span_scale, round_bias):
    # Mixed tanks and cargo modules on struts off an exposed boom.
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

def _build_pod(bm, span_scale, round_bias):
    # A raised command section and ribbed nacelles on straight or swept wings.
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

_BUILDERS = {'wedge': _build_wedge, 'fighter': _build_fighter, 'freighter': _build_freighter,
             'saucer': _build_saucer, 'spine': _build_spine, 'pod': _build_pod}

def _build_archetype(bm, archetype, wing_span, fuselage_roundness):
    _BUILDERS[archetype](bm, min(max(wing_span, 0.0), 1.0), min(max(fuselage_roundness, 0.0), 1.0))
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
    for face in result['geom']:
        if isinstance(face, bmesh.types.BMFace):
            material_index = Material.hull_lights if random() > 0.5 else Material.hull
            extruded_face_list = []
            face = extrude_face(bm, face, grid_length, extruded_face_list)
            for extruded_face in extruded_face_list:
                if abs(face.normal.z) < 0.707: # side face
                    extruded_face.material_index = material_index
            scale_face(bm, face, scale, scale, scale)

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

class Material(IntEnum):
    hull = 0            # Plain spaceship hull
    hull_lights = 1     # Spaceship hull with emissive windows
    hull_dark = 2       # Plain Spaceship hull, darkened
    exhaust_burn = 3    # Emissive engine burn material
    glow_disc = 4       # Emissive landing pad disc material


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

    return ret

# Generates a textured spaceship mesh and returns the object.
# Just uses global cube texture coordinates rather than generating UVs.
# Takes an optional random seed value to generate a specific spaceship.
#
# The default is a symmetric wedge. `classic` selects the original extrusion machinery.
# Archetypes use one primary form, attached secondary forms and sparse surface detail.
#
#   archetype                      wedge, fighter, freighter, saucer, spine, pod, or classic
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
#   assign_materials                build the textured materials; otherwise five empty slots
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
                       taper=0.5):
    if random_seed:
        seed(random_seed)
    max_round_segments = max(3, int(max_round_segments))
    if archetype not in ARCHETYPES:
        raise ValueError("Unknown archetype: " + archetype)

    bm = bmesh.new()
    if archetype == 'classic':
        bmesh.ops.create_cube(bm, size=1)
        scale_vector = Vector(
            (uniform(*hull_scale_x), uniform(*hull_scale_y), uniform(*hull_scale_z)))
        bmesh.ops.scale(bm, vec=scale_vector, verts=bm.verts)
    else:
        _build_archetype(bm, archetype, wing_span, fuselage_roundness)
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
    if create_face_detail and archetype != 'classic' and create_grids:
        length = max(v.co.x for v in bm.verts) - min(v.co.x for v in bm.verts)
        panels = [face for face in bm.faces
                  if len(face.verts) == 4 and face.material_index == Material.hull
                  and face.normal.z > 0.5 and get_aspect_ratio(face) < 3
                  and face.calc_area() < length * length * 0.04 and random() < 0.18]
        for face in panels[:6]:
            add_grid_to_face(bm, face, (length * 0.002, length * 0.004), cuts=1, fractal=0)

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

    # Add materials to the spaceship: the textured ones, or five empty slots that keep each face's material index
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
