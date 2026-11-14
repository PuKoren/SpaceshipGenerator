# Spaceship Generator

A Blender script to procedurally generate 3D spaceships from a random seed.

![Spaceship screenshots](https://raw.githubusercontent.com/a1studmuffin/SpaceshipGenerator/master/screenshots/spaceships_grid.jpg)

What this fork adds
-------------------
This is a fork of [Michael Davies's Spaceship Generator](https://github.com/a1studmuffin/SpaceshipGenerator), under the same MIT licence. It is maintained for Galaxy, a browser space game whose hulls it generates. The screenshot above is the original's.

In the generator itself:

* **Blender 4.2 to 5.x.** The API the original was written against is gone from current Blender; this runs on it as it is, add-on included.
* **Bug fixes.** Equal minimum and maximum segment counts no longer raise; `assign_materials=False` no longer builds and loads the textured materials anyway; a darkened material colour keeps its alpha.
* **Parameters for what was hard-coded** in `generate_spaceship()`: the hull's proportions, the length of a segment, how often an end face tapers, steps, tilts or is ribbed, how often a face grows an outgrowth, each kind of detail on or off, how deep a grid is cut, how thickly antennas stand, how many sides a round part has, how often the ship is mirrored. The comment above the function lists them all.
* **Two new shapes**: a nose that closes to a point (`nose_taper`) and a floor on how slender the hull is (`min_slenderness`).
* **Every ship with detail has an engine.** The original could leave one out: when no stern face was square enough to carry it, or when the only one stood on the half the mirror discarded.
* The movie renderer and other unused code are gone.
* Every default is the value the original held and the random draws come in the same order: a seed draws the ship it drew, unless that ship had no engine.

### What the parameters do

![Six rows of three ships: defaults, a tapered nose, a slender hull, always mirrored, no outgrowths, more outgrowths](docs/images/parameter-sweep.webp)

Three seeds, one a column, and one change a row: the defaults, `nose_taper=0.7`, `min_slenderness=4`, `horizontal_symmetry_chance=1`, `create_asymmetry_segments=False`, `asymmetry_chance=0.45`. The fourth row matches the first because these three seeds were already mirrored. The labels are Galaxy's own names for the parameters and for its ship classes. These are Blender renders of the generator's mesh in Galaxy's flat paint, not in the generator's own materials.

### In Galaxy

The next two pictures are not what this add-on renders. They are the generator's meshes drawn in Galaxy's real-time shader (three.js, WebGL2), and the paint, chips, rust and dirt are that shader's. It reads masks that Galaxy bakes onto the mesh after generation — the distance to each sharp edge, how sheltered each point is, what each face is made of. That code lives in Galaxy, not in this repository. What comes from here is the shape.

![Six generated hulls, twice: in flat paint above, in layered paint with chipped edges and rust below](docs/images/galaxy-before-after.webp)

Six hulls from this fork, in Galaxy. Above, its earlier flat paint; below, its layered paint on the same meshes.

![One hull in six finishes: grey, worn olive, clean white, graphite, two-tone sand, heavily rusted](docs/images/galaxy-six-looks.webp)

One generated hull, six finishes, all from Galaxy's shader: the mesh is the same in each.

Usage
-----
* Install Blender 4.2 or greater: http://blender.org/download/
* Run `python build.py` in this folder to make `add_mesh_SpaceshipGenerator.zip`
* Under Edit > Preferences... > Add-ons > Install... open the downloaded ZIP file
* Under Edit > Preferences... > Add-ons enable the "Add Mesh: Spaceship Generator" script (search for "spaceship")
* Add a spaceship in the 3D View under Add > Mesh > Spaceship
* Expand the Spaceship tab that appears in the bottom left of the viewport to adjust procedural generation settings

How it works
------------

![Step-by-step animation](https://raw.githubusercontent.com/a1studmuffin/SpaceshipGenerator/master/screenshots/step-by-step-animation.gif)

Watch on YouTube: https://www.youtube.com/watch?v=xJZyXqJ6nog

* Start with a box.
* Build the hull: Extrude the front/rear faces several times, adding random translation/scaling/rotation along the way.
* Add asymmetry to the hull: Pick random faces and extrude them out in a similar manner, reducing in scale each time.
* Add detail to the hull: Categorize each face by its orientation and generate details on it such as engines, antenna, weapon turrets, lights etc.
* Sometimes apply horizontal symmetry.
* Add a Bevel modifier to angularize the shape a bit.
* Apply materials to the final result.
* Take over the universe with your new infinite fleet of spaceships.

Extreme examples
----------------
The following screenshots were created using extreme values for the number of hull segments and asymmetry segments to show how the algorithm works.

![Extreme spaceship screenshots](https://raw.githubusercontent.com/a1studmuffin/SpaceshipGenerator/master/screenshots/extreme_examples.jpg)

Tips and Tricks
---------------
* By default the script will delete all objects starting with `Spaceship` before generating a new spaceship. To disable this feature, remove or comment out the call to `reset_scene()` around line 735 in the main function.
* You can provide a seed to the `generate_spaceship()` function to always generate the same spaceship. For example, `generate_spaceship('michael')`.
* The `generate_spaceship()` function takes many more parameters that affect the generation process. Try playing with them!
* You can replace the textures with your own ones. All textures are applied using global-space cube UVs. `hull_normal.png` is a normal map that adds extra surface "greebles". `hull_lights_diffuse.png` is an additive diffuse texture to set the color of the window lights. `hull_lights_emit.png` is an emissive texture to make the windows glow in darkness.

Credits
-------
Written for fun as part of the [/r/proceduralgeneration](https://www.reddit.com/r/proceduralgeneration/) June 2016 [monthly challenge](https://www.reddit.com/r/proceduralgeneration/comments/4mn9gj/monthly_challenge_7_june_2016_procedural/).

Released under the [MIT License].

Authored and maintained by Michael Davies.

> GitHub [@a1studmuffin](https://github.com/a1studmuffin)
> Twitter [@butterparty](https://twitter.com/butterparty)

Special thanks to [@panzi](https://github.com/panzi) for bugfixes, a proper GUI and build script. Also to [@mjrthemes](https://github.com/mjrthemes) for bugfixing, and [@LendoK](https://github.com/LendoK) for the 2.80 port.

[MIT License]: http://mit-license.org/
