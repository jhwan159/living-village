import bpy
import bmesh
import math
import random
import os
import struct
import zlib
from mathutils import Vector, Matrix, Euler, Quaternion

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

    # 9. Woven Linen & Canvas Fabric Texture (for Darae's Blouse, Apron & Skirt)
    albedo = bytearray(W * H * 3)
    heights = [0.0] * (W * H)
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            warp = 0.5 + 0.5 * math.sin(u * 64.0 * math.pi * 2.0)
            weft = 0.5 + 0.5 * math.sin(v * 64.0 * math.pi * 2.0)
            weave = (warp * 0.52 + weft * 0.48)
            n = fbm(u, v, 16, 3, 123)
            h_val = weave * 0.65 + n * 0.35
            heights[y * W + x] = h_val
            tone = 0.94 + (weave - 0.5) * 0.06 + (n - 0.5) * 0.05
            i = (y * W + x) * 3
            albedo[i] = clamp8(tone)
            albedo[i + 1] = clamp8(tone * 0.99)
            albedo[i + 2] = clamp8(tone * 0.97)
    write_png(os.path.join(TEX_DIR, "Fabric_Albedo.png"), W, H, albedo)
    height_to_normal_png(os.path.join(TEX_DIR, "Fabric_Normal.png"), heights, W, H, 1.8)

    # 10. Silky Hair Strand Texture (for Darae's Chestnut Hair)
    albedo = bytearray(W * H * 3)
    heights = [0.0] * (W * H)
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            s1 = fbm(u * 6.0, v * 0.5, 16, 4, 211)
            s2 = 0.5 + 0.5 * math.sin((u * 48.0 + s1 * 0.8) * math.pi * 2.0)
            h_val = s1 * 0.6 + s2 * 0.4
            heights[y * W + x] = h_val
            tone = 0.88 + (h_val - 0.5) * 0.18
            i = (y * W + x) * 3
            albedo[i] = clamp8(tone * 1.02)
            albedo[i + 1] = clamp8(tone * 0.96)
            albedo[i + 2] = clamp8(tone * 0.90)
    write_png(os.path.join(TEX_DIR, "Hair_Albedo.png"), W, H, albedo)
    height_to_normal_png(os.path.join(TEX_DIR, "Hair_Normal.png"), heights, W, H, 2.4)

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
    get_mat("Mat_FlowerPink", (0.95, 0.56, 0.68), roughness=0.45)
    get_mat("Mat_FlowerWhite", (0.97, 0.96, 0.93), roughness=0.45)
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
    """Create a cylinder/cone with split-vertex end caps so cap normals never bleed into smooth side walls."""
    ret = bmesh.ops.create_cone(
        bm,
        cap_ends=False,
        cap_tris=False,
        segments=segments,
        radius1=radius_bottom,
        radius2=radius_top,
        depth=height,
    )
    verts = list(ret["verts"])
    verts_set = set(verts)
    for f in bm.faces:
        if all(v in verts_set for v in f.verts):
            f.material_index = mat_idx
            f.smooth = True

    # Separate flat end caps with independent vertices so normals stay crisp at rims
    half_h = height * 0.5
    for z_sign, rad in ((-1.0, radius_bottom), (1.0, radius_top)):
        if rad <= 1e-5:
            continue
        cap_verts = []
        for i in range(segments):
            ang = (i / segments) * math.pi * 2.0
            vx = rad * math.cos(ang)
            vy = rad * math.sin(ang)
            vz = z_sign * half_h
            cap_verts.append(bm.verts.new((vx, vy, vz)))
        if z_sign < 0:
            cap_verts.reverse()
        f_cap = bm.faces.new(cap_verts)
        f_cap.material_index = mat_idx
        f_cap.smooth = False
        verts.extend(cap_verts)

    if any(rot_euler):
        rmat = Euler(rot_euler, "XYZ").to_matrix().to_4x4()
        bmesh.ops.rotate(bm, matrix=rmat, verts=verts)
    bmesh.ops.translate(bm, vec=center, verts=verts)
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
        "Mat_FlowerPink",     # 15
        "Mat_FlowerWhite",    # 16
        "Mat_FoliageLight",   # 17
        "Mat_DarkWood",       # 18
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

    # Welcome floral wreath on front door
    for w_i in range(12):
        wang = w_i * math.pi * 2.0 / 12.0
        wx = math.cos(wang) * 0.22
        wz = 1.98 + math.sin(wang) * 0.22
        add_sphere(bm, 8 if (w_i % 2 == 0) else 17, (wx, -2.76, wz), (0.065, 0.04, 0.065), 8, 6)
        if w_i % 3 == 0:
            f_m = [9, 10, 15, 16][(w_i // 3) % 4]
            add_sphere(bm, f_m, (wx * 1.02, -2.79, wz), (0.045, 0.03, 0.045), 8, 6)

    # Sloped café awning over front storefront
    add_box(bm, 7, (-2.55, -3.15, 3.15), (2.7, 1.15, 0.12), rot_euler=(math.radians(22), 0, 0))
    add_box(bm, 7, (2.55, -3.15, 3.15), (2.7, 1.15, 0.12), rot_euler=(math.radians(22), 0, 0))
    # Wooden sign board above door with brass floral emblem
    add_box(bm, 2, (0, -2.78, 3.42), (2.4, 0.16, 0.55))
    add_box(bm, 5, (0, -2.85, 3.42), (2.1, 0.06, 0.38))
    for b_i in range(6):
        bang = b_i * math.pi / 3.0
        add_sphere(bm, 15, (-0.75 + math.cos(bang) * 0.07, -2.89, 3.42 + math.sin(bang) * 0.07), (0.035, 0.015, 0.035), 8, 6)
        add_sphere(bm, 10, (0.75 + math.cos(bang) * 0.07, -2.89, 3.42 + math.sin(bang) * 0.07), (0.035, 0.015, 0.035), 8, 6)
    add_sphere(bm, 14, (-0.75, -2.90, 3.42), (0.03, 0.015, 0.03), 8, 6)
    add_sphere(bm, 14, (0.75, -2.90, 3.42), (0.03, 0.015, 0.03), 8, 6)

    # Hanging flower baskets under awnings
    for hx in (-3.55, -1.55, 1.55, 3.55):
        add_cylinder(bm, 3, (hx, -3.45, 2.74), 0.008, 0.008, 0.42, 6)
        add_cylinder(bm, 12, (hx, -3.45, 2.48), 0.09, 0.16, 0.14, 12)
        add_sphere(bm, 8, (hx, -3.45, 2.55), (0.18, 0.18, 0.10), 10, 8)
        for b_i in range(5):
            bang = b_i * math.pi * 2.0 / 5.0 + hx
            bx = hx + math.cos(bang) * 0.11
            by = -3.45 + math.sin(bang) * 0.11
            add_sphere(bm, [9, 10, 11, 15, 16][b_i % 5], (bx, by, 2.61), (0.055, 0.055, 0.045), 8, 6)

    # Pitched terracotta roof (front slope + back slope meeting at ridge z=5.05) + central gable dormer
    add_box(bm, 6, (0, -1.25, 4.60), (9.1, 3.4, 0.24), rot_euler=(math.radians(22), 0, 0))
    add_box(bm, 6, (0, 1.65, 4.60), (9.1, 3.4, 0.24), rot_euler=(math.radians(-22), 0, 0))
    add_box(bm, 6, (0, 0.20, 5.22), (9.2, 0.45, 0.22))  # Ridge cap
    add_box(bm, 0, (0, 0.20, 4.45), (8.5, 3.2, 1.15))
    add_framed_window(bm, 2, 4, 5, 0, -1.42, 4.55, 1.4, 0.90, "Y-", sill_m=2)

    def add_rich_flower_pot(px, py, pz_base, pot_mat, flower_mats, scale=1.0):
        # Tapered pot body + rim + dark soil
        h_pot = 0.24 * scale
        r_bot = 0.10 * scale
        r_top = 0.145 * scale
        add_cylinder(bm, pot_mat, (px, py, pz_base + h_pot * 0.5), r_bot, r_top, h_pot, 12)
        add_cylinder(bm, pot_mat, (px, py, pz_base + h_pot - 0.015 * scale), r_top * 1.06, r_top * 1.08, 0.035 * scale, 12)
        add_cylinder(bm, 18, (px, py, pz_base + h_pot - 0.005 * scale), r_top * 0.92, r_top * 0.92, 0.02 * scale, 10)
        # Organic leafy foliage mound (multiple overlapping leafy tufts, not a single sphere)
        top_z = pz_base + h_pot
        for l_i in range(5):
            lang = l_i * math.pi * 2.0 / 5.0 + px * 1.7
            lx = px + math.cos(lang) * 0.065 * scale
            ly = py + math.sin(lang) * 0.065 * scale
            add_sphere(bm, 8 if (l_i % 2 == 0) else 17, (lx, ly, top_z + 0.05 * scale), (0.095 * scale, 0.085 * scale, 0.075 * scale), 10, 8)
        add_sphere(bm, 8, (px, py, top_z + 0.08 * scale), (0.10 * scale, 0.10 * scale, 0.08 * scale), 10, 8)
        # Stems & multi-blossom cluster
        for f_i in range(6):
            fang = f_i * math.pi * 2.0 / 6.0 + py * 1.3
            rad = (0.075 if f_i < 5 else 0.0) * scale
            fx = px + math.cos(fang) * rad
            fy = py + math.sin(fang) * rad
            fz = top_z + (0.145 if f_i < 5 else 0.175) * scale + (f_i % 2) * 0.018 * scale
            fm = flower_mats[f_i % len(flower_mats)]
            add_sphere(bm, fm, (fx, fy, fz), (0.048 * scale, 0.048 * scale, 0.036 * scale), 8, 6)
            add_sphere(bm, 10 if fm != 10 else 16, (fx, fy, fz + 0.018 * scale), (0.020 * scale, 0.020 * scale, 0.015 * scale), 6, 6)

    # Outdoor 2-tier wooden flower stands with rich multi-blossom flower pots in front of shop
    palette_sets = [
        [9, 15, 16],
        [10, 16, 9],
        [11, 15, 16],
        [15, 10, 16],
    ]
    for side_x in (-2.55, 2.55):
        # 2-tier wooden rack
        add_box(bm, 2, (side_x, -3.25, 0.42), (2.2, 0.70, 0.10))
        add_box(bm, 2, (side_x, -3.05, 0.78), (2.2, 0.42, 0.10))
        add_box(bm, 2, (side_x - 1.0, -3.15, 0.45), (0.10, 0.65, 0.75))
        add_box(bm, 2, (side_x + 1.0, -3.15, 0.45), (0.10, 0.65, 0.75))
        for i, ox in enumerate((-0.75, -0.25, 0.25, 0.75)):
            px = side_x + ox
            p_idx = (i + (0 if side_x < 0 else 2)) % 4
            add_rich_flower_pot(px, -3.38, 0.47, 12, palette_sets[p_idx], scale=0.95)
            add_rich_flower_pot(px, -3.05, 0.83, 12 if (i % 2 == 0) else 3, palette_sets[(p_idx + 1) % 4], scale=0.92)

    # Charming wooden A-frame chalkboard easel sign & tall galvanized florist bucket by the entrance
    add_box(bm, 2, (1.05, -3.25, 0.68), (0.52, 0.05, 0.78), rot_euler=(math.radians(-10), 0, math.radians(-12)))
    add_box(bm, 2, (1.08, -3.05, 0.68), (0.52, 0.05, 0.78), rot_euler=(math.radians(10), 0, math.radians(-12)))
    add_box(bm, 3, (1.04, -3.28, 0.72), (0.42, 0.02, 0.56), rot_euler=(math.radians(-10), 0, math.radians(-12)))
    add_rich_flower_pot(-1.02, -3.22, 0.32, 3, [15, 9, 10, 16], scale=1.18)

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
def _dspline(rows, n):
    """Catmull-Rom resample of a list of equal-length tuples to n rows."""
    rows = [tuple(r) for r in rows]
    m = len(rows) - 1
    out = []
    for i in range(n):
        x = m * i / (n - 1)
        k = min(int(x), m - 1)
        t = x - k
        p0, p1, p2, p3 = rows[max(k - 1, 0)], rows[k], rows[k + 1], rows[min(k + 2, m)]
        out.append(tuple(0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (3 * b - a - 3 * c + d) * t ** 3)
                         for a, b, c, d in zip(p0, p1, p2, p3)))
    return out


def _dtab(tab, x):
    """Linear lookup in a table sorted ascending by its first column."""
    x = max(tab[0][0], min(tab[-1][0], x))
    for a, b in zip(tab, tab[1:]):
        if x <= b[0]:
            k = (x - a[0]) / (b[0] - a[0])
            return tuple(p + (q - p) * k for p, q in zip(a, b))
    return tuple(tab[-1])


def _dring(z, cy, w, f, b, ts, nf=2.0):
    """Horizontal cross-section: t=0 is the front (-Y), t=pi/2 her left (+X). Front half is a superellipse (nf)."""
    pts = []
    for t in ts:
        s, c = math.sin(t), math.cos(t)
        if c > 0:
            e = 2.0 / nf
            pts.append(Vector((w * math.copysign(abs(s) ** e, s), cy - f * c ** e, z)))
        else:
            pts.append(Vector((w * s, cy - b * c, z)))
    return pts


def _dweights(p, bones, cands, power=4.0):
    """Smooth skin weights from inverse distance to the candidate bone segments."""
    ws = {}
    for name in cands:
        a, c = bones[name][0], bones[name][1]
        ab = c - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
        ws[name] = 1.0 / max((p - (a + ab * t)).length, 1e-4) ** power
    s = sum(ws.values())
    return {k: v / s for k, v in ws.items() if v / s > 0.02}


class _DPart:
    """One mesh part of Darae: quad grids with metric UVs and per-vertex bone weights, finished with modifiers."""

    def __init__(self, name, mat_objs, M, bone_names):
        self.name, self.mat_objs, self.M, self.bone_names = name, mat_objs, M, bone_names
        self.B = {b: i for i, b in enumerate(bone_names)}
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.verify()
        self.dv = self.bm.verts.layers.deform.verify()

    def vert(self, p, w):
        v = self.bm.verts.new(p)
        ws = w(v.co) if callable(w) else w
        if isinstance(ws, str):
            ws = {ws: 1.0}
        for k, x in ws.items():
            if x > 0.0:
                v[self.dv][self.B[k]] = x
        return v

    def grid(self, rows, mat, w, closed=True, cap0=None, cap1=None, wrap=False, skip=None, uvfn=None):
        """Quad grid from rows of points (or existing verts). UVs are in metres unless uvfn(co, column) is given."""
        bm, uv, mi = self.bm, self.uv, self.M[mat]
        vs = [[p if isinstance(p, bmesh.types.BMVert) else self.vert(p, w) for p in row] for row in rows]
        nr, nc = len(vs), len(vs[0])
        cols = nc if closed else nc - 1
        nrow = nr if wrap else nr - 1
        U = [0.0]
        for j in range(cols):
            U.append(U[-1] + sum((r[(j + 1) % nc].co - r[j].co).length for r in vs) / nr)
        Vv = [0.0]
        for i in range(nrow):
            Vv.append(Vv[-1] + sum((vs[(i + 1) % nr][j].co - vs[i][j].co).length for j in range(nc)) / nc)

        def face(verts, uvs, j):
            f = bm.faces.new(verts)
            f.material_index = mi
            f.smooth = True
            for loop, q in zip(f.loops, uvs):
                loop[uv].uv = uvfn(loop.vert.co, j) if uvfn else q

        for i in range(nrow):
            i2 = (i + 1) % nr
            for j in range(cols):
                if skip and skip(i, j):
                    continue
                j2 = (j + 1) % nc
                face((vs[i][j], vs[i][j2], vs[i2][j2], vs[i2][j]),
                     ((U[j], Vv[i]), (U[j + 1], Vv[i]), (U[j + 1], Vv[i + 1]), (U[j], Vv[i + 1])), j)
        for cap, row in ((cap0, vs[0]), (cap1, vs[-1])):
            if cap is None or cap is False:
                continue
            c = sum((v.co for v in row), Vector()) / nc
            e1 = (row[0].co - c).normalized()
            n = sum(((row[j].co - c).cross(row[(j + 1) % nc].co - c) for j in range(nc)), Vector()).normalized()
            e2 = n.cross(e1)
            cv = self.vert(cap if isinstance(cap, Vector) else c, w)
            for j in range(cols):
                tri = (row[j], row[(j + 1) % nc], cv)
                face(tri, [((p.co - c).dot(e1), (p.co - c).dot(e2)) for p in tri], j)
        return vs

    def tube(self, pts, radii, mat, w, ref, n=8):
        """Round tube along pts (radii per point), rounded tip at the end."""
        pts = [Vector(p) for p in pts]
        m = len(pts)
        rows = []
        for i, p in enumerate(pts):
            T = (pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]).normalized()
            N = (ref - T * ref.dot(T)).normalized()
            Bv = T.cross(N)
            rows.append([p + (N * math.cos(2 * math.pi * q / n) + Bv * math.sin(2 * math.pi * q / n)) * radii[i] for q in range(n)])
        T = (pts[-1] - pts[-2]).normalized()
        rows.append([pts[-1] + (p - pts[-1]) * 0.72 + T * radii[-1] * 0.6 for p in rows[-1]])
        self.grid(rows, mat, w, cap0=True, cap1=pts[-1] + T * radii[-1])

    def ellipsoid(self, center, ax1, ax2, ax3, mat, w, nu=10, nv=6, sq=1.0):
        """Ellipsoid with half-axes ax1/ax2/ax3 (ax2 = pole axis). sq < 1 makes it boxier."""
        center = Vector(center)

        def sp(x):
            return math.copysign(abs(x) ** sq, x)

        rows = []
        for i in range(1, nv):
            la = -math.pi / 2 + math.pi * i / nv
            rows.append([center + ax1 * (sp(math.cos(la)) * sp(math.cos(2 * math.pi * j / nu))) +
                         ax3 * (sp(math.cos(la)) * sp(math.sin(2 * math.pi * j / nu))) + ax2 * sp(math.sin(la)) for j in range(nu)])
        self.grid(rows, mat, w, cap0=center - ax2, cap1=center + ax2)

    def torus(self, center, e1, e2, r1, r2, r, mat, w, nu=18, nv=6, nf=2.0):
        """Ring in the e1/e2 plane (superellipse nf for rounded rectangles) with tube radius r."""
        center = Vector(center)
        e3 = e1.cross(e2)
        rows = []
        for i in range(nu):
            c, s = math.cos(2 * math.pi * i / nu), math.sin(2 * math.pi * i / nu)
            o = e1 * (r1 * math.copysign(abs(c) ** (2 / nf), c)) + e2 * (r2 * math.copysign(abs(s) ** (2 / nf), s))
            d = o.normalized()
            rows.append([center + o + (d * math.cos(2 * math.pi * j / nv) + e3 * math.sin(2 * math.pi * j / nv)) * r for j in range(nv)])
        self.grid(rows, mat, w, wrap=True)

    def finish(self, mods=(), orient=None, post=None, hull=0.0, lining=None):
        """Create the object, apply modifiers, run post(ob), then add the inverted-hull outline."""
        bm = self.bm
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()
        if orient:
            # Open sheets: recalc cannot know which side is out, so decide per connected island
            seen = set()
            for f0 in bm.faces[:]:
                if f0 in seen:
                    continue
                isl, stack = [], [f0]
                seen.add(f0)
                while stack:
                    f = stack.pop()
                    isl.append(f)
                    for e in f.edges:
                        for g in e.link_faces:
                            if g not in seen:
                                seen.add(g)
                                stack.append(g)
                if sum(f.normal.dot(orient(f.calc_center_median())) * f.calc_area() for f in isl) < 0:
                    bmesh.ops.reverse_faces(bm, faces=isl)
        me = bpy.data.meshes.new(self.name)
        for m in self.mat_objs:
            me.materials.append(m)
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.collection.objects.link(ob)
        for b in self.bone_names:
            ob.vertex_groups.new(name=b)
        bm.to_mesh(me)
        bm.free()
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        LIN = len(self.mat_objs) - 1
        for kind, kw in mods:
            m = ob.modifiers.new(kind, kind)
            if kind == "SOLIDIFY" and lining:
                m.material_offset = m.material_offset_rim = LIN - self.M[lining]
            for k, v in kw.items():
                setattr(m, k, v)
            bpy.ops.object.modifier_apply(modifier=m.name)
        me = ob.data
        if lining:
            # Solidify copies the outer UVs onto the lining; give the lining its own small island instead
            uvd = me.uv_layers.active.data
            for poly in me.polygons:
                if poly.material_index == LIN:
                    poly.material_index = self.M[lining]
                    for li in poly.loop_indices:
                        uvd[li].uv = (uvd[li].uv[0] * 0.3 + 40.0, uvd[li].uv[1] * 0.3)
        if post:
            post(ob)
        if hull > 0.0:
            hb = bmesh.new()
            hb.from_mesh(me)
            hb.normal_update()
            push = {v.index: v.normal * hull for v in hb.verts}
            ret = bmesh.ops.duplicate(hb, geom=hb.faces[:])
            for src, dst in ret["vert_map"].items():
                if src.index in push and dst.index != src.index and dst.is_valid:
                    dst.co = src.co + push[src.index]
            faces = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMFace)]
            bmesh.ops.reverse_faces(hb, faces=faces)
            for f in faces:
                f.material_index = self.M["Outline"]
            hb.to_mesh(me)
            hb.free()
        return ob


def build_florist_darae(name="Character_Darae"):
    """
    Darae (34, flower-shop owner), stylized anime proportions (~7.3 heads), built from spline-lofted quad
    base meshes that go through Mirror / Solidify / Subdivision modifiers, not from stacked primitives.
    - Head: one lofted mesh, front-warped columns, sculpted eye planes / nose / lips; eyes, lashes, brows and
      mouth are thin shells projected onto the face. Face UV is a planar front island (see face_uv).
    - Hair: skull cap + tapered lens-section clumps (side-swept bangs, side locks, hair gathered to a low
      ponytail that falls over her right shoulder), ribbon and a daisy clip.
    - Outfit: cream blouse + collar, sage cardigan with set-in sleeves bridged into the body (mirrored,
      solidified), leather belt with buckle / pouch / shears, linen waist apron, terracotta pleated skirt,
      ankle boots. Left hand grips a kraft-wrapped bouquet (the arm pose lives in the idle/walk clips).
    - Rig: 19 bones with smooth weights; clips "idle" and "walk". Outline is an inverted hull (Outline slot).
    """
    clear_scene()
    V = Vector
    PI = math.pi
    sin, cos, exp = math.sin, math.cos, math.exp

    def flat(key, srgb, rough):
        # Display (sRGB) values, the same as in VillageBuilder.cs; Blender wants linear
        return get_mat(f"Mat_{name}_{key}", tuple(c ** 2.2 for c in srgb), roughness=rough)

    mats = {
        "Skin": flat("Skin", (0.96, 0.82, 0.74), 0.80),
        "Face": flat("Face", (0.96, 0.82, 0.74), 0.80),
        "Hair": flat("Hair", (0.28, 0.16, 0.11), 0.75),
        "Top": flat("Top", (0.98, 0.95, 0.88), 0.90),
        "Outer": flat("Outer", (0.56, 0.72, 0.58), 0.90),
        "Bottom": flat("Bottom", (0.80, 0.47, 0.34), 0.90),
        "Apron": flat("Apron", (0.93, 0.88, 0.76), 0.90),
        "Belt": flat("Belt", (0.55, 0.32, 0.17), 0.70),
        "Shoes": flat("Shoes", (0.40, 0.23, 0.14), 0.70),
        "Eye": flat("Eye", (0.55, 0.32, 0.14), 0.60),
        "EyeWhite": flat("EyeWhite", (1.00, 1.00, 1.00), 0.60),
        "EyeDark": flat("EyeDark", (0.12, 0.07, 0.06), 0.60),
        "Lip": flat("Lip", (0.86, 0.42, 0.40), 0.80),
        "Kraft": flat("Kraft", (0.80, 0.60, 0.38), 0.90),
        "Outline": flat("Outline", (0.19, 0.11, 0.08), 1.00),
        "Brass": get_mat("Mat_Brass", (0.90, 0.72, 0.34), roughness=0.20, metallic=0.90),
        "Foliage": get_mat("Mat_Foliage", (0.28, 0.50, 0.23), roughness=0.58),
        "FlowerPink": get_mat("Mat_FlowerPink", (0.95, 0.56, 0.68), roughness=0.45),
        "FlowerWhite": get_mat("Mat_FlowerWhite", (0.97, 0.96, 0.93), roughness=0.45),
        "FlowerYellow": get_mat("Mat_FlowerYellow", (0.96, 0.78, 0.18), roughness=0.45),
        "FlowerRed": get_mat("Mat_FlowerRed", (0.90, 0.22, 0.26), roughness=0.45),
    }
    mat_list = list(mats.keys())
    M = {k: i for i, k in enumerate(mat_list)}
    lining_tmp = bpy.data.materials.new("_darae_lining")
    mat_objs = [mats[k] for k in mat_list] + [lining_tmp]

    # -----------------------------------------------------------------------
    # Skeleton (authoring space: Z up, she faces -Y, her left is +X)
    # -----------------------------------------------------------------------
    bones = {}

    def bone(bname, head, tail, parent):
        bones[bname] = (V(head), V(tail), parent)

    bone("hips", (0, 0.01, 0.90), (0, 0.01, 1.02), None)
    bone("spine", (0, 0.01, 1.02), (0, 0.01, 1.17), "hips")
    bone("chest", (0, 0.01, 1.17), (0, 0.012, 1.33), "spine")
    bone("neck", (0, 0.012, 1.33), (0, 0.006, 1.43), "chest")
    bone("head", (0, 0.006, 1.43), (0, 0.006, 1.64), "neck")
    SH, EL, WR, HT = V((0.158, 0.0, 1.305)), V((0.205, 0.008, 1.075)), V((0.243, -0.012, 0.845)), V((0.258, -0.020, 0.760))
    HIP, KN, AN, TOE = V((0.080, 0.0, 0.88)), V((0.078, -0.005, 0.47)), V((0.077, 0.012, 0.09)), V((0.079, -0.13, 0.02))
    for sfx, g in ((".L", 1), (".R", -1)):
        mx = lambda p: V((p.x * g, p.y, p.z))
        bone("shoulder" + sfx, (0.03 * g, 0.01, 1.30), (0.150 * g, 0.0, 1.312), "chest")
        bone("upper_arm" + sfx, mx(SH), mx(EL), "shoulder" + sfx)
        bone("forearm" + sfx, mx(EL), mx(WR), "upper_arm" + sfx)
        bone("hand" + sfx, mx(WR), mx(HT), "forearm" + sfx)
        bone("thigh" + sfx, mx(HIP), mx(KN), "hips")
        bone("shin" + sfx, mx(KN), mx(AN), "thigh" + sfx)
        bone("foot" + sfx, mx(AN), mx(TOE), "shin" + sfx)
    bone_names = list(bones.keys())

    parts = []

    def part(pname):
        return _DPart(pname, mat_objs, M, bone_names)

    def dw(*cands, power=4.0):
        return lambda p: _dweights(p, bones, cands, power)

    SUB = ("SUBSURF", {"levels": 1})
    OL = 0.0022  # outline thickness
    GNF = 2.3    # front superellipse of torso garments

    def radial(cy):
        return lambda c: V((c.x, c.y - cy, 0.0))

    # -----------------------------------------------------------------------
    # 1. HEAD: lofted from chin to crown; zr = height relative to the head centre HZ
    # -----------------------------------------------------------------------
    HZ, HS = 1.504, 1.07

    def hzs(zr):  # design height -> real: bigger head, shorter lower face
        return zr * HS * (0.9 if zr < 0 else 1.0)

    HEAD = [(hzs(r[0]), r[1] * HS, r[2] * HS, r[3] * HS, r[4] * HS, r[5]) for r in [
         # zr, ring centre y, half width, front depth, back depth, front superellipse
        (-0.108, -0.046, 0.015, 0.016, 0.016, 2.0), (-0.098, -0.036, 0.030, 0.038, 0.036, 2.1),
        (-0.085, -0.022, 0.046, 0.058, 0.055, 2.2), (-0.070, -0.008, 0.060, 0.076, 0.070, 2.3),
        (-0.055, 0.000, 0.069, 0.087, 0.080, 2.4), (-0.040, 0.004, 0.074, 0.091, 0.086, 2.5),
        (-0.020, 0.005, 0.077, 0.091, 0.092, 2.5), (0.000, 0.005, 0.078, 0.092, 0.095, 2.4),
        (0.020, 0.005, 0.078, 0.092, 0.095, 2.3), (0.040, 0.005, 0.076, 0.089, 0.091, 2.2),
        (0.060, 0.005, 0.070, 0.082, 0.083, 2.1), (0.080, 0.005, 0.058, 0.067, 0.067, 2.0),
        (0.095, 0.005, 0.040, 0.045, 0.045, 2.0), (0.103, 0.005, 0.018, 0.020, 0.020, 2.0),
    ]]
    HC = V((0.0, 0.005, HZ + 0.015))
    EX, EZ, EW = 0.0390, HZ - 0.030, 0.0220  # eye centre x / z, eye half width
    FS = 4.2  # face UV scale

    def hp(t, zr, off=0.0):
        """Point on the head at angle t / design height zr, pushed outward by off."""
        r = _dtab(HEAD, hzs(zr))
        p = _dring(HZ + r[0], r[1], r[2], r[3], r[4], [t], r[5])[0]
        return p + (p - HC).normalized() * off

    def face_uv(p):
        return (0.5 + p.x * FS, 0.50 + (p.z - HZ) * FS)

    NC = 36
    hts = [u - 0.2 * sin(2 * u) for u in (2 * PI * j / NC for j in range(NC))]  # denser columns on the face

    def head_uv(p, j):
        if j < NC // 4 or j >= 3 * NC // 4:
            return face_uv(p)
        return (0.93 - p.x * 0.7, 0.5 + (p.z - HZ) * 0.7)

    def sculpt_head(ob):
        me = ob.data
        for v in me.vertices:
            x, y, zr = v.co.x, v.co.y, v.co.z - HZ
            if y >= 0.0:
                continue
            d = 0.0045 * exp(-((abs(x) - EX) / 0.030) ** 2 - ((zr + 0.030) / 0.020) ** 2)  # flat eye planes
            d -= 0.0025 * exp(-(x / 0.007) ** 2) * smoothstep(-0.066, -0.050, zr) * smoothstep(-0.005, -0.03, zr)  # bridge
            d -= 0.0075 * exp(-(x / 0.0065) ** 2 - ((zr + 0.058) / (0.010 if zr > -0.058 else 0.005)) ** 2)  # nose tip
            d -= 0.0022 * exp(-(x / 0.018) ** 2 - ((zr + 0.079) / 0.008) ** 2)  # lips
            d -= 0.003 * exp(-(x / 0.016) ** 2 - ((zr + 0.097) / 0.010) ** 2)  # chin
            v.co.y += d * smoothstep(0.0, -0.03, y)
        # The contract with the texture painter: front island is an exact planar projection
        uvd = me.uv_layers.active.data
        for li, loop in enumerate(me.loops):
            if uvd[li].uv[0] < 0.86:
                uvd[li].uv = face_uv(me.vertices[loop.vertex_index].co)

    P = part("head")
    P.grid([_dring(HZ + r[0], r[1], r[2], r[3], r[4], hts, r[5]) for r in _dspline(HEAD, 22)], "Face", "head",
           cap0=V((0.0, -0.046 * HS, HZ + hzs(-0.113))), cap1=V((0.0, 0.005, HZ + hzs(0.1065))), uvfn=head_uv)
    head_ob = P.finish([SUB], post=sculpt_head, hull=0.0016)
    parts.append(head_ob)

    P = part("skin")
    for g in (1, -1):
        wdir = V((0.45 * g, 0.9, 0.0)).normalized()
        up = V((0.0, 0.18, 1.0)).normalized()
        P.ellipsoid((0.081 * g, 0.020, HZ - 0.030), wdir * 0.014, up * 0.027, wdir.cross(up) * 0.007, "Skin", "head", 8, 6)
    # Neck
    NECK = [(1.30, 0.016, 0.047, 0.045, 0.047), (1.335, 0.014, 0.041, 0.040, 0.042), (1.37, 0.011, 0.038, 0.037, 0.039),
            (1.405, 0.008, 0.038, 0.037, 0.039), (1.445, 0.006, 0.039, 0.038, 0.040)]
    nts = [2 * PI * j / 14 for j in range(14)]
    P.grid([_dring(z, cy, w, f, b, nts) for z, cy, w, f, b in NECK], "Skin", dw("chest", "neck", "head"))
    # Lower legs (the rest of the leg is under the skirt and is not built)
    LEG = [(0.52, -0.004, 0.052, 0.052, 0.052), (0.47, -0.006, 0.048, 0.050, 0.048), (0.42, 0.000, 0.043, 0.044, 0.046),
           (0.36, 0.006, 0.045, 0.042, 0.052), (0.30, 0.008, 0.041, 0.038, 0.046), (0.24, 0.010, 0.034, 0.034, 0.036),
           (0.16, 0.012, 0.030, 0.030, 0.032)]
    lts = [2 * PI * j / 12 for j in range(12)]
    for sfx, g in ((".L", 1), (".R", -1)):
        rows = [[p + V((0.077 * g, 0, 0)) for p in _dring(z, cy, w, f, b, lts)] for z, cy, w, f, b in LEG]
        P.grid(rows, "Skin", dw("thigh" + sfx, "shin" + sfx))
    parts.append(P.finish([SUB], hull=OL))

    # Hands: palm loft + finger tubes, built in the wrist frame (a = along the hand, b = thumb side, c = palm normal)
    P = part("hands")
    hand_frames = {}
    for sfx, g, grip in ((".L", 1, True), (".R", -1, False)):
        o = V((WR.x * g, WR.y, WR.z))
        a = (V((HT.x * g, HT.y, HT.z)) - o).normalized()
        b = V((0.0, -1.0, 0.0))
        b = (b - a * b.dot(a)).normalized()
        c = a.cross(b) * g
        hand_frames[sfx] = (o, a, b, c)
        w = "hand" + sfx

        def L(s, bb, cc):
            return o + a * s + b * bb + c * cc

        qs = [2 * PI * q / 10 for q in range(10)]
        P.grid([[L(s, cb + hb * cos(q), hc * sin(q)) for q in qs] for s, hb, hc, cb in
                ((-0.03, 0.016, 0.013, 0.0), (0.0, 0.019, 0.013, 0.0), (0.022, 0.029, 0.014, 0.002),
                 (0.048, 0.036, 0.013, 0.0), (0.072, 0.035, 0.011, -0.002))], "Skin", w, cap0=True, cap1=L(0.080, -0.002, 0.0))
        curl = (1.0, 1.25, 0.8) if grip else (0.30, 0.50, 0.40)
        for i, (bo, ln) in enumerate(((0.026, 0.062), (0.009, 0.070), (-0.008, 0.065), (-0.024, 0.052))):
            d = (a + b * 0.03 * (1.5 - i) / 1.5).normalized()
            pts, ang = [L(0.068, bo, 0.0)], 0.0
            for k, seg in enumerate((0.45, 0.30, 0.25)):
                ang += curl[k]
                dd = d * cos(ang) + c * sin(ang)
                pts += [pts[-1] + dd * ln * seg * 0.5, pts[-1] + dd * ln * seg]
            P.tube(pts, [0.0082 - 0.002 * k / 6 for k in range(7)], "Skin", w, b)
        d = (a * 0.45 + b * 0.25 + c * 0.86).normalized() if grip else (a * 0.6 + b * 0.7 + c * 0.38).normalized()
        d2 = (d + c * 0.5 - b * (0.5 if grip else 0.2)).normalized()
        p0 = L(0.018, 0.024, 0.004)
        P.tube([p0, p0 + d * 0.014, p0 + d * 0.028, p0 + d * 0.028 + d2 * 0.012, p0 + d * 0.028 + d2 * 0.024],
               [0.0105, 0.0098, 0.0090, 0.0084, 0.0076], "Skin", w, b.cross(d))
    parts.append(P.finish(hull=0.0016))

    # -----------------------------------------------------------------------
    # 2. FACE DETAILS: thin shells projected onto the sculpted face (layer = stacking order)
    # -----------------------------------------------------------------------
    from mathutils.bvhtree import BVHTree
    hbm = bmesh.new()
    hbm.from_mesh(head_ob.data)
    face_faces = [f for f in hbm.faces if f.material_index == M["Face"]]
    bmesh.ops.delete(hbm, geom=[f for f in hbm.faces if f.material_index != M["Face"]], context="FACES")
    bvh = BVHTree.FromBMesh(hbm)

    def proj(x, z, layer):
        loc, nrm, _, _ = bvh.ray_cast(V((x, -0.5, z)), V((0.0, 1.0, 0.0)))
        return loc + (nrm * 0.6 + V((0.0, -0.4, 0.0))) * (0.0007 * layer)

    def eye_uv(p):
        g = 1 if p.x > 0 else -1
        return (0.5 + 0.25 * g + (p.x - g * EX) * 17.0, 0.5 + (p.z - EZ - 0.001) * 17.0)

    def lid_u(a):
        return 0.0150 * max(0.0, 1 - (a / EW) ** 2) ** 0.6 - 0.0012 * a / EW

    def lid_l(a):
        return -0.0105 * max(0.0, 1 - (a / EW) ** 2) ** 0.75 - 0.0012 * a / EW

    def lin(a0, a1, n):
        return [a0 + (a1 - a0) * i / (n - 1) for i in range(n)]

    P = part("face_details")

    def fan(g, outline, layer, mat, uvfn):
        ca = sum(a for a, _ in outline) / len(outline)
        cb = sum(b for _, b in outline) / len(outline)
        rows = [[proj(g * (EX + ca + (a - ca) * k), EZ + cb + (b - cb) * k, layer) for a, b in outline] for k in (1.0, 0.55)]
        P.grid(rows, mat, "head", cap1=True, uvfn=lambda p, j: uvfn(p))

    def strip(xz_rows, layer, mat, uvfn=None):
        P.grid([[proj(x, z, layer) for x, z in row] for row in xz_rows], mat, "head", closed=False,
               uvfn=(lambda p, j: uvfn(p)) if uvfn else None)

    def ellipse(ca, cb, ra, rb, n=16, clip=True):
        out = []
        for q in range(n):
            a, b = ca + ra * cos(2 * PI * q / n), cb + rb * sin(2 * PI * q / n)
            if clip:
                a = max(-EW * 0.98, min(EW * 0.98, a))
                b = max(lid_l(a), min(lid_u(a), b))
            out.append((a, b))
        return out

    for g in (1, -1):
        fan(g, [(a, lid_u(a)) for a in lin(-EW, EW, 13)] + [(a, lid_l(a)) for a in lin(EW, -EW, 13)[1:-1]], 1, "EyeWhite", face_uv)
        fan(g, ellipse(0.0, 0.001, 0.0120, 0.0148, 20), 2, "Eye", eye_uv)
        fan(g, ellipse(0.0, 0.0015, 0.0050, 0.0072, 12), 3, "EyeDark", face_uv)
        fan(g, ellipse(-0.0042 * g, 0.0068, 0.0032, 0.0037, 10), 5, "EyeWhite", face_uv)
        fan(g, ellipse(0.0040 * g, -0.0052, 0.0016, 0.0017, 8), 5, "EyeWhite", face_uv)
        # Upper lash: thicker toward the outer corner, small wing
        lo, up = [], []
        for a in lin(-EW - 0.001, EW + 0.0045, 18):
            ac = max(-EW, min(EW, a))
            base = lid_u(ac) + max(0.0, a - EW) * 0.55
            th = (0.0022 + 0.0026 * smoothstep(-EW, EW, a)) * (1 - smoothstep(EW, EW + 0.0045, a)) * smoothstep(-EW - 0.001, -EW + 0.005, a) + 0.0003
            lo.append((g * (EX + a), EZ + base - 0.0007))
            up.append((g * (EX + a), EZ + base + th))
        strip([lo, up], 4, "EyeDark", face_uv)
        lo = [(g * (EX + a), EZ + lid_l(a) - 0.0008) for a in lin(EW * 0.15, EW, 8)]
        up = [(g * (EX + a), EZ + lid_l(a)) for a in lin(EW * 0.15, EW, 8)]
        strip([lo, up], 4, "EyeDark", face_uv)
        # Brow (hair colour): soft arch, tapering outward
        lo, up = [], []
        for a in lin(-0.018, 0.025, 10):
            cb = 0.0260 + 0.0035 * (1 - ((a - 0.003) / 0.0215) ** 2) - 0.0012 * a / 0.0215
            th = 0.0028 * (1 - 0.75 * smoothstep(-0.018, 0.025, a))
            lo.append((g * (EX + a), EZ + cb - th / 2))
            up.append((g * (EX + a), EZ + cb + th / 2))
        strip([lo, up], 1, "Hair")
    # Mouth: small closed smile
    lo, up = [], []
    for x in lin(-0.014, 0.014, 11):
        zc = HZ - 0.0800 + 0.0040 * (x / 0.014) ** 2
        th = 0.0013 * (1 - (x / 0.014) ** 2) + 0.0004
        lo.append((x, zc - th))
        up.append((x, zc + th * 0.4))
    strip([lo, up], 1, "Lip", face_uv)
    parts.append(P.finish(orient=lambda c: V((0.0, -1.0, 0.0))))
    hbm.free()

    # -----------------------------------------------------------------------
    # 3. HAIR
    # -----------------------------------------------------------------------
    HL = [(0.0, 0.064), (0.7, 0.060), (1.15, -0.005), (1.3, -0.022), (1.9, -0.022), (2.35, -0.068), (PI, -0.076)]

    def zl(t):  # hairline height by angle
        return _dtab(HL, abs(math.atan2(sin(t), cos(t))))[1]

    P = part("hair")
    cts = [2 * PI * j / 36 for j in range(36)]
    rows = [[hp(t, 0.1035 + (zl(t) - 0.1035) * (i / 11) ** 0.85, 0.007) for t in cts] for i in range(1, 12)]
    rows.append([hp(t, zl(t) - 0.003, 0.0005) for t in cts])
    P.grid(rows, "Hair", "head", cap0=V((0.0, 0.005, HZ + hzs(0.1035) + 0.009)))

    def strand(pts, width, thick, w="head", ref=None, n=13, around=8):
        """Tapered clump with a lens cross-section following pts (flat side toward ref / the head)."""
        pts = [V(p) for p in _dspline([tuple(p) for p in pts], n)]
        rows = []
        for i, p in enumerate(pts):
            s = i / (n - 1)
            T = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
            N = p - (ref(p) if ref else HC)
            N = (N - T * N.dot(T)).normalized()
            Bv = T.cross(N)
            k = max((0.5 + 0.5 * sin(min(s / 0.35, 1.0) * PI / 2)) * min(1.0, (1.0 - s) / 0.55) ** 0.8, 0.03)  # leaf: pointed tip
            row = []
            for q in range(around):
                ca, sa = cos(2 * PI * q / around), sin(2 * PI * q / around)
                row.append(p + Bv * (width * 0.5 * k * ca) + N * (thick * k ** 0.6 * (sa if sa > 0 else sa * 0.25)))
            rows.append(row)
        P.grid(rows, "Hair", w, cap0=True, cap1=True)

    def hpath(params, n=10):
        return [hp(*q) for q in _dspline(params, n)]

    # Side-swept bangs from a part on her left
    for t0, t1, t2, ztip, wd in ((0.30, 0.05, -0.12, 0.006, 0.040), (0.15, -0.25, -0.45, -0.004, 0.042), (-0.10, -0.50, -0.72, -0.012, 0.040),
                                 (-0.35, -0.80, -0.98, -0.034, 0.038), (0.55, 0.50, 0.40, 0.014, 0.032), (0.70, 0.80, 0.92, -0.024, 0.038),
                                 (0.48, 0.22, 0.14, 0.018, 0.030)):
        strand(hpath([(t0, 0.101, 0.009), ((t0 + t1) / 2, 0.086, 0.014), (t1, 0.060, 0.016), ((t1 + t2) / 2, 0.034, 0.015),
                      (t2, ztip + 0.014, 0.011), (t2 + (t2 - t1) * 0.25, ztip, 0.006)], 12), wd, 0.007)
    # Side locks in front of the ears
    for g, zt in ((1, -0.118), (-1, -0.105)):
        pts = hpath([(g * 0.95, 0.098, 0.010), (g * 1.05, 0.06, 0.017), (g * 1.12, 0.02, 0.018), (g * 1.16, -0.02, 0.015)], 8)
        e = pts[-1]
        pts += [V((e.x - g * 0.002, e.y - 0.006, HZ - 0.06)), V((e.x - g * 0.008, e.y - 0.010, HZ + zt + 0.03)), V((e.x - g * 0.016, e.y - 0.008, HZ + zt))]
        strand(pts, 0.032, 0.011, n=16)
    # Hair pulled back over the skull to the tie at the nape
    for g, t0s in ((1, (0.95, 1.35, 1.75, 2.15, 2.55, 2.95)), (-1, (0.75, 1.15, 1.55, 1.95, 2.35, 2.75, 3.1))):
        for t0 in t0s:
            la = lambda k: g * (t0 + (PI - t0) * k)
            strand(hpath([(la(0), 0.101, 0.010), (la(0.12), 0.07, 0.015), (la(0.4), 0.02, 0.016), (la(0.75), -0.04, 0.014),
                          (la(1.0), -0.076, 0.011)], 12), 0.050, 0.010, n=11, around=6)
    # Low ponytail over her right shoulder: follows the head near the tie, the chest further down
    tie = hp(PI, -0.076, 0.014) + V((-0.010, 0.0, 0.0))
    TAIL = [tuple(tie + V((0.005, -0.004, 0.004))), (-0.06, 0.062, tie.z - 0.022), (-0.103, 0.032, 1.386), (-0.116, -0.040, 1.352),
            (-0.104, -0.094, 1.285), (-0.090, -0.116, 1.205), (-0.080, -0.120, 1.13)]

    def tail_w(p):
        k = smoothstep(1.35, 1.42, p.z)
        return {"head": k, "chest": 1.0 - k}

    for dx, dz, ln, wd in ((0.0, 0.0, 1.0, 0.036), (0.011, 0.004, 0.90, 0.030), (-0.011, 0.004, 0.94, 0.030),
                           (0.004, 0.010, 0.80, 0.026), (-0.005, -0.007, 0.86, 0.028)):
        base = [V(p) for p in _dspline(TAIL, 16)][:max(4, int(16 * ln))]
        for i, p in enumerate(base):
            k = sin(PI * min(1.0, i / 9.0) * 0.5)
            p += V((dx, -abs(dx) * 0.3, dz)) * k
        strand(base, wd, 0.016, w=tail_w, ref=lambda p: V((0.0, 0.02, p.z - 0.05)), n=18)
    # Ribbon at the tie
    P.ellipsoid(tie, V((0.012, 0, 0)), V((0, 0, 0.011)), V((0, 0.010, 0)), "FlowerYellow", "head", 8, 5)
    for g in (1, -1):
        ax = V((g * 0.85, 0.15, 0.45 * g if g > 0 else 0.25)).normalized()
        P.ellipsoid(tie + ax * 0.022 + V((0, 0.006, 0)), ax * 0.022, V((0, 1, 0)).cross(ax).normalized() * 0.012, V((0, 0.006, 0)),
                    "FlowerYellow", "head", 8, 5)

    def daisy(center, up, r, w, petals=8):
        e1 = up.cross(V((0.0, 0.0, 1.0)) if abs(up.z) < 0.9 else V((1.0, 0.0, 0.0))).normalized()
        e2 = up.cross(e1)
        P.ellipsoid(center + up * r * 0.10, e1 * r * 0.30, up * r * 0.22, e2 * r * 0.30, "FlowerYellow", w, 8, 4)
        for i in range(petals):
            d = e1 * cos(2 * PI * i / petals) + e2 * sin(2 * PI * i / petals)
            P.ellipsoid(center + d * r * 0.62 + up * r * 0.04, d * r * 0.40, up.cross(d) * r * 0.17, up * r * 0.06, "FlowerWhite", w, 5, 4)

    cp = hp(1.02, 0.030, 0.024)
    daisy(cp, (cp - HC).normalized(), 0.030, "head")
    parts.append(P.finish(hull=0.0015))

    # -----------------------------------------------------------------------
    # 4. OUTFIT
    # -----------------------------------------------------------------------
    # Blouse (mostly under the cardigan; visible at the chest opening and neck)
    BL = [(0.98, 0.010, 0.102, 0.082, 0.084), (1.04, 0.010, 0.094, 0.078, 0.078), (1.10, 0.010, 0.104, 0.088, 0.084),
          (1.16, 0.010, 0.118, 0.100, 0.090), (1.21, 0.012, 0.124, 0.108, 0.092), (1.26, 0.014, 0.126, 0.098, 0.094),
          (1.30, 0.016, 0.110, 0.080, 0.086), (1.33, 0.014, 0.078, 0.060, 0.066), (1.352, 0.012, 0.050, 0.046, 0.050),
          (1.362, 0.012, 0.042, 0.040, 0.043)]
    bts = [2 * PI * j / 24 for j in range(24)]
    P = part("blouse")
    rows = []
    for z, cy, w, f, b in BL:
        ring = _dring(z, cy, w, f, b, bts, GNF)
        for p in ring:
            if p.y < cy:
                p.y -= 0.010 * exp(-((abs(p.x) - 0.055) / 0.035) ** 2 - ((z - 1.215) / 0.045) ** 2)
        rows.append(ring)
    P.grid(rows, "Top", dw("hips", "spine", "chest", "neck"))
    parts.append(P.finish([SUB]))

    # Shirt collar: folded leaf around the neck, open at the front, longer points
    P = part("collar")
    cts = lin(0.10, 2 * PI - 0.10, 23)
    rows = [[], [], [], []]
    for t in cts:
        fr = ((1 + cos(t)) / 2)
        z0 = 1.380 - 0.016 * fr ** 1.5
        drop = 0.020 + 0.022 * fr ** 3
        for row, dz, dr in zip(rows, (-0.014, 0.0, -0.010, -drop), (-0.002, 0.0, 0.012, 0.021)):
            row.append(_dring(z0 + dz, 0.011, 0.043 + dr, 0.041 + dr, 0.044 + dr, [t])[0])
    P.grid(rows, "Top", dw("chest", "neck"), closed=False)
    parts.append(P.finish([("SOLIDIFY", {"thickness": 0.003, "offset": 1.0}), SUB], orient=radial(0.011), hull=0.0016, lining="Top"))

    # Cardigan: left half with the sleeve bridged into an armhole, then Mirror + Solidify + Subsurf
    CARD = [  # z, centre y, half width, front, back, front opening angle
        (0.895, 0.012, 0.170, 0.132, 0.138, 0.40), (0.94, 0.012, 0.160, 0.125, 0.128, 0.40), (0.99, 0.012, 0.138, 0.110, 0.110, 0.40),
        (1.035, 0.012, 0.112, 0.092, 0.090, 0.42), (1.09, 0.012, 0.119, 0.098, 0.094, 0.46), (1.15, 0.012, 0.130, 0.110, 0.099, 0.52),
        (1.21, 0.013, 0.138, 0.119, 0.102, 0.60), (1.262, 0.014, 0.145, 0.110, 0.103, 0.72), (1.315, 0.015, 0.150, 0.088, 0.095, 0.86),
        (1.345, 0.013, 0.114, 0.072, 0.084, 0.93), (1.354, 0.012, 0.074, 0.056, 0.068, 0.97),
    ]
    CA, CM = 4, 11
    P = part("cardigan")
    w_torso = dw("hips", "spine", "chest")
    rows = []
    for z, cy, w, f, b, gap in CARD:
        ts = [gap + (1.0 - gap) * j / CA for j in range(CA)] + [1.0 + (PI - 1.0) * j / CM for j in range(CM + 1)]
        ring = _dring(z, cy, w, f, b, ts, GNF)
        for p, t in zip(ring, ts):  # peplum folds below the belt
            k = 1.0 + 0.035 * smoothstep(1.0, 0.90, z) * sin(7.0 * t + 0.5)
            p.x, p.y = p.x * k, cy + (p.y - cy) * k
        ring[-1].x = 0.0
        rows.append(ring)
    vs = P.grid(rows, "Outer", w_torso, closed=False, skip=lambda i, j: 6 <= i < 8 and 5 <= j < 9)
    per = [vs[6][j] for j in range(5, 10)] + [vs[7][9]] + [vs[8][j] for j in range(9, 4, -1)] + [vs[7][5]]

    def ring_frame(n):
        e1 = V((0.0, -1.0, 0.0))
        e1 = (e1 - n * e1.dot(n)).normalized()
        return e1, n.cross(e1)

    n1 = V((0.75, 0.0, -0.66)).normalized()
    c0 = sum((v.co for v in per), V()) / len(per)
    e1, e2 = ring_frame(n1)
    ang_of = lambda v: math.atan2((v.co - c0).dot(e2), (v.co - c0).dot(e1))
    per.sort(key=ang_of)
    ang0 = [ang_of(v) for v in per]
    SLV = [((0.168, 0.006, 1.256), 0.044), ((0.183, 0.006, 1.195), 0.038), ((0.195, 0.007, 1.130), 0.035), ((0.203, 0.008, 1.085), 0.034),
           ((0.208, 0.006, 1.050), 0.035), ((0.219, 0.000, 0.980), 0.033), ((0.231, -0.006, 0.910), 0.031), ((0.238, -0.010, 0.865), 0.030),
           ((0.2405, -0.011, 0.850), 0.026), ((0.2445, -0.013, 0.822), 0.026)]
    srows = [per]
    for m, (c, r) in enumerate(SLV):
        n = n1 if m == 0 else (V(SLV[min(m + 1, len(SLV) - 1)][0]) - V(SLV[m - 1][0])).normalized()
        e1, e2 = ring_frame(n)
        k = min(1.0, (m + 1) / 3)
        srows.append([V(c) + (e1 * cos(a) + e2 * sin(a)) * r for a in
                      (a0 + (-PI + 2 * PI * (q + 0.5) / len(per) - a0) * k for q, a0 in enumerate(ang0))])
    w_arm = dw("upper_arm.L", "forearm.L")
    P.grid(srows, "Outer", lambda p: {"chest": 0.45, "upper_arm.L": 0.55} if p.z > 1.235 else w_arm(p))

    def card_post(ob):
        # Compression folds at the elbows and gathers above/below the belt
        me = ob.data
        for v in me.vertices:
            x, y, z = v.co
            d = 0.0
            if abs(x) > 0.160 and z < 1.20:
                d += 0.0035 * exp(-((z - 1.075) / 0.05) ** 2) * sin((z - 1.075) * 150.0)
            elif abs(x) <= 0.160:
                d += 0.0030 * exp(-((z - 1.04) / 0.05) ** 2) * (1.0 - exp(-((z - 1.04) / 0.022) ** 2)) * sin(math.atan2(x, -(y - 0.012)) * 22.0)
            v.co += v.normal * d

    parts.append(P.finish([("MIRROR", {"use_mirror_merge": True, "merge_threshold": 0.002, "offset_u": 20.0}),
                           ("SOLIDIFY", {"thickness": 0.004, "offset": 1.0}), SUB],
                          orient=radial(0.012), post=card_post, hull=OL, lining="Outer"))

    # Skirt: A-line with pleat folds growing toward the hem; the hem folds back inside for thickness
    SK = [(0.37, 0.012, 0.206, 0.162, 0.172), (0.46, 0.012, 0.196, 0.152, 0.162), (0.58, 0.012, 0.182, 0.138, 0.150),
          (0.72, 0.012, 0.166, 0.124, 0.138), (0.85, 0.012, 0.152, 0.112, 0.128), (0.93, 0.012, 0.138, 0.104, 0.116),
          (1.00, 0.010, 0.112, 0.090, 0.092), (1.045, 0.010, 0.100, 0.082, 0.082)]
    sts = [2 * PI * j / 40 for j in range(40)]

    def skirt_ring(z, shrink=0.0):
        _, cy, w, f, b = _dtab(SK, z)
        ring = _dring(z, cy, w - shrink, f - shrink, b - shrink, sts, GNF)
        amp = 0.095 * smoothstep(0.97, 0.40, z)
        for p, t in zip(ring, sts):
            k = 1.0 + amp * (0.6 * sin(8.0 * t + 0.7) + 0.4 * sin(13.0 * t + 2.1))
            p.x, p.y = p.x * k, cy + (p.y - cy) * k
        return ring

    def w_skirt(p):
        # Each side follows its own thigh (so a forward leg never pokes through), blending over the centre
        h, l = smoothstep(0.84, 1.0, p.z), smoothstep(-0.07, 0.07, p.x)
        return {"hips": h, "thigh.L": (1.0 - h) * l, "thigh.R": (1.0 - h) * (1.0 - l)}

    P = part("skirt")
    rows = [skirt_ring(0.42, 0.012), skirt_ring(0.372, 0.007)] + [skirt_ring(z) for z in lin(0.37, 1.045, 10)]
    P.grid(rows, "Bottom", w_skirt)
    parts.append(P.finish([SUB], hull=OL))

    # Waist apron over the skirt, with a pocket
    def apron_pt(t, z, off):
        _, cy, w, f, b = _dtab(SK, z)
        p = _dring(z, cy, w + off, f + off, b + off, [t], GNF)[0]
        k = 1.0 + 0.012 * smoothstep(1.0, 0.7, z) * sin(5.0 * t)
        return V((p.x * k, cy + (p.y - cy) * k, z))

    P = part("apron")
    ats = lin(-0.95, 0.95, 15)
    azs = [1.05, 1.02, 0.97, 0.90, 0.82, 0.74, 0.66, 0.60]
    rows = []
    for i, z in enumerate(azs):
        off = 0.006 + 0.012 * smoothstep(1.0, 0.88, z)
        rows.append([apron_pt(t, z + 0.06 * (i / 7) ** 2 * (abs(t) / 0.95) ** 4, off) for t in ats])
    P.grid(rows, "Apron", w_skirt, closed=False)
    P.grid([[apron_pt(t, z, 0.024) for t in lin(-0.36, 0.36, 7)] for z in (0.905, 0.87, 0.83, 0.795)], "Apron", w_skirt, closed=False)
    parts.append(P.finish([("SOLIDIFY", {"thickness": 0.003, "offset": 1.0}), SUB], orient=radial(0.012), hull=OL, lining="Apron"))

    # Belt over the cardigan, buckle, pouch (right hip), shears in a holster (left hip)
    P = part("belt")
    BZ = 1.038
    w_belt = dw("hips", "spine")
    wts = [2 * PI * j / 36 for j in range(36)]

    def belt_pt(t, z, off):
        return _dring(z, 0.012, 0.1205 + off, 0.1000 + off, 0.0990 + off, [t], GNF)[0]

    P.grid([[belt_pt(t, BZ + dz, dr) for t in wts] for dz, dr in
            ((-0.020, -0.004), (-0.019, 0.002), (-0.016, 0.0035), (0.016, 0.0035), (0.019, 0.002), (0.020, -0.004))], "Belt", w_belt)
    bc = belt_pt(0.0, BZ, 0.006)
    P.torus(bc, V((1, 0, 0)), V((0, 0, 1)), 0.019, 0.024, 0.0035, "Brass", w_belt, nu=20, nv=6, nf=5.0)
    P.tube([bc + V((-0.019, -0.001, 0)), bc + V((0.0, -0.003, 0)), bc + V((0.017, -0.002, 0))], [0.002, 0.002, 0.0018], "Brass", w_belt, V((0, 0, 1)), 6)
    up = V((0.0, 0.0, 1.0))
    tp = -0.78
    o = belt_pt(tp, BZ, 0.0)
    nrm = V((o.x, o.y - 0.012, 0.0)).normalized()
    tan = up.cross(nrm)
    P.ellipsoid(o + nrm * 0.020 - up * 0.040, tan * 0.036, up * 0.046, nrm * 0.020, "Belt", w_belt, 12, 8, sq=0.6)
    P.ellipsoid(o + nrm * 0.024 - up * 0.014, tan * 0.038, up * 0.028, nrm * 0.021, "Belt", w_belt, 12, 6, sq=0.7)
    P.ellipsoid(o + nrm * 0.046 - up * 0.030, tan * 0.005, up * 0.005, nrm * 0.004, "Brass", w_belt, 8, 4)
    tp = 0.80
    o = belt_pt(tp, BZ, 0.0)
    nrm = V((o.x, o.y - 0.012, 0.0)).normalized()
    tan = up.cross(nrm)
    P.ellipsoid(o + nrm * 0.012 - up * 0.050, tan * 0.022, up * 0.062, nrm * 0.011, "Belt", w_belt, 10, 8, sq=0.7)
    for g in (1, -1):
        P.torus(o + nrm * 0.014 + up * 0.040 + tan * 0.013 * g, tan, (up + tan * 0.25 * g).normalized(), 0.011, 0.017, 0.0036,
                "FlowerRed", w_belt, nu=14, nv=6)
    P.ellipsoid(o + nrm * 0.014 + up * 0.016, tan * 0.006, up * 0.006, nrm * 0.005, "Brass", w_belt, 8, 4)
    # Apron ties in a bow at the back, cardigan buttons, a small ribbon at the collar
    o = belt_pt(PI, BZ, 0.010)
    for g in (1, -1):
        ax = V((g, 0.0, -0.25)).normalized()
        P.ellipsoid(o + ax * 0.032, ax * 0.034, V((0, 1, 0)).cross(ax) * 0.017, V((0, 0.007, 0)), "Apron", w_belt, 8, 5)
        ax = V((g * 0.22, 0.0, -1.0)).normalized()
        P.ellipsoid(o + ax * 0.055 + V((0, 0.004, 0)), V((0, 1, 0)).cross(ax) * 0.012, ax * 0.055, V((0, 0.004, 0)), "Apron", w_torso, 6, 6)
    P.ellipsoid(o, V((0.010, 0, 0)), V((0, 0, 0.011)), V((0, 0.008, 0)), "Apron", w_belt, 8, 4)
    for z in (0.955, 1.095, 1.155):
        _, cy, cw, cf, cb, gap = _dtab(CARD, z)
        p = _dring(z, cy, cw, cf, cb, [gap + 0.11], GNF)[0]
        nrm = V((p.x * 0.5, p.y - cy, 0.0)).normalized()
        P.ellipsoid(p + nrm * 0.006, V((0, 0, 1)).cross(nrm) * 0.0075, V((0, 0, 0.0075)), nrm * 0.003, "Brass", w_torso, 8, 4)
    o = V((0.0, -0.058, 1.350))
    w_chest = dw("chest", "neck")
    P.ellipsoid(o, V((0.006, 0, 0)), V((0, 0, 0.007)), V((0, 0.005, 0)), "Bottom", w_chest, 8, 4)
    for g in (1, -1):
        ax = V((g, 0.25, 0.22)).normalized()
        P.ellipsoid(o + ax * 0.019, ax * 0.019, V((0, 1, 0)).cross(ax).normalized() * 0.011, V((0, 0.005, 0)), "Bottom", w_chest, 8, 5)
        ax = V((g * 0.30, -0.15, -1.0)).normalized()
        P.ellipsoid(o + ax * 0.026, V((0, 1, 0)).cross(ax).normalized() * 0.007, ax * 0.026, V((0, 0.003, 0)), "Bottom", w_chest, 6, 5)
    parts.append(P.finish(hull=0.0016))

    # Ankle boots with a welted sole
    BOOT = [(0.205, 0.011, 0.032, 0.032, 0.034), (0.236, 0.010, 0.035, 0.035, 0.037), (0.240, 0.010, 0.040, 0.040, 0.042),
            (0.215, 0.011, 0.038, 0.038, 0.040), (0.16, 0.012, 0.035, 0.036, 0.038), (0.11, 0.012, 0.034, 0.038, 0.040),
            (0.080, 0.010, 0.037, 0.070, 0.043), (0.058, 0.008, 0.040, 0.120, 0.045), (0.038, 0.008, 0.042, 0.154, 0.046),
            (0.022, 0.008, 0.042, 0.162, 0.046)]
    fts = [2 * PI * j / 14 for j in range(14)]
    P = part("boots")
    for sfx, g in ((".L", 1), (".R", -1)):
        place = Matrix.Translation((0.077 * g, 0.012, 0.0)) @ Matrix.Rotation(0.10 * g, 4, "Z") @ Matrix.Translation((0.0, -0.012, 0.0))
        w = dw("shin" + sfx, "foot" + sfx)
        P.grid([[place @ p for p in _dring(z, cy, w_, f, b, fts, 2.5)] for z, cy, w_, f, b in BOOT], "Shoes", w, cap1=True)
        P.grid([[place @ p for p in _dring(z, 0.008, 0.042 + d, 0.162 + d, 0.046 + d, fts, 2.5)] for z, d in
                ((0.024, 0.0), (0.021, 0.004), (0.004, 0.004), (0.0, 0.001))], "Belt", w, cap0=True, cap1=True)
    parts.append(P.finish([SUB], hull=OL))

    # -----------------------------------------------------------------------
    # 5. BOUQUET in the left hand (rigid to hand.L; axis u runs along the thumb side of the fist)
    # -----------------------------------------------------------------------
    o, a, b, c = hand_frames[".L"]
    G = o + a * 0.050 + c * 0.027
    u = (b + c * 0.10).normalized()
    v1 = (a - u * a.dot(u)).normalized()
    v2 = u.cross(v1)
    if v2.dot(c) < 0:
        v2 = -v2
    w = "hand.L"
    P = part("bouquet")

    def bq(s, q, r):
        return G + u * s + (v1 * cos(q) + v2 * sin(q)) * r

    qs = [2 * PI * j / 20 for j in range(20)]
    CONE = [(-0.040, 0.013), (0.0, 0.016), (0.045, 0.026), (0.095, 0.043), (0.145, 0.060), (0.190, 0.076)]
    rows = []
    for i, (s, r) in enumerate(CONE):
        k = (i / 5) ** 2
        rows.append([bq(s + 0.045 * k * sin(q), q, r * (1.0 + 0.06 * k * sin(5 * q + 1.0))) for q in qs])
    rows.append([bq(0.186 + 0.045 * sin(q), q, 0.071) for q in qs])
    rows.append([bq(0.10, q, 0.038) for q in qs])
    P.grid(rows, "Kraft", w, cap0=True)
    P.tube([bq(-0.038, 0, 0), bq(-0.07, 0, 0), bq(-0.10, 0, 0.002)], [0.010, 0.009, 0.010], "Foliage", w, v1, 8)
    P.torus(bq(0.012, 0, 0), v1, v2, 0.0185, 0.0185, 0.004, "FlowerYellow", w, nu=14, nv=6)

    def rose(center, up, r, mat):
        e1 = up.cross(v1 if abs(up.dot(v1)) < 0.9 else v2).normalized()
        e2 = up.cross(e1)
        P.ellipsoid(center + up * r * 0.1, e1 * r * 0.62, up * r * 0.70, e2 * r * 0.62, mat, w, 8, 6)
        for n, rad, sz, lift in ((5, 0.58, 0.62, -0.12), (3, 0.34, 0.50, 0.22)):
            for i in range(n):
                q = 2 * PI * i / n + lift * 3
                d = e1 * cos(q) + e2 * sin(q)
                pu = (up * 0.85 + d * 0.5).normalized()
                P.ellipsoid(center + d * r * rad + up * r * lift, pu.cross(d).normalized() * r * sz, pu * r * 0.62,
                            (pu.cross(d)).cross(pu).normalized() * r * 0.16, mat, w, 6, 4)

    def fdir(q, rho):
        return (u + (v1 * cos(q) + v2 * sin(q)) * rho * 14.0).normalized()

    for q, rho, s, r, mat in ((0.3, 0.030, 0.212, 0.034, "FlowerPink"), (2.4, 0.036, 0.206, 0.033, "FlowerPink"), (4.4, 0.034, 0.200, 0.032, "FlowerPink"),
                              (3.3, 0.004, 0.232, 0.026, "FlowerRed")):
        rose(bq(s, q, rho), fdir(q, rho), r, mat)
    for q, rho, s in ((1.35, 0.050, 0.196), (5.45, 0.050, 0.192), (3.45, 0.056, 0.180)):
        daisy(bq(s, q, rho), fdir(q, rho), 0.030, w)
    for i in range(8):
        q = 2 * PI * i / 8 + 0.35
        d = (u * 0.8 + (v1 * cos(q) + v2 * sin(q)) * 0.75).normalized()
        side = u.cross(d).normalized()
        P.ellipsoid(bq(0.165, q, 0.058) + d * 0.030, side * 0.016, d * 0.040, side.cross(d) * 0.003, "Foliage", w, 6, 6)
    for i in range(7):
        q = 2 * PI * i / 7 + 0.9
        P.ellipsoid(bq(0.225 + 0.012 * sin(3 * q), q, 0.050 + 0.012 * cos(2 * q)), v1 * 0.006, u * 0.006, v2 * 0.006, "FlowerWhite", w, 6, 4)
    parts.append(P.finish(hull=0.0016))

    # -----------------------------------------------------------------------
    # 6. JOIN, pack UVs per material, clean weights
    # -----------------------------------------------------------------------
    bpy.ops.object.select_all(action="DESELECT")
    for ob in parts:
        ob.select_set(True)
    char_obj = parts[0]
    bpy.context.view_layer.objects.active = char_obj
    bpy.ops.object.join()
    char_obj.name = "body-mesh"
    mesh = char_obj.data
    mesh.name = "body-mesh"
    mesh.materials.pop(index=len(mat_list))
    bpy.data.materials.remove(lining_tmp)

    # Face / eye / lip slots keep their hand-placed UVs; everything else has metric islands packed to 0..1
    bpy.ops.object.mode_set(mode="EDIT")
    for key in mat_list:
        if key in ("Face", "Eye", "EyeWhite", "EyeDark", "Lip", "Outline"):
            continue
        bpy.ops.mesh.select_all(action="DESELECT")
        char_obj.active_material_index = M[key]
        bpy.ops.object.material_slot_select()
        bpy.ops.mesh.hide(unselected=True)  # UV operators only see visible faces
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(rotate=False, margin=0.003)
        bpy.ops.mesh.reveal()
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)

    # Convert to Y-up, +Z-front so the root rotation is (0,0,0) in Unity
    rot_to_yup = Matrix.Rotation(-math.pi * 0.5, 4, "X")
    mesh.transform(rot_to_yup)
    mesh.update()

    arm_data = bpy.data.armatures.new("root_data")
    arm_obj = bpy.data.objects.new("root", arm_data)
    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    ebones = {}
    for bname, (head, tail, parent) in bones.items():
        eb = arm_data.edit_bones.new(bname)
        eb.head = rot_to_yup @ head
        eb.tail = rot_to_yup @ tail
        if parent:
            eb.parent = ebones[parent]
        ebones[bname] = eb
    bpy.ops.object.mode_set(mode="OBJECT")

    char_obj.parent = arm_obj
    mod = char_obj.modifiers.new(name="Armature", type="ARMATURE")
    mod.object = arm_obj
    arm_obj.rotation_euler = (math.pi * 0.5, 0.0, 0.0)

    _darae_action(arm_obj, "idle", False)
    _darae_action(arm_obj, "walk", True)
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
    print(f"Exported detailed florist character {out_path}")


def _darae_action(arm_obj, action_name, is_walk):
    """idle / walk for Darae's rig. Rotations are written about authoring-space axes (X = her left, Y = back, Z = up)."""
    if not arm_obj.animation_data:
        arm_obj.animation_data_create()
    act = bpy.data.actions.new(name=action_name)
    arm_obj.animation_data.action = act
    to_arm = Matrix.Rotation(-math.pi * 0.5, 3, "X")
    X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
    frame = 1

    def pose(bname, *rots, move=None):
        pb = arm_obj.pose.bones[bname]
        pb.rotation_mode = "QUATERNION"
        R = pb.bone.matrix_local.to_3x3()
        q = Quaternion()
        for axis, ang in rots:  # applied right to left
            q = q @ Quaternion(to_arm @ axis, ang)
        pb.rotation_quaternion = (R.inverted() @ q.to_matrix() @ R).to_quaternion()
        pb.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        if move is not None:
            pb.location = R.inverted() @ (to_arm @ Vector(move))
            pb.keyframe_insert(data_path="location", frame=frame)

    total = 40 if is_walk else 60
    for frame in range(1, total + 2, 2):
        ph = 2.0 * math.pi * (frame - 1) / total
        s, c = math.sin(ph), math.cos(ph)
        # Left arm cradles the bouquet in both clips
        pose("forearm.L", (Z, -0.70), (X, -1.45 + 0.02 * s))
        pose("hand.L", (X, 0.0))
        if not is_walk:
            pose("hips", move=(0, 0, 0))
            pose("spine", (X, 0.010 * s))
            pose("chest", (X, 0.012 * s))
            pose("neck", (X, -0.010 * s))
            pose("head", (Y, 0.05 + 0.02 * s), (X, 0.02 * c), (Z, 0.04 * s))
            pose("upper_arm.L", (X, -0.08 + 0.01 * s))
            pose("upper_arm.R", (X, -0.04 + 0.02 * s))
            pose("forearm.R", (X, -0.20 + 0.02 * c))
            pose("hand.R", (X, -0.08))
            for b in ("thigh", "shin", "foot"):
                pose(b + ".L")
                pose(b + ".R")
        else:
            A = 0.30
            kl, kr = 0.65 * max(0.0, c) ** 2, 0.65 * max(0.0, -c) ** 2
            pose("hips", (Z, -0.05 * s), (X, 0.03), move=(0, 0, 0.012 * math.cos(2 * ph) - 0.012))
            pose("spine", (Z, 0.03 * s))
            pose("chest", (Z, 0.06 * s))
            pose("neck", (Z, -0.02 * s))
            pose("head", (Z, -0.03 * s), (Y, 0.03), (X, -0.02))
            pose("thigh.L", (X, -A * s))
            pose("thigh.R", (X, A * s))
            pose("shin.L", (X, kl))
            pose("shin.R", (X, kr))
            pose("foot.L", (X, 0.6 * A * s - 0.5 * kl))
            pose("foot.R", (X, -0.6 * A * s - 0.5 * kr))
            pose("upper_arm.L", (X, -0.08 + 0.03 * math.sin(2 * ph)))
            pose("upper_arm.R", (X, -0.05 - 0.36 * s))
            pose("forearm.R", (X, -0.30 - 0.15 * s))
            pose("hand.R", (X, -0.08))


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
    build_florist_darae("Character_Darae")

    print("ALL BLENDER ASSETS GENERATED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
