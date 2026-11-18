"""Paint Darae's final UV maps. Use --phase1 to regenerate the original tile study."""
import os
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
try:
    import numpy as np
except ModuleNotFoundError:
    # The project's existing Python environment includes NumPy on the artist machine.
    python = ROOT / "tools/finetune/work/.venv/bin/python"
    if python.is_file() and Path(sys.executable) != python:
        os.execv(python, [str(python), "-B", __file__, *sys.argv[1:]])
    raise SystemExit("Run with Python 3 and NumPy installed.")

OUT = ROOT / "Assets/Blender/Textures"
SHEET = ROOT / "Logs/darae_tex_phase1.png"
PALETTE = {
    "Knit": (.56, .72, .58), "Cotton": (.98, .95, .88),
    "Linen": (.80, .47, .34), "Leather": (.55, .32, .17),
    "Kraft": (.80, .60, .38), "Hair": (.28, .16, .11), "Eye": (.50, .26, .10),
}
TAU = 2 * np.pi
SKIN = np.array((.96, .82, .74), dtype=np.float32)
APRON = (.93, .89, .78)


def write_png(path, pixels):
    height, width, channels = pixels.shape
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data)))
    header = struct.pack(">2I5B", width, height, 8, {3: 2, 4: 6}[channels], 0, 0, 0)
    # PNG's Sub filter substantially reduces the size of painted gradients.
    residual = pixels.copy()
    residual[:, 1:] -= pixels[:, :-1]
    rows = b"".join(b"\x01" + row.tobytes() for row in residual)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(rows, 7)) + chunk(b"IEND", b""))


def grid(width, height):
    y, x = np.ogrid[:height, :width]
    return (x + .5) / width, (y + .5) / height


def smooth(x):
    t = np.clip(x, 0, 1)
    return t * t * (3 - 2 * t)


def noise(x, y, cols, rows, rng):
    """Bicubic smoothstep between random values on a torus."""
    knots = rng.uniform(-1, 1, (rows, cols))
    x, y = x * cols, y * rows
    i, j = np.floor(x).astype(int), np.floor(y).astype(int)
    a, b = smooth(x - i), smooth(y - j)
    low = (1-a) * knots[j % rows, i % cols] + a * knots[j % rows, (i+1) % cols]
    high = (1-a) * knots[(j+1) % rows, i % cols] + a * knots[(j+1) % rows, (i+1) % cols]
    return (1-b) * low + b * high


def brush_marks(rng, count, lengths, widths, angles, bend=0):
    """Tapered, curved ink strokes in pixel units, wrapping across tile edges."""
    size = 1024
    ink = np.zeros((size, size))
    for _ in range(count):
        cx, cy = rng.uniform(0, size, 2)
        length, width = rng.uniform(*lengths), rng.uniform(*widths)
        curve, angle = rng.uniform(-bend, bend), rng.uniform(*angles)
        dx, dy = np.cos(angle), np.sin(angle)
        rx = int(np.ceil(abs(dx)*length + abs(dy)*(width + abs(curve)))) + 1
        ry = int(np.ceil(abs(dy)*length + abs(dx)*(width + abs(curve)))) + 1
        ix = np.arange(int(cx)-rx, int(cx)+rx+1)
        iy = np.arange(int(cy)-ry, int(cy)+ry+1)
        x, y = ix[None, :] - cx, iy[:, None] - cy
        along = (x*dx + y*dy) / length
        across = (y*dx - x*dy - curve*(1 - along**2)) / width
        stamp = smooth(1 - along**2 - across**2)
        ink[np.ix_(iy % size, ix % size)] += rng.uniform(.45, 1) * stamp
    return ink


def knit(u, y, rng):
    dye = noise(u, y, 6, 7, rng)
    col = 24*u + .14*noise(u, y, 15, 10, rng)
    row = 27*y + .12*noise(u, y, 17, 12, rng)
    lane = np.floor(col).astype(int)
    x = col % 1 - .5
    row += .045*np.sin(TAU*lane/3)
    t = 1 - row % 1
    rib = (lane % 3 == 1)
    loop = np.zeros_like(x)
    yarn_light = np.zeros_like(x)
    # The two arms of a stitch tuck beneath the next row. Every third wale is recessed.
    for overlap in (-1, 0, 1):
        progress = (t + overlap + .135)/1.27
        p = np.clip(progress, 0, 1)
        center = .016 + .326*p + .028*np.sin(TAU*p-.45)
        half_width = .069 + .113*np.sin(np.pi*p)**.76
        end = (progress-p) / .11
        for side in (-1, 1):
            offset = (x - side*center) / half_width
            section = np.maximum(0, 1 - offset**2 - end**2)
            crown = section**.72 * (.76 + .24*np.sin(np.pi*p))
            twist = np.cos(TAU*(3.7*p + side*.45*offset))
            light = crown * (.84 - .26*offset + .17*twist)
            yarn_light = np.where(crown > loop, light, yarn_light)
            loop = np.maximum(loop, crown)
    purl = np.maximum(0, 1 - (x/.33)**2 - ((t-.47-.13*np.cos(TAU*x))/.19)**2)**.8
    height = np.where(rib, .58*loop + .31*purl, loop)
    fleck = noise(u, y, 140, 120, rng)
    tone = .098*np.where(rib, .52*yarn_light + .33*purl - .11, yarn_light)
    return tone + .018*dye + .008*fleck, 1.85*height + .12*fleck


def plain_weave(u, y, rng, linen=False):
    cols, rows = (70, 62) if linen else (120, 126)
    wobble = .18 if linen else .038
    warp = cols*u + wobble*noise(u, y, cols//2, 12, rng)
    weft = rows*y + wobble*noise(u, y, 14, rows//2, rng)
    a, b = np.cos(TAU*warp), np.cos(TAU*weft)
    crossing = np.cos(np.pi*warp)*np.cos(np.pi*weft)
    yarn_a = (.5 + .5*a)**1.65 * (.73 + .27*crossing)
    yarn_b = (.5 + .5*b)**1.65 * (.73 - .27*crossing)
    weave = np.maximum(yarn_a, yarn_b)
    dye = noise(u, y, 9, 11, rng)
    if linen:
        flax = (brush_marks(rng, 1150, (6, 28), (1.1, 2.8), (-.045, .045), .45)
                + brush_marks(rng, 800, (5, 20), (1, 2.6), (1.53, 1.61), .45))
        slub = (yarn_a*noise(u, y, 128, 15, rng) + yarn_b*noise(u, y, 16, 128, rng))
        return .045*weave + .030*slub + .055*flax + .011*dye, 1.1*weave + .52*slub + .80*flax
    return .016*weave + .004*dye, .41*weave


def leather(u, y, rng):
    # Distorted pebble boundaries dissolve into soft patches of unbroken hide.
    x = 43*u + .38*noise(u, y, 26, 25, rng)
    z = 57*y + .44*noise(u, y, 29, 34, rng)
    i, j = np.floor(x).astype(int), np.floor(z).astype(int)
    seeds = rng.uniform(.09, .91, (57, 43, 2))
    first = np.full_like(x, 10.)
    second = first.copy()
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            point = seeds[(j+dy) % 57, (i+dx) % 43]
            dist = np.hypot(i+dx+point[..., 0]-x, j+dy+point[..., 1]-z)
            second = np.minimum(second, np.maximum(first, dist))
            first = np.minimum(first, dist)
    dye = noise(u, y, 7, 9, rng)
    grain = smooth((second-first)/.39) * smooth(.45 + .56*noise(u, y, 23, 27, rng))
    pores = brush_marks(rng, 4500, (1.5, 4), (.9, 1.7), (-.7, .7))
    nap = noise(u, y, 184, 160, rng)
    return .033*grain + .014*dye - .031*pores + .008*nap, .91*grain - .51*pores + .17*nap


def kraft(u, y, rng):
    # Neighboring triangular facets meet on a fold; the lattice is gently distorted.
    x = 6*u + .48*noise(u, y, 5, 6, rng)
    z = 7*y + .45*noise(u, y, 6, 6, rng)
    i, j = np.floor(x).astype(int), np.floor(z).astype(int)
    fx, fy = x-i, z-j
    heights = rng.uniform(-1, 1, (7, 6))
    a, b = heights[j % 7, i % 6], heights[j % 7, (i+1) % 6]
    c, d = heights[(j+1) % 7, i % 6], heights[(j+1) % 7, (i+1) % 6]
    fold = a + (b-a)*fx + (c-a)*fy + (a-b-c+d)*np.minimum(fx, fy)
    light = (np.roll(fold, 1, axis=1) - np.roll(fold, -1, axis=1))*22
    crease = brush_marks(rng, 53, (18, 78), (1.3, 3), (-np.pi, np.pi), 4)
    lip = np.roll(crease, (-2, -2), (0, 1))
    pulp = brush_marks(rng, 6700, (1.2, 5.6), (.7, 1.4), (-.85, .65), .5)
    dark_fibre = brush_marks(rng, 2250, (1.4, 7), (.65, 1.5), (-1.3, 1.4), .6)
    cloud = noise(u, y, 57, 54, rng)
    tooth = noise(u, y, 270, 250, rng)
    tone = (.026*fold + .030*light + .032*lip - .039*crease
            + .035*pulp - .033*dark_fibre + .010*cloud + .008*tooth)
    return tone, 4.8*fold - 1.05*crease + .32*pulp - .30*dark_fibre + .38*cloud + .12*tooth


def normal_map(height, wrap_v=True):
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * .5
    dy = ((np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * .5
          if wrap_v else np.gradient(height, axis=0))
    # Image row indices grow opposite to UV V. In tangent space N = (-h_u, -h_v, 1).
    normal = np.stack((-dx, dy, np.ones_like(dx)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return quantize(.5 + .5*normal)


def quantize(rgb):
    return np.rint(255*np.clip(rgb, 0, 1)).astype(np.uint8)


def hair():
    rng = np.random.default_rng(2906)
    u, y = grid(512, 1024)
    v = 1 - y
    # Bow whole locks first so fine strokes and the reflected light follow the same flow.
    flow = (u + .013*np.sin(TAU*(2*u + .68*v)) + .008*np.sin(TAU*(4*u - .57*v))
            + .008*np.sin(TAU*(v + .15)) + .004*noise(u, v, 9, 4, rng))
    lock = 9*flow + .24*np.sin(TAU*3*flow) + .12*np.sin(TAU*(flow - .3*v))
    frac = lock % 1
    body = np.sin(np.pi*frac)**.7
    ridge = np.exp(-((frac-.18)/.15)**2)
    ink = np.exp(-(np.minimum(frac, 1-frac)/.057)**2)
    strand = noise(flow, v, 245, 5, rng)
    ribbon = noise(flow, v, 64, 4, rng)
    comb = np.cos(TAU*(173*flow + .24*noise(flow, v, 55, 4, rng)))
    tone = .058*body + .019*ridge - .034*ink + .027*ribbon + .016*strand + .005*comb
    rgb = tone[..., None] * (1, .80, .66)
    rgb += ((.052*v - .035*np.exp(-(v/.14)**2))[..., None] * (1, .71, .43))
    axis = .30 + .022*np.sin(TAU*(flow + .08)) + .011*np.cos(TAU*4*flow)
    axis += .018*(frac-.5) + .009*ribbon
    width = .048 + .019*body
    halo = np.exp(-((v-axis)/width)**2)
    glint = np.exp(-((v-axis+.008)/(.009+.017*body))**4)
    glint *= smooth((body+.53*ribbon-.57)/.42) * (.80 + .20*strand)
    rgb += halo[..., None]*(.116, .072, .041) + glint[..., None]*(.128, .084, .044)
    silk = np.exp(-((frac-.29-.11*v)/.051)**2) * smooth(ribbon+.62)
    rgb += (silk*(.25+.75*np.sin(np.pi*v)**2))[..., None]*(.046, .030, .019)
    rgb += (smooth((v-.66)/.34)*body)[..., None]*(.030, .014, .006)
    rgb += np.array(PALETTE["Hair"]) - rgb.mean(axis=(0, 1))
    relief = 2.4*body + .60*ridge - .60*ink + .33*ribbon + .22*strand + .08*comb
    return quantize(rgb), normal_map(relief, wrap_v=False)


def blend(rgb, color, mask):
    return rgb + (color-rgb)*np.clip(mask[..., None], 0, 1)


def eye(width=512, height=512, radius_u=.45, radius_v=.45):
    u, y = grid(width, height)
    x, z = (u-.5)/radius_u, (y-.5)/radius_v
    r, theta = np.hypot(x, z), np.arctan2(z, x)
    lower = smooth((z+.19)/1.08)
    shadow = smooth((.15-z)/.97)
    rgb = np.zeros((*r.shape, 3)) + (.586, .274, .072)
    rgb += lower[..., None]*(.205, .18, .077) - shadow[..., None]*(.19, .125, .024)
    lash = smooth((-.28 + .20*x*x - z)/.35)
    rgb = blend(rgb, (.225, .111, .128), .43*lash)
    # Soft radial fans underlie the separately painted, broken amber strokes.
    rays = (np.sin(19*theta + 1.4*np.sin(3*theta) + 2*r)
            + .55*np.sin(33*theta - 3*r + np.cos(7*theta)))
    fan = (smooth((r-.36)/.18)*smooth((.93-r)/.17)*(.27+.73*lower))
    rgb += (fan*rays)[..., None]*(.052, .033, .012)
    collar = .52 + .025*np.sin(12*theta+.8*np.cos(5*theta)) + .015*np.cos(21*theta)
    rgb += (np.exp(-((r-collar)/.038)**2)*(.18+.82*lower))[..., None]*(.12, .08, .024)
    inside = smooth((collar-r)/.035)*smooth((r-.33)/.12)
    rgb = blend(rgb, (.48, .226, .102), inside*(.12+.37*lower))
    tide = .71 + .047*np.sin(6*theta+.7*np.sin(3*theta))
    copper = smooth((r-tide)/.057)*smooth((.91-r)/.095)*lower
    rgb = blend(rgb, (.94, .596, .238), .51*copper)
    rng = np.random.default_rng(2907)
    amber = np.zeros_like(r)
    for group in (.12, .55, .98, 1.56, 2.11, 2.63, 3.02):
        for angle in group + np.cumsum(rng.uniform(.035, .093, rng.integers(2, 5))):
            center, length = rng.uniform(.60, .73), rng.uniform(.050, .119)
            along = (r-center)/length
            delta = np.arctan2(np.sin(theta-angle), np.cos(theta-angle))
            lean = rng.uniform(.30, .97)*np.cos(angle)
            across = (delta - lean*(r-center) - .021*along**2)/rng.uniform(.013, .044)
            stroke = np.abs(along) + np.abs(across)*(.90+.35*np.clip(along, -1, 1))
            amber = np.maximum(amber, smooth((1-stroke)*3)*rng.uniform(.25, .67))
    rgb = blend(rgb, (.95, .64, .25), amber*(.28+.72*lower))
    # Asymmetric arcs pick out the copper at the bottom of the anterior iris.
    for angle, radius, span in ((.81, .796, .15), (1.78, .794, .22), (2.43, .799, .13)):
        along = (theta-angle)/span
        across = (r-radius-.026*along-.016*along**2)/.013
        rgb = blend(rgb, (.97, .64, .28), .72*smooth(1-along**2-across**2))
    rim = smooth((r-.904)/.055)
    rgb = blend(rgb, (.195, .097, .093), .93*rim)
    pupil = np.hypot(x/.97, (z+.045)/1.08)
    rgb = blend(rgb, (.300, .139, .082), smooth((.384-pupil)/.045)*.85)
    pupil_color = np.array((.106, .059, .085)) + smooth((z+.18)/.58)[..., None]*(.126, .046, .024)
    rgb = blend(rgb, pupil_color, smooth((.350-pupil)/.012))
    # A short golden bounce follows the curvature just inside the lower limbus.
    bounce = np.exp(-((r-.851)/.014)**2) * smooth((z-.49)/.32)
    rgb = blend(rgb, (.98, .69, .33), .66*bounce)
    for cx, cy, w, h, tilt in [(-.315, -.385, .153, .102, -.58),
                                 (.376, .33, .054, .042, -.57)]:
        dx, dy = x-cx, z-cy
        dist = np.hypot((dx*np.cos(tilt)+dy*np.sin(tilt))/w,
                        (dy*np.cos(tilt)-dx*np.sin(tilt))/h)
        rgb = blend(rgb, (.98, .73, .47), .26*np.exp(-(dist/1.30)**4))
        rgb = blend(rgb, (1., .962, .855), smooth((1.04-dist)/.10))
    alpha = smooth((1-r)*min(radius_u*width, radius_v*height) + .5)
    return quantize(np.dstack((rgb, alpha)))


def eye_atlas():
    # The full disc on the mesh is 12 x 14.8 mm in radius; the lids clip its poles.
    iris = eye(512, 1024, radius_u=.408, radius_v=.247)
    rim = np.array((52, 26, 25))
    half = np.rint(blend(rim, iris[..., :3], iris[..., 3]/255.)).astype(np.uint8)
    return np.tile(half, (1, 2, 1))


def face():
    u, y = grid(2048, 2048)
    u, v = u.astype(np.float32), (1-y).astype(np.float32)
    # Work in upright face UV. 'side' measures distance from the midline on either cheek.
    side = np.abs(u-.5)
    rgb = np.empty((2048, 2048, 3), dtype=np.float32)
    rgb[:] = SKIN

    def glaze(color, opacity):
        nonlocal rgb
        rgb = blend(rgb, np.asarray(color, dtype=np.float32), opacity)

    def oval(dx, dv, width, height):
        return np.exp(-((dx/width)**2 + (dv/height)**2))

    # A soft cel terminator follows the chin contour. Both shades fade before the back island.
    front = smooth((.364-side)/.032)
    jaw = np.interp(side, [0, .065, .13, .20, .26, .31, .35],
                    [.045, .054, .097, .153, .212, .289, .36]).astype(np.float32)
    glaze((.78, .56, .54), .20*front*smooth((jaw+.030-v)/.030)*smooth((v-jaw+.045)/.028))
    hairline = .75 + .025*np.cos(9*(u-.48)) + .009*np.sin(18*u)
    glaze((.71, .48, .47), .21*front*smooth((v-hairline+.018)/.027)
          * smooth((hairline+.076-v)/.045))
    glaze((.95, .61, .56), .23*oval(side-.318, v-.328, .038, .10)*front)

    cheek = side-.21
    cheek_v = v-.279-.11*cheek
    glaze((.95, .51, .52), .48*oval(cheek, cheek_v, .093, .045))
    glaze((1., .66, .60), .20*oval(cheek+.012, cheek_v+.009, .055, .025))
    for offset, length in ((-.031, .007), (-.016, .010), (0, .012), (.017, .009), (.031, .006)):
        along = (cheek_v+.001- .06*offset)/length
        across = (cheek-offset-.005*along)/.0017
        glaze((.82, .45, .45), .23*np.exp(-across**2)*smooth(1-along**2))

    # Follow the modeler's almond opening, with space for the separate upper lash strip.
    a = (side-.164)/.0924
    arch = np.maximum(0, 1-a*a)
    upper = .374 + .063*arch**.60 - .005*a
    lower = .374 - .044*arch**.75 - .005*a
    span = smooth((1-np.abs(a))/.30)
    glaze((.82, .56, .52), .25*span*np.exp(-((v-upper-.009)/.016)**2))
    crease = upper + .025 + .004*a
    glaze((.65, .41, .39), .37*span*np.exp(-((v-crease)/.0027)**2))
    glaze((.93, .62, .58), .20*span*np.exp(-((v-lower+.008)/.012)**2))

    glaze((.97, .54, .51), .36*oval(u-.5, v-.252, .034, .023))
    glaze((1., .91, .80), .49*oval(u-.498, v-.264, .011, .006))
    # Feathered rose follows the smile around the existing mouth line.
    lip_x = (u-.5)/.059
    lip_v = .163 + .017*np.minimum(lip_x**2, 1.2)
    lip_span = smooth((1-np.abs(lip_x))/.52)
    glaze((.89, .55, .53), .32*lip_span*np.exp(-((v-lip_v+.004)/.012)**2))
    glaze((1., .88, .79), .30*oval(u-.497, v-.151, .022, .003))
    return quantize(rgb)


def skin(u, y):
    # Packed islands may abut anywhere. Limit warmth variation to two sRGB codes.
    warmth = .5 + .5*noise(u, y, 6, 7, np.random.default_rng(2910))
    return quantize(SKIN + warmth[..., None]*(.002, -.005, -.005))


# Fixed 5x7 lettering keeps the review sheet identical without Pillow or system fonts.
GLYPHS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 /+-.", (
    "7e1111117e", "7f49494936", "3e41414122", "7f4141221c", "7f49494941",
    "7f09090901", "3e4141497a", "7f0808087f", "00417f4100", "2040413f01",
    "7f08142241", "7f40404040", "7f020c027f", "7f0408107f", "3e4141413e",
    "7f09090906", "3e4151215e", "7f09192946", "4649494931", "01017f0101",
    "3f4040403f", "1f2040201f", "3f4038403f", "6314081463", "0708700807",
    "6151494543", "3e5149453e", "00427f4000", "4261514946", "2141454b31",
    "1814127f10", "2745454539", "3c4a494930", "0171090503", "3649494936",
    "064949291e", "0000000000", "2010080402", "08083e0808", "0808080808", "0060600000",
)))


def label(canvas, x, y, words, scale, ink):
    for letter in words:
        bits = np.frombuffer(bytes.fromhex(GLYPHS[letter]), dtype=np.uint8)
        glyph = ((bits[None, :] >> np.arange(7)[:, None]) & 1).astype(bool)
        mask = glyph.repeat(scale, axis=0).repeat(scale, axis=1)
        canvas[y:y+7*scale, x:x+5*scale][mask] = ink
        x += 6*scale


def resize(image, w, h):
    """Box-average samples, including subpixel coverage at both ends of each box."""
    def boxes(pixels, size):
        n = len(pixels)
        edges = np.linspace(0, n, size+1)
        index = edges.astype(int)
        prefix = np.zeros((n+1, *pixels.shape[1:]), dtype=np.float64)
        np.cumsum(pixels, axis=0, out=prefix[1:])
        area = prefix[index] + pixels[np.minimum(index, n-1)]*(edges-index)[:, None, None]
        return np.diff(area, axis=0)*(size/n)
    vertical = boxes(image, h)
    return np.rint(boxes(vertical.swapaxes(0, 1), w).swapaxes(0, 1)).astype(np.uint8)


def contact_sheet(maps):
    canvas = np.full((1200, 1664, 3), (243, 240, 230), dtype=np.uint8)
    ink, muted = (42, 58, 49), (86, 99, 86)
    canvas[:109] = ink
    canvas[109:115] = (152, 175, 144)
    label(canvas, 42, 28, "DARAE", 8, (247, 241, 222))
    label(canvas, 325, 44, "FLORIST / TEXTURE STUDY", 3, (222, 228, 209))
    label(canvas, 1368, 44, "PHASE 01", 4, (222, 228, 209))
    for x, title in [(42, "SURFACE"), (265, "ALBEDO / 1X SEAM DETAIL"),
                     (736, "2X2 REPEAT"), (955, "NORMAL / 1X")]:
        label(canvas, x, 150, title, 2, muted)
    canvas[140:1156, 1140:1142] = (194, 199, 181)
    for index, (name, use) in enumerate(zip(
            list(PALETTE)[:5], ("CARDIGAN", "BLOUSE", "SKIRT / APRON", "BELT / SHOES", "BOUQUET WRAP"))):
        y = 190 + index*193
        albedo, normal = maps[name]
        canvas[y-9:y-8, 42:1117] = (201, 202, 187)
        canvas[y+25:y+37, 43:81] = quantize(PALETTE[name])
        label(canvas, 42, y+55, name.upper(), 4, ink)
        label(canvas, 43, y+103, use, 2, muted)
        iy = np.arange(-80, 80) % 1024
        canvas[y:y+160, 265:703] = albedo[np.ix_(iy, np.arange(-219, 219) % 1024)]
        thumb = resize(albedo, 80, 80)
        canvas[y:y+160, 736:896] = np.tile(thumb, (2, 2, 1))
        canvas[y:y+160, 955:1115] = normal[np.ix_(iy, iy)]

    label(canvas, 1180, 147, "HAIR", 4, ink)
    label(canvas, 1180, 202, "ROOT / V0", 2, muted)
    hair_rgb, hair_n = maps["Hair"]
    canvas[230:670, 1180:1400] = resize(hair_rgb[::-1], 220, 440)
    label(canvas, 1180, 682, "TIP / V1", 2, muted)
    canvas[230:494, 1454:1586] = resize(hair_n[::-1], 132, 264)
    label(canvas, 1454, 507, "NORMAL", 2, muted)
    canvas[732:733, 1180:1622] = (201, 202, 187)
    label(canvas, 1180, 757, "IRIS", 4, ink)
    label(canvas, 1439, 767, "RGBA", 2, muted)
    rgba = maps["Eye"][0]
    iy, ix = np.indices(rgba.shape[:2])
    backing = np.where((((ix//32 + iy//32) % 2) == 0)[..., None],
                       (218, 217, 203), (229, 226, 212))
    eye_rgb = blend(backing, rgba[..., :3], rgba[..., 3]/255.)
    canvas[803:1155, 1180:1532] = resize(eye_rgb, 352, 352)
    return canvas


def check_edges(pixels, wrap_v):
    """A tile boundary should behave like a single ordinary texel step inside the tile."""
    values = pixels.astype(np.int16)
    scores = []
    for axis in ((1, 0) if wrap_v else (1,)):
        inner = np.diff(values, axis=axis).astype(np.float32)
        seam = (values.take(0, axis) - values.take(-1, axis)).astype(np.float32)
        rms = np.sqrt(np.mean(seam**2))
        typical = np.sqrt(np.mean(inner**2))
        assert rms <= 1 + 1.75*typical, (axis, rms, typical)
        assert np.percentile(abs(seam), 99.5) <= 3 + 2.2*np.percentile(abs(inner), 99.5)
        scores.append(f"{rms:.2f}")
    return "/".join(scores)


def check_eye_atlas(atlas):
    assert atlas.shape == (1024, 1024, 3) and atlas.dtype == np.uint8
    assert np.array_equal(atlas[:, :512], atlas[:, 512:])
    for start, center_u in ((0, .25), (512, .75)):
        half = atlas[:, start:start+512]
        y, x = np.nonzero(np.any(half != atlas[0, 0], axis=-1))
        bounds_u = (start + x.min() + .5)/1024, (start + x.max() + .5)/1024
        bounds_v = 1-(y.max()+.5)/1024, 1-(y.min()+.5)/1024
        assert abs(sum(bounds_u)/2-center_u) < .002 and abs(sum(bounds_v)/2-.5) < .002
        assert .400 < bounds_u[1]-bounds_u[0] < .415 and .48 < bounds_v[1]-bounds_v[0] < .50
        y, x = np.nonzero((half[..., 0] > 247) & (half[..., 1] > 229))
        assert np.mean(x < 256) > .8 and np.mean(y < 512) > .8


def self_check(maps):
    summaries = []
    for name, (albedo, normal) in maps.items():
        if name == "EyeAtlas":
            check_eye_atlas(albedo)
            summaries.append("Darae_EyeAtlas_Albedo.png  UV centers (.25,.5), (.75,.5), upper-left light")
            continue
        expected = (512, 512, 4) if name == "Eye" else (1024, 512 if name == "Hair" else 1024, 3)
        if name == "Face":
            expected = (2048, 2048, 3)
        assert albedo.shape == expected and albedo.dtype == np.uint8
        if name == "Eye":
            alpha = albedo[..., 3]
            assert alpha[0, 0] == 0 and alpha[256, 256] == 255
            assert .62 < alpha.mean()/255 < .65
            mean = np.average(albedo[..., :3].reshape(-1, 3), axis=0, weights=alpha.ravel())/255
        else:
            mean = albedo.mean(axis=(0, 1))/255
        base = {"Face": SKIN, "Skin": SKIN, "Apron": APRON}.get(name, PALETTE.get(name))
        assert np.all(abs(mean - base) <= .03), (name, mean)
        if name == "Face":
            # Test the central worn area too, so empty atlas space cannot hide a color shift.
            worn = albedo[480:1830, 570:1478].mean(axis=(0, 1))/255
            assert np.max(abs(mean-SKIN)) < .012 and np.max(abs(worn-SKIN)) < .020
        if name == "Skin":
            assert np.max(np.ptp(albedo, axis=(0, 1))) <= 2
        summary = "mean " + "/".join(f"{c:.3f}" for c in mean)
        if normal is not None:
            assert normal.shape == expected and normal.dtype == np.uint8
            vector = normal.astype(np.float32)/127.5 - 1
            assert np.all(vector[..., 2] > 0)
            assert np.max(abs(np.linalg.norm(vector, axis=-1) - 1)) < .007
            wrap_v = name != "Hair"
            summary += " | seam RMS " + check_edges(albedo, wrap_v)
            summaries.append(f"Darae_{name}_Albedo.png  {summary}")
            summaries.append(f"Darae_{name}_Normal.png  unit Y+ | seam RMS {check_edges(normal, wrap_v)}")
        elif name == "Eye":
            summaries.append(f"Darae_Eye_Albedo.png  {summary} | alpha {alpha.mean()/255:.3f}")
        else:
            summaries.append(f"Darae_{name}_Albedo.png  {summary}")
    return summaries


def phase_one():
    u, y = grid(1024, 1024)
    maps = {}
    painters = (knit, plain_weave, lambda u, y, rng: plain_weave(u, y, rng, linen=True),
                leather, kraft)
    for seed, (name, painter) in enumerate(zip(PALETTE, painters), 2901):
        tone, relief = painter(u, y, np.random.default_rng(seed))
        rgb = PALETTE[name] + (tone-tone.mean())[..., None]*np.array((1, .90, .76))
        maps[name] = quantize(rgb), normal_map(relief)
    maps["Hair"] = hair()
    maps["Eye"] = eye(), None
    return maps


def main():
    if sys.argv[1:] == ["--phase1"]:
        maps = phase_one()
    elif not sys.argv[1:]:
        u, y = grid(1024, 1024)
        tone, relief = plain_weave(u, y, np.random.default_rng(2903), linen=True)
        linen = APRON + (tone-tone.mean())[..., None]*np.array((1, .90, .76))
        maps = {"Face": (face(), None), "Skin": (skin(u, y), None), "EyeAtlas": (eye_atlas(), None),
                "Apron": (quantize(linen), normal_map(relief))}
    else:
        raise SystemExit("Usage: paint_darae_textures.py [--phase1]")
    summaries = self_check(maps)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (albedo, normal) in maps.items():
        write_png(OUT / f"Darae_{name}_Albedo.png", albedo)
        if normal is not None:
            write_png(OUT / f"Darae_{name}_Normal.png", normal)
    if "Eye" in maps:
        SHEET.parent.mkdir(parents=True, exist_ok=True)
        write_png(SHEET, contact_sheet(maps))
    print("\n".join(summaries))


if __name__ == "__main__":
    main()
