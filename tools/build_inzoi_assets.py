import bpy
import bmesh
import math
import random
import os
import struct
import zlib
from mathutils import Vector, Matrix, Euler

OUT_DIR = os.path.abspath("Assets/Blender")
TEX_DIR = os.path.join(OUT_DIR, "Textures")
MOD_DIR = os.path.join(OUT_DIR, "Models")
os.makedirs(TEX_DIR, exist_ok=True)
os.makedirs(MOD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Fast PNG Writer & Procedural PBR Texture Generator
# ---------------------------------------------------------------------------
def write_png(path, width, height, rgb_bytes):
    """Write raw RGB or RGBA bytes (top-to-bottom) to a PNG file using stdlib zlib."""
    channels = len(rgb_bytes) // (width * height)
    color_type = 6 if channels == 4 else 2
    stride = width * channels
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0
        row_start = y * stride
        raw.extend(rgb_bytes[row_start : row_start + stride])

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 6)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", idat))
        f.write(chunk(b"IEND", b""))


def hash2(x, y, seed=0):
    n = (x * 374761393 + y * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def value_noise(x, y, period=16, seed=0):
    ix = int(math.floor(x))
    iy = int(math.floor(y))
    fx = x - ix
    fy = y - iy
    ux = fx * fx * (3.0 - 2.0 * fx)
    uy = fy * fy * (3.0 - 2.0 * fy)
    x0 = ix % period
    x1 = (ix + 1) % period
    y0 = iy % period
    y1 = (iy + 1) % period
    a = hash2(x0, y0, seed)
    b = hash2(x1, y0, seed)
    c = hash2(x0, y1, seed)
    d = hash2(x1, y1, seed)
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy


def fbm(u, v, base_period=8, octaves=4, seed=0):
    val = 0.0
    amp = 0.5
    freq = base_period
    for i in range(octaves):
        val += amp * value_noise(u * freq, v * freq, int(freq), seed + i * 31)
        freq *= 2
        amp *= 0.5
    return val


def height_to_normal_png(path, heights, w, h, strength=3.0):
    buf = bytearray(w * h * 3)
    idx = 0
    for y in range(h):
        ym = (y - 1) % h
        yp = (y + 1) % h
        row_y = y * w
        row_ym = ym * w
        row_yp = yp * w
        for x in range(w):
            xm = (x - 1) % w
            xp = (x + 1) % w
            dx = (heights[row_y + xp] - heights[row_y + xm]) * strength
            dy = (heights[row_yp + x] - heights[row_ym + x]) * strength
            dz = 1.0
            inv = 1.0 / math.sqrt(dx * dx + dy * dy + dz * dz)
            nx = int(max(0, min(255, (-dx * inv * 0.5 + 0.5) * 255.0)))
            ny = int(max(0, min(255, (-dy * inv * 0.5 + 0.5) * 255.0)))
            nz = int(max(0, min(255, (dz * inv * 0.5 + 0.5) * 255.0)))
            buf[idx] = nx
            buf[idx + 1] = ny
            buf[idx + 2] = nz
            idx += 3
    write_png(path, w, h, buf)


def generate_textures():
    print("Generating high-res procedural PBR textures...")
    W, H = 256, 256

    # 1. Cobblestone / Modern Street Pavers
    albedo = bytearray(W * H * 3)
    heights = [0.0] * (W * H)
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            row = int(v * 8)
            col_offset = 0.5 if (row % 2 == 1) else 0.0
            bu = (u * 8 + col_offset) % 1.0
            bv = (v * 8) % 1.0
            col = int(u * 8 + col_offset)
            brick_seed = hash2(col, row, 101)
            # Mortar groove
            edge_u = min(bu, 1.0 - bu)
            edge_v = min(bv, 1.0 - bv)
            edge = min(edge_u, edge_v)
            mortar = smoothstep(0.03, 0.09, edge)
            n = fbm(u, v, 16, 3, 11)
            h_val = mortar * (0.75 + 0.25 * n)
            heights[y * W + x] = h_val
            # Warm-cool granite paver tones
            tone = 0.52 + (brick_seed - 0.5) * 0.14 + (n - 0.5) * 0.10
            r = (tone * 1.02) * mortar + 0.28 * (1.0 - mortar)
            g = (tone * 1.00) * mortar + 0.27 * (1.0 - mortar)
            b = (tone * 0.97) * mortar + 0.26 * (1.0 - mortar)
            i = (y * W + x) * 3
            albedo[i] = clamp8(r)
            albedo[i + 1] = clamp8(g)
            albedo[i + 2] = clamp8(b)
    write_png(os.path.join(TEX_DIR, "Cobble_Albedo.png"), W, H, albedo)
    height_to_normal_png(os.path.join(TEX_DIR, "Cobble_Normal.png"), heights, W, H, 4.5)

    # 2. Lush Meadow Grass
    albedo = bytearray(W * H * 3)
    heights = [0.0] * (W * H)
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            n1 = fbm(u, v, 8, 4, 21)
            n2 = fbm(u, v, 32, 2, 77)
            heights[y * W + x] = n2 * 0.6 + n1 * 0.4
            # Natural realistic grass palette (warm sunlit olive-emerald, not neon plastic)
            r = 0.28 + n1 * 0.12 + (n2 - 0.5) * 0.06
            g = 0.44 + n1 * 0.16 + (n2 - 0.5) * 0.08
            b = 0.21 + n1 * 0.08 + (n2 - 0.5) * 0.04
            i = (y * W + x) * 3
            albedo[i] = clamp8(r)
            albedo[i + 1] = clamp8(g)
            albedo[i + 2] = clamp8(b)
    write_png(os.path.join(TEX_DIR, "Grass_Albedo.png"), W, H, albedo)
    height_to_normal_png(os.path.join(TEX_DIR, "Grass_Normal.png"), heights, W, H, 3.0)

    # 3. Architectural Stucco / Warm Plaster
    albedo = bytearray(W * H * 3)
    heights = [0.0] * (W * H)
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            n = fbm(u, v, 16, 4, 33)
            heights[y * W + x] = n
            r = 0.90 + (n - 0.5) * 0.07
            g = 0.87 + (n - 0.5) * 0.07
            b = 0.82 + (n - 0.5) * 0.07
            i = (y * W + x) * 3
            albedo[i] = clamp8(r)
            albedo[i + 1] = clamp8(g)
            albedo[i + 2] = clamp8(b)
    write_png(os.path.join(TEX_DIR, "Stucco_Albedo.png"), W, H, albedo)
    height_to_normal_png(os.path.join(TEX_DIR, "Stucco_Normal.png"), heights, W, H, 2.2)

    # 4. Architectural Brick
    albedo = bytearray(W * H * 3)
    heights = [0.0] * (W * H)
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            row = int(v * 12)
            col_offset = 0.5 if (row % 2 == 1) else 0.0
            bu = (u * 6 + col_offset) % 1.0
            bv = (v * 12) % 1.0
            col = int(u * 6 + col_offset)
            bseed = hash2(col, row, 202)
            mortar = smoothstep(0.03, 0.08, min(min(bu, 1.0 - bu), min(bv, 1.0 - bv)))
            n = fbm(u, v, 16, 3, 44)
            heights[y * W + x] = mortar * (0.8 + 0.2 * n)
            br = 0.64 + (bseed - 0.5) * 0.14 + (n - 0.5) * 0.08
            bg = 0.35 + (bseed - 0.5) * 0.10 + (n - 0.5) * 0.06
            bb = 0.27 + (bseed - 0.5) * 0.08 + (n - 0.5) * 0.05
            r = br * mortar + 0.72 * (1.0 - mortar)
            g = bg * mortar + 0.70 * (1.0 - mortar)
            b = bb * mortar + 0.66 * (1.0 - mortar)
            i = (y * W + x) * 3
            albedo[i] = clamp8(r)
            albedo[i + 1] = clamp8(g)
            albedo[i + 2] = clamp8(b)
    write_png(os.path.join(TEX_DIR, "Brick_Albedo.png"), W, H, albedo)
    height_to_normal_png(os.path.join(TEX_DIR, "Brick_Normal.png"), heights, W, H, 4.0)

    # 5. Architectural Cedar / Timber Planks
    albedo = bytearray(W * H * 3)
    heights = [0.0] * (W * H)
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            plank = int(v * 8)
            pv = (v * 8) % 1.0
            seam = smoothstep(0.02, 0.06, min(pv, 1.0 - pv))
            grain = fbm(u * 0.5, v * 4.0, 8, 3, 55 + plank)
            pseed = hash2(plank, 3, 55)
            heights[y * W + x] = seam * (0.7 + 0.3 * grain)
            r = (0.58 + (pseed - 0.5) * 0.10 + (grain - 0.5) * 0.12) * seam + 0.20 * (1.0 - seam)
            g = (0.40 + (pseed - 0.5) * 0.08 + (grain - 0.5) * 0.09) * seam + 0.14 * (1.0 - seam)
            b = (0.26 + (pseed - 0.5) * 0.06 + (grain - 0.5) * 0.06) * seam + 0.10 * (1.0 - seam)
            i = (y * W + x) * 3
            albedo[i] = clamp8(r)
            albedo[i + 1] = clamp8(g)
            albedo[i + 2] = clamp8(b)
    write_png(os.path.join(TEX_DIR, "Wood_Albedo.png"), W, H, albedo)
    height_to_normal_png(os.path.join(TEX_DIR, "Wood_Normal.png"), heights, W, H, 3.5)

    # 6. Architectural Roof Tiles
    albedo = bytearray(W * H * 3)
    heights = [0.0] * (W * H)
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            tu = (u * 10) % 1.0
            tv = (v * 10) % 1.0
            wave = 0.5 + 0.5 * math.cos(tu * math.pi * 2.0)
            step = smoothstep(0.0, 0.15, tv)
            n = fbm(u, v, 16, 2, 66)
            h_val = (wave * 0.6 + step * 0.4) * 0.85 + n * 0.15
            heights[y * W + x] = h_val
            base = 0.22 + h_val * 0.12
            i = (y * W + x) * 3
            albedo[i] = clamp8(base * 0.96)
            albedo[i + 1] = clamp8(base * 1.00)
            albedo[i + 2] = clamp8(base * 1.06)
    write_png(os.path.join(TEX_DIR, "Roof_Albedo.png"), W, H, albedo)
    height_to_normal_png(os.path.join(TEX_DIR, "Roof_Normal.png"), heights, W, H, 5.0)

    # 7. Coastal Water Normal Map
    heights = [0.0] * (W * H)
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            w1 = math.sin((u * 6.0 + v * 2.0) * math.pi * 2.0) * 0.35
            w2 = math.cos((u * 3.0 - v * 5.0) * math.pi * 2.0) * 0.30
            w3 = fbm(u, v, 12, 3, 88) * 0.35
            heights[y * W + x] = 0.5 + 0.5 * (w1 + w2 + w3)
    height_to_normal_png(os.path.join(TEX_DIR, "Water_Normal.png"), heights, W, H, 3.2)

    # 8. Panoramic Sky Texture (1024x512 Equirectangular Golden-Afternoon Coastal Sky)
    SW, SH = 1024, 512
    sky = bytearray(SW * SH * 3)
    # Sun direction matching Unity directional light Euler(32, -35, 0)
    sun_az = math.radians(-35.0)
    sun_el = math.radians(32.0)
    sun_vec = (
        math.cos(sun_el) * math.sin(sun_az),
        math.sin(sun_el),
        math.cos(sun_el) * math.cos(sun_az),
    )
    for y in range(SH):
        # y=0 is top (zenith), y=SH-1 is bottom (nadir)
        theta = (0.5 - y / SH) * math.pi  # +pi/2 at top, -pi/2 at bottom
        sin_t = math.sin(theta)
        cos_t = math.cos(theta)
        for x in range(SW):
            phi = (x / SW - 0.5) * 2.0 * math.pi
            dx = cos_t * math.sin(phi)
            dy = sin_t
            dz = cos_t * math.cos(phi)
            sun_dot = max(0.0, dx * sun_vec[0] + dy * sun_vec[1] + dz * sun_vec[2])

            if dy >= 0.0:
                # Sky hemisphere
                t = math.pow(dy, 0.55)
                # Horizon warm peach-gold -> Mid sky soft azure -> Zenith rich cerulean
                hr, hg, hb = 0.96, 0.86, 0.76
                mr, mg, mb = 0.46, 0.68, 0.90
                zr, zg, zb = 0.18, 0.38, 0.68
                if t < 0.45:
                    k = t / 0.45
                    r = hr + (mr - hr) * k
                    g = hg + (mg - hg) * k
                    b = hb + (mb - hb) * k
                else:
                    k = (t - 0.45) / 0.55
                    r = mr + (zr - mr) * k
                    g = mg + (zg - mg) * k
                    b = mb + (zb - mb) * k

                # Soft cumulus clouds in mid-low sky
                if 0.04 < dy < 0.65:
                    cu = (x / SW) * 2.0
                    cv = dy * 2.5
                    cn = fbm(cu, cv, 6, 4, 99)
                    cloud_mask = smoothstep(0.52, 0.72, cn) * smoothstep(0.04, 0.15, dy) * smoothstep(0.65, 0.30, dy)
                    cr = 0.99
                    cg = 0.96
                    cb = 0.92
                    r = r * (1.0 - cloud_mask * 0.75) + cr * (cloud_mask * 0.75)
                    g = g * (1.0 - cloud_mask * 0.75) + cg * (cloud_mask * 0.75)
                    b = b * (1.0 - cloud_mask * 0.75) + cb * (cloud_mask * 0.75)

                # Sun glow & disc
                glow = math.pow(sun_dot, 8.0) * 0.35 + math.pow(sun_dot, 64.0) * 0.55
                r += glow * 1.0
                g += glow * 0.85
                b += glow * 0.55
            else:
                # Ground hemisphere (warm coastal reflection for ambient GI & reflection probes)
                gt = min(1.0, -dy * 3.0)
                r = 0.78 * (1.0 - gt) + 0.34 * gt
                g = 0.76 * (1.0 - gt) + 0.38 * gt
                b = 0.72 * (1.0 - gt) + 0.32 * gt

            i = (y * SW + x) * 3
            sky[i] = clamp8(r)
            sky[i + 1] = clamp8(g)
            sky[i + 2] = clamp8(b)
    write_png(os.path.join(TEX_DIR, "Sky_Panorama.png"), SW, SH, sky)
    print("Textures generated successfully.")


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def clamp8(v):
    return int(max(0, min(255, v * 255.0)))


# ---------------------------------------------------------------------------
# Blender Material & Geometry Helpers
# ---------------------------------------------------------------------------
MATS = {}


def get_mat(name, color, roughness=0.5, metallic=0.0, emission=None, albedo_tex=None, normal_tex=None):
    if name in MATS:
        return MATS[name]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if albedo_tex:
            tex_path = os.path.join(TEX_DIR, albedo_tex)
            if os.path.exists(tex_path):
                tnode = nt.nodes.new("ShaderNodeTexImage")
                tnode.image = bpy.data.images.load(tex_path)
                mix = nt.nodes.new("ShaderNodeMix")
                mix.data_type = "RGBA"
                mix.blend_type = "MULTIPLY"
                mix.inputs["Factor"].default_value = 1.0
                mix.inputs[6].default_value = (*color, 1.0)
                nt.links.new(tnode.outputs["Color"], mix.inputs[7])
                nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        if normal_tex:
            n_path = os.path.join(TEX_DIR, normal_tex)
            if os.path.exists(n_path):
                nnode = nt.nodes.new("ShaderNodeTexImage")
                nnode.image = bpy.data.images.load(n_path)
                nnode.image.colorspace_settings.name = "Non-Color"
                nmap = nt.nodes.new("ShaderNodeNormalMap")
                nmap.inputs["Strength"].default_value = 1.0
                nt.links.new(nnode.outputs["Color"], nmap.inputs["Color"])
                nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
        if emission and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 3.5
    mat.diffuse_color = (*color, 1.0)
    MATS[name] = mat
    return mat


def init_materials():
    MATS.clear()
    get_mat("Mat_Stucco", (0.95, 0.92, 0.87), roughness=0.72, albedo_tex="Stucco_Albedo.png", normal_tex="Stucco_Normal.png")
    get_mat("Mat_StuccoSage", (0.76, 0.84, 0.75), roughness=0.68, albedo_tex="Stucco_Albedo.png", normal_tex="Stucco_Normal.png")
    get_mat("Mat_StuccoWarm", (0.97, 0.90, 0.81), roughness=0.70, albedo_tex="Stucco_Albedo.png", normal_tex="Stucco_Normal.png")
    get_mat("Mat_Brick", (0.92, 0.86, 0.82), roughness=0.75, albedo_tex="Brick_Albedo.png", normal_tex="Brick_Normal.png")
    get_mat("Mat_Wood", (0.92, 0.86, 0.80), roughness=0.52, albedo_tex="Wood_Albedo.png", normal_tex="Wood_Normal.png")
    get_mat("Mat_DarkWood", (0.55, 0.42, 0.30), roughness=0.55, albedo_tex="Wood_Albedo.png", normal_tex="Wood_Normal.png")
    get_mat("Mat_Concrete", (0.76, 0.75, 0.73), roughness=0.68, albedo_tex="Stucco_Albedo.png", normal_tex="Stucco_Normal.png")
    get_mat("Mat_Cobble", (0.88, 0.87, 0.85), roughness=0.60, albedo_tex="Cobble_Albedo.png", normal_tex="Cobble_Normal.png")
    get_mat("Mat_RoofSlate", (0.80, 0.82, 0.86), roughness=0.48, albedo_tex="Roof_Albedo.png", normal_tex="Roof_Normal.png")
    get_mat("Mat_RoofTerracotta", (0.86, 0.44, 0.30), roughness=0.52, normal_tex="Roof_Normal.png")
    get_mat("Mat_DarkMetal", (0.16, 0.18, 0.20), roughness=0.25, metallic=0.85)
    get_mat("Mat_Brass", (0.90, 0.72, 0.34), roughness=0.20, metallic=0.90)
    get_mat("Mat_Glass", (0.14, 0.22, 0.30), roughness=0.04, metallic=0.35, emission=(0.06, 0.09, 0.12))
    get_mat("Mat_WarmGlow", (1.0, 0.90, 0.68), roughness=0.15, emission=(1.0, 0.86, 0.58))
    get_mat("Mat_AwningStripe", (0.86, 0.34, 0.26), roughness=0.62)
    get_mat("Mat_Foliage", (0.28, 0.50, 0.23), roughness=0.62, normal_tex="Grass_Normal.png")
    get_mat("Mat_FoliageLight", (0.36, 0.58, 0.26), roughness=0.60, normal_tex="Grass_Normal.png")
    get_mat("Mat_PineNeedles", (0.20, 0.40, 0.22), roughness=0.65, normal_tex="Grass_Normal.png")
    get_mat("Mat_Bark", (0.42, 0.31, 0.22), roughness=0.82, normal_tex="Wood_Normal.png")
    get_mat("Mat_BirchBark", (0.86, 0.83, 0.78), roughness=0.72, normal_tex="Wood_Normal.png")
    get_mat("Mat_FlowerRed", (0.90, 0.22, 0.26), roughness=0.45)
    get_mat("Mat_FlowerYellow", (0.96, 0.78, 0.18), roughness=0.45)
    get_mat("Mat_FlowerPurple", (0.65, 0.36, 0.82), roughness=0.45)
    get_mat("Mat_TerracottaPot", (0.76, 0.42, 0.28), roughness=0.62)
    get_mat("Mat_Water", (0.14, 0.44, 0.58), roughness=0.06, metallic=0.15, normal_tex="Water_Normal.png")
    get_mat("Mat_ShellPearl", (0.96, 0.86, 0.82), roughness=0.22, metallic=0.12)
    get_mat("Mat_MushroomCap", (0.82, 0.26, 0.20), roughness=0.48)
    get_mat("Mat_MushroomStem", (0.92, 0.88, 0.78), roughness=0.62)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def add_box(bm, mat_idx, center, size, rot_euler=(0, 0, 0), bevel=0.0):
    ret = bmesh.ops.create_cube(bm, size=1.0)
    verts = ret["verts"]
    bmesh.ops.scale(bm, vec=size, verts=verts)
    if any(rot_euler):
        rmat = Euler(rot_euler, "XYZ").to_matrix().to_4x4()
        bmesh.ops.rotate(bm, matrix=rmat, verts=verts)
    bmesh.ops.translate(bm, vec=center, verts=verts)
    for f in bm.faces:
        if all(v in verts for v in f.verts):
            f.material_index = mat_idx
    return verts


def add_cylinder(bm, mat_idx, center, radius_bottom, radius_top, height, segments=16, rot_euler=(0, 0, 0)):
    ret = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius_bottom,
        radius2=radius_top,
        depth=height,
    )
    verts = ret["verts"]
    if any(rot_euler):
        rmat = Euler(rot_euler, "XYZ").to_matrix().to_4x4()
        bmesh.ops.rotate(bm, matrix=rmat, verts=verts)
    bmesh.ops.translate(bm, vec=center, verts=verts)
    for f in bm.faces:
        if all(v in verts for v in f.verts):
            f.material_index = mat_idx
            f.smooth = True
    return verts


def add_sphere(bm, mat_idx, center, radius_vec, segments=16, rings=12, rot_euler=(0, 0, 0)):
    ret = bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1.0)
    verts = ret["verts"]
    bmesh.ops.scale(bm, vec=radius_vec, verts=verts)
    if any(rot_euler):
        rmat = Euler(rot_euler, "XYZ").to_matrix().to_4x4()
        bmesh.ops.rotate(bm, matrix=rmat, verts=verts)
    bmesh.ops.translate(bm, vec=center, verts=verts)
    for f in bm.faces:
        if all(v in verts for v in f.verts):
            f.material_index = mat_idx
            f.smooth = True
    return verts


def finalize_mesh(name, bm, mat_names, auto_uv=True):
    mesh = bpy.data.meshes.new(name)
    for mname in mat_names:
        mesh.materials.append(MATS[mname])
    bm.normal_update()
    # Cubic box projection UVs in bmesh so textures tile cleanly in world meters
    uv_layer = bm.loops.layers.uv.verify()
    if auto_uv:
        for f in bm.faces:
            n = f.normal
            ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
            for loop in f.loops:
                co = loop.vert.co
                if az >= ax and az >= ay:
                    u, v = co.x * 0.5, co.y * 0.5
                elif ax >= ay:
                    u, v = co.y * 0.5, co.z * 0.5
                else:
                    u, v = co.x * 0.5, co.z * 0.5
                loop[uv_layer].uv = (u, v)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_framed_window(bm, m_frame, m_glass, m_glow, cx, cy, cz, w, h, facing="Y-", sill_m=None):
    """Add an architectural window with 4 outer frame bars, mullions, reflective glass, and interior warm glow."""
    ft = 0.08  # Frame bar thickness
    if facing == "Y-":
        # Warm interior glow backing + reflective glass pane in front of wall face cy
        add_box(bm, m_glow, (cx, cy - 0.02, cz), (w - 0.06, 0.02, h - 0.06))
        add_box(bm, m_glass, (cx, cy - 0.045, cz), (w - 0.02, 0.02, h - 0.02))
        # 4 Outer frame bars (Top, Bottom, Left, Right) protruding to cy - 0.10
        add_box(bm, m_frame, (cx, cy - 0.06, cz + h * 0.5 + ft * 0.4), (w + ft * 2, 0.10, ft))
        add_box(bm, m_frame, (cx, cy - 0.06, cz - h * 0.5 - ft * 0.4), (w + ft * 2, 0.10, ft))
        add_box(bm, m_frame, (cx - w * 0.5 - ft * 0.4, cy - 0.06, cz), (ft, 0.10, h + ft * 2))
        add_box(bm, m_frame, (cx + w * 0.5 + ft * 0.4, cy - 0.06, cz), (ft, 0.10, h + ft * 2))
        # Inner cross mullions in front of glass
        add_box(bm, m_frame, (cx, cy - 0.065, cz), (0.045, 0.06, h))
        add_box(bm, m_frame, (cx, cy - 0.065, cz + h * 0.14), (w, 0.06, 0.045))
        if sill_m is not None:
            add_box(bm, sill_m, (cx, cy - 0.12, cz - h * 0.5 - 0.07), (w + 0.30, 0.24, 0.09))
    elif facing == "Y+":
        add_box(bm, m_glow, (cx, cy + 0.02, cz), (w - 0.06, 0.02, h - 0.06))
        add_box(bm, m_glass, (cx, cy + 0.045, cz), (w - 0.02, 0.02, h - 0.02))
        add_box(bm, m_frame, (cx, cy + 0.06, cz + h * 0.5 + ft * 0.4), (w + ft * 2, 0.10, ft))
        add_box(bm, m_frame, (cx, cy + 0.06, cz - h * 0.5 - ft * 0.4), (w + ft * 2, 0.10, ft))
        add_box(bm, m_frame, (cx - w * 0.5 - ft * 0.4, cy + 0.06, cz), (ft, 0.10, h + ft * 2))
        add_box(bm, m_frame, (cx + w * 0.5 + ft * 0.4, cy + 0.06, cz), (ft, 0.10, h + ft * 2))
        add_box(bm, m_frame, (cx, cy + 0.065, cz), (0.045, 0.06, h))
        if sill_m is not None:
            add_box(bm, sill_m, (cx, cy + 0.12, cz - h * 0.5 - 0.07), (w + 0.30, 0.24, 0.09))
    elif facing == "X-":
        add_box(bm, m_glow, (cx - 0.02, cy, cz), (0.02, w - 0.06, h - 0.06))
        add_box(bm, m_glass, (cx - 0.045, cy, cz), (0.02, w - 0.02, h - 0.02))
        add_box(bm, m_frame, (cx - 0.06, cy, cz + h * 0.5 + ft * 0.4), (0.10, w + ft * 2, ft))
        add_box(bm, m_frame, (cx - 0.06, cy, cz - h * 0.5 - ft * 0.4), (0.10, w + ft * 2, ft))
        add_box(bm, m_frame, (cx - 0.06, cy - w * 0.5 - ft * 0.4, cz), (0.10, ft, h + ft * 2))
        add_box(bm, m_frame, (cx - 0.06, cy + w * 0.5 + ft * 0.4, cz), (0.10, ft, h + ft * 2))
        add_box(bm, m_frame, (cx - 0.065, cy, cz), (0.06, 0.045, h))
    elif facing == "X+":
        add_box(bm, m_glow, (cx + 0.02, cy, cz), (0.02, w - 0.06, h - 0.06))
        add_box(bm, m_glass, (cx + 0.045, cy, cz), (0.02, w - 0.02, h - 0.02))
        add_box(bm, m_frame, (cx + 0.06, cy, cz + h * 0.5 + ft * 0.4), (0.10, w + ft * 2, ft))
        add_box(bm, m_frame, (cx + 0.06, cy, cz - h * 0.5 - ft * 0.4), (0.10, w + ft * 2, ft))
        add_box(bm, m_frame, (cx + 0.06, cy - w * 0.5 - ft * 0.4, cz), (0.10, ft, h + ft * 2))
        add_box(bm, m_frame, (cx + 0.06, cy + w * 0.5 + ft * 0.4, cz), (0.10, ft, h + ft * 2))
        add_box(bm, m_frame, (cx + 0.065, cy, cz), (0.06, 0.045, h))


def add_door(bm, m_frame, m_wood, m_brass, m_glass, cx, cy, cz_bottom, w=1.2, h=2.3, facing="Y-"):
    cz = cz_bottom + h * 0.5
    ft = 0.09
    if facing == "Y-":
        # Wooden door slab in front of wall face cy
        add_box(bm, m_wood, (cx, cy - 0.04, cz), (w, 0.07, h))
        # Outer door frame architrave (left, right, top)
        add_box(bm, m_frame, (cx - w * 0.5 - ft * 0.4, cy - 0.06, cz), (ft, 0.12, h + ft))
        add_box(bm, m_frame, (cx + w * 0.5 + ft * 0.4, cy - 0.06, cz), (ft, 0.12, h + ft))
        add_box(bm, m_frame, (cx, cy - 0.06, cz + h * 0.5 + ft * 0.4), (w + ft * 2, 0.12, ft))
        # Upper glass transom in door
        add_box(bm, m_glass, (cx, cy - 0.08, cz + h * 0.20), (w * 0.62, 0.02, h * 0.30))
        add_box(bm, m_frame, (cx, cy - 0.085, cz + h * 0.20), (0.03, 0.03, h * 0.30))
        # Brass handle
        add_box(bm, m_brass, (cx + w * 0.36, cy - 0.10, cz - 0.05), (0.04, 0.08, 0.24))


# ---------------------------------------------------------------------------
# 1. Architectural Buildings (inZOI Korean Modern Town & Coastal Aesthetic)
# ---------------------------------------------------------------------------
def build_north_residence():
    """Modern 2-story Korean architectural townhouse (House_North)."""
    bm = bmesh.new()
    mats = [
        "Mat_Stucco",       # 0
        "Mat_Wood",         # 1
        "Mat_DarkMetal",    # 2
        "Mat_Glass",        # 3
        "Mat_WarmGlow",     # 4
        "Mat_Concrete",     # 5
        "Mat_RoofSlate",    # 6
        "Mat_Brass",        # 7
        "Mat_Foliage",      # 8
        "Mat_Brick",        # 9
    ]
    # Foundation plinth (9.0m x 6.4m)
    add_box(bm, 5, (0, 0, 0.18), (9.0, 6.4, 0.36))
    # Front step
    add_box(bm, 5, (0, -3.45, 0.10), (2.6, 0.6, 0.20))

    # Ground floor main volume
    add_box(bm, 0, (0, 0, 1.95), (8.6, 6.0, 3.2))
    # Brick accent wing on left ground floor
    add_box(bm, 9, (-2.6, -0.1, 1.95), (3.5, 6.15, 3.2))

    # Recessed timber-lined entrance porch
    add_box(bm, 1, (0, -2.95, 3.35), (2.8, 0.8, 0.18))
    add_box(bm, 4, (0, -3.10, 3.24), (0.6, 0.25, 0.04))  # Porch downlight
    add_door(bm, 2, 1, 7, 3, 0.0, -3.0, 0.36, w=1.3, h=2.4, facing="Y-")

    # Ground floor large windows
    add_framed_window(bm, 2, 3, 4, -2.6, -3.18, 2.0, 2.1, 1.6, "Y-", sill_m=5)
    add_framed_window(bm, 2, 3, 4, 2.6, -3.01, 2.0, 2.1, 1.6, "Y-", sill_m=5)
    add_framed_window(bm, 2, 3, 4, -4.36, 0.0, 2.0, 2.0, 1.5, "X-", sill_m=5)
    add_framed_window(bm, 2, 3, 4, 4.31, 0.0, 2.0, 2.0, 1.5, "X+", sill_m=5)

    # Inter-floor concrete slab belt
    add_box(bm, 5, (0, -0.15, 3.62), (9.0, 6.5, 0.22))

    # Second floor cantilevered volume + balcony
    add_box(bm, 0, (0.8, 0.2, 5.15), (7.0, 5.4, 2.85))
    # Cedar louver screen on upper left
    for i in range(9):
        lx = -3.8 + i * 0.22
        add_box(bm, 1, (lx, -2.55, 5.15), (0.08, 0.18, 2.75))
    # Glass balcony balustrade on second floor front
    add_box(bm, 3, (-2.8, -3.25, 4.20), (2.8, 0.05, 0.95))
    add_box(bm, 2, (-2.8, -3.25, 4.70), (2.85, 0.09, 0.06))
    # Second floor panoramic windows
    add_framed_window(bm, 2, 3, 4, 0.6, -2.52, 5.15, 2.2, 1.65, "Y-", sill_m=5)
    add_framed_window(bm, 2, 3, 4, 3.0, -2.52, 5.15, 1.6, 1.65, "Y-", sill_m=5)

    # Modern overhanging roof with dark metal fascia & soffit warm lights
    add_box(bm, 6, (0.2, 0.0, 6.70), (9.1, 6.6, 0.28))
    add_box(bm, 2, (0.2, 0.0, 6.76), (9.18, 6.68, 0.14))
    for lx in (-3.0, 0.0, 3.0):
        add_box(bm, 4, (lx, -3.05, 6.55), (0.35, 0.20, 0.04))

    # Front architectural planter boxes with lush bushes
    for px in (-2.6, 2.6):
        add_box(bm, 5, (px, -3.45, 0.35), (2.2, 0.65, 0.55))
        for bx in (-0.65, 0.0, 0.65):
            add_sphere(bm, 8, (px + bx, -3.45, 0.78), (0.45, 0.38, 0.38), 12, 8)

    obj = finalize_mesh("Building_North_Residence", bm, mats)
    return obj


def build_flower_shop():
    """Darae's Boutique Flower Shop & Greenhouse Atelier (FlowerShop)."""
    bm = bmesh.new()
    mats = [
        "Mat_StuccoWarm",     # 0
        "Mat_StuccoSage",     # 1
        "Mat_Wood",           # 2
        "Mat_DarkMetal",      # 3
        "Mat_Glass",          # 4
        "Mat_WarmGlow",       # 5
        "Mat_RoofTerracotta", # 6
        "Mat_AwningStripe",   # 7
        "Mat_Foliage",        # 8
        "Mat_FlowerRed",      # 9
        "Mat_FlowerYellow",   # 10
        "Mat_FlowerPurple",   # 11
        "Mat_TerracottaPot",  # 12
        "Mat_Concrete",       # 13
        "Mat_Brass",          # 14
    ]
    # Stone plinth (9.0m x 6.4m)
    add_box(bm, 13, (0, 0, 0.16), (9.0, 6.4, 0.32))
    # Main shop body (warm cream stucco + sage green wainscoting)
    add_box(bm, 0, (0, 0.2, 2.25), (8.6, 5.6, 3.85))
    add_box(bm, 1, (0, 0.2, 0.85), (8.7, 5.7, 1.05))  # Sage green lower trim

    # Front entrance door (center) & large boutique display windows
    add_door(bm, 1, 2, 14, 4, 0.0, -2.66, 0.32, w=1.35, h=2.45, facing="Y-")
    add_framed_window(bm, 1, 4, 5, -2.55, -2.66, 1.95, 2.4, 1.85, "Y-", sill_m=2)
    add_framed_window(bm, 1, 4, 5, 2.55, -2.66, 1.95, 2.4, 1.85, "Y-", sill_m=2)
    add_framed_window(bm, 1, 4, 5, -4.36, 0.2, 1.95, 2.2, 1.7, "X-", sill_m=2)
    add_framed_window(bm, 1, 4, 5, 4.36, 0.2, 1.95, 2.2, 1.7, "X+", sill_m=2)

    # Sloped café awning over front storefront
    add_box(bm, 7, (-2.55, -3.15, 3.15), (2.7, 1.15, 0.12), rot_euler=(math.radians(22), 0, 0))
    add_box(bm, 7, (2.55, -3.15, 3.15), (2.7, 1.15, 0.12), rot_euler=(math.radians(22), 0, 0))
    # Wooden sign board above door
    add_box(bm, 2, (0, -2.78, 3.42), (2.4, 0.16, 0.55))
    add_box(bm, 5, (0, -2.85, 3.42), (2.1, 0.06, 0.38))

    # Pitched terracotta roof (front slope + back slope meeting at ridge z=5.05) + central gable dormer
    add_box(bm, 6, (0, -1.25, 4.60), (9.1, 3.4, 0.24), rot_euler=(math.radians(22), 0, 0))
    add_box(bm, 6, (0, 1.65, 4.60), (9.1, 3.4, 0.24), rot_euler=(math.radians(-22), 0, 0))
    add_box(bm, 6, (0, 0.20, 5.22), (9.2, 0.45, 0.22))  # Ridge cap
    add_box(bm, 0, (0, 0.20, 4.45), (8.5, 3.2, 1.15))
    add_framed_window(bm, 2, 4, 5, 0, -1.42, 4.55, 1.4, 0.90, "Y-", sill_m=2)

    # Outdoor 2-tier wooden flower stands with vibrant flower pots in front of shop
    for side_x in (-2.55, 2.55):
        # 2-tier wooden rack
        add_box(bm, 2, (side_x, -3.25, 0.42), (2.2, 0.70, 0.10))
        add_box(bm, 2, (side_x, -3.05, 0.78), (2.2, 0.42, 0.10))
        add_box(bm, 2, (side_x - 1.0, -3.15, 0.45), (0.10, 0.65, 0.75))
        add_box(bm, 2, (side_x + 1.0, -3.15, 0.45), (0.10, 0.65, 0.75))
        # Flower pots on tiers
        for i, ox in enumerate((-0.75, -0.25, 0.25, 0.75)):
            px = side_x + ox
            # Lower row
            add_cylinder(bm, 12, (px, -3.38, 0.58), 0.11, 0.15, 0.24, 10)
            add_sphere(bm, 8, (px, -3.38, 0.74), (0.19, 0.19, 0.15), 10, 8)
            fmat = 9 + ((i + (0 if side_x < 0 else 1)) % 3)
            add_sphere(bm, fmat, (px, -3.38, 0.85), (0.15, 0.15, 0.13), 10, 8)
            # Upper row
            add_cylinder(bm, 12, (px, -3.05, 0.94), 0.11, 0.15, 0.24, 10)
            add_sphere(bm, 8, (px, -3.05, 1.10), (0.19, 0.19, 0.15), 10, 8)
            fmat2 = 9 + ((i + 2) % 3)
            add_sphere(bm, fmat2, (px, -3.05, 1.21), (0.15, 0.15, 0.13), 10, 8)

    obj = finalize_mesh("Building_FlowerShop_Darae", bm, mats)
    return obj


def build_east_cafe():
    """East Corner Brick & Timber Atelier / Bakery (House_East)."""
    bm = bmesh.new()
    mats = [
        "Mat_Brick",        # 0
        "Mat_Stucco",       # 1
        "Mat_Wood",         # 2
        "Mat_DarkMetal",    # 3
        "Mat_Glass",        # 4
        "Mat_WarmGlow",     # 5
        "Mat_Concrete",     # 6
        "Mat_Brass",        # 7
        "Mat_AwningStripe", # 8
    ]
    add_box(bm, 6, (0, 0, 0.18), (9.0, 6.4, 0.36))
    # First floor brick masonry
    add_box(bm, 0, (0, 0, 2.0), (8.6, 6.0, 3.3))
    # Second floor warm stucco with brick corner pilasters
    add_box(bm, 1, (0, 0, 4.95), (8.5, 5.9, 2.6))
    add_box(bm, 0, (-4.0, -2.7, 4.95), (0.7, 0.7, 2.65))
    add_box(bm, 0, (4.0, -2.7, 4.95), (0.7, 0.7, 2.65))
    # Cornice & parapet roof
    add_box(bm, 6, (0, 0, 3.68), (8.9, 6.3, 0.22))
    add_box(bm, 6, (0, 0, 6.35), (9.0, 6.4, 0.32))
    add_box(bm, 3, (0, 0, 6.56), (9.1, 6.5, 0.12))

    # Door & storefront windows
    add_door(bm, 3, 2, 7, 4, -2.4, -3.02, 0.36, w=1.3, h=2.4, facing="Y-")
    add_framed_window(bm, 3, 4, 5, 1.2, -3.02, 2.0, 3.6, 1.85, "Y-", sill_m=6)
    add_framed_window(bm, 3, 4, 5, -2.4, -2.97, 4.95, 1.8, 1.45, "Y-", sill_m=6)
    add_framed_window(bm, 3, 4, 5, 0.6, -2.97, 4.95, 1.8, 1.45, "Y-", sill_m=6)
    add_framed_window(bm, 3, 4, 5, 3.0, -2.97, 4.95, 1.5, 1.45, "Y-", sill_m=6)
    add_framed_window(bm, 3, 4, 5, -4.32, 0.0, 2.0, 2.2, 1.7, "X-", sill_m=6)
    add_framed_window(bm, 3, 4, 5, 4.32, 0.0, 2.0, 2.2, 1.7, "X+", sill_m=6)

    # Awning & warm exterior sconces
    add_box(bm, 8, (1.2, -3.45, 3.18), (3.9, 1.0, 0.12), rot_euler=(math.radians(20), 0, 0))
    for lx in (-3.4, -1.2, 3.6):
        add_box(bm, 3, (lx, -3.08, 2.45), (0.14, 0.16, 0.28))
        add_box(bm, 5, (lx, -3.12, 2.42), (0.10, 0.12, 0.18))

    obj = finalize_mesh("Building_East_Cafe", bm, mats)
    return obj


def build_fisher_hut():
    """Hansu's Coastal Harbor Timber House (FisherHut)."""
    bm = bmesh.new()
    mats = [
        "Mat_Wood",         # 0
        "Mat_DarkWood",     # 1
        "Mat_Concrete",     # 2
        "Mat_RoofSlate",    # 3
        "Mat_DarkMetal",    # 4
        "Mat_Glass",        # 5
        "Mat_WarmGlow",     # 6
        "Mat_Stucco",       # 7
        "Mat_FlowerRed",    # 8 (Life buoy accent)
        "Mat_Brass",        # 9
    ]
    # Raised coastal stone & timber deck foundation (9.0m x 6.4m)
    add_box(bm, 2, (0, 0.3, 0.22), (8.8, 5.8, 0.44))
    # Front wooden veranda deck
    add_box(bm, 1, (0, -2.65, 0.38), (8.8, 1.4, 0.14))
    add_box(bm, 1, (0, -3.45, 0.19), (2.4, 0.5, 0.22))

    # Timber cabin main body
    add_box(bm, 0, (0, 0.55, 2.15), (8.2, 4.6, 3.45))
    # Exposed dark timber corner posts & porch pillars
    for px in (-4.1, -1.4, 1.4, 4.1):
        add_box(bm, 1, (px, -3.20, 1.95), (0.18, 0.18, 3.1))
    # Veranda railing
    add_box(bm, 1, (-2.75, -3.20, 1.05), (2.5, 0.10, 0.08))
    add_box(bm, 1, (2.75, -3.20, 1.05), (2.5, 0.10, 0.08))
    for rx in (-3.6, -3.0, -2.4, -1.8, 1.8, 2.4, 3.0, 3.6):
        add_box(bm, 1, (rx, -3.20, 0.72), (0.06, 0.06, 0.65))

    # Pitched dark slate coastal roof (front porch overhang slope + back slope meeting at ridge)
    add_box(bm, 3, (0, -1.15, 4.15), (9.1, 3.9, 0.22), rot_euler=(math.radians(18), 0, 0))
    add_box(bm, 3, (0, 1.85, 4.22), (9.1, 3.3, 0.22), rot_euler=(math.radians(-20), 0, 0))
    add_box(bm, 3, (0, 0.42, 4.76), (9.2, 0.42, 0.20))  # Roof ridge beam
    add_box(bm, 0, (0, 0.45, 4.00), (8.1, 3.0, 1.05))

    # Door & warm cottage windows
    add_door(bm, 1, 1, 9, 5, 0.0, -1.76, 0.44, w=1.25, h=2.3, facing="Y-")
    add_framed_window(bm, 1, 5, 6, -2.45, -1.76, 1.95, 1.8, 1.35, "Y-", sill_m=1)
    add_framed_window(bm, 1, 5, 6, 2.45, -1.76, 1.95, 1.8, 1.35, "Y-", sill_m=1)
    add_framed_window(bm, 1, 5, 6, -4.12, 0.55, 1.95, 1.8, 1.35, "X-", sill_m=1)
    add_framed_window(bm, 1, 5, 6, 4.12, 0.55, 1.95, 1.8, 1.35, "X+", sill_m=1)

    # Hanging harbor lantern on porch + wooden fish crates + life ring buoy
    add_box(bm, 4, (-1.2, -3.15, 3.05), (0.28, 0.28, 0.36))
    add_box(bm, 6, (-1.2, -3.15, 3.02), (0.20, 0.20, 0.24))
    # Crates on right porch
    add_box(bm, 0, (3.1, -2.5, 0.68), (0.75, 0.55, 0.46))
    add_box(bm, 0, (3.2, -2.45, 1.10), (0.65, 0.50, 0.40), rot_euler=(0, 0, 0.2))
    # Life ring on front wall
    add_cylinder(bm, 8, (1.15, -1.82, 2.15), 0.34, 0.34, 0.10, 16, rot_euler=(math.radians(90), 0, 0))
    add_cylinder(bm, 7, (1.15, -1.83, 2.15), 0.20, 0.20, 0.11, 16, rot_euler=(math.radians(90), 0, 0))

    obj = finalize_mesh("Building_FisherHut_Hansu", bm, mats)
    return obj


# ---------------------------------------------------------------------------
# 2. Realistic Organic Trees, Street Furniture & Pickups
# ---------------------------------------------------------------------------
def build_trees():
    mats = ["Mat_Bark", "Mat_Foliage", "Mat_FoliageLight", "Mat_BirchBark", "Mat_PineNeedles"]

    # A. Realistic Multi-Branch Oak Tree
    bm = bmesh.new()
    add_cylinder(bm, 0, (0, 0, 1.1), 0.34, 0.22, 2.2, 12)
    branches = [
        ((0.45, 0.25, 2.5), (0.18, 0.11, 1.4), (0.25, 0.38, 0.1)),
        ((-0.42, 0.30, 2.6), (0.17, 0.10, 1.5), (-0.30, -0.32, 0.2)),
        ((0.15, -0.45, 2.4), (0.16, 0.10, 1.4), (-0.38, 0.15, -0.1)),
        ((0.0, 0.05, 2.8), (0.20, 0.12, 1.6), (0.05, -0.05, 0.0)),
    ]
    for pos, (r1, r2, h), rot in branches:
        add_cylinder(bm, 0, pos, r1, r2, h, 10, rot_euler=rot)
    canopy_blobs = [
        ((0.0, 0.0, 4.1), (1.75, 1.65, 1.35), 1),
        ((1.05, 0.45, 3.45), (1.25, 1.15, 1.05), 2),
        ((-1.05, 0.50, 3.55), (1.30, 1.20, 1.10), 1),
        ((0.35, -1.0, 3.35), (1.20, 1.15, 1.00), 2),
        ((-0.55, -0.75, 3.60), (1.15, 1.10, 0.98), 1),
        ((0.55, 0.85, 3.80), (1.10, 1.05, 0.95), 2),
        ((0.0, 0.1, 4.85), (1.20, 1.15, 0.95), 2),
    ]
    for pos, rad, m in canopy_blobs:
        add_sphere(bm, m, pos, rad, 14, 10)
    oak = finalize_mesh("Tree_Realistic_Oak", bm, mats)
    export_single(oak, "Tree_Realistic_Oak.fbx")

    # B. Realistic Layered Pine / Cypress Tree
    bm = bmesh.new()
    add_cylinder(bm, 0, (0, 0, 1.4), 0.28, 0.14, 2.8, 12)
    tiers = [
        (2.1, 1.65, 0.25, 1.35),
        (2.9, 1.40, 0.20, 1.30),
        (3.65, 1.12, 0.16, 1.20),
        (4.35, 0.82, 0.08, 1.10),
        (4.95, 0.48, 0.02, 0.90),
    ]
    for z, r1, r2, h in tiers:
        add_cylinder(bm, 4, (0, 0, z), r1, r2, h, 14)
    pine = finalize_mesh("Tree_Realistic_Pine", bm, mats)
    export_single(pine, "Tree_Realistic_Pine.fbx")

    # C. Realistic Silver Birch / Boulevard Tree
    bm = bmesh.new()
    add_cylinder(bm, 3, (0, 0, 1.35), 0.24, 0.14, 2.7, 12)
    add_cylinder(bm, 3, (0.28, 0.15, 2.8), 0.12, 0.07, 1.4, 10, rot_euler=(0.15, 0.25, 0))
    add_cylinder(bm, 3, (-0.25, -0.18, 2.9), 0.11, 0.06, 1.4, 10, rot_euler=(-0.18, -0.22, 0))
    birch_blobs = [
        ((0.0, 0.0, 3.85), (1.35, 1.30, 1.45), 2),
        ((0.75, 0.35, 3.35), (1.05, 0.95, 1.10), 1),
        ((-0.70, -0.35, 3.50), (1.00, 0.95, 1.15), 2),
        ((0.15, -0.65, 4.20), (0.95, 0.90, 1.05), 1),
        ((0.0, 0.10, 4.90), (0.90, 0.85, 0.95), 2),
    ]
    for pos, rad, m in birch_blobs:
        add_sphere(bm, m, pos, rad, 14, 10)
    birch = finalize_mesh("Tree_Realistic_Birch", bm, mats)
    export_single(birch, "Tree_Realistic_Birch.fbx")


def build_props_and_pickups():
    # 1. Boulevard Street Lamp
    bm = bmesh.new()
    mats = ["Mat_DarkMetal", "Mat_WarmGlow", "Mat_Glass", "Mat_Brass"]
    add_cylinder(bm, 0, (0, 0, 0.25), 0.18, 0.13, 0.50, 12)
    add_cylinder(bm, 0, (0, 0, 1.95), 0.07, 0.05, 3.20, 12)
    add_box(bm, 0, (0.28, 0, 3.52), (0.62, 0.06, 0.06))
    add_cylinder(bm, 0, (0.52, 0, 3.42), 0.22, 0.14, 0.12, 12)
    add_sphere(bm, 1, (0.52, 0, 3.26), (0.14, 0.14, 0.16), 12, 10)
    lamp = finalize_mesh("Prop_StreetLamp", bm, mats)
    export_single(lamp, "Prop_StreetLamp.fbx")

    # 2. Park Bench
    bm = bmesh.new()
    mats_b = ["Mat_Wood", "Mat_DarkMetal"]
    for sx in (-0.75, 0.75):
        add_box(bm, 1, (sx, 0, 0.24), (0.06, 0.52, 0.48))
        add_box(bm, 1, (sx, 0.22, 0.62), (0.06, 0.08, 0.52), rot_euler=(math.radians(-12), 0, 0))
    for i in range(4):
        add_box(bm, 0, (0, -0.18 + i * 0.11, 0.46), (1.68, 0.08, 0.04))
    for i in range(3):
        add_box(bm, 0, (0, 0.20 + i * 0.02, 0.62 + i * 0.12), (1.68, 0.04, 0.09), rot_euler=(math.radians(-12), 0, 0))
    bench = finalize_mesh("Prop_Bench", bm, mats_b)
    export_single(bench, "Prop_Bench.fbx")

    # 3. Pickup: Blooming Flower Cluster
    bm = bmesh.new()
    mats_f = ["Mat_Foliage", "Mat_FlowerRed", "Mat_FlowerYellow", "Mat_FlowerPurple"]
    stems = [
        ((0.0, 0.0), 0.46, 1),
        ((0.10, 0.06), 0.38, 2),
        ((-0.09, 0.05), 0.40, 3),
    ]
    for (sx, sy), sh, cmat in stems:
        add_cylinder(bm, 0, (sx, sy, sh * 0.5), 0.018, 0.014, sh, 8)
        add_sphere(bm, 0, (sx + 0.05, sy, sh * 0.45), (0.07, 0.03, 0.015), 8, 6, rot_euler=(0, 0.4, 0.3))
        add_sphere(bm, 2, (sx, sy, sh + 0.02), (0.04, 0.04, 0.03), 8, 6)
        for p in range(6):
            ang = p * math.pi / 3.0
            px = sx + math.cos(ang) * 0.065
            py = sy + math.sin(ang) * 0.065
            add_sphere(bm, cmat, (px, py, sh + 0.01), (0.048, 0.035, 0.018), 8, 6, rot_euler=(0, 0, ang))
    p_flower = finalize_mesh("Pickup_Flower", bm, mats_f)
    export_single(p_flower, "Pickup_Flower.fbx")

    # 4. Pickup: Forest Mushroom Cluster
    bm = bmesh.new()
    mats_m = ["Mat_MushroomStem", "Mat_MushroomCap"]
    mushrooms = [
        ((0.0, 0.0), 0.24, 0.16),
        ((0.13, 0.06), 0.16, 0.11),
        ((-0.11, -0.05), 0.14, 0.09),
    ]
    for (mx, my), mh, mr in mushrooms:
        add_cylinder(bm, 0, (mx, my, mh * 0.5), mr * 0.32, mr * 0.24, mh, 12)
        add_sphere(bm, 1, (mx, my, mh), (mr, mr, mr * 0.58), 14, 10)
        # White spots on cap
        for s in range(5):
            ang = s * math.pi * 2.0 / 5.0 + 0.3
            add_sphere(bm, 0, (mx + math.cos(ang) * mr * 0.55, my + math.sin(ang) * mr * 0.55, mh + mr * 0.38), (mr * 0.14, mr * 0.14, mr * 0.08), 8, 6)
    p_mush = finalize_mesh("Pickup_Mushroom", bm, mats_m)
    export_single(p_mush, "Pickup_Mushroom.fbx")

    # 5. Pickup: Ribbed Sea Scallop Shell
    bm = bmesh.new()
    mats_s = ["Mat_ShellPearl", "Mat_StuccoWarm"]
    for rib in range(-5, 6):
        ang = rib * 0.13
        rx = math.sin(ang) * 0.11
        ry = math.cos(ang) * 0.11 - 0.08
        add_box(bm, 0, (rx, ry, 0.04 + (1.0 - abs(rib) * 0.12) * 0.02), (0.032, 0.26, 0.035), rot_euler=(0.12, 0, -ang))
    add_box(bm, 1, (0, -0.18, 0.03), (0.16, 0.06, 0.03))
    p_shell = finalize_mesh("Pickup_Shell", bm, mats_s)
    export_single(p_shell, "Pickup_Shell.fbx")


# ---------------------------------------------------------------------------
# 3. Village Roads, Sidewalks, Plaza & Harbor Pier
# ---------------------------------------------------------------------------
def build_village_environment():
    bm = bmesh.new()
    mats = [
        "Mat_Cobble",       # 0: Stone paved streets & plaza
        "Mat_Concrete",     # 1: Curbs & sidewalk slabs
        "Mat_Wood",         # 2: Harbor pier timber deck
        "Mat_DarkWood",     # 3: Pier pilings & bollards
        "Mat_Water",        # 4: Coastal harbor water surface
        "Mat_Foliage",      # 5: Central plaza planter greenery
        "Mat_FlowerYellow", # 6: Plaza flowers
    ]
    # Central plaza stone pavement (cobblestone disk slightly above outer concrete curb ring)
    add_cylinder(bm, 1, (0, 0, 0.008), 5.55, 5.55, 0.016, 36)
    add_cylinder(bm, 0, (0, 0, 0.014), 5.20, 5.20, 0.022, 36)

    # 4 Radiating Cobblestone Streets (in Blender -Y is Unity +Z, +Y is Unity -Z):
    # North avenue (towards North House at +Z in Unity -> -Y in Blender)
    add_box(bm, 0, (0, -5.5, 0.010), (3.4, 11.0, 0.020))
    add_box(bm, 1, (-1.85, -5.5, 0.022), (0.28, 10.5, 0.036))
    add_box(bm, 1, (1.85, -5.5, 0.022), (0.28, 10.5, 0.036))

    # West avenue (towards Darae's Flower Shop at -X, +Z in Unity -> -X, -Y in Blender)
    add_box(bm, 0, (-6.2, -2.0, 0.010), (12.5, 3.2, 0.020), rot_euler=(0, 0, math.radians(16)))
    # East avenue (towards East Cafe at +X, +Z in Unity -> +X, -Y in Blender)
    add_box(bm, 0, (6.2, -1.0, 0.010), (12.0, 3.2, 0.020), rot_euler=(0, 0, math.radians(-9)))
    # South-East avenue (towards Hansu's Fisher Hut at +X, -Z in Unity -> +X, +Y in Blender)
    add_box(bm, 0, (4.8, 8.5, 0.010), (3.2, 16.0, 0.020), rot_euler=(0, 0, math.radians(-24)))

    # Coastal Harbor Water, Stone Quay Seawall & Wooden Pier behind/beside Fisher Hut (South-East)
    add_box(bm, 1, (14.0, 20.4, 0.03), (48.5, 0.85, 0.06))  # Stone seawall promenade edge
    add_box(bm, 2, (9.5, 22.2, 0.05), (9.5, 4.8, 0.09))     # Wooden pier deck
    for px in (5.2, 8.0, 11.0, 13.8):
        add_cylinder(bm, 3, (px, 20.0, 0.32), 0.13, 0.13, 0.64, 10)
        add_cylinder(bm, 3, (px, 24.4, 0.32), 0.13, 0.13, 0.64, 10)
    # Shimmering coastal water basin in the south-east bay
    add_box(bm, 4, (14.0, 31.8, 0.012), (48.0, 22.0, 0.020))

    env = finalize_mesh("Village_Environment", bm, mats)
    export_single(env, "Village_Environment.fbx")


# ---------------------------------------------------------------------------
# 4. Proportioned Humanoid Characters with Clean Anatomical Rig & Idle/Walk Clips
# ---------------------------------------------------------------------------
def build_humanoid_character(name, is_female=False):
    """
    Build a 7.5-head-tall stylized-realistic human character with clean anatomical rigging
    (leg-left, leg-right, torso, arm-left, arm-right, head) and smooth idle/walk animations.
    """
    clear_scene()
    mats = {
        "Skin": get_mat(f"Mat_{name}_Skin", (0.94, 0.78, 0.70) if is_female else (0.85, 0.67, 0.56), roughness=0.48),
        "Hair": get_mat(f"Mat_{name}_Hair", (0.26, 0.15, 0.10) if is_female else (0.20, 0.21, 0.23), roughness=0.42),
        "Top": get_mat(f"Mat_{name}_Top", (0.96, 0.93, 0.88) if is_female else (0.20, 0.31, 0.44), roughness=0.68),
        "Outer": get_mat(f"Mat_{name}_Outer", (0.44, 0.61, 0.47) if is_female else (0.33, 0.37, 0.27), roughness=0.65),
        "Bottom": get_mat(f"Mat_{name}_Bottom", (0.83, 0.76, 0.66) if is_female else (0.18, 0.20, 0.24), roughness=0.70),
        "Shoes": get_mat(f"Mat_{name}_Shoes", (0.30, 0.19, 0.13) if is_female else (0.17, 0.14, 0.11), roughness=0.52),
        "EyeDark": get_mat(f"Mat_{name}_EyeDark", (0.07, 0.05, 0.04), roughness=0.08),
        "EyeWhite": get_mat(f"Mat_{name}_EyeWhite", (0.97, 0.97, 0.98), roughness=0.12),
        "Lip": get_mat(f"Mat_{name}_Lip", (0.84, 0.45, 0.43) if is_female else (0.72, 0.48, 0.42), roughness=0.42),
    }
    mat_list = ["Skin", "Hair", "Top", "Outer", "Bottom", "Shoes", "EyeDark", "EyeWhite", "Lip"]
    vg_names = ["leg-left", "leg-right", "torso", "arm-left", "arm-right", "head"]

    bm = bmesh.new()
    vg_layer = bm.verts.layers.int.new("vg")

    def tag_verts(verts, vg_id):
        for v in verts:
            v[vg_layer] = vg_id

    def add_part_box(m, vg_id, center, size, rot=(0, 0, 0)):
        v = add_box(bm, m, center, size, rot)
        tag_verts(v, vg_id)

    def add_part_cyl(m, vg_id, center, r1, r2, h, segs=14, rot=(0, 0, 0)):
        v = add_cylinder(bm, m, center, r1, r2, h, segs, rot)
        tag_verts(v, vg_id)

    def add_part_sph(m, vg_id, center, rvec, segs=16, rings=12, rot=(0, 0, 0)):
        v = add_sphere(bm, m, center, rvec, segs, rings, rot)
        tag_verts(v, vg_id)

    # 0: leg-left (+X), 1: leg-right (-X)
    for sx, vg_id in ((0.10, 0), (-0.10, 1)):
        add_part_box(5, vg_id, (sx, -0.025, 0.055), (0.095, 0.21, 0.11))
        add_part_cyl(0 if is_female else 4, vg_id, (sx, 0.0, 0.26), 0.050, 0.060, 0.34, 14)
        add_part_cyl(4, vg_id, (sx, 0.0, 0.58), 0.064, 0.078, 0.34, 14)

    # 2: torso
    if is_female:
        add_part_cyl(4, 2, (0, 0, 0.72), 0.20, 0.145, 0.44, 18)        # Midi skirt
        add_part_cyl(3, 2, (0, -0.012, 0.94), 0.175, 0.145, 0.52, 18)  # Sage florist apron
        add_part_cyl(2, 2, (0, 0, 1.14), 0.14, 0.16, 0.38, 18)         # Cream blouse
        add_part_cyl(0, 2, (0, 0.005, 1.37), 0.050, 0.046, 0.12, 14)   # Neck
    else:
        add_part_cyl(4, 2, (0, 0, 0.78), 0.16, 0.17, 0.24, 18)         # Work trousers pelvis
        add_part_cyl(2, 2, (0, 0, 1.10), 0.165, 0.19, 0.44, 18)        # Shirt
        add_part_cyl(3, 2, (0, -0.008, 1.11), 0.18, 0.198, 0.40, 18)   # Utility fishing vest
        add_part_cyl(0, 2, (0, 0.005, 1.37), 0.056, 0.052, 0.12, 14)   # Neck

    # 3: arm-left (+X), 4: arm-right (-X) — natural relaxed silhouette at sides
    for sx, vg_id in ((1.0, 3), (-1.0, 4)):
        sh_x = sx * (0.185 if is_female else 0.21)
        add_part_sph(2, vg_id, (sh_x, 0, 1.28), (0.062, 0.062, 0.062), 12, 10)
        add_part_cyl(2, vg_id, (sh_x + sx * 0.025, 0.0, 1.13), 0.045, 0.052, 0.26, 12, (0, sx * -0.10, 0))
        add_part_cyl(0, vg_id, (sh_x + sx * 0.048, -0.015, 0.91), 0.036, 0.043, 0.24, 12, (0.10, sx * -0.06, 0))
        add_part_sph(0, vg_id, (sh_x + sx * 0.058, -0.03, 0.77), (0.036, 0.028, 0.045), 10, 8)

    # 5: head (center at z=1.53m, eyes at z=1.54m)
    add_part_sph(0, 5, (0, 0.0, 1.53), (0.102, 0.114, 0.128), 20, 16)
    add_part_sph(0, 5, (0, -0.114, 1.515), (0.016, 0.022, 0.030), 10, 8)  # Nose
    for sx in (-1.0, 1.0):
        add_part_sph(0, 5, (sx * 0.103, 0.01, 1.52), (0.016, 0.025, 0.032), 8, 6)  # Ears
        ex = sx * 0.040
        add_part_sph(7, 5, (ex, -0.100, 1.538), (0.019, 0.011, 0.014), 12, 10)
        add_part_sph(6, 5, (ex, -0.108, 1.538), (0.012, 0.008, 0.012), 12, 10)
        add_part_sph(7, 5, (ex + 0.004, -0.114, 1.542), (0.0035, 0.003, 0.0035), 8, 6)
        add_part_box(1, 5, (ex, -0.104, 1.564), (0.032, 0.010, 0.007), (0, sx * 0.08, 0))
    add_part_sph(8, 5, (0, -0.105, 1.472), (0.025, 0.012, 0.009), 10, 8)  # Lips

    if is_female:
        add_part_sph(1, 5, (0, 0.014, 1.558), (0.110, 0.120, 0.122), 18, 14)
        add_part_sph(1, 5, (-0.052, -0.072, 1.585), (0.062, 0.052, 0.045), 12, 10)
        add_part_sph(1, 5, (0.052, -0.072, 1.585), (0.062, 0.052, 0.045), 12, 10)
        add_part_sph(1, 5, (0, 0.132, 1.49), (0.055, 0.055, 0.055), 12, 10)
    else:
        add_part_sph(1, 5, (0, 0.01, 1.55), (0.108, 0.116, 0.112), 18, 14)
        add_part_sph(3, 5, (0, 0.014, 1.602), (0.112, 0.118, 0.082), 18, 12)  # Fisherman beanie
        add_part_sph(1, 5, (0, -0.062, 1.460), (0.080, 0.060, 0.042), 12, 10)  # Beard

    vert_vg_Assignments = [v[vg_layer] for v in bm.verts]

    # Convert mesh vertices to Y-up, +Z-front so root rotation is (0,0,0) in Unity
    rot_to_yup = Matrix.Rotation(-math.pi * 0.5, 4, "X")
    bmesh.ops.transform(bm, matrix=rot_to_yup, verts=bm.verts)

    mesh = bpy.data.meshes.new("body-mesh")
    for mkey in mat_list:
        mesh.materials.append(mats[mkey])
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()

    # Build Armature with exact human joint positions in Y-up, +Z-front space
    arm_data = bpy.data.armatures.new("root_data")
    arm_obj = bpy.data.objects.new("root", arm_data)
    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")

    def make_bone(bname, head, tail, parent=None):
        b = arm_data.edit_bones.new(bname)
        b.head = head
        b.tail = tail
        if parent:
            b.parent = parent
        return b

    b_torso = make_bone("torso", (0, 0.72, 0), (0, 1.34, 0))
    make_bone("leg-left", (0.10, 0.72, 0), (0.10, 0.05, 0), b_torso)
    make_bone("leg-right", (-0.10, 0.72, 0), (-0.10, 0.05, 0), b_torso)
    make_bone("arm-left", (0.20, 1.28, 0), (0.24, 0.78, 0), b_torso)
    make_bone("arm-right", (-0.20, 1.28, 0), (-0.24, 0.78, 0), b_torso)
    make_bone("head", (0, 1.36, 0), (0, 1.68, 0), b_torso)

    bpy.ops.object.mode_set(mode="OBJECT")

    char_obj = bpy.data.objects.new("body-mesh", mesh)
    bpy.context.collection.objects.link(char_obj)
    char_obj.parent = arm_obj
    mod = char_obj.modifiers.new(name="Armature", type="ARMATURE")
    mod.object = arm_obj

    vgroups = {vgn: char_obj.vertex_groups.new(name=vgn) for vgn in vg_names}
    for v_idx, vg_id in enumerate(vert_vg_Assignments):
        vgroups[vg_names[vg_id]].add([v_idx], 1.0, "REPLACE")

    arm_obj.rotation_euler = (math.pi * 0.5, 0.0, 0.0)

    # Create natural 'idle' and 'walk' actions
    create_human_action(arm_obj, "idle", is_walk=False)
    create_human_action(arm_obj, "walk", is_walk=True)
    arm_obj.animation_data.action = bpy.data.actions["idle"]
    bpy.context.scene.frame_set(1)

    bpy.ops.object.select_all(action="DESELECT")
    arm_obj.select_set(True)
    char_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    out_path = os.path.join(MOD_DIR, f"{name}.fbx")
    bpy.ops.export_scene.fbx(
        filepath=out_path,
        use_selection=True,
        add_leaf_bones=False,
        bake_anim=True,
        bake_anim_use_all_actions=True,
        bake_anim_use_nla_strips=False,
        axis_forward="-Z",
        axis_up="Y",
    )
    print(f"Exported character {out_path}")


def create_human_action(arm_obj, action_name, is_walk=False):
    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    act = bpy.data.actions.new(name=action_name)
    arm_obj.animation_data.action = act
    for bname in ["torso", "head", "arm-left", "arm-right", "leg-left", "leg-right"]:
        arm_obj.pose.bones[bname].rotation_mode = "XYZ"

    pb_torso = arm_obj.pose.bones["torso"]
    pb_head = arm_obj.pose.bones["head"]
    pb_al = arm_obj.pose.bones["arm-left"]
    pb_ar = arm_obj.pose.bones["arm-right"]
    pb_ll = arm_obj.pose.bones["leg-left"]
    pb_lr = arm_obj.pose.bones["leg-right"]

    frames = [1, 15, 30, 45, 60] if not is_walk else [1, 10, 20, 30, 40]
    for i, f in enumerate(frames):
        phase = (i / (len(frames) - 1)) * math.pi * 2.0
        s = math.sin(phase)
        c = math.cos(phase)
        if not is_walk:
            pb_torso.location = (0, 0, s * 0.006)
            pb_torso.rotation_euler = (s * 0.015, 0, c * 0.010)
            pb_head.rotation_euler = (c * 0.020, 0, s * 0.025)
            pb_al.rotation_euler = (s * 0.025, 0, 0)
            pb_ar.rotation_euler = (-s * 0.025, 0, 0)
            pb_ll.rotation_euler = (0, 0, 0)
            pb_lr.rotation_euler = (0, 0, 0)
        else:
            pb_torso.location = (0, 0, abs(s) * 0.022)
            pb_torso.rotation_euler = (0.03, 0, s * 0.04)
            pb_head.rotation_euler = (-0.02, 0, -s * 0.03)
            pb_al.rotation_euler = (s * 0.35, 0, 0)
            pb_ar.rotation_euler = (-s * 0.35, 0, 0)
            pb_ll.rotation_euler = (-s * 0.40, 0, 0)
            pb_lr.rotation_euler = (s * 0.40, 0, 0)
        pb_torso.keyframe_insert(data_path="location", frame=f)
        for pb in (pb_torso, pb_head, pb_al, pb_ar, pb_ll, pb_lr):
            pb.keyframe_insert(data_path="rotation_euler", frame=f)


def export_single(obj, filename):
    bpy.ops.object.select_all(action="DESELECT")
    # Transform mesh vertices so local +Y is Up and local +Z is Front (matching Unity SetPositionAndRotation)
    rot_mat = Matrix.Rotation(-math.pi * 0.5, 4, "X")
    obj.data.transform(rot_mat)
    obj.data.update()
    obj.rotation_euler = (math.pi * 0.5, 0.0, 0.0)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    out_path = os.path.join(MOD_DIR, filename)
    bpy.ops.export_scene.fbx(
        filepath=out_path,
        use_selection=True,
        axis_forward="-Z",
        axis_up="Y",
        path_mode="AUTO",
    )
    # Restore mesh orientation in Blender scene
    obj.data.transform(rot_mat.inverted())
    obj.data.update()
    obj.rotation_euler = (0.0, 0.0, 0.0)
    print(f"Exported {out_path}")


def main():
    generate_textures()
    clear_scene()
    init_materials()

    # Export buildings
    b_north = build_north_residence()
    export_single(b_north, "Building_North_Residence.fbx")

    b_flower = build_flower_shop()
    export_single(b_flower, "Building_FlowerShop_Darae.fbx")

    b_east = build_east_cafe()
    export_single(b_east, "Building_East_Cafe.fbx")

    b_fisher = build_fisher_hut()
    export_single(b_fisher, "Building_FisherHut_Hansu.fbx")

    # Export trees, street props, pickups, and road/plaza environment
    build_trees()
    build_props_and_pickups()
    build_village_environment()

    # Save master .blend scene with all architectural assets arranged for Blender MCP inspection
    b_north.location = (0, 12, 0)
    b_North_rot = (0, 0, math.pi)
    b_north.rotation_euler = b_North_rot
    b_flower.location = (-15, 4, 0)
    b_flower.rotation_euler = (0, 0, -math.pi * 0.5)
    b_east.location = (15, 2, 0)
    b_east.rotation_euler = (0, 0, math.pi * 0.5)
    b_fisher.location = (12, -15, 0)
    b_fisher.rotation_euler = (0, 0, math.pi * 0.5)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT_DIR, "InzoiVillage.blend"))

    # Export realistic humanoid characters with Idle & Walk animations
    init_materials()
    build_humanoid_character("Character_Hansu", is_female=False)
    init_materials()
    build_humanoid_character("Character_Darae", is_female=True)

    print("ALL BLENDER ASSETS GENERATED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
