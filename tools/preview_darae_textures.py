"""Render the final Darae FBX and its painted maps from the project root."""
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
TEXTURES = ROOT / "Assets/Blender/Textures"
# FBX slot: (Darae texture stem, (Unity tiling X, Y), tangent normal strength).
MATERIALS = {
    "Face":   ("Face",     (1, 1),   0),
    "Eye":    ("EyeAtlas", (1, 1),   0),
    "Skin":   ("Skin",     (1, 1),   0),
    "Top":    ("Cotton",   (3, 3),   .22),
    "Outer":  ("Knit",     (7, 7),   .40),
    "Bottom": ("Linen",    (5, 5),   .24),
    "Apron":  ("Apron",    (2.5, 2.5), .29),
    "Belt":   ("Leather",  (4, 4),   .38),
    "Shoes":  ("Leather",  (3, 3),   .38),
    "Kraft":  ("Kraft",    (1.25, 1.25), .42),
    "Hair":   ("Hair",     (5, .76), .24),
}


def by_type(tree, kind):
    return next(node for node in tree.nodes if node.type == kind)


def assign_maps(mat, stem, tiling, strength):
    tree = mat.node_tree
    bsdf = by_type(tree, "BSDF_PRINCIPLED")
    coord = tree.nodes.new("ShaderNodeTexCoord").outputs["UV"]
    if tiling != (1, 1):
        mapping = tree.nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (*tiling, 1)
        tree.links.new(coord, mapping.inputs["Vector"])
        coord = mapping.outputs["Vector"]

    def image_map(kind):
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(TEXTURES / f"Darae_{stem}_{kind}.png"), check_existing=True)
        node.image.colorspace_settings.name = "Non-Color" if kind == "Normal" else "sRGB"
        node.extension = "REPEAT" if strength else "EXTEND"
        tree.links.new(coord, node.inputs["Vector"])
        return node.outputs["Color"]

    tree.links.new(image_map("Albedo"), bsdf.inputs["Base Color"])
    if strength:
        normal = next((n for n in tree.nodes if n.type == "NORMAL_MAP"), None)
        if normal is None:
            normal = tree.nodes.new("ShaderNodeNormalMap")
        normal.space = "TANGENT"
        normal.inputs["Strength"].default_value = strength
        tree.links.new(image_map("Normal"), normal.inputs["Color"])
        tree.links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    else:
        for link in list(bsdf.inputs["Normal"].links):
            tree.links.remove(link)


def outline_material(mat):
    # Cycles sees both sides of the FBX inverted hull. Ink only its visible front faces.
    tree = mat.node_tree
    surface = by_type(tree, "OUTPUT_MATERIAL").inputs["Surface"]
    ink = surface.links[0].from_socket
    visible = tree.nodes.new("ShaderNodeMath")
    visible.operation = "SUBTRACT"
    visible.use_clamp = True
    tree.links.new(tree.nodes.new("ShaderNodeLightPath").outputs["Is Camera Ray"], visible.inputs[0])
    tree.links.new(tree.nodes.new("ShaderNodeNewGeometry").outputs["Backfacing"], visible.inputs[1])
    mix = tree.nodes.new("ShaderNodeMixShader")
    tree.links.new(visible.outputs[0], mix.inputs[0])
    tree.links.new(tree.nodes.new("ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
    tree.links.new(ink, mix.inputs[2])
    tree.links.new(mix.outputs[0], surface)


def aim(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat("-Z", "Y").to_euler()


def area_light(name, position, target, watts, size, color):
    bpy.ops.object.light_add(type="AREA", location=position)
    light = bpy.context.object
    light.name = name
    light.data.energy = watts
    light.data.shape = "DISK"
    light.data.size = size
    light.data.color = color
    aim(light, target)


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.import_scene.fbx(filepath=str(ROOT / "Assets/Blender/Models/Character_Darae.fbx"))
    meshes = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    assert meshes and all(o.data.uv_layers.active for o in meshes), "Expected UV-mapped Darae mesh"
    rig = next(o for o in bpy.context.selected_objects if o.type == "ARMATURE")
    rig.animation_data.action = next(a for a in bpy.data.actions if a.name.rsplit("|", 1)[-1] == "idle")
    scene = bpy.context.scene
    scene.frame_set(1)

    # The FBX foliage normal carries the exporter's absolute path.
    for im in bpy.data.images:
        if im.filepath and not im.packed_file and not Path(bpy.path.abspath(im.filepath)).is_file():
            replacement = TEXTURES / bpy.path.basename(im.filepath)
            if not replacement.is_file():
                raise FileNotFoundError(im.filepath)
            im.filepath = str(replacement)
            im.reload()

    found = set()
    for mat in {slot.material for obj in meshes for slot in obj.material_slots if slot.material}:
        if not mat.name.startswith("Mat_Character_Darae_"):
            continue
        slot = mat.name.removeprefix("Mat_Character_Darae_").split(".", 1)[0]
        if slot == "Outline":
            outline_material(mat)
        if slot in MATERIALS:
            assign_maps(mat, *MATERIALS[slot])
            found.add(slot)
    assert found == MATERIALS.keys(), f"Missing material slots: {MATERIALS.keys()-found}"
    print("Darae slot -> (texture, UV tiling, normal strength):", MATERIALS, flush=True)

    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.cycles.transparent_max_bounces = 24
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    bg = by_type(scene.world.node_tree, "BACKGROUND")
    bg.inputs["Color"].default_value = (.78, .86, 1, 1)
    bg.inputs["Strength"].default_value = .22
    area_light("Window", (-2.4, -2.5, 3.5), (0, 0, 1.1), 340, 1.7, (1, .93, .87))
    area_light("Fill", (1.8, -1.8, 1.9), (0, 0, 1.15), 55, 2.0, (.84, .92, 1))
    area_light("Rim", (1.1, 1.4, 2.8), (0, 0, 1.13), 105, 1.8, (1, .92, .80))

    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.008))
    floor = bpy.data.materials.new("Studio floor")
    floor_bsdf = by_type(floor.node_tree, "BSDF_PRINCIPLED")
    floor_bsdf.inputs["Base Color"].default_value = (.31, .39, .40, 1)
    floor_bsdf.inputs["Roughness"].default_value = .88
    bpy.context.object.data.materials.append(floor)
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    scene.camera = camera
    logs = ROOT / "Logs"
    logs.mkdir(exist_ok=True)
    for view, target, offset, scale, width, height in (
        ("front", (0, 0, .815), (0, -4, .22), 1.84, 720, 1000),
        ("face", (0, -.04, 1.47), (0, -3, .09), .385, 900, 900),
        ("34", (0, -.02, .815), (2.45, -3.2, .34), 1.84, 720, 1000),
    ):
        camera.location = Vector(target) + Vector(offset)
        aim(camera, target)
        camera.data.ortho_scale = scale
        scene.render.resolution_x, scene.render.resolution_y = width, height
        scene.render.filepath = str(logs / f"darae_v3_tex_{view}.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
