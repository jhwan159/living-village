import bpy
import math
import os

bpy.ops.wm.open_mainfile(filepath=os.path.abspath("Assets/Blender/InzoiVillage.blend"))
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 16
scene.cycles.use_denoising = False
scene.render.resolution_x = 960
scene.render.resolution_y = 540

# World sky lighting
world = bpy.data.worlds.new("InzoiWorld")
scene.world = world
world.use_nodes = True
nt = world.node_tree
bg = nt.nodes.get("Background")
env_tex = nt.nodes.new("ShaderNodeTexEnvironment")
env_tex.image = bpy.data.images.load(os.path.abspath("Assets/Blender/Textures/Sky_Panorama.png"))
nt.links.new(env_tex.outputs["Color"], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 1.2

# Sun light
light_data = bpy.data.lights.new(name="Sun", type="SUN")
light_data.energy = 3.5
light_data.color = (1.0, 0.93, 0.80)
light_data.angle = math.radians(2.5)
light_obj = bpy.data.objects.new(name="Sun", object_data=light_data)
bpy.context.collection.objects.link(light_obj)
light_obj.rotation_euler = (math.radians(52), math.radians(15), math.radians(-35))

# Ground plane with Grass PBR texture
bpy.ops.mesh.primitive_plane_add(size=120.0, location=(0, 0, 0))
ground = bpy.context.active_object
mat_g = bpy.data.materials.new("GroundGrass")
mat_g.use_nodes = True
bsdf_g = mat_g.node_tree.nodes.get("Principled BSDF")
tex_g = mat_g.node_tree.nodes.new("ShaderNodeTexImage")
tex_g.image = bpy.data.images.load(os.path.abspath("Assets/Blender/Textures/Grass_Albedo.png"))
mat_g.node_tree.links.new(tex_g.outputs["Color"], bsdf_g.inputs["Base Color"])
bsdf_g.inputs["Roughness"].default_value = 0.8
ground.data.materials.append(mat_g)

# Import trees & characters & street lamps into the master Blender scene so the full village is in InzoiVillage.blend!
tree_spots = [(-8, -16), (9, -18), (-20, 6), (-12, 16), (22, -12), (22, 6), (-22, -16), (2, 20)]
tree_files = ["Tree_Realistic_Oak.fbx", "Tree_Realistic_Birch.fbx", "Tree_Realistic_Pine.fbx"]
for i, (tx, ty) in enumerate(tree_spots):
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(f"Assets/Blender/Models/{tree_files[i % 3]}"))
    for o in bpy.context.selected_objects:
        o.location = (tx, ty, 0)
        o.rotation_euler = (math.pi * 0.5, 0, i * 1.1)

# Adjust building locations in Blender coordinates (-Y in Blender = +Z in Unity)
if "Building_North_Residence" in bpy.data.objects:
    b = bpy.data.objects["Building_North_Residence"]
    b.location = (0, -12, 0)
    b.rotation_euler = (0, 0, math.pi)
if "Building_FlowerShop_Darae" in bpy.data.objects:
    b = bpy.data.objects["Building_FlowerShop_Darae"]
    b.location = (-15, -4, 0)
    b.rotation_euler = (0, 0, math.pi * 0.5)
if "Building_East_Cafe" in bpy.data.objects:
    b = bpy.data.objects["Building_East_Cafe"]
    b.location = (15, -2, 0)
    b.rotation_euler = (0, 0, -math.pi * 0.5)
if "Building_FisherHut_Hansu" in bpy.data.objects:
    b = bpy.data.objects["Building_FisherHut_Hansu"]
    b.location = (12, 15, 0)
    b.rotation_euler = (0, 0, -math.pi * 0.5)

# Import Darae in front of her Flower Shop (-8.5, -4.0, 0) facing East/South-East toward the plaza
bpy.ops.import_scene.fbx(filepath=os.path.abspath("Assets/Blender/Models/Character_Darae.fbx"))
for o in bpy.context.selected_objects:
    if o.animation_data:
        o.animation_data_clear()
    if o.type == "ARMATURE" or o.parent is None:
        o.location = (-8.5, -4.0, 0.0)
        # Imported FBX armature has X=90deg rotation; rotate Z so +Z local faces camera at (-6.2, -2.8)
        o.rotation_euler = (math.pi * 0.5, 0.0, math.radians(118))

# Fix any relative image paths from FBX import
for img in bpy.data.images:
    if img.filepath:
        bname = os.path.basename(img.filepath)
        cand = os.path.abspath(os.path.join("Assets/Blender/Textures", bname))
        if os.path.exists(cand):
            img.filepath = cand
            img.reload()

# Save updated complete master scene
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath("Assets/Blender/InzoiVillage.blend"))

# 1st-person eye-level camera in Blender looking towards the North Residence & Flower Shop plaza
cam_data = bpy.data.cameras.new("FirstPersonCam")
cam_data.lens = 24  # Wide 1st-person FOV (~73 deg)
cam_obj = bpy.data.objects.new("FirstPersonCam", cam_data)
bpy.context.collection.objects.link(cam_obj)
scene.camera = cam_obj

# Render 1: Plaza & North Modern Residence
cam_obj.location = (2.5, 2.5, 1.56)
cam_obj.rotation_euler = (math.radians(86), 0, math.radians(192))
scene.render.filepath = os.path.abspath("Logs/blender_plaza.png")
bpy.ops.render.render(write_still=True)

# Render 2: Darae's Boutique Flower Shop + Darae
cam_obj.location = (-6.2, -2.8, 1.50)
cam_obj.rotation_euler = (math.radians(88), 0, math.radians(104))
scene.render.filepath = os.path.abspath("Logs/blender_flowershop.png")
bpy.ops.render.render(write_still=True)

# Render 3: Close-up Portrait & Full-Concept View of Darae in front of Flower Shop
scene.cycles.samples = 48
cam_data.lens = 35  # Portrait lens showing full head + upper body + apron + flower basket
cam_obj.location = (-7.05, -3.22, 1.24)
cam_obj.rotation_euler = (math.radians(89), 0, math.radians(118))
scene.render.filepath = os.path.abspath("Logs/blender_darae_portrait.png")
bpy.ops.render.render(write_still=True)
print("Blender preview renders completed.")
