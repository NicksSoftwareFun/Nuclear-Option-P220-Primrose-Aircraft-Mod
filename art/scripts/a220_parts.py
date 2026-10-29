"""A220-300 first-pass model, split into the damage parts of the Medusa-derived prefab.
Run: python3 a220_parts.py -- <out.blend>
Axes: Blender X right, Y forward, Z up. d = metres aft of the nose tip, Y = NOSE_Y - d. Z = 0 on the fuselage
centreline, ground at GROUND. Every part is its own mesh object whose origin is the part pivot (world-aligned).
Collection MODEL holds visible meshes, COLLISION holds <part>_colmesh convex hulls, POINTS holds empties
(pivots, hinges, gear, seats, mounts) that the Unity builder places transforms on."""
import bpy, bmesh, math, sys
from mathutils import Vector, Matrix

L = 38.7
NOSE_Y = L / 2
GROUND = -3.77
def Y(d): return NOSE_Y - d

# ------------------------------------------------------------------ geometry helpers
def pchip(st, step=0.3):
    ds = [s[0] for s in st]; n = len(st); cols = list(zip(*[s[1:] for s in st]))
    def slopes(v):
        h = [ds[i + 1] - ds[i] for i in range(n - 1)]; dl = [(v[i + 1] - v[i]) / h[i] for i in range(n - 1)]
        return [dl[0]] + [0.0 if dl[i - 1] * dl[i] <= 0 else 3 * (h[i - 1] + h[i]) / ((2 * h[i] + h[i - 1]) / dl[i - 1] + (h[i] + 2 * h[i - 1]) / dl[i]) for i in range(1, n - 1)] + [dl[-1]]
    ms = [slopes(c) for c in cols]
    def at(d):
        for i in range(n - 1):
            if ds[i] <= d <= ds[i + 1]:
                hgt = ds[i + 1] - ds[i]; tt = (d - ds[i]) / hgt
                h00 = 2 * tt ** 3 - 3 * tt ** 2 + 1; h10 = tt ** 3 - 2 * tt ** 2 + tt; h01 = -2 * tt ** 3 + 3 * tt ** 2; h11 = tt ** 3 - tt ** 2
                return (d,) + tuple(h00 * c[i] + h10 * hgt * m[i] + h01 * c[i + 1] + h11 * hgt * m[i + 1] for c, m in zip(cols, ms))
        return st[0] if d < ds[0] else st[-1]
    return at

FUS = [
    (0.00, 0.05, -0.62, -0.80), (0.35, 0.62, -0.05, -1.20), (0.90, 1.00, 0.45, -1.48), (2.00, 1.42, 1.05, -1.70),
    (3.20, 1.68, 1.55, -1.82), (4.40, 1.82, 1.84, -1.90), (6.00, 1.86, 1.91, -1.93), (27.5, 1.86, 1.91, -1.93),
    (30.0, 1.80, 1.91, -1.80), (32.5, 1.62, 1.82, -1.45), (34.8, 1.30, 1.52, -0.82), (36.8, 0.82, 1.20, -0.25),
    (38.1, 0.32, 0.98, 0.30), (38.45, 0.12, 0.86, 0.52)]
fus = pchip(FUS)
FAIR = [(12.0, 0.6, -1.0, -1.3), (14.0, 1.90, -0.6, -2.20), (18.0, 2.02, -0.6, -2.35), (22.5, 1.95, -0.6, -2.25), (25.0, 0.6, -0.8, -1.6)]
fair = pchip(FAIR)

def skin_z(tab, x, d):
    # lower surface height of a superellipse section (ex 2.2) at lateral offset x
    _, hw, zt, zb = tab(d); zc, hh = (zt + zb) / 2, (zt - zb) / 2
    u = min(abs(x) / hw, 0.999)
    return zc - hh * (1 - u ** 2.2) ** (1 / 2.2)
def fair_z(x, d): return skin_z(fair, x, d)

# main wheel wells (stowed wheels lie flat in the belly fairing) and the nose gear bay
WELL_X, WELL_D, WELL_R = 1.40, 18.8, 0.64
NB_X, NB_D0, NB_D1, NB_TOP = 0.40, 1.10, 3.75, -0.85
def in_well(c, zmax):
    return c.z < zmax and (abs(c.x) - WELL_X) ** 2 + ((NOSE_Y - c.y) - WELL_D) ** 2 < WELL_R ** 2
def in_nose_bay(c):
    dd = NOSE_Y - c.y
    return c.z < -0.9 and abs(c.x) < NB_X and NB_D0 < dd < NB_D1

def section(d, hw, ztop, zbot, n=40, ex=2.2):
    zc = (ztop + zbot) / 2; hh = (ztop - zbot) / 2; pts = []
    for i in range(n):
        a = 2 * math.pi * i / n; c, s = math.cos(a), math.sin(a)
        pts.append(Vector((hw * math.copysign(abs(c) ** (2 / ex), c), Y(d), zc + hh * math.copysign(abs(s) ** (2 / ex), s))))
    return pts

def section_at(cx, d, hw, ztop, zbot, n=16):
    return [p + Vector((cx, 0, 0)) for p in section(d, hw, ztop, zbot, n=n, ex=3.0)]

# ------------------------------------------------------------------ openings in the fuselage skin
# The skin rings carry extra vertices at the heights of the cabin window band and the forward door sill/top, and at the
# weapons bay edges on the belly, so those openings can be cut along exact ring edges.
FN = 96
ZA, ZB, WZ = 0.30, 0.80, 0.55                  # cabin window band and window centre height
WIN_D0, WIN_P, WIN_N = 5.92, 0.56, 10          # 10 rows of cabin windows into the crew cabin
DOOR_D0, DOOR_D1, DOOR_Z0, DOOR_Z1 = 4.05, 4.95, -0.55, 1.28    # forward doors (open for the crew to bail out)
BAY_X, BAY_D0, BAY_D1, BAY_TOP = 1.15, 25.2, 29.6, -0.60        # rear weapons bay, two Medusa bays side by side
FLOOR_Z, CAB_D0, CAB_D1 = -0.55, 3.35, 12.4
EXTRA_Z = [DOOR_Z0, ZA, ZB, DOOR_Z1]
def fsec(d, n=FN, ex=2.2):
    _, hw, zt, zb = fus(d); zc, hh = (zt + zb) / 2, (zt - zb) / 2
    angs = [2 * math.pi * i / n for i in range(n)]
    for z in EXTRA_Z:
        t = max(-0.97, min(0.97, (z - zc) / hh)); a = math.asin(math.copysign(abs(t) ** (ex / 2), t))
        angs += [a % (2 * math.pi), (math.pi - a) % (2 * math.pi)]
    a = math.acos(min(BAY_X / hw, 0.97) ** (ex / 2))
    angs += [(-a) % (2 * math.pi), (math.pi + a) % (2 * math.pi)]
    out = []
    for a in sorted(angs):
        if out and a - out[-1] < 1e-3: a = out[-1] + 1e-3
        out.append(a)
    return [Vector((hw * math.copysign(abs(math.cos(a)) ** (2 / ex), math.cos(a)), Y(d),
                    zc + hh * math.copysign(abs(math.sin(a)) ** (2 / ex), math.sin(a)))) for a in out]
FUS_BREAKS = [WIN_D0 + WIN_P * j for j in range(WIN_N + 1)] + [DOOR_D0, DOOR_D1, BAY_D0, BAY_D1, CAB_D0, CAB_D1]
def skin_open(c):
    dd = NOSE_Y - c.y
    if abs(c.x) > 0.5 and WIN_D0 < dd < WIN_D0 + WIN_P * WIN_N and ZA < c.z < ZB: return True
    if abs(c.x) > 0.5 and DOOR_D0 < dd < DOOR_D1 and DOOR_Z0 < c.z < DOOR_Z1: return True
    if abs(c.x) < BAY_X and BAY_D0 < dd < BAY_D1 and c.z < -1.0: return True
    return False

def skin_pt(sx, dd, z, off=0.0):
    """Point on the fuselage side at station dd and height z, pushed off along the skin normal."""
    _, hw, zt, zb = fus(dd); zc, hh = (zt + zb) / 2, (zt - zb) / 2
    u = min(abs(z - zc) / hh, 0.999); x = hw * (1 - u ** 2.2) ** (1 / 2.2)
    gx, gz = (x / hw) ** 1.2 / hw, math.copysign(u ** 1.2 / hh, z - zc); g = math.hypot(gx, gz)
    return Vector((sx * (x + off * gx / g), Y(dd), z + off * gz / g))

def rect_uv(hd, hz, k=4):
    """Points round a rectangle of half sizes (hd, hz), corners included, counter-clockwise from the lower right."""
    c = [(hd, -hz), (hd, hz), (-hd, hz), (-hd, -hz)]; out = []
    for i in range(4):
        (a0, b0), (a1, b1) = c[i], c[(i + 1) % 4]
        out += [(a0 + (a1 - a0) * j / k, b0 + (b1 - b0) * j / k) for j in range(k)]
    return out
def squircle_uv(pts, hd, hz, wa, wb):
    out = []
    for a, b in pts:
        t = math.atan2(b / hz, a / hd); ca, sa = math.cos(t), math.sin(t)
        out.append((wa * math.copysign(abs(ca) ** 0.5, ca), wb * math.copysign(abs(sa) ** 0.5, sa)))
    return out

def fan(m, centre, ring, mat):
    mi = m.mat(mat); c = m.bm.verts.new(centre); vs = [m.bm.verts.new(q) for q in ring]
    for j in range(len(vs)):
        f = m.bm.faces.new((c, vs[j], vs[(j + 1) % len(vs)])); f.material_index = mi

def outline(m, sx, d0, d1, z0, z1, mat, w=0.03, off=0.004, k=24):
    """A seam line round a door: a strip just outside the rectangle (d0..d1, z0..z1), standing off the skin."""
    dc, zc = (d0 + d1) / 2, (z0 + z1) / 2; hd, hz = (d1 - d0) / 2, (z1 - z0) / 2
    inner = rect_uv(hd, hz, k); outer = rect_uv(hd + w, hz + w, k)
    m.loft([[skin_pt(sx, dc + a, zc + b, off) for a, b in r] for r in (inner, outer)], mat, cap0=False, cap1=False)

def door_window(m, sx, dc, mat, off=0.006, wa=0.12, wb=0.17):
    ring = squircle_uv(rect_uv(1, 1, 5), 1, 1, wa, wb)
    fan(m, skin_pt(sx, dc, WZ, off), [skin_pt(sx, dc + a, WZ + b, off) for a, b in ring], mat)

# flight deck glazing as on the real nose: two front panes either side of a centre post on the forehead, two side
# panes behind a canted post, each a quad in (station d, section angle in degrees) for the right side
PANES = [((1.36, 87), (2.25, 87), (2.50, 55), (1.62, 55)),     # front: bottom-inner, top-inner, top-outer, bottom-outer
         ((2.63, 52), (3.42, 49), (3.30, 24), (2.48, 26))]     # side: top-front, top-rear, bottom-rear, bottom-front
def pane_coords(p):
    dd = NOSE_Y - p.y; _, hw, zt, zb = fus(dd); zc, hh = (zt + zb) / 2, (zt - zb) / 2
    t = max(-1.0, min(1.0, (p.z - zc) / hh))
    return dd, math.degrees(math.atan2(math.copysign(abs(t) ** 1.1, t), min(abs(p.x) / hw, 1.0) ** 1.1))
def in_quad(pt, quad):
    sgn = 0
    for i in range(4):
        (a0, b0), (a1, b1) = quad[i], quad[(i + 1) % 4]
        cr = (a1 - a0) * (pt[1] - b0) - (b1 - b0) * (pt[0] - a0)
        if abs(cr) < 1e-12: continue
        if sgn == 0: sgn = 1 if cr > 0 else -1
        elif (cr > 0) != (sgn > 0): return False
    return True
def windscreen_open(q):
    """Skin quads wholly inside a windscreen pane are cut out, so the glass looks into the flight deck."""
    if any(abs(p.x) < 0.02 for p in q) or len({p.x > 0 for p in q}) > 1: return False
    cs = [pane_coords(p) for p in q]
    return any(all(in_quad(c, quad) for c in cs) for quad in PANES)
def surf(dd, ang, pad=0.012):
    _, hw, zt, zb = fus(dd); hw += pad; zt += pad; zb -= pad
    zc, hh = (zt + zb) / 2, (zt - zb) / 2; c, sn = math.cos(ang), math.sin(ang)
    return Vector((hw * math.copysign(abs(c) ** (2 / 2.2), c), Y(dd), zc + hh * math.copysign(abs(sn) ** (2 / 2.2), sn)))
def pane_pt(quad, u, v):
    p0 = [quad[0][k] + (quad[1][k] - quad[0][k]) * u for k in (0, 1)]
    p1 = [quad[3][k] + (quad[2][k] - quad[3][k]) * u for k in (0, 1)]
    return p0[0] + (p1[0] - p0[0]) * v, p0[1] + (p1[1] - p0[1]) * v

DECOR = [(31.0, 31.82, -0.55, 1.20, True, (-1, 1)),     # rear passenger/service doors
         (15.35, 15.90, 0.02, 0.97, True, (-1, 1)),     # over-wing emergency exits, two each side
         (16.45, 17.00, 0.02, 0.97, True, (-1, 1)),
         (7.6, 9.0, -1.72, -0.88, False, (1,))]         # forward belly cargo door, right side

def drange(d0, d1, step):
    k = max(1, int(math.ceil((d1 - d0) / step))); return [d0 + (d1 - d0) * i / k for i in range(k + 1)]

class Mesh:
    def __init__(self): self.bm = bmesh.new(); self.mats = []
    def mat(self, m):
        if m not in self.mats: self.mats.append(m)
        return self.mats.index(m)
    def loft(self, rings, m, cap0=True, cap1=True, quads=None, keep=None, keep4=None):
        mi = self.mat(m); vs = [[self.bm.verts.new(p) for p in r] for r in rings]; n = len(rings[0])
        for a, b in zip(vs, vs[1:]):
            for i in range(n):
                if quads and not quads(i): continue
                if keep and not keep((a[i].co + a[(i + 1) % n].co + b[(i + 1) % n].co + b[i].co) / 4): continue
                if keep4 and not keep4((a[i].co, a[(i + 1) % n].co, b[(i + 1) % n].co, b[i].co)): continue
                f = self.bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i])); f.material_index = mi
        if cap0: f = self.bm.faces.new(list(reversed(vs[0]))); f.material_index = mi
        if cap1: f = self.bm.faces.new(vs[-1]); f.material_index = mi
    def box(self, c, size, m):
        mi = self.mat(m); r = bmesh.ops.create_cube(self.bm, size=1.0)
        for v in r['verts']: v.co = Vector((c[0] + v.co.x * size[0], c[1] + v.co.y * size[1], c[2] + v.co.z * size[2]))
        for f in {f for v in r['verts'] for f in v.link_faces}: f.material_index = mi
    def cyl(self, c, axis, r, length, m, seg=20):
        mi = self.mat(m); res = bmesh.ops.create_cone(self.bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=length)
        rot = {'X': Matrix.Rotation(math.pi / 2, 3, 'Y'), 'Y': Matrix.Rotation(math.pi / 2, 3, 'X'), 'Z': Matrix.Identity(3)}[axis]
        for v in res['verts']: v.co = rot @ v.co + Vector(c)
        for f in {f for v in res['verts'] for f in v.link_faces}: f.material_index = mi

MATS = {}
def material(name, rgb):
    if name not in MATS:
        m = bpy.data.materials.new(name); m.diffuse_color = (*rgb, 1); MATS[name] = m
    return MATS[name]

def coll(name):
    c = bpy.data.collections.get(name)
    if not c: c = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c)
    return c

def emit(name, mesh, pivot, hull=True, hull_pad=0.0):
    """Create the MODEL object (origin at pivot) and its convex-hull colmesh."""
    bmesh.ops.recalc_face_normals(mesh.bm, faces=mesh.bm.faces)
    me = bpy.data.meshes.new(name)
    bm = mesh.bm
    for v in bm.verts: v.co -= Vector(pivot)
    if hull:
        hb = bmesh.new()
        for v in bm.verts: hb.verts.new(v.co)
        bmesh.ops.convex_hull(hb, input=hb.verts)
        # keep the hull light: merge close vertices
        bmesh.ops.remove_doubles(hb, verts=hb.verts, dist=0.08)
        bmesh.ops.convex_hull(hb, input=hb.verts[:])
        loose = [v for v in hb.verts if not v.link_faces]; bmesh.ops.delete(hb, geom=loose, context='VERTS')
        bmesh.ops.recalc_face_normals(hb, faces=hb.faces)
        hm = bpy.data.meshes.new(name + '_colmesh'); hb.to_mesh(hm); hb.free()
        ho = bpy.data.objects.new(name + '_colmesh', hm); ho.location = pivot; coll('COLLISION').objects.link(ho)
    bm.to_mesh(me); bm.free()
    for m in mesh.mats: me.materials.append(m)
    ob = bpy.data.objects.new(name, me); ob.location = pivot; coll('MODEL').objects.link(ob)
    return ob

def point(name, pos, rot=None):
    e = bpy.data.objects.new(name, None); e.location = pos
    if rot is not None: e.rotation_mode = 'QUATERNION'; e.rotation_quaternion = rot
    coll('POINTS').objects.link(e); return e

# ------------------------------------------------------------------ wing / tail tables
DIH = math.tan(math.radians(5.0)); ZR = -1.35
WING = [(0.0, 12.9, 8.6, 0.13), (1.86, 13.87, 6.46, 0.13), (6.1, 16.2, 4.13, 0.12), (17.2, 22.0, 1.65, 0.10), (17.45, 22.35, 1.30, 0.09)]
def lerp_tab(tab, s):
    for a, b in zip(tab, tab[1:]):
        if a[0] <= s <= b[0]:
            t = (s - a[0]) / (b[0] - a[0]); return tuple(x + (y - x) * t for x, y in zip(a[1:], b[1:]))
    return tab[-1][1:] if s > tab[-1][0] else tab[0][1:]
def wing_at(s):
    le, c, t = lerp_tab(WING, s); return le, c, t, ZR + s * DIH

def foil_ring(x_of, y_of, z_of, chord, t, u0, u1, n=14, camber=0.02):
    """Partial-chord airfoil ring over chord fraction [u0, u1]: upper surface u0->u1, lower u1->u0.
    x_of/y_of/z_of map (u, thickness offset) to a 3D point."""
    us = [u0 + (u1 - u0) * (1 - math.cos(math.pi * i / n)) / 2 for i in range(n + 1)]
    def th(u):
        return 5 * t * (0.2969 * math.sqrt(max(u, 0)) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4) * chord
    ring = []
    for u in us: ring.append((u, th(u) + camber * chord * 4 * u * (1 - u)))
    for u in reversed(us[1:-1]): ring.append((u, -th(u) + camber * chord * 4 * u * (1 - u)))
    if u0 > 0: pass
    return [Vector((x_of(u, o), y_of(u, o), z_of(u, o))) for u, o in ring]

def wing_ring(s, sx, u0, u1, n=14):
    le, c, t, z = wing_at(s)
    return foil_ring(lambda u, o: sx * s, lambda u, o: Y(le + u * c), lambda u, o: z + o, c, t, u0, u1, n)

def panel(mesh, sx, s0, s1, u0, u1, m, ds=0.8):
    ss = drange(s0, s1, ds); mesh.loft([wing_ring(s, sx, u0, u1) for s in ss], m)

def quarter_point(sx, s0, s1):
    sm = (s0 + s1) / 2; le, c, t, z = wing_at(sm); return Vector((sx * sm, Y(le + 0.25 * c), z))

HT = [(0.0, 32.6, 4.2, 0.11), (0.95, 33.1, 3.6, 0.11), (6.16, 36.3, 1.42, 0.10)]
HZ = 0.80; HDIH = math.tan(math.radians(3.0))
def ht_ring(s, sx, u0, u1):
    le, c, t = lerp_tab(HT, s); z = HZ + s * HDIH
    return foil_ring(lambda u, o: sx * s, lambda u, o: Y(le + u * c), lambda u, o: z + o, c, t, u0, u1, 12, camber=0.0)
FIN = [(1.2, 29.6, 8.8, 0.10), (1.6, 30.0, 8.4, 0.10), (7.65, 37.1, 1.6, 0.10)]
def fin_ring(z, u0, u1):
    le, c, t = lerp_tab(FIN, z)
    return foil_ring(lambda u, o: o, lambda u, o: Y(le + u * c), lambda u, o: z, c, t, u0, u1, 12, camber=0.0)

def revolve(profile, cx, cz, n=28):
    return [[Vector((cx + r * math.cos(2 * math.pi * i / n), Y(d), cz + r * math.sin(2 * math.pi * i / n))) for i in range(n)] for d, r in profile]

# ------------------------------------------------------------------ build
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for c in ('MODEL', 'COLLISION', 'POINTS'): coll(c)
    SKIN = material('A220_skin', (0.86, 0.87, 0.89)); DARK = material('A220_dark', (0.05, 0.05, 0.06))
    METAL = material('A220_metal', (0.42, 0.43, 0.45)); TYRE = material('A220_tyre', (0.06, 0.06, 0.06))
    GLASS = material('A220_glass', (0.10, 0.13, 0.17)); WIN = material('A220_window', (0.07, 0.08, 0.10)); BAY = material('A220_bay', (0.30, 0.31, 0.32))

    # fuselage parts (d ranges); the window band and windshield ride the part they sit on
    FP = [('nose', 0.0, 0.9), ('cockpit_F', 0.9, 3.2), ('cockpit_R', 3.2, 9.5), ('fuselage_F', 9.5, 13.5),
          ('fuselage', 13.5, 22.0), ('fuselage_R', 22.0, 30.5), ('tail', 30.5, 38.45)]
    for name, d0, d1 in FP:
        m = Mesh()
        step = 0.1 if name == 'cockpit_F' else (0.25 if (d0 < 6 or d1 > 30) else 1.0)
        brk = [b for b in FUS_BREAKS if d0 < b < d1]
        ds = sorted([x for x in drange(max(d0, 0.0), d1, step) if all(abs(x - b) > 0.04 for b in brk)] + brk)
        if name == 'nose': ds[0] = 0.0
        m.loft([fsec(d) for d in ds], SKIN, cap0=True, keep=lambda c: not (in_nose_bay(c) or in_well(c, -1.0) or skin_open(c)),
               keep4=(lambda q: not windscreen_open(q)) if name == 'cockpit_F' else None)
        # cabin window band: 10 rows of windows into the crew cabin, each a skin panel with a rounded opening, a shallow
        # reveal and a glass pane
        hd, hz, zc = WIN_P / 2, (ZB - ZA) / 2, (ZA + ZB) / 2
        rect = rect_uv(hd, hz); ell = [(a, b + WZ - zc) for a, b in squircle_uv(rect, hd, hz, 0.14, 0.20)]
        for k in range(WIN_N):
            wd = WIN_D0 + (k + 0.5) * WIN_P
            if not (d0 <= wd < d1): continue
            for sx in (-1, 1):
                lip = [skin_pt(sx, wd + a, zc + b) for a, b in ell]
                m.loft([[skin_pt(sx, wd + a, zc + b) for a, b in rect], lip], SKIN, cap0=False, cap1=False)
                m.loft([lip, [skin_pt(sx, wd + a, zc + b, -0.08) for a, b in ell]], BAY, cap0=False, cap1=False)
                fan(m, skin_pt(sx, wd, WZ, -0.02), [skin_pt(sx, wd + a, zc + b, -0.02) for a, b in ell], GLASS)
        # crew cabin blockout behind the flight deck: floor, bulkheads and five rows of paired seats each side
        fa, fb = max(d0, CAB_D0), min(d1, CAB_D1)
        if fa < fb:
            fx = lambda dd: skin_pt(1, dd, FLOOR_Z).x - 0.03
            m.loft([[Vector((-fx(dd), Y(dd), FLOOR_Z)), Vector((fx(dd), Y(dd), FLOOR_Z))] for dd in drange(fa, fb, 0.5)], BAY,
                   cap0=False, cap1=False, quads=lambda i: i == 0)
        for row in range(5):
            rd = WIN_D0 + WIN_P / 2 - 0.05 + row * 2 * WIN_P
            if not (d0 <= rd < d1): continue
            for x in (-1.15, -0.65, 0.65, 1.15):
                m.box((x, Y(rd), FLOOR_Z + 0.25), (0.46, 0.48, 0.5), DARK)
                m.box((x, Y(rd + 0.29), FLOOR_Z + 0.75), (0.46, 0.10, 0.95), DARK)
        for bd in (CAB_D0, CAB_D1):
            if d0 <= bd < d1:
                _, hw_, zt_, zb_ = fus(bd); zcb = (zt_ + zb_) / 2
                ring = [Vector((p.x * 0.985, p.y, zcb + (p.z - zcb) * 0.985)) for p in section(*fus(bd), n=48)]
                fan(m, Vector((0, Y(bd), zcb)), ring, BAY)
        if d0 <= CAB_D0 < d1: m.box((0, Y(CAB_D0 - 0.02), FLOOR_Z + 0.95), (0.7, 0.03, 1.9), DARK)   # flight deck door
        # door seams: forward doors (the doors themselves are separate parts), rear doors, over-wing exits, cargo door
        if d0 <= DOOR_D0 < d1:
            for sx in (-1, 1): outline(m, sx, DOOR_D0, DOOR_D1, DOOR_Z0, DOOR_Z1, DARK)
        for e0, e1, z0, z1, win, sides in DECOR:
            if not (d0 <= (e0 + e1) / 2 < d1): continue
            for sx in sides:
                outline(m, sx, e0, e1, z0, z1, DARK, w=0.025)
                if win: door_window(m, sx, (e0 + e1) / 2, WIN)
        if name == 'cockpit_F':
            # flight deck glazing: the skin behind each pane is cut away (windscreen_open); each pane gets a dark frame
            # that covers the stepped edge of the cut
            for sx in (-1, 1):
                for quad in PANES:
                    rows = []
                    for i in range(9):
                        row = []
                        for j in range(9):
                            dd, deg = pane_pt(quad, i / 8, j / 8); pt = surf(dd, math.radians(deg)); pt.x *= sx; row.append(pt)
                        rows.append(row)
                    mi = m.mat(GLASS); vs = [[m.bm.verts.new(q) for q in r] for r in rows]
                    for r0, r1 in zip(vs, vs[1:]):
                        for j in range(8):
                            f = m.bm.faces.new((r0[j], r0[j + 1], r1[j + 1], r1[j])); f.material_index = mi
                    edge = [pane_pt(quad, u, 0) for u in (k / 8 for k in range(8))] + [pane_pt(quad, 1, v) for v in (k / 8 for k in range(8))] \
                         + [pane_pt(quad, 1 - u, 1) for u in (k / 8 for k in range(8))] + [pane_pt(quad, 0, 1 - v) for v in (k / 8 for k in range(8))]
                    cd = sum(e[0] for e in edge) / len(edge); ca = sum(e[1] for e in edge) / len(edge)
                    def fp(dd, deg):
                        q = surf(dd, math.radians(deg), 0.008); q.x *= sx; return q
                    m.loft([[fp(*e) for e in edge], [fp(cd + (e[0] - cd) * 0.70, ca + (e[1] - ca) * 0.70) for e in edge]], DARK, cap0=False, cap1=False)
            # flight deck floor under the crew stations
            fx = lambda dd: skin_pt(1, dd, -0.22).x - 0.03
            m.loft([[Vector((-fx(dd), Y(dd), -0.22)), Vector((fx(dd), Y(dd), -0.22))] for dd in drange(1.1, 3.2, 0.3)], BAY,
                   cap0=False, cap1=False, quads=lambda i: i == 0)
        if name == 'cockpit_F':
            # nose gear bay: side walls from the skin opening up to the bay roof, front and rear walls, roof
            for sx in (-1, 1):
                rings = [[Vector((sx * NB_X, Y(dd), skin_z(fus, NB_X, dd) + 0.03)), Vector((sx * NB_X, Y(dd), NB_TOP))] for dd in drange(NB_D0, NB_D1, 0.25)]
                m.loft(rings, BAY, cap0=False, cap1=False, quads=lambda i: i == 0)
            for dd in (NB_D0, NB_D1):
                xs = [-NB_X + 2 * NB_X * k / 8 for k in range(9)]
                rings = [[Vector((x, Y(dd), skin_z(fus, x, dd) + 0.03)), Vector((x, Y(dd), NB_TOP))] for x in xs]
                m.loft(rings, BAY, cap0=False, cap1=False, quads=lambda i: i == 0)
            m.loft([[Vector((-NB_X, Y(dd), NB_TOP)), Vector((NB_X, Y(dd), NB_TOP))] for dd in drange(NB_D0, NB_D1, 0.5)], BAY, cap0=False, cap1=False, quads=lambda i: i == 0)
            # door frame strip around the bay opening, proud of the skin, hiding the stepped cut
            def fr(x, dd): return Vector((x, Y(dd), skin_z(fus, x, dd) - 0.012))
            for sx in (-1, 1):
                m.loft([[fr(sx * (NB_X - 0.05), dd), fr(sx * (NB_X + 0.12), dd)] for dd in drange(NB_D0 - 0.12, NB_D1 + 0.12, 0.2)], BAY, cap0=False, cap1=False, quads=lambda i: i == 0)
            for d0_, d1_ in ((NB_D0 - 0.12, NB_D0 + 0.05), (NB_D1 - 0.05, NB_D1 + 0.12)):
                m.loft([[fr(x, d0_), fr(x, d1_)] for x in [-NB_X + 2 * NB_X * k / 8 for k in range(9)]], BAY, cap0=False, cap1=False, quads=lambda i: i == 0)
        if name == 'fuselage_R':
            # rear weapons bay behind the wing: one opening with a single pair of doors, holding two Medusa-sized bays
            # side by side (left and right hardpoints)
            for sx in (-1, 1):
                rings = [[Vector((sx * BAY_X, Y(dd), skin_z(fus, BAY_X, dd))), Vector((sx * BAY_X, Y(dd), BAY_TOP))] for dd in drange(BAY_D0, BAY_D1, 0.4)]
                m.loft(rings, BAY, cap0=False, cap1=False, quads=lambda i: i == 0)
            for dd in (BAY_D0, BAY_D1):
                xs = [-BAY_X + 2 * BAY_X * k / 12 for k in range(13)]
                m.loft([[Vector((x, Y(dd), skin_z(fus, x, dd))), Vector((x, Y(dd), BAY_TOP))] for x in xs], BAY, cap0=False, cap1=False, quads=lambda i: i == 0)
            m.loft([[Vector((-BAY_X, Y(dd), BAY_TOP)), Vector((BAY_X, Y(dd), BAY_TOP))] for dd in drange(BAY_D0, BAY_D1, 0.5)], BAY,
                   cap0=False, cap1=False, quads=lambda i: i == 0)
            m.box((0, Y((BAY_D0 + BAY_D1) / 2), BAY_TOP - 0.25), (0.06, BAY_D1 - BAY_D0 - 0.1, 0.5), BAY)     # centre keel between the two sides
        if name == 'tail':
            # dorsal fin fillet running into the fin leading edge (meets it at about z 2.6)
            rings = []
            for dd in drange(28.2, 31.3, 0.25):
                ztop = fus(dd)[2]; h = 0.78 * ((dd - 28.2) / 3.1) ** 1.6
                w = 0.05 + 0.15 * (dd - 28.2) / 3.1
                rings.append([Vector((-w, Y(dd), ztop - 0.05)), Vector((0, Y(dd), ztop + h)), Vector((w, Y(dd), ztop - 0.05))])
            m.loft(rings, SKIN, cap0=False)
        if name == 'fuselage':
            m.loft([section(*fair(d), n=72) for d in drange(12.0, 25.0, 0.2)], SKIN, keep=lambda c: not in_well(c, -1.5))
            # main wheel wells: the A220 has no doors over the main wheels; the tyres sit in open wells in the belly
            # fairing, so each well is a dark cylinder rising from the fairing skin to above the stowed wheels
            for sx in (-1, 1):
                ring_lo, ring_hi = [], []
                for k in range(24):
                    a = 2 * math.pi * k / 24
                    x = sx * WELL_X + WELL_R * math.cos(a); dd = WELL_D + WELL_R * math.sin(a)
                    ring_lo.append(Vector((x, Y(dd), fair_z(abs(x), dd) + 0.03))); ring_hi.append(Vector((x, Y(dd), -1.42)))
                m.loft([ring_lo, ring_hi], BAY, cap0=False, cap1=True)
                # rubber seal ring just proud of the skin around the well edge (also hides the stepped skin cut)
                inner, outer = [], []
                for k in range(48):
                    a = 2 * math.pi * k / 48; ca, sa = math.cos(a), math.sin(a)
                    for r, lst in ((WELL_R - 0.05, inner), (WELL_R + 0.16, outer)):
                        x = sx * WELL_X + r * ca; dd = WELL_D + r * sa
                        lst.append(Vector((x, Y(dd), fair_z(abs(x), dd) - 0.012)))
                m.loft([inner, outer], BAY, cap0=False, cap1=False)
        mid = (d0 + d1) / 2
        piv = Vector((0, Y(mid), 0)) if name != 'fuselage' else Vector((0, 0, 0))
        if name == 'cockpit_F': piv = Vector((0, Y(2.46), 0.33))   # puts the reused crew stations at the flight deck
        emit(name, m, piv)

    # forward doors: they hinge open at their front edge on the ground and are jettisoned for the crew to bail out
    for side, sx in (('L', -1), ('R', 1)):
        m = Mesh(); zs = drange(DOOR_Z0, DOOR_Z1, 0.15); nz = len(zs)
        for off, mat in ((0.0, SKIN), (-0.06, BAY)):
            m.loft([[skin_pt(sx, dd, z, off) for z in zs] for dd in drange(DOOR_D0, DOOR_D1, 0.15)], mat, cap0=False, cap1=False, quads=lambda i: i < nz - 1)
        hd, hz = (DOOR_D1 - DOOR_D0) / 2, (DOOR_Z1 - DOOR_Z0) / 2; dc, zc = DOOR_D0 + hd, DOOR_Z0 + hz
        edge = rect_uv(hd, hz, 16)
        m.loft([[skin_pt(sx, dc + a, zc + b, off) for a, b in edge] for off in (0.0, -0.06)], BAY, cap0=False, cap1=False)
        door_window(m, sx, dc, WIN)
        hp = skin_pt(sx, DOOR_D0, zc)
        emit('fdoor_' + side, m, hp); point('fdoor_' + side + '_hinge', hp)
    # weapons bay doors: one pair, hinged along the bay edges, shaped to the belly they close flush with
    for side, sx in (('L', -1), ('R', 1)):
        rings = []
        for dd in drange(BAY_D0 + 0.02, BAY_D1 - 0.02, 0.4):
            xs = [0.006 + (BAY_X - 0.012) * k / 8 for k in range(9)]
            lo = [Vector((sx * x, Y(dd), skin_z(fus, x, dd) - 0.004)) for x in xs]
            rings.append(lo + [Vector((p.x, p.y, p.z + 0.04)) for p in reversed(lo)])
        m = Mesh(); m.loft(rings, SKIN)
        ha = Vector((sx * BAY_X, Y(BAY_D0), skin_z(fus, BAY_X, BAY_D0))); hb = Vector((sx * BAY_X, Y(BAY_D1), skin_z(fus, BAY_X, BAY_D1)))
        emit('baydoor_' + side, m, (ha + hb) / 2, hull=False)
        point('baydoor_' + side + '_hingeA', ha); point('baydoor_' + side + '_hingeB', hb)
        point('bayHardpoint_' + side, Vector((sx * 0.57, Y((BAY_D0 + BAY_D1) / 2), -1.00)))

    for side, sx in (('L', -1), ('R', 1)):
        # wing: 1a root 1.7-3.0, 1b 3.0-7.0 (gear, engine), 2 7.0-11.5 (pylon), 3 11.5-16.2 (aileron), tip 16.2-17.55.
        # Moving surfaces as on the real wing: slats 7.0-16.2 (front 13 % chord), spoilers ahead of the flaps, an inboard
        # flap from the fairing to the trailing-edge kink, an outboard flap to 12.5 and the aileron 12.5-16.2 (rear 27 %)
        FC, SC = 0.73, 0.13
        m = Mesh(); panel(m, sx, 1.7, 3.0, 0.0, FC, SKIN, 0.65); panel(m, sx, 1.7, 2.1, FC - 0.01, 1.0, SKIN, 0.4)
        emit('wing1a_' + side, m, quarter_point(sx, 1.86, 3.0))
        m = Mesh(); panel(m, sx, 3.0, 7.0, 0.0, FC, SKIN); emit('wing1b_' + side, m, quarter_point(sx, 3.0, 7.0))
        m = Mesh(); panel(m, sx, 7.0, 11.5, SC, FC, SKIN)
        for cs in (8.4, 11.0):     # flap track fairings ("canoes") under the wing
            le, c, t, z = wing_at(cs)
            prof = [(le + c * 0.50, 0.03), (le + c * 0.62, 0.15), (le + c * 0.9, 0.17), (le + c * 1.15, 0.10), (le + c * 1.32, 0.02)]
            m.loft([[Vector((sx * cs + r * math.cos(2 * math.pi * k / 12), Y(dd), z - 0.12 - r + r * math.sin(2 * math.pi * k / 12)))
                     for k in range(12)] for dd, r in prof], SKIN)
        emit('wing2_' + side, m, quarter_point(sx, 7.0, 11.5))
        m = Mesh(); panel(m, sx, 11.5, 16.2, SC, FC, SKIN); emit('wing3_' + side, m, quarter_point(sx, 11.5, 16.2))
        # wingtip: the wing runs on to 16.75, then a raked tip that keeps going outward while it sweeps back and curves up
        m = Mesh(); panel(m, sx, 16.2, 16.75, 0.0, 1.0, SKIN, 0.55)
        le0, c0, t0, z0 = wing_at(16.75); rings = []
        for k in range(9):
            tt = k / 8; ss = 16.75 + 0.80 * tt; dz = 0.95 * tt ** 1.7
            le_k = le0 + 1.10 * tt ** 1.15; c_k = c0 + (0.40 - c0) * tt ** 0.9; zb = ZR + ss * DIH + dz
            rings.append(foil_ring(lambda u, o, ss=ss: sx * ss, lambda u, o, le_k=le_k, c_k=c_k: Y(le_k + u * c_k),
                                   lambda u, o, zb=zb: zb + o, c_k, 0.10 - 0.04 * tt, 0.0, 1.0))
        m.loft(rings, SKIN, cap0=False)
        emit('wingtip_' + side, m, quarter_point(sx, 16.2, 16.75))
        point('navlight_' + side, Vector((sx * 17.55, Y(le0 + 1.10 + 0.2), ZR + 17.55 * DIH + 0.95)))
        def hinge_pt(ss, u, dz=0.0):
            le, c, t, z = wing_at(ss); return Vector((sx * ss, Y(le + u * c), z + dz))
        def foil_z(ss, u, upper):
            le, c, t, z = wing_at(ss)
            th = 5 * t * (0.2969 * math.sqrt(u) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4) * c
            return z + 0.02 * c * 4 * u * (1 - u) + (th if upper else -th)
        # flaps and aileron: AeroPart pivot and hinge both on the hinge line at mid span
        for nm, s0, s1 in (('flapin', 2.1, 6.1), ('flap', 6.1, 12.5), ('aileron', 12.5, 16.2)):
            m = Mesh(); panel(m, sx, s0, s1, FC, 1.0, SKIN, 0.7)
            a, b = hinge_pt(s0, FC), hinge_pt(s1, FC)
            emit(nm + '_' + side, m, (a + b) / 2)
            point(nm + '_' + side + '_hingeA', a); point(nm + '_' + side + '_hingeB', b)
        # leading-edge slats (droop forward and down about a hinge near their lower trailing edge)
        for nm, s0, s1 in (('slat1', 7.0, 11.5), ('slat2', 11.5, 16.2)):
            m = Mesh(); panel(m, sx, s0, s1, 0.0, SC + 0.01, SKIN, 0.75)
            a = hinge_pt(s0, SC, foil_z(s0, SC, False) - wing_at(s0)[3]); b = hinge_pt(s1, SC, foil_z(s1, SC, False) - wing_at(s1)[3])
            emit(nm + '_' + side, m, (a + b) / 2, hull=False)
            point(nm + '_' + side + '_hingeA', a); point(nm + '_' + side + '_hingeB', b)
        # spoilers: panels on the upper surface just ahead of the flaps, hinged at their front edge
        for nm, s0, s1, n in (('spoilerin', 2.4, 6.0, 2), ('spoilerout', 7.2, 12.3, 3)):
            m = Mesh(); w = (s1 - s0) / n
            for k in range(n):
                p0, p1 = s0 + k * w + 0.04, s0 + (k + 1) * w - 0.04
                rings = []
                for ss in drange(p0, p1, 0.6):
                    le, c, t, z = wing_at(ss); us = [0.585 + (FC - 0.595) * j / 5 for j in range(6)]
                    top = [Vector((sx * ss, Y(le + u * c), foil_z(ss, u, True) + 0.035)) for u in us]
                    bot = [Vector((sx * ss, Y(le + u * c), foil_z(ss, u, True) + 0.008)) for u in reversed(us)]
                    rings.append(top + bot)
                m.loft(rings, SKIN)
            a = hinge_pt(s0, 0.585, foil_z(s0, 0.585, True) - wing_at(s0)[3] + 0.02)
            b = hinge_pt(s1, 0.585, foil_z(s1, 0.585, True) - wing_at(s1)[3] + 0.02)
            emit(nm + '_' + side, m, (a + b) / 2, hull=False)
            point(nm + '_' + side + '_hingeA', a); point(nm + '_' + side + '_hingeB', b)
        # pylon hardpoint midway between the two flap track fairings (wing2 underside, s 9.7)
        le, c, t, z = wing_at(9.7)
        point('pylon_' + side + '1', Vector((sx * 9.7, Y(le + 0.35 * c), z - 0.06 * c)))
        # engine: nacelle (engine_*), pylon strut (intake_*), exhaust plug (nozzle_R*)
        cx, cz = sx * 5.35, -2.25
        prof = [(12.80, 0.88), (12.90, 1.02), (13.25, 1.09), (14.1, 1.10), (15.3, 1.04), (16.4, 0.86), (16.85, 0.74)]
        m = Mesh(); m.loft(revolve(prof, cx, cz), SKIN, cap0=False, cap1=False)
        m.loft(revolve([(13.05, 0.02), (13.05, 0.93)], cx, cz), DARK, cap0=False, cap1=False)
        m.loft(revolve([(12.80, 0.88), (13.05, 0.93)], cx, cz), METAL, cap0=False, cap1=False)
        emit('engine_' + side, m, Vector((cx, Y(14.8), cz)))
        m = Mesh(); m.loft(revolve([(16.5, 0.62), (16.85, 0.58), (17.3, 0.40), (17.85, 0.05)], cx, cz, 20), METAL, cap1=False)
        emit('nozzle_' + side, m, Vector((cx, Y(16.85), cz)))
        point('thrust_' + side, Vector((cx, Y(17.9), cz)))
        # pylon: a streamlined strut from just behind the fan cowl to past the trailing edge, buried in the nacelle
        # below and the wing above, tapered at both ends like the real pylon
        def nac_r(dd):
            for (a0, r0), (a1, r1) in zip(prof, prof[1:]):
                if a0 <= dd <= a1: return r0 + (r1 - r0) * (dd - a0) / (a1 - a0)
            return prof[-1][1]
        m = Mesh(); rings = []
        for dd in drange(13.3, 18.1, 0.3):
            k = (dd - 13.3) / 4.8
            hw = 0.19 * min(1.0, k / 0.12, (1 - k) / 0.25) + 0.03
            top = -0.80 if dd > 15.2 else -0.80 - 0.10 * (15.2 - dd) / 1.9
            bot = cz + (nac_r(dd) if dd <= 16.85 else 0.55) - 0.12
            if dd > 16.85: bot = max(bot, top - 0.9 + 0.75 * (dd - 16.85) / 1.25)
            rings.append(section_at(cx, dd, hw, top, bot))
        m.loft(rings, SKIN)
        emit('intake_' + side, m, Vector((cx, Y(15.7), -1.12)))
        # horizontal tail: fixed stabiliser (0-70 % chord) + elevator
        m = Mesh(); m.loft([ht_ring(s, sx, 0.0, 0.7) for s in drange(0.6, 6.16, 1.0)], SKIN)
        emit('hstab_' + side, m, Vector((sx * 3.4, Y(34.3), HZ + 3.4 * HDIH)))
        m = Mesh(); m.loft([ht_ring(s, sx, 0.7, 1.0) for s in drange(0.95, 6.16, 1.0)], SKIN)
        def hpt(s):
            le, c, t = lerp_tab(HT, s); return Vector((sx * s, Y(le + 0.7 * c), HZ + s * HDIH))
        a, b = hpt(0.95), hpt(6.16); emit('elevator_' + side, m, (a + b) / 2)
        point('elevator_' + side + '_hingeA', a); point('elevator_' + side + '_hingeB', b)
        # main gear: strut (gear_*), oleo (gear_*_unsprung), twin wheels (wheel_*) about the axle; track 6.7 m
        gx, gd, wr = sx * 3.35, 18.8, 0.58
        top, axle = -1.30, GROUND + wr
        m = Mesh(); m.cyl((gx, Y(gd), (top + axle + 0.9) / 2), 'Z', 0.15, top - (axle + 0.9), METAL, 12)
        m.box((gx, Y(gd + 0.35), top - 0.35), (0.12, 0.7, 0.12), METAL)
        # leg door on the outboard face of the strut: it closes the leg slot flush with the lower skin when stowed
        m.box((gx + sx * 0.21, Y(gd), top - 0.72), (0.04, 0.72, 1.25), SKIN)
        emit('gear_' + side, m, Vector((gx, Y(gd), top)))
        point('gearHinge_' + side, Vector((gx, Y(gd), top)))
        m = Mesh(); m.cyl((gx, Y(gd), axle + 0.45), 'Z', 0.11, 0.9, METAL, 12); m.cyl((gx, Y(gd), axle), 'X', 0.07, 0.95, METAL, 10)
        emit('gear_' + side + '_unsprung', m, Vector((gx, Y(gd), axle)))
        m = Mesh()
        for k in (-0.32, 0.32): m.cyl((gx + k, Y(gd), axle), 'X', wr, 0.36, TYRE, 24); m.cyl((gx + k, Y(gd), axle), 'X', 0.30, 0.38, METAL, 16)
        emit('wheel_' + side, m, Vector((gx, Y(gd), axle)), hull=False)
        point('axle_' + side, Vector((gx, Y(gd), axle)))

    # nose gear (d 3.5), twin wheels; retracts forward
    nd, wr = 3.5, 0.36; top, axle = -1.45, GROUND + wr
    m = Mesh(); m.cyl((0, Y(nd), (top + axle + 0.7) / 2), 'Z', 0.10, top - (axle + 0.7), METAL, 12)
    emit('gear_F', m, Vector((0, Y(nd), top)))
    point('gearHinge_F', Vector((0, Y(nd), top)))
    m = Mesh(); m.cyl((0, Y(nd), axle + 0.35), 'Z', 0.08, 0.7, METAL, 12); m.cyl((0, Y(nd), axle), 'X', 0.05, 0.6, METAL, 10)
    emit('gear_F_unsprung', m, Vector((0, Y(nd), axle)))
    m = Mesh()
    for k in (-0.21, 0.21): m.cyl((k, Y(nd), axle), 'X', wr, 0.22, TYRE, 20); m.cyl((k, Y(nd), axle), 'X', 0.18, 0.24, METAL, 12)
    emit('wheel_F', m, Vector((0, Y(nd), axle)), hull=False)
    point('axle_F', Vector((0, Y(nd), axle)))
    # nose bay doors: two clamshell doors hinged along the bay sides, shaped to the skin they close flush with
    for side, sx in (('L', -1), ('R', 1)):
        rings = []
        for dd in drange(NB_D0 + 0.02, NB_D1 - 0.02, 0.2):
            xs = [0.006 + (NB_X - 0.012) * k / 6 for k in range(7)]
            lo = [Vector((sx * x, Y(dd), skin_z(fus, x, dd) - 0.012)) for x in xs]
            rings.append(lo + [Vector((p.x, p.y, p.z + 0.03)) for p in reversed(lo)])
        m = Mesh(); m.loft(rings, SKIN)
        ha = Vector((sx * NB_X, Y(NB_D0), skin_z(fus, NB_X, NB_D0))); hb = Vector((sx * NB_X, Y(NB_D1), skin_z(fus, NB_X, NB_D1)))
        emit('geardoor_F' + side, m, (ha + hb) / 2, hull=False)
        point('geardoor_F' + side + '_hingeA', ha); point('geardoor_F' + side + '_hingeB', hb)

    # fin: lower (vstab_L, z 1.2-4.6) and upper (vstab_R, z 4.6-7.65) fixed parts, each with a rudder (70-100 % chord)
    for nm, z0, z1 in (('L', 1.2, 4.6), ('R', 4.6, 7.65)):
        m = Mesh(); m.loft([fin_ring(z, 0.0, 0.7) for z in drange(z0, z1, 0.6)], SKIN, cap0=(nm == 'R'))
        zm = (z0 + z1) / 2; le, c, t = lerp_tab(FIN, zm); emit('vstab_' + nm, m, Vector((0, Y(le + 0.3 * c), zm)))
        za, zb = max(z0, 1.6), z1
        m = Mesh(); m.loft([fin_ring(z, 0.7, 1.0) for z in drange(za, zb, 0.6)], SKIN)
        def fpt(z):
            le, c, t = lerp_tab(FIN, z); return Vector((0, Y(le + 0.7 * c), z))
        a, b = fpt(za), fpt(zb); emit('rudder_' + nm, m, (a + b) / 2)
        point('rudder_' + nm + '_hingeA', a); point('rudder_' + nm + '_hingeB', b)

    # GlobalEye (Erieye) dorsal radar: the balanced beam ("ski") stands on two swept, streamlined pylons over the wing box
    # and slopes slightly down towards the front, as on the real aircraft. Built in mount space: pivot = dorsalMount on
    # the crown at d 17.2
    dm = Vector((0, Y(17.2), 1.91))
    m = Mesh()
    bl, bh, bw, b0, slope = 8.0, 0.80, 0.62, 0.66, math.radians(1.5)
    zmid = 1.91 + b0 + bh / 2
    def beam_z(dd): return zmid - (17.2 - dd) * math.tan(slope)      # lower towards the nose
    rings = []
    for dd in drange(17.2 - bl / 2, 17.2 + bl / 2, 0.2):
        end = min(dd - (17.2 - bl / 2), (17.2 + bl / 2) - dd); taper = math.sqrt(max(0.0, min(1.0, end / 0.7)))
        hw, hh = bw / 2 * (0.25 + 0.75 * taper), bh / 2 * (0.45 + 0.55 * taper)
        zc = beam_z(dd); rings.append(section(dd, max(hw, 0.04), zc + hh, zc - hh, n=24, ex=6.0))
    m.loft(rings, SKIN)
    for pd in (15.0, 19.0):
        # pylon: symmetric aerofoil section, 1.5 m chord at the root tapering to 1.1 m, leading edge swept back 35 deg
        prings = []
        for k in range(6):
            tt = k / 5; zb = 1.91 - 0.06; zt = beam_z(pd) - bh / 2 + 0.06; z = zb + (zt - zb) * tt
            c = 1.5 - 0.4 * tt; le = pd - 0.75 + (z - zb) * math.tan(math.radians(35))
            prings.append(foil_ring(lambda u, o: o, lambda u, o, le=le, c=c: Y(le + u * c), lambda u, o, z=z: z, c, 0.12, 0.0, 1.0, 10, camber=0.0))
        m.loft(prings, SKIN)
    emit('globaleye', m, dm)
    point('dorsalMount', dm)

    # crew, mounts, cameras, CoM
    rd = WIN_D0 + WIN_P / 2 - 0.05
    for nm, x, d, z in (('RearSeater1', -0.65, rd, FLOOR_Z + 0.70), ('RearSeater2', 0.65, rd, FLOOR_Z + 0.70)):
        point(nm, Vector((x, Y(d), z)))
    point('laserMount', Vector((0, Y(38.25), 0.62)))
    point('CoM', Vector((0, Y(17.6), -0.3)))
    point('targetCamForward', Vector((0, Y(1.2), -1.25)))
    point('targetCamRear', Vector((0, Y(36.5), 1.6)))
    point('landingCamPoint', Vector((0, Y(5.0), -1.95)))
    point('flareEjector_L', Vector((-1.2, Y(31.5), -1.0)))
    point('flareEjector_R', Vector((1.2, Y(31.5), -1.0)))
    point('contactSparks', Vector((0, Y(20.0), -2.4)))

if __name__ == '__main__':
    build()
    out = sys.argv[sys.argv.index('--') + 1]
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print('parts', len(bpy.data.collections['MODEL'].objects), 'cols', len(bpy.data.collections['COLLISION'].objects), 'points', len(bpy.data.collections['POINTS'].objects))
