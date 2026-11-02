"""P220 Primrose first-pass model, split into the damage parts of the Medusa-derived prefab.
Run: python3 p220_parts.py -- <out.blend>
Axes: Blender X right, Y forward, Z up. d = metres aft of the nose tip, Y = NOSE_Y - d. Z = 0 on the fuselage
centreline, ground at GROUND. Every part is its own mesh object whose origin is the part pivot (world-aligned).
Collection MODEL holds visible meshes, COLLISION holds <part>_colmesh convex hulls, POINTS holds empties
(pivots, hinges, gear, seats, mounts) that the Unity builder places transforms on."""
import bpy, bmesh, math, sys, os
from mathutils import Vector, Matrix

L = 38.7
NOSE_Y = L / 2
GROUND = -3.77
def Y(d): return NOSE_Y - d
FIN_SPLIT = 3.35   # upper fin fold line (0.3.10: 3.8 left the folded fin top at 7.95 m against the 8.00 m medium hangar door)

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
    (30.0, 1.80, 1.91, -1.80), (32.5, 1.62, 1.86, -1.40), (34.8, 1.30, 1.74, -0.70), (36.8, 0.82, 1.50, -0.05),
    (38.1, 0.36, 1.31, 0.60), (38.28, 0.315, 1.272, 0.642)]   # round 0.63 m end: the laser ball sits half inside it
# Airbus tail: the crown runs almost straight under the fin (0.23 m drop to the fin trailing edge, measured off the
# HB-JCF side photo) and the underside sweeps up to a high, small tail cone
fus = pchip(FUS)
# wing-to-body fairing: broad and flat-bottomed like the real one, only ~0.15 m below the fuselage keel
# belly fairing (0.3.11: it started abruptly and ran into the weapons bay): both ends now start inside the
# fuselage and swell out over a long taper, and the rear end is back inside the skin before the bay at d 25.2
FAIR = [(8.6, 0.80, -1.25, -1.84), (10.2, 1.35, -1.02, -1.92), (11.8, 1.85, -0.80, -1.98), (13.4, 2.18, -0.64, -2.02),
        (15.5, 2.32, -0.60, -2.03), (19.5, 2.35, -0.60, -2.03), (21.6, 2.18, -0.63, -2.01), (23.0, 1.72, -0.78, -1.96),
        (24.2, 1.12, -1.02, -1.89), (24.9, 0.75, -1.22, -1.84)]
FAIR_EX = 5.0
fair = pchip(FAIR)

def skin_z(tab, x, d, ex=2.2):
    # lower surface height of a superellipse section at lateral offset x
    _, hw, zt, zb = tab(d); zc, hh = (zt + zb) / 2, (zt - zb) / 2
    u = min(abs(x) / hw, 0.999)
    return zc - hh * (1 - u ** ex) ** (1 / ex)
def fair_z(x, d): return skin_z(fair, x, d, FAIR_EX)
def wing_lower(ss, dd):
    le, c, t, z = wing_at(ss); u = (dd - le) / c
    if not (0.0 <= u <= 1.0): return None
    th = 5 * t * (0.2969 * math.sqrt(u) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4) * c
    return z + 0.02 * c * 4 * u * (1 - u) - th
def under_z(x, dd):
    """Lowest skin under the wing root at (x, d): belly fairing or wing lower surface."""
    x = abs(x); zs = []
    if x < fair(dd)[1] * 0.995: zs.append(fair_z(x, dd))
    if x >= 1.7:
        w = wing_lower(x, dd)
        if w is not None: zs.append(w)
    return min(zs) if zs else -1.2

# main wheel wells (stowed wheels lie flat in the belly fairing) and the nose gear bay
# main gear: trunnion at x 3.35, d 18.40 (on the rear spar just ahead of the inboard flap), folding 80 deg inboard
GEAR_X, GEAR_D, GEAR_TOP, GEAR_FOLD = 3.35, 18.40, -1.05, 80.0
WELL_X, WELL_D, WELL_R = 1.27, GEAR_D, 0.66     # where the twin wheels lie when the leg has folded 80 deg inboard
SLOT_W, SLOT_X1 = 0.22, 3.62           # leg bay: half width and outboard end
WELL_CX, WELL_RX = 1.40, 0.76           # the wheel well is a slight oval, stretched outboard where the tyres swing in
NOTCH_X, NOTCH_W = WELL_CX + WELL_RX, SLOT_W
WELL_ROOF = -0.86   # 0.3.14: was -0.82, the roof plate showed through the wing root skin
def in_cut(c):
    """Underside opening for the main gear: oval wheel well and the leg bay slot out to the trunnion."""
    x = abs(c.x); dd = NOSE_Y - c.y; e = abs(dd - GEAR_D)
    if ((x - WELL_CX) / WELL_RX) ** 2 + (e / WELL_R) ** 2 < 1.0: return True
    return WELL_CX < x < SLOT_X1 and e < SLOT_W
def cut_outline():
    """Plan outline (x, d) of the opening on the right side, counter-clockwise, densely sampled."""
    a0 = math.degrees(math.asin(SLOT_W / WELL_R))
    pts = [(WELL_CX + WELL_RX * math.cos(math.radians(a)), GEAR_D + WELL_R * math.sin(math.radians(a))) for a in drange(a0, 360 - a0, 6)]
    corners = [(SLOT_X1, GEAR_D - SLOT_W), (SLOT_X1, GEAR_D + SLOT_W), pts[0]]
    prev = pts[-1]
    for cpt in corners:
        n = max(1, int(math.hypot(cpt[0] - prev[0], cpt[1] - prev[1]) / 0.08))
        pts += [(prev[0] + (cpt[0] - prev[0]) * k / n, prev[1] + (cpt[1] - prev[1]) * k / n) for k in range(1, n + 1)]
        prev = cpt
    return pts[:-1]
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
FN = 36
ZA, ZB, WZ = 0.30, 0.80, 0.55                  # cabin window band and window centre height
WIN_D0, WIN_P, WIN_N = 5.92, 0.56, 10          # 10 rows of cabin windows into the crew cabin
DOOR_D0, DOOR_D1, DOOR_Z0, DOOR_Z1 = 4.65, 5.55, -0.55, 1.28    # forward doors (open for the crew to bail out)
LASER_HOOD = 38.60                              # aft edge of the tail laser hood (the cone ended at 38.28 until 0.3.6)
BAY_X, BAY_D0, BAY_D1, BAY_TOP = 1.15, 25.2, 29.6, -0.60        # rear weapons bay, two Medusa bays side by side
FLOOR_Z, CAB_D0, CAB_D1 = -0.55, 4.45, 12.4   # 0.3.22: crew cabin bulkhead 0.5 m aft (flight deck bulkhead moved aft)
EXTRA_Z = [DOOR_Z0, ZA, ZB, DOOR_Z1]
def fsec(d, n=FN, ex=2.2):
    _, hw, zt, zb = fus(d); zc, hh = (zt + zb) / 2, (zt - zb) / 2
    angs = [2 * math.pi * i / n for i in range(n)]
    # the extra edge angles only matter where the doors, windows and bay are cut; in the nose and the tail cone they
    # are frozen at their values at the ends of that stretch, so they never cross the regular angles from one ring to
    # the next (that twisted quads into creases under the nose tip, 0.3.10)
    da = min(max(d, 3.2), 30.0)
    _, hw_, zt_, zb_ = fus(da); zc_, hh_ = (zt_ + zb_) / 2, (zt_ - zb_) / 2
    for z in EXTRA_Z:
        t = max(-0.97, min(0.97, (z - zc_) / hh_)); a = math.asin(math.copysign(abs(t) ** (ex / 2), t))
        angs += [a % (2 * math.pi), (math.pi - a) % (2 * math.pi)]
    a = math.acos(min(BAY_X / hw_, 0.97) ** (ex / 2))
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

def door_window(m, sx, dc, mat, off=0.006, wa=0.10, wb=0.12):   # small and round, as on Airbus doors
    ring = squircle_uv(rect_uv(1, 1, 5), 1, 1, wa, wb)
    fan(m, skin_pt(sx, dc, WZ, off), [skin_pt(sx, dc + a, WZ + b, off) for a, b in ring], mat)

# flight deck glazing as on the real nose: two front panes either side of a centre post on the forehead, two side
# panes behind a canted post, each a quad in (station d, section angle in degrees) for the right side
# 0.3.20: front pane sills lowered to run along the glareshield top for more view over the nose
# (bottom-inner 84 -> 80 deg, bottom-outer 26 -> 19 deg at d 2.26), side pane front-bottom follows (22.5 -> 17)
# 0.3.21: all four window tops on one level line (z 1.094 in the front view), and a narrow centre post with
# parallel sides (inner pane edges at 0.07 m either side of the centre line, bottom and top)
PANES = [((1.15, 87.28), (2.10, 87.95), (2.40, 63.58), (2.26, 19)),    # front: bottom-inner, top-inner, top-outer, bottom-outer
         ((2.486, 60.39), (3.25, 44.33), (3.45, 38.5), (3.45, 15), (2.374, 17.72))]   # 0.3.22: canted post a constant 12 cm wide (parallel edges)   # side: top-front, notch top, notch rear, bottom-rear, bottom-front
# deep A220 glazing: the windscreen and side window share one nearly straight sill at z ~0.40-0.57 (Airbus look),
# the windscreen tops out at z ~1.15 and the side window runs 0.9 m aft, for a wide field of view from the seats.
# Pane edges run straight in 3D between the corners (not straight in section-angle space, which bowed the sills),
# and the side window has the Airbus 45 degree notch in its top rear corner.
def pane_coords(p):
    dd = NOSE_Y - p.y; _, hw, zt, zb = fus(dd); zc, hh = (zt + zb) / 2, (zt - zb) / 2
    t = max(-1.0, min(1.0, (p.z - zc) / hh))
    return dd, math.degrees(math.atan2(math.copysign(abs(t) ** 1.1, t), min(abs(p.x) / hw, 1.0) ** 1.1))
def in_quad(pt, quad):
    sgn = 0
    for i in range(len(quad)):
        (a0, b0), (a1, b1) = quad[i], quad[(i + 1) % len(quad)]
        cr = (a1 - a0) * (pt[1] - b0) - (b1 - b0) * (pt[0] - a0)
        if abs(cr) < 1e-12: continue
        if sgn == 0: sgn = 1 if cr > 0 else -1
        elif (cr > 0) != (sgn > 0): return False
    return True
_PPOLY = {}
PANE_OUT = []
def pane_poly(quad, k=10):
    """Dense pane outline in (d, deg): each edge is a straight 3D line between the corner points, projected onto the skin."""
    if quad in _PPOLY: return _PPOLY[quad]
    cs = [surf(d, math.radians(a), 0.0) for d, a in quad]; out = []
    for i in range(len(cs)):
        a, b = cs[i], cs[(i + 1) % len(cs)]
        for j in range(k):
            out.append(pane_coords(a.lerp(b, j / k)))
    _PPOLY[quad] = out; return out
def windscreen_open(q):
    """Skin quads wholly inside a windscreen pane are cut out, so the glass looks into the flight deck."""
    if any(abs(p.x) < 0.02 for p in q) or len({p.x > 0 for p in q}) > 1: return False
    cs = [pane_coords(p) for p in q]
    return any(all(in_quad(c, pane_poly(quad)) for c in cs) for quad in PANES)
# The skin is cut exactly along each pane (0.3.10: the old stepped cut left spiky skin over the glass). Work in
# the pane's (station, section angle) space: each skin quad that crosses a pane outline is split into convex pieces
# outside the pane, mapped back onto the quad bilinearly so the cut edges stay on the original quad edges.
_PCONV = {}
def pane_convex(quad):
    if quad in _PCONV: return _PCONV[quad]
    pts = pane_poly(quad); cd = sum(p[0] for p in pts) / len(pts); ca = sum(p[1] for p in pts) / len(pts)
    pts = sorted(set((cd + (p[0] - cd) * 0.985, ca + (p[1] - ca) * 0.985) for p in pts))   # tuck 1.5% under the frame
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0: hi.pop()
        hi.append(p)
    _PCONV[quad] = lo[:-1] + hi[:-1]; return _PCONV[quad]       # counter-clockwise
def _clip(poly, a, b, keep_left):
    """Clip a polygon to one side of the line a->b (left = inside of a CCW polygon)."""
    def side(p): return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    out = []
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        sp, sq = side(p), side(q)
        ip, iq = (sp >= 0) == keep_left, (sq >= 0) == keep_left
        if ip: out.append(p)
        if ip != iq:
            t = sp / (sp - sq); out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out
def _subtract(poly, conv):
    """Convex polygon minus a convex CCW polygon, as a list of convex pieces."""
    pieces, rest = [], poly
    for i in range(len(conv)):
        if len(rest) < 3: break
        a, b = conv[i], conv[(i + 1) % len(conv)]
        out = _clip(rest, a, b, False)
        if len(out) >= 3: pieces.append(out)
        rest = _clip(rest, a, b, True)
    return pieces
def _area(poly): return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
def windscreen_clip(q):
    if any(abs(p.x) < 0.02 for p in q) or len({p.x > 0 for p in q}) > 1: return None
    return clip_quad(q, [pane_coords(p) for p in q], [pane_convex(quad) for quad in PANES])
def clip_quad(q, cs, convs):
    """Split a skin quad (3D corners q, 2D coords cs) into the convex pieces outside every convex CCW polygon in convs.
    None = untouched (keep the quad), [] = wholly inside (drop it)."""
    pieces = [list(cs)]; hit = False
    for conv in convs:
        dmin = min(c[0] for c in conv); dmax = max(c[0] for c in conv); amin = min(c[1] for c in conv); amax = max(c[1] for c in conv)
        if max(c[0] for c in cs) < dmin or min(c[0] for c in cs) > dmax or max(c[1] for c in cs) < amin or min(c[1] for c in cs) > amax: continue
        new = []
        for pc in pieces:
            if _area(pc) < 0: pc = list(reversed(pc))
            sub = _subtract(pc, conv)
            if len(sub) != 1 or abs(abs(_area(sub[0])) - abs(_area(pc))) > 1e-9: hit = True
            new += sub
        pieces = new
    if not hit: return None
    def to3d(pt):
        u, v = 0.5, 0.5
        for _ in range(16):
            f = [(1 - u) * (1 - v) * cs[0][k] + u * (1 - v) * cs[1][k] + u * v * cs[2][k] + (1 - u) * v * cs[3][k] for k in (0, 1)]
            rx, ry = f[0] - pt[0], f[1] - pt[1]
            du = [(1 - v) * (cs[1][k] - cs[0][k]) + v * (cs[2][k] - cs[3][k]) for k in (0, 1)]
            dv = [(1 - u) * (cs[3][k] - cs[0][k]) + u * (cs[2][k] - cs[1][k]) for k in (0, 1)]
            det = du[0] * dv[1] - du[1] * dv[0]
            if abs(det) < 1e-14: break
            u -= (rx * dv[1] - ry * dv[0]) / det; v -= (du[0] * ry - du[1] * rx) / det
        u = min(1.0, max(0.0, u)); v = min(1.0, max(0.0, v))
        return q[0] * ((1 - u) * (1 - v)) + q[1] * (u * (1 - v)) + q[2] * (u * v) + q[3] * ((1 - u) * v)
    flip = _area(cs) < 0; out = []
    for pc in pieces:
        if (_area(pc) < 0) != flip: pc = list(reversed(pc))
        out.append([to3d(p) for p in pc])
    return out
_WCONV = []
def well_convex():
    """The main gear opening (right side, plan x/d) as two convex CCW polygons: the oval wheel well and the leg slot."""
    if not _WCONV:
        _WCONV.append([(WELL_CX + WELL_RX * math.cos(2 * math.pi * k / 64), GEAR_D + WELL_R * math.sin(2 * math.pi * k / 64)) for k in range(64)])
        _WCONV.append([(WELL_CX, GEAR_D - SLOT_W), (SLOT_X1, GEAR_D - SLOT_W), (SLOT_X1, GEAR_D + SLOT_W), (WELL_CX, GEAR_D + SLOT_W)])
    return _WCONV
def well_clip(zmax_fn):
    """Clip for skin under the main gear: lower-surface quads are cut exactly along the opening (0.3.11: the old
    stepped cut and its covering lip z-fought and looked jagged)."""
    def clip(q):
        if any(p.z >= zmax_fn(p) for p in q): return None
        sx = 1 if sum(p.x for p in q) > 0 else -1
        if any(p.x * sx < 0 for p in q): return None
        return clip_quad(q, [(p.x * sx, NOSE_Y - p.y) for p in q], well_convex())
    return clip
def surf(dd, ang, pad=0.012):
    _, hw, zt, zb = fus(dd); hw += pad; zt += pad; zb -= pad
    zc, hh = (zt + zb) / 2, (zt - zb) / 2; c, sn = math.cos(ang), math.sin(ang)
    return Vector((hw * math.copysign(abs(c) ** (2 / 2.2), c), Y(dd), zc + hh * math.copysign(abs(sn) ** (2 / 2.2), sn)))
def pane_pt(quad, u, v):
    p0 = [quad[0][k] + (quad[1][k] - quad[0][k]) * u for k in (0, 1)]
    p1 = [quad[3][k] + (quad[2][k] - quad[3][k]) * u for k in (0, 1)]
    return p0[0] + (p1[0] - p0[0]) * v, p0[1] + (p1[1] - p0[1]) * v

DECOR = [(29.8, 30.7, -0.55, 1.20, True, (-1, 1)),      # rear passenger/service doors, under the fin leading edge
         (15.30, 15.90, -0.14, 1.08, True, (-1, 1)),    # over-wing emergency exits, two each side, 0.6 x 1.22 m as measured
         (16.40, 17.00, -0.14, 1.08, True, (-1, 1)),    # off a side photo of the A220-300
         (7.6, 9.0, -1.72, -0.88, False, (1,))]         # forward belly cargo door, right side

def drange(d0, d1, step):
    k = max(1, int(math.ceil((d1 - d0) / step))); return [d0 + (d1 - d0) * i / k for i in range(k + 1)]

class Mesh:
    def __init__(self): self.bm = bmesh.new(); self.mats = []
    def mat(self, m):
        if m not in self.mats: self.mats.append(m)
        return self.mats.index(m)
    def loft(self, rings, m, cap0=True, cap1=True, quads=None, keep=None, keep4=None, bandmats=None, wrap=False, clip4=None):
        mi = self.mat(m); vs = [[self.bm.verts.new(p) for p in r] for r in rings]; n = len(rings[0])
        pairs = list(zip(vs, vs[1:])) + ([(vs[-1], vs[0])] if wrap else [])
        for bi, (a, b) in enumerate(pairs):
            if bandmats: mi = self.mat(bandmats[bi])
            for i in range(n):
                if quads and not quads(i): continue
                if keep and not keep((a[i].co + a[(i + 1) % n].co + b[(i + 1) % n].co + b[i].co) / 4): continue
                if keep4 and not keep4((a[i].co, a[(i + 1) % n].co, b[(i + 1) % n].co, b[i].co)): continue
                if clip4:
                    pieces = clip4((a[i].co, a[(i + 1) % n].co, b[(i + 1) % n].co, b[i].co))
                    if pieces is not None:
                        for poly in pieces:
                            if len(poly) < 3: continue
                            f = self.bm.faces.new([self.bm.verts.new(v) for v in poly]); f.material_index = mi
                        continue
                f = self.bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i])); f.material_index = mi
        if wrap: return
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

def frame(axis):
    a = Vector(axis).normalized(); t = Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((1, 0, 0))
    u = a.cross(t).normalized(); return a, u, a.cross(u)
def rod(m, p0, p1, r, mat, seg=10, r1=None):
    """Closed tube from p0 to p1 (radius r, or tapering to r1)."""
    p0, p1 = Vector(p0), Vector(p1); a, u, v = frame(p1 - p0); r1 = r if r1 is None else r1
    m.loft([[p + (u * math.cos(2 * math.pi * i / seg) + v * math.sin(2 * math.pi * i / seg)) * rr for i in range(seg)] for p, rr in ((p0, r), (p1, r1))], mat)
def lathe(m, c, axis, prof, mat, seg=24, cap0=False, cap1=False):
    """Surface of revolution about axis through c; prof = [(axial offset, radius), ...]."""
    a, u, v = frame(axis); c = Vector(c)
    m.loft([[c + a * t + (u * math.cos(2 * math.pi * i / seg) + v * math.sin(2 * math.pi * i / seg)) * r for i in range(seg)] for t, r in prof], mat, cap0=cap0, cap1=cap1)
def tyre(m, c, r, w, tmat, hmat, seg=14):
    """Wheel about the X axis: rounded tyre, recessed rim, hub and hubcap."""
    h = w / 2; rr = r * 0.62
    lathe(m, c, (1, 0, 0), [(-h * 0.55, rr), (-h, r * 0.80), (-h * 0.80, r * 0.97), (0, r), (h * 0.80, r * 0.97), (h, r * 0.80), (h * 0.55, rr)], tmat, seg)
    for sg in (-1, 1):
        lathe(m, c, (1, 0, 0), [(sg * h * 0.55, rr), (sg * h * 0.40, rr * 0.45), (sg * h * 0.62, rr * 0.12), (sg * h * 0.62, 0.0)], hmat, seg)
def blade(m, base, up, l, h, mat, sweep=0.7, t=0.035):
    """Swept blade antenna standing on base, pointing along up (unit vector), chord l at the root."""
    up = Vector(up).normalized(); fwd = Vector((0, 1, 0)); side = up.cross(fwd).normalized(); b = Vector(base)
    tip_l = l * 0.45
    def ring(z, c, d_off):
        o = b + up * z + fwd * (-d_off)
        return [o + fwd * (c * 0.5), o + side * t * (1 - z / (h * 1.6)) + fwd * 0.0, o - fwd * (c * 0.5), o - side * t * (1 - z / (h * 1.6))]
    m.loft([ring(-0.03, l, 0.0), ring(h, tip_l, sweep * h - (l - tip_l) * 0.5)], mat)
def skin_frame(sx, dd, z):
    p = skin_pt(sx, dd, z); n = (skin_pt(sx, dd, z, 1.0) - p).normalized(); return p, n
def dome(m, p, n, r, h, mat, win=None, seg=16):
    """Low sensor dome (missile warner, GPS patch) on the skin at p with outward normal n."""
    a, u, v = frame(n); p = Vector(p) - a * 0.02
    prof = [(0, r), (h * 0.55, r * 0.97), (h * 0.85, r * 0.78), (h, r * 0.45), (h * 1.04, 0.0)]
    lathe(m, p, a, prof, mat, seg, cap0=True)
    if win: lathe(m, p, a, [(h * 0.86, r * 0.80), (h * 1.03, r * 0.40), (h * 1.065, 0.0)], win, seg)

def keel_z(dd):
    zb = fus(dd)[3]
    if FAIR[0][0] < dd < FAIR[-1][0]: zb = min(zb, fair(dd)[3])
    return zb
# aircraft survivability equipment for the military conversion and the antenna farm, by station d
MWS = [(2.75, 'side', -0.70), (35.6, 'side', 0.35), (11.0, 'bottom', 0), (12.1, 'top', 0), (33.6, 'bottom', 0)]   # missile warning sensors
BLADES = [(5.2, 'top', 0.30, 0.42), (7.6, 'top', 0.18, 0.26), (21.9, 'top', 0.36, 0.46), (6.6, 'bottom', 0.30, 0.42),
          (10.4, 'bottom', 0.18, 0.26), (23.4, 'bottom', 0.34, 0.44), (30.4, 'bottom', 0.30, 0.40)]
GPS = [8.7, 9.2]
FLARE_D0, FLARE_L, FLARE_Z = 30.7, 1.8, -1.15
def survivability(m, d0, d1, SKIN, DARK, GLASS, METAL):
    for dd, where, z in MWS:
        if not (d0 <= dd < d1): continue
        if where == 'side':
            for sx in (-1, 1): p, n = skin_frame(sx, dd, z); dome(m, p, n, 0.11, 0.09, SKIN, GLASS)
        else:
            p = Vector((0, Y(dd), fus(dd)[2] if where == 'top' else keel_z(dd))); dome(m, p, Vector((0, 0, 1 if where == 'top' else -1)), 0.11, 0.09, SKIN, GLASS)
    for dd, where, h, l in BLADES:
        if d0 <= dd < d1:
            up = 1 if where == 'top' else -1
            blade(m, Vector((0, Y(dd), fus(dd)[2] if up > 0 else keel_z(dd))), (0, 0, up), l, h, SKIN)
    for dd in GPS:
        if d0 <= dd < d1: dome(m, Vector((0, Y(dd), fus(dd)[2])), Vector((0, 0, 1)), 0.09, 0.025, DARK)
    # directional infrared countermeasure turrets: one on the belly behind the rear doors, one on the crown aft
    for dd, up in ((32.2, -1), (26.4, 1)):
        if d0 <= dd < d1:
            zb = fus(dd)[2] if up > 0 else keel_z(dd); p = Vector((0, Y(dd), zb)); n = Vector((0, 0, up))
            lathe(m, p - n * 0.03, n, [(0, 0.30), (0.10, 0.30), (0.12, 0.26)], SKIN, 20, cap1=True)
            dome(m, p + n * 0.11, n, 0.22, 0.22, METAL, GLASS)
    # chaff/flare dispenser pods on short pylons either side of the lower aft fuselage, firing aft
    if d0 <= FLARE_D0 + FLARE_L / 2 < d1:
        for sx in (-1, 1):
            p, n = skin_frame(sx, FLARE_D0 + 0.9, FLARE_Z); c = p + n * 0.26
            # flare dispenser pod: round top, flat bottom carrying a rectangular grid of flare cells
            zf = c.z - 0.11; prof = [(0.0, 0.025), (0.10, 0.08), (0.35, 0.155), (1.45, 0.16), (FLARE_L, 0.135)]
            def pring(a, r):
                return [Vector((c.x + r * math.cos(2 * math.pi * k / 20), Y(FLARE_D0 + a), max(c.z + r * math.sin(2 * math.pi * k / 20), zf))) for k in range(20)]
            m.loft([pring(a, r) for a, r in prof], SKIN, cap0=True, cap1=False)
            m.loft([pring(FLARE_L, 0.135), pring(FLARE_L + 0.004, 0.11)], DARK, cap0=False, cap1=True)
            g0, g1, gw, nc = FLARE_D0 + 0.45, FLARE_D0 + 1.40, 0.16, 10
            m.box((c.x, Y((g0 + g1) / 2), zf - 0.004), (gw, g1 - g0, 0.010), DARK)
            for k in range(nc + 1):
                m.box((c.x, Y(g0 + (g1 - g0) * k / nc), zf - 0.008), (gw + 0.012, 0.014, 0.008), METAL)
            for xo in (-gw / 2, 0.0, gw / 2):
                m.box((c.x + xo, Y((g0 + g1) / 2), zf - 0.008), (0.014, g1 - g0 + 0.014, 0.008), METAL)
            for dd in (FLARE_D0 + 0.55, FLARE_D0 + 1.25): rod(m, skin_pt(sx, dd, FLARE_Z, -0.02), Vector((c.x, Y(dd), c.z)) - n * 0.12, 0.045, SKIN, 8, 0.04)
    # SATCOM radome, a low flat blister on the crown behind the radar
    if d0 <= 23.8 < d1:
        rings = []
        for dd in drange(22.6, 25.0, 0.15):
            t = (dd - 22.6) / 2.4; sn = max(math.sin(math.pi * t), 0.0); h = 0.24 * sn ** 0.6; w = 0.05 + 0.50 * sn ** 0.45
            zt = fus(dd)[2]; rings.append([Vector((w * math.cos(math.pi * k / 12), Y(dd), zt - 0.04 + (h + 0.04) * math.sin(math.pi * k / 12) ** 0.6)) for k in range(13)])
        m.loft(rings, SKIN, cap0=False, cap1=False)

# ------------------------------------------------------------------ cargo bay (0.3.14 blockout)
# Main deck from the crew cabin's aft bulkhead to just ahead of the weapons bay: floor with roller tracks and side
# guide rails, a lined shell (no cargo for now) (a closed crescent so it is seen from inside through damage holes),
# an aft bulkhead, and a big pallet door in the left side at the aft end (outline only; no windows). Low detail on
# purpose: all non-cockpit interior spaces get a dedicated detail pass later.
CARGO_D0, CARGO_D1 = 12.55, 24.95
CARGO_DOOR = (21.2, 24.6, -0.40, 1.30)          # d0, d1, z0, z1, left side
PALLETS = []   # 0.3.16: bay kept empty for now; was (13.0, 16.2), (16.6, 19.8), (20.2, 23.4)
def cargo_bay(m, d0, d1, SKIN, DARK, METAL, BAY):
    a, b = max(d0, CARGO_D0), min(d1, CARGO_D1)
    if a >= b: return
    L = b - a; mid = (a + b) / 2
    hw = min(skin_pt(1, dd, FLOOR_Z, -0.05).x for dd in (a, b))
    m.box((0, Y(mid), FLOOR_Z - 0.02), (2 * hw, L, 0.04), BAY)                              # floor
    for x in (-1.0, -0.45, 0.45, 1.0):                                                     # roller tracks
        m.box((x, Y(mid), FLOOR_Z + 0.02), (0.10, L - 0.02, 0.04), METAL)
    for x in (-1.27, 1.27):                                                                # side guide rails
        m.box((x, Y(mid), FLOOR_Z + 0.05), (0.05, L - 0.02, 0.10), DARK)
    # lined shell: crescent section from floor level up over the crown, 5-8 cm inside the skin
    def crescent(dd):
        zt = fus(dd)[2] - 0.12; zs = [FLOOR_Z + (zt - FLOOR_Z) * k / 6 for k in range(7)]
        outer = [skin_pt(1, dd, z, -0.05) for z in zs] + [skin_pt(-1, dd, z, -0.05) for z in reversed(zs)]
        inner = [skin_pt(-1, dd, z, -0.08) for z in zs] + [skin_pt(1, dd, z, -0.08) for z in reversed(zs)]
        return outer + inner
    m.loft([crescent(dd) for dd in drange(a, b, 0.6 if (a < 6.0 or b > 27.5) else 6.0)], BAY, cap0=False, cap1=False)
    # aft bulkhead
    if d0 <= CARGO_D1 < d1 + 0.05:
        _, hw_, zt_, zb_ = fus(CARGO_D1); zcb = (zt_ + zb_) / 2
        ring = lambda dd: [Vector((p.x * 0.975, Y(dd), zcb + (p.z - zcb) * 0.975)) for p in section(*fus(CARGO_D1), n=24)]
        m.loft([ring(CARGO_D1 - 0.05), ring(CARGO_D1)], BAY, cap0=True, cap1=True)
    # pallets with netted loads, each built in the part that holds its centre
    for p0, p1 in PALLETS:
        pm = (p0 + p1) / 2
        if not (d0 <= pm < d1): continue
        pl = p1 - p0; zb = FLOOR_Z + 0.04
        m.box((0, Y(pm), zb + 0.025), (2.24, pl, 0.05), METAL)                                 # pallet base
        m.box((0, Y(pm), zb + 0.05 + 0.50), (2.10, pl - 0.10, 1.00), BAY)                       # load, lower block
        m.box((0, Y(pm), zb + 0.05 + 1.00 + 0.25), (1.50, pl - 0.20, 0.50), BAY)                # contoured top
        for k in range(4):                                                                     # net straps across
            dk = p0 + 0.25 + (pl - 0.5) * k / 3
            m.box((0, Y(dk), zb + 1.56), (1.54, 0.05, 0.02), DARK)
            for sx in (-1, 1):
                m.box((sx * 0.76, Y(dk), zb + 1.30), (0.02, 0.05, 0.52), DARK)
                m.box((sx * 1.06, Y(dk), zb + 0.55), (0.02, 0.05, 1.02), DARK)
                m.box((sx * 0.91, Y(dk), zb + 1.055), (0.32, 0.05, 0.02), DARK)
        for x in (-0.4, 0.4):                                                                  # net straps along
            m.box((x, Y(pm), zb + 1.56), (0.05, pl - 0.18, 0.02), DARK)
    # pallet door: seam outline on the left side at the aft end, hinges along its top edge
    e0, e1, z0, z1 = CARGO_DOOR
    if d0 <= (e0 + e1) / 2 < d1:
        outline(m, -1, e0, e1, z0, z1, DARK, w=0.03)
        for k in range(5):
            dk = e0 + 0.3 + (e1 - e0 - 0.6) * k / 4; p, n = skin_frame(-1, dk, z1 + 0.06)
            m.box(p + n * 0.01, (0.04, 0.16, 0.05), DARK)

MATS = {}
def material(name, rgb):
    if name not in MATS:
        m = bpy.data.materials.new(name); m.diffuse_color = (*rgb, 1); MATS[name] = m
    return MATS[name]

def coll(name):
    c = bpy.data.collections.get(name)
    if not c: c = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c)
    return c

def emit(name, mesh, pivot, hull=True, hull_pad=0.0, local=False, recalc=True, hull_keep=None):
    """Create the MODEL object (origin at pivot) and its convex-hull colmesh."""
    # internal structure (p220_structure.py) rides the part it sits in; it is left out of the colmesh hull below
    nstruct = len(mesh.bm.verts)
    structure(name, mesh)
    if recalc: bmesh.ops.recalc_face_normals(mesh.bm, faces=mesh.bm.faces)
    if name.startswith(('wheel_', 'gear_', 'engine_', 'revdoor_', 'fdoor_')) and not os.environ.get('NOBACK'):
        # open shells seen from both sides (hubs, the bypass duct through open reversers, door edges): add back faces,
        # since the game culls them
        # only open islands (any boundary edge) get back faces; closed solids are already seen correctly
        bm2 = mesh.bm; seen = set(); vmap = {}; bm2.normal_update()
        for f0 in list(bm2.faces):
            if f0 in seen: continue
            isl, stack = [], [f0]; seen.add(f0)
            while stack:
                f = stack.pop(); isl.append(f)
                for e in f.edges:
                    for g in e.link_faces:
                        if g not in seen: seen.add(g); stack.append(g)
            if not any(e.is_boundary for f in isl for e in f.edges): continue
            for f in isl:
                for v in f.verts:
                    if v not in vmap: vmap[v] = bm2.verts.new(v.co - v.normal * 0.002)   # 2 mm in: no z-fight with the front face
                g = bm2.faces.new([vmap[v] for v in reversed(f.verts)]); g.material_index = f.material_index
    me = bpy.data.meshes.new(name)
    bm = mesh.bm
    if not local:
        for v in bm.verts: v.co -= Vector(pivot)
    if hull:
        hb = bmesh.new()
        for v in list(bm.verts)[:nstruct]:
            if hull_keep is None or hull_keep(v.co + (Vector((0, 0, 0)) if local else Vector(pivot))): hb.verts.new(v.co)
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

def foil_ring(x_of, y_of, z_of, chord, t, u0, u1, n=14, camber=0.02, extra=()):
    """Partial-chord airfoil ring over chord fraction [u0, u1]: upper surface u0->u1, lower u1->u0.
    x_of/y_of/z_of map (u, thickness offset) to a 3D point. extra: chord fractions to add (kept inside (u0, u1),
    always the same count so neighbouring rings still match)."""
    us = [u0 + (u1 - u0) * (1 - math.cos(math.pi * i / n)) / 2 for i in range(n + 1)]
    if extra:
        us = sorted(us[1:-1] + [min(max(e, u0 + 0.001 * (k + 1)), u1 - 0.001 * (k + 1)) for k, e in enumerate(extra)])
        us = [u0] + us + [u1]
    def th(u):
        return 5 * t * (0.2969 * math.sqrt(max(u, 0)) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4) * chord
    ring = []
    for u in us: ring.append((u, th(u) + camber * chord * 4 * u * (1 - u)))
    for u in reversed(us[1:-1]): ring.append((u, -th(u) + camber * chord * 4 * u * (1 - u)))
    if u0 > 0: pass
    return [Vector((x_of(u, o), y_of(u, o), z_of(u, o))) for u, o in ring]

def wing_ring(s, sx, u0, u1, n=14, extra_d=()):
    le, c, t, z = wing_at(s)
    return foil_ring(lambda u, o: sx * s, lambda u, o: Y(le + u * c), lambda u, o: z + o, c, t, u0, u1, n,
                     extra=[(dd - le) / c for dd in extra_d])

def panel(mesh, sx, s0, s1, u0, u1, m, ds=0.8, ss=None, gearcut=False, caps=(True, True)):
    """Wing panel loft. gearcut: open the main gear bay in the lower skin (rings get the bay edges as extra chord stations)."""
    if ss is None: ss = drange(s0, s1, ds)
    if not gearcut:
        mesh.loft([wing_ring(s, sx, u0, u1) for s in ss], m, cap0=caps[0], cap1=caps[1]); return
    ed = [GEAR_D + k for k in (-WELL_R, -SLOT_W, SLOT_W, WELL_R)]
    before = set(mesh.bm.verts)
    mesh.loft([wing_ring(s, sx, u0, u1, 14, ed) for s in ss], m, cap0=caps[0], cap1=caps[1], clip4=well_clip(lambda p: wing_at(abs(p.x))[3]))
    bmesh.ops.remove_doubles(mesh.bm, verts=[v for v in mesh.bm.verts if v not in before], dist=0.0005)

def quarter_point(sx, s0, s1):
    sm = (s0 + s1) / 2; le, c, t, z = wing_at(sm); return Vector((sx * sm, Y(le + 0.25 * c), z))

HT = [(0.0, 32.6, 4.2, 0.11), (0.95, 33.1, 3.6, 0.11), (6.16, 36.3, 1.42, 0.10)]
HZ = 0.80; HDIH = math.tan(math.radians(3.0))
def ht_ring(s, sx, u0, u1):
    le, c, t = lerp_tab(HT, s); z = HZ + s * HDIH
    return foil_ring(lambda u, o: sx * s, lambda u, o: Y(le + u * c), lambda u, o: z + o, c, t, u0, u1, 12, camber=0.0)
FIN = [(1.2, 30.0, 5.75, 0.10), (1.9, 30.55, 5.30, 0.10), (7.55, 36.1, 1.45, 0.10)]   # measured off the HB-JCF side photo
def fin_ring(z, u0, u1):
    le, c, t = lerp_tab(FIN, z)
    return foil_ring(lambda u, o: o, lambda u, o: Y(le + u * c), lambda u, o: z, c, t, u0, u1, 12, camber=0.0)

def revolve(profile, cx, cz, n=28):
    return [[Vector((cx + r * math.cos(2 * math.pi * i / n), Y(d), cz + r * math.sin(2 * math.pi * i / n))) for i in range(n)] for d, r in profile]

# ------------------------------------------------------------------ engines
# nacelle: a closed shell (outer cowl, intake lip, bypass duct) with four pivoting thrust-reverser doors in the aft cowl
# (centred at 45/135/225/315 deg from the top, 72 deg wide, between beams at the pylon, the sides and the bottom) and
# a chevron ("toothed") fan nozzle. Doors pivot about a tangential axis at d REV_HINGE, as on the A320's pivot-door
# reversers: the forward edge kicks out and the short aft part tucks into the bypass duct to block the fan flow and
# turn it forward.
NAC_OUT = [(12.80, 0.88), (12.90, 1.02), (13.25, 1.09), (14.1, 1.10), (15.3, 1.04), (16.4, 0.86), (16.85, 0.74)]
NAC_IN = [(16.85, 0.705), (16.4, 0.76), (15.5, 0.86), (14.5, 0.93), (13.6, 0.95), (13.25, 0.935), (13.05, 0.925), (12.86, 0.90)]
REV_D0, REV_D1, REV_HINGE, NSEG = 15.45, 16.65, 16.38, 40     # doors at the back of the cowl, hinged near their aft edge
REV_DOORS = [(49.5, 31.5), (135, 36), (225, 36), (310.5, 31.5)]     # (centre, half width) deg from the top; the upper pair clears the pylon
def prof_r(prof, dd):
    pts = sorted(prof)
    for (a0, r0), (a1, r1) in zip(pts, pts[1:]):
        if a0 <= dd <= a1: return r0 + (r1 - r0) * (dd - a0) / (a1 - a0)
    return pts[0][1] if dd < pts[0][0] else pts[-1][1]
def nac_pt(cx, cz, dd, r, th):
    t = math.radians(th); return Vector((cx + r * math.sin(t), Y(dd), cz + r * math.cos(t)))
def in_door(dd, th):
    if not (REV_D0 < dd < REV_D1): return False
    th = th % 360; return any(abs(th - c) < hw for c, hw in REV_DOORS)
def engine(sx, side, cx, cz, SKIN, DARK, METAL, BAY):
    m = Mesh(); ths = [360.0 * i / NSEG for i in range(NSEG)]
    def stations(prof, extra):
        ds = sorted(set([round(d, 4) for d, r in prof] + [round(x, 4) for x in extra]))
        return ds
    outd = stations(NAC_OUT, drange(13.25, 16.85, 0.5) + [REV_D0, REV_D1])
    ind = sorted(stations(NAC_IN, drange(13.25, 16.85, 0.6) + [REV_D0, REV_D1]), reverse=True)
    rings, mats = [], []
    for dd in ind: rings.append([nac_pt(cx, cz, dd, prof_r(NAC_IN, dd), th) for th in ths]); mats.append(BAY)
    for dd in outd: rings.append([nac_pt(cx, cz, dd, prof_r(NAC_OUT, dd), th) for th in ths]); mats.append(SKIN)
    mats = mats[1:] + [SKIN]                          # band k joins ring k and k+1; the last band closes the trailing edge
    mats[len(ind) - 1] = METAL                        # intake lip
    def keep(c):
        dd = NOSE_Y - c.y; th = math.degrees(math.atan2(c.x - cx, c.z - cz)); return not in_door(dd, th)
    m.loft(rings, SKIN, bandmats=mats, keep=keep, wrap=True)
    # walls round each reverser opening, so an open door shows the cowl thickness, not a hollow shell
    for c, hw in REV_DOORS:
        a0, a1 = c - hw, c + hw; arc = [a0 + (a1 - a0) * k / 8 for k in range(9)]
        for dd in (REV_D0, REV_D1):
            m.loft([[nac_pt(cx, cz, dd, prof_r(NAC_OUT, dd), th) for th in arc], [nac_pt(cx, cz, dd, prof_r(NAC_IN, dd), th) for th in arc]], BAY, cap0=False, cap1=False, quads=lambda i: i < 8)
        dds = drange(REV_D0, REV_D1, 0.3)
        for th in (a0, a1):
            m.loft([[nac_pt(cx, cz, dd, prof_r(NAC_OUT, dd), th) for dd in dds], [nac_pt(cx, cz, dd, prof_r(NAC_IN, dd), th) for dd in dds]], BAY, cap0=False, cap1=False, quads=lambda i: i < len(dds) - 1)
    # fan: spinner, twenty swept blades, dark disc behind; core cowl visible through the bypass duct
    ax = Vector((0, -1, 0))
    lathe(m, Vector((cx, Y(12.92), cz)), ax, [(0, 0.0), (0.06, 0.09), (0.16, 0.18), (0.30, 0.26), (0.38, 0.28)], METAL, 12)
    lathe(m, Vector((cx, Y(13.36), cz)), ax, [(0, 0.95), (0, 0.0)], DARK, 20)
    for b in range(20):
        ph = 360.0 * b / 20; rr = [0.27, 0.6, 0.92]
        rows = []
        for r in rr:
            sw = 0.10 + 0.10 * (r - 0.27) / 0.65                       # half chord in angle-metres, more twist at the tip
            pa = ph - math.degrees(sw * 0.8 / r); pb = ph + math.degrees(sw * 0.8 / r)
            rows.append([nac_pt(cx, cz, 13.14 + 0.02 * (r - 0.27), r, pa), nac_pt(cx, cz, 13.32, r, pb)])
        m.loft([[p for p in row] + [p + Vector((0, 0.008, 0)) for p in reversed(row)] for row in rows], DARK, cap0=True, cap1=True)
    lathe(m, Vector((cx, Y(13.36), cz)), ax, [(0, 0.42), (0.7, 0.52), (1.6, 0.60), (3.14, 0.62)], METAL, 16)
    # chevron fan nozzle: fourteen thin teeth trailing from the cowl lip, toed slightly in
    NT = 12; r0 = prof_r(NAC_OUT, 16.85); ri = prof_r(NAC_IN, 16.85)
    for k in range(NT):
        ta, tb = 360.0 * k / NT, 360.0 * (k + 1) / NT; tm = (ta + tb) / 2
        ring = lambda dr: [nac_pt(cx, cz, 16.84, r0 - dr, ta), nac_pt(cx, cz, 16.84, r0 - dr, tb), nac_pt(cx, cz, 17.03, r0 - 0.022 - dr, tm)]
        outer, inner = ring(0.0), ring(r0 - ri)
        mi = m.mat(SKIN); vo = [m.bm.verts.new(p) for p in outer]; vi = [m.bm.verts.new(p) for p in inner]
        m.bm.faces.new(vo).material_index = mi; m.bm.faces.new(list(reversed(vi))).material_index = mi
        for i in range(3):
            j = (i + 1) % 3
            if i == 0: continue                                   # the base edge is buried in the cowl lip
            m.bm.faces.new((vo[j], vo[i], vi[i], vi[j])).material_index = mi
    emit('engine_' + side, m, Vector((cx, Y(14.8), cz)))
    point('engineAxis_' + side, Vector((cx, Y(REV_HINGE), cz)))
    # the four reverser doors (separate parts so they can pivot), each a closed solid of the cowl skin and duct wall
    for k, (c, hw) in enumerate(REV_DOORS):
        a0, a1 = c - hw + 0.6, c + hw - 0.6; arc = [a0 + (a1 - a0) * j / 6 for j in range(7)]
        dds = drange(REV_D0 + 0.01, REV_D1 - 0.01, 0.3)
        sec = lambda th: [nac_pt(cx, cz, dd, prof_r(NAC_OUT, dd), th) for dd in dds] + [nac_pt(cx, cz, dd, prof_r(NAC_IN, dd) + 0.01, th) for dd in reversed(dds)]
        m = Mesh()
        m.loft([sec(th) for th in arc], SKIN, bandmats=None)
        hr = (prof_r(NAC_OUT, REV_HINGE) + prof_r(NAC_IN, REV_HINGE)) / 2
        hp = nac_pt(cx, cz, REV_HINGE, hr, c)
        name = 'revdoor_%s%d' % (side, k + 1)
        # actuator lug on the door's inner face near its forward edge
        lug = nac_pt(cx, cz, 15.65, prof_r(NAC_IN, 15.65) + 0.05, c)
        for sg in (-1, 1):
            q = nac_pt(cx, cz, 15.65, prof_r(NAC_IN, 15.65) + 0.05, c + sg * 1.6)
            rod(m, q, nac_pt(cx, cz, 15.65, prof_r(NAC_IN, 15.65) + 0.012, c + sg * 1.6), 0.025, METAL, 6)
        emit(name, m, hp, hull=False); point(name + '_hinge', hp)
        # hydraulic actuator: cylinder pivoting in the fixed cowl ahead of the door, rod pinned to the door lug. Both
        # meshes are built along +Y from their pivots, so the game can aim them at each other as the door moves
        anc = nac_pt(cx, cz, 15.25, prof_r(NAC_IN, 15.25) + 0.03, c)      # on the forward frame, inside the duct wall
        L = (lug - anc).length
        m = Mesh(); o = Vector((0, 0, 0))
        rod(m, o, o + Vector((0, 0.32, 0)), 0.040, DARK, 10); rod(m, o + Vector((-0.05, 0, 0)), o + Vector((0.05, 0, 0)), 0.03, METAL, 6)
        emit('revcyl_%s%d' % (side, k + 1), m, anc, hull=False, local=True)
        m = Mesh()
        rod(m, o, o + Vector((0, 0.38, 0)), 0.022, METAL, 8); rod(m, o + Vector((-0.04, 0, 0)), o + Vector((0.04, 0, 0)), 0.03, METAL, 6)
        emit('revrod_%s%d' % (side, k + 1), m, lug, hull=False, local=True)
        point('revcyl_%s%d' % (side, k + 1), anc); point('revrod_%s%d' % (side, k + 1), lug)
    return m

# ------------------------------------------------------------------ build
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for c in ('MODEL', 'COLLISION', 'POINTS'): coll(c)
    SKIN = material('P220_skin', (0.86, 0.87, 0.89)); DARK = material('P220_dark', (0.05, 0.05, 0.06))
    METAL = material('P220_metal', (0.42, 0.43, 0.45)); TYRE = material('P220_tyre', (0.06, 0.06, 0.06))
    GLASS = material('P220_glass', (0.10, 0.13, 0.17)); GLASS_INT = material('P220_glass_int', (0.12, 0.15, 0.19)); WIN = material('P220_window', (0.07, 0.08, 0.10)); BAY = material('P220_bay', (0.30, 0.31, 0.32))

    # fuselage parts (d ranges); the window band and windshield ride the part they sit on
    FP = [('nose', 0.0, 0.9), ('cockpit_F', 0.9, 3.2), ('cockpit_R', 3.2, 9.5), ('fuselage_F', 9.5, 13.5),
          ('fuselage', 13.5, 22.0), ('fuselage_R', 22.0, 30.5), ('tail', 30.5, 38.28)]
    for name, d0, d1 in FP:
        m = Mesh()
        step = 0.2 if name == 'cockpit_F' else (0.5 if (d0 < 6 or d1 > 30) else 1.0)
        brk = [b for b in FUS_BREAKS if d0 < b < d1]
        ds = sorted([x for x in drange(max(d0, 0.0), d1, step) if all(abs(x - b) > 0.04 for b in brk)] + brk)
        if name == 'nose': ds[0] = 0.0
        # 0.3.23: the cockpit_F / cockpit_R joint at d 3.2 sits right across the crew seats; its end caps were a solid grey
        # disc inside the flight deck (covering the bulkhead, cutting the seats). Leave that joint open on both parts.
        # 0.3.25 structure pass: production breaks are open (the frames either side show when a section breaks away);
        # only the forward pressure bulkhead (cockpit_F front), the aft pressure bulkhead (fuselage_R end) and the two
        # extremities stay closed
        if STRUCT_ON: c0, c1 = name in ('nose', 'cockpit_F'), name in ('fuselage_R', 'tail')
        else: c0, c1 = name != 'cockpit_R', name != 'cockpit_F'
        m.loft([fsec(d) for d in ds], SKIN, cap0=c0, cap1=c1, keep=lambda c: not (in_nose_bay(c) or skin_open(c)),
               clip4=windscreen_clip if name == 'cockpit_F' else (well_clip(lambda p: -1.0) if name == 'fuselage' else None))
        if name in ('cockpit_F', 'fuselage'): bmesh.ops.remove_doubles(m.bm, verts=m.bm.verts, dist=0.0005)
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
                ring = [Vector((p.x * 0.985, p.y, zcb + (p.z - zcb) * 0.985)) for p in section(*fus(bd), n=24)]
                fan(m, Vector((0, Y(bd), zcb)), ring, BAY)
        if d0 <= CAB_D0 < d1: m.box((0, Y(CAB_D0 + 0.02), FLOOR_Z + 0.95), (0.7, 0.03, 1.9), DARK)   # flight deck door
        # door seams: forward doors (the doors themselves are separate parts), rear doors, over-wing exits, cargo door
        if d0 <= DOOR_D0 < d1:
            for sx in (-1, 1): outline(m, sx, DOOR_D0, DOOR_D1, DOOR_Z0, DOOR_Z1, DARK)
        for e0, e1, z0, z1, win, sides in DECOR:
            if not (d0 <= (e0 + e1) / 2 < d1): continue
            for sx in sides:
                outline(m, sx, e0, e1, z0, z1, DARK, w=0.025)
                if win: door_window(m, sx, (e0 + e1) / 2, WIN)
        if name == 'cockpit_F':
            glass_x, glass_i = Mesh(), Mesh()
        if name == 'cockpit_F':
            # flight deck glazing: the skin behind each pane is cut away (windscreen_open); each pane gets a dark frame
            # that covers the stepped edge of the cut
            for sx in (-1, 1):
                for quad in PANES:
                    edge = pane_poly(quad)
                    cd = sum(e[0] for e in edge) / len(edge); ca = sum(e[1] for e in edge) / len(edge)
                    def gp(dd, deg):
                        q = surf(dd, math.radians(deg)); q.x *= sx; return q
                    rings = [[gp(cd + (e[0] - cd) * f, ca + (e[1] - ca) * f) for e in edge] for f in (1.0, 0.75, 0.5, 0.25)]
                    # stock canopy convention (0.3.11: tint inside): the outer pane faces out and is seen from outside;
                    # a second pane just inside the skin, on the cockpit layer with the stock interior glass shader, faces in
                    # 0.3.17 (review): the glass sat 12 mm proud of the skin with a visible lifted edge; it now sits 5 mm out,
                    # under a frame band that laps over its edge and slopes down onto the skin
                    def gq(dd, deg):
                        q = surf(dd, math.radians(deg), 0.005); q.x *= sx; return q
                    rings = [[gq(cd + (e[0] - cd) * f, ca + (e[1] - ca) * f) for e in edge] for f in (1.0, 0.75, 0.5, 0.25)]
                    glass_x.loft(rings, GLASS, cap0=False, cap1=True)
                    PANE_OUT.append([[sx * v.x, v.y, v.z] for v in (surf(e[0], math.radians(e[1]), 0.0) for e in edge)])
                    def gi(dd, deg):
                        q = surf(dd, math.radians(deg), -0.03); q.x *= sx; return q
                    glass_i.loft([[gi(cd + (e[0] - cd) * f, ca + (e[1] - ca) * f) for e in edge] for f in (1.0, 0.75, 0.5, 0.25)], GLASS_INT, cap0=False, cap1=True)
                    def fp(dd, deg):
                        q = surf(dd, math.radians(deg), 0.008); q.x *= sx; return q
                    def fs(dd, deg):
                        q = surf(dd, math.radians(deg), 0.0); q.x *= sx; return q
                    m.loft([[fs(cd + (e[0] - cd) * 1.025, ca + (e[1] - ca) * 1.025) for e in edge], [fp(*e) for e in edge],
                            [fp(cd + (e[0] - cd) * 0.95, ca + (e[1] - ca) * 0.95) for e in edge]], DARK, cap0=False, cap1=False)
            # flight deck floor under the crew stations
            # 0.3.22: 3 cm under the flight deck carpet (was level with it: z-fighting)
            fx = lambda dd: skin_pt(1, dd, -0.25).x - 0.03
            m.loft([[Vector((-fx(dd), Y(dd), -0.25)), Vector((fx(dd), Y(dd), -0.25))] for dd in drange(1.1, CAB_D0, 0.3)], BAY,
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
            # nose gear bay opening lip in skin colour (no grey border), hiding the stepped cut
            def fr(x, dd): return Vector((x, Y(dd), skin_z(fus, x, dd) - 0.012))
            for sx in (-1, 1):
                m.loft([[fr(sx * (NB_X - 0.05), dd), fr(sx * (NB_X + 0.05), dd)] for dd in drange(NB_D0 - 0.05, NB_D1 + 0.05, 0.2)], SKIN, cap0=False, cap1=False, quads=lambda i: i == 0)
            for d0_, d1_ in ((NB_D0 - 0.05, NB_D0 + 0.05), (NB_D1 - 0.05, NB_D1 + 0.05)):
                m.loft([[fr(x, d0_), fr(x, d1_)] for x in [-NB_X + 2 * NB_X * k / 8 for k in range(9)]], SKIN, cap0=False, cap1=False, quads=lambda i: i == 0)
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
            # dorsal fin fillet: Airbus-style rounded root, a low concave fairing whose round-topped section widens and
            # rises into the fin leading edge (meets it at z 2.9), rather than the 737's sharp triangular dorsal fin
            def fin_half(z, dd):
                le, c, t_ = lerp_tab(FIN, z); u = (dd - le) / c
                if u <= 0: return 0.0
                u = min(u, 1.0); return 5 * t_ * (0.2969 * math.sqrt(u) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4) * c
            rings = []
            for dd in drange(29.3, 30.95, 0.22):
                t = (dd - 29.3) / 1.9; ztop = fus(dd)[2]
                sh = max(0.0, min(1.0, (dd - 30.15) / 0.8))          # narrows to the fin thickness where it meets the fin
                h = 0.62 * t ** 2.0; w = (0.06 + 0.24 * t ** 1.3) * (1 - 0.45 * sh)
                ring = []
                for k in range(9):
                    a_ = math.pi * k / 8; ca = math.cos(a_); zz = ztop - 0.06 + (h + 0.06) * math.sin(a_) ** 0.7
                    ring.append(Vector((w * math.copysign(abs(ca) ** 0.8, ca) * (1.0 + 0.6 * (1 - math.sin(a_))), Y(dd), zz)))
                rings.append(ring)
            m.loft(rings, SKIN, cap0=False, cap1=True)
            # the laser housing (scooped hood) is part of the laser mount since 0.3.8: built with the laser below
            lathe(m, (0, Y(38.255), 0.957), (0, -1, 0), [(0, 0.316), (0.012, 0.316)], DARK, 28, cap0=False, cap1=False)   # joint line
            # horizontal tailplane root: a low rounded fairing along the fuselage over the stabiliser root chord
            for sx in (-1, 1):
                rings = []
                for dd in drange(32.3, 35.5, 0.4):   # 0.3.14: ended ahead of the elevators (the tail hull overlapped them and damaged them)
                    p = skin_pt(sx, dd, HZ); q = (skin_pt(sx, dd, HZ, 1.0) - p).normalized()
                    k = max(0.0, min(1.0, (dd - 32.3) / 1.0, (35.5 - dd) / 1.0)); k = math.sin(k * math.pi / 2)
                    rings.append([p + Vector((0, 0, 0.20 * k * math.cos(a_))) + q * (0.10 * k * math.sin(a_) - 0.02) for a_ in [math.pi * j / 8 for j in range(9)]])
                m.loft(rings, SKIN, cap0=False, cap1=False)
        if name == 'fuselage':
            before = set(m.bm.verts)
            m.loft([section(*fair(d), n=32, ex=FAIR_EX) for d in sorted(set(drange(FAIR[0][0], FAIR[-1][0], 0.7) + [GEAR_D + k for k in (-WELL_R, -SLOT_W, SLOT_W, WELL_R)]))],
                    SKIN, clip4=well_clip(lambda p: -1.0))
            bmesh.ops.remove_doubles(m.bm, verts=[v for v in m.bm.verts if v not in before], dist=0.0005)
            # main gear bays: the A220 has no doors over the main wheels; the tyres sit in open wells in the belly
            # fairing, and the leg folds into a bay running out to the trunnion, closed by the door on the leg. Each bay
            # is a closed wall band round the opening plus a roof slab, so it reads from inside without back faces
            for sx in (-1, 1):
                ol = [(sx * x, dd) for x, dd in cut_outline()]
                if sx < 0: ol = ol[::-1]
                n = len(ol); rings = []
                for i in range(n):
                    (x0, e0), (x1, e1) = ol[i - 1], ol[(i + 1) % n]
                    tx, te = x1 - x0, e1 - e0; tl = math.hypot(tx, te) or 1.0; ox, oe = te / tl * 0.03, -tx / tl * 0.03
                    x, dd = ol[i]; zb = under_z(x, dd) + 0.004
                    rings.append([Vector((x, Y(dd), zb)), Vector((x, Y(dd), WELL_ROOF)), Vector((x + ox, Y(dd + oe), WELL_ROOF)), Vector((x + ox, Y(dd + oe), zb + 0.02))])
                m.loft(rings, BAY, cap0=False, cap1=False, wrap=True)
                mi = m.mat(BAY)
                top = [m.bm.verts.new(Vector((x, Y(dd), WELL_ROOF))) for x, dd in ol]
                bot = [m.bm.verts.new(Vector((x, Y(dd), WELL_ROOF + 0.02))) for x, dd in ol]
                m.bm.faces.new(top).material_index = mi; m.bm.faces.new(bot[::-1]).material_index = mi
                for i in range(n):
                    j = (i + 1) % n; m.bm.faces.new((top[i], top[j], bot[j], bot[i])).material_index = mi
                # (no lip since 0.3.11: the skin is now cut exactly along the opening)
        survivability(m, d0, d1, SKIN, DARK, GLASS, METAL)
        cargo_bay(m, d0, d1, SKIN, DARK, METAL, BAY)
        if name == 'fuselage_R':
            # weapons bay structure: frames down the side walls and across the roof, a hardpoint beam over each side,
            # and hinge fairings along both door edges
            for dd in drange(BAY_D0 + 0.35, BAY_D1 - 0.35, 0.6):
                for sx in (-1, 1):
                    # slim frames, flush-ish with the wall (0.3.10: present but less significant)
                    zl = skin_z(fus, BAY_X, dd); m.box((sx * (BAY_X - 0.015), Y(dd), (zl + BAY_TOP) / 2), (0.03, 0.035, BAY_TOP - zl), BAY)
                m.box((0, Y(dd), BAY_TOP - 0.015), (2 * BAY_X, 0.035, 0.03), BAY)
            for sx in (-1, 1):
                m.box((sx * 0.57, Y((BAY_D0 + BAY_D1) / 2), BAY_TOP - 0.10), (0.16, BAY_D1 - BAY_D0 - 0.3, 0.20), METAL)
                # (0.3.14: the raised hinge fairing rods along the door edges are gone; the doors close flush)
        mid = (d0 + d1) / 2
        piv = Vector((0, Y(mid), 0)) if name != 'fuselage' else Vector((0, 0, 0))
        if name == 'cockpit_F': piv = Vector((0, Y(2.81), 0.33))   # puts the reused crew stations at the flight deck
        emit(name, m, piv)
        if name == 'cockpit_F':
            # orient the panes: outer faces point away from the fuselage axis, inner ones towards it
            for gm_, out in ((glass_x, True), (glass_i, False)):
                gm_.bm.normal_update()
                for f in gm_.bm.faces:
                    c = f.calc_center_median(); dd = NOSE_Y - c.y; zc = (fus(dd)[2] + fus(dd)[3]) / 2
                    radial = Vector((c.x, 0.0, c.z - zc))
                    if (f.normal.dot(radial) > 0) != out: f.normal_flip()
            emit('canopy_glass', glass_x, piv, hull=False, recalc=False)
            emit('canopy_glass_int', glass_i, piv, hull=False, recalc=False)
            import json as _j; _j.dump(PANE_OUT, open('/tmp/dp/panes.json', 'w'))     # pane outlines on the skin, for the cockpit window reveals

    # forward doors: plug doors 0.16 m thick (outer skin, edge, inner trim panel) with a raised inner frame, two
    # stiffening ribs, a lever handle, the evacuation-slide pack across the bottom and a window reveal through the door.
    # They hinge open at their front edge on the ground and are jettisoned for the crew to bail out
    DT = 0.16
    for side, sx in (('L', -1), ('R', 1)):
        m = Mesh(); zs = drange(DOOR_Z0, DOOR_Z1, 0.3); nz = len(zs)
        hd, hz = (DOOR_D1 - DOOR_D0) / 2, (DOOR_Z1 - DOOR_Z0) / 2; dc, zc = DOOR_D0 + hd, DOOR_Z0 + hz
        hole = squircle_uv(rect_uv(1, 1, 5), 1, 1, 0.10, 0.12)
        def inside_win(q):
            dd = NOSE_Y - q.y; return abs(dd - dc) < 0.105 and abs(q.z - WZ) < 0.125
        for off, mat in ((0.0, SKIN), (-DT, BAY)):
            m.loft([[skin_pt(sx, dd, z, off) for z in zs] for dd in drange(DOOR_D0, DOOR_D1, 0.3)], mat, cap0=False, cap1=False, quads=lambda i: i < nz - 1)
        edge = rect_uv(hd, hz, 6)
        m.loft([[skin_pt(sx, dc + a, zc + b, off) for a, b in edge] for off in (0.0, -DT)], BAY, cap0=False, cap1=False)
        # window: dark pane on the outside, reveal tube through the door, pane on the inside
        door_window(m, sx, dc, WIN)
        m.loft([[skin_pt(sx, dc + a, WZ + b, off) for a, b in hole] for off in (0.004, -DT - 0.004)], METAL, cap0=False, cap1=False)
        fan(m, skin_pt(sx, dc, WZ, -DT - 0.006), [skin_pt(sx, dc + a, WZ + b, -DT - 0.006) for a, b in hole], WIN)
        # inner frame round the trim panel
        inner = rect_uv(hd - 0.03, hz - 0.03, 4); inner2 = rect_uv(hd - 0.10, hz - 0.10, 4)
        for r0, r1, o0, o1 in ((inner, inner, -DT, -DT - 0.06), (inner, inner2, -DT - 0.06, -DT - 0.06), (inner2, inner2, -DT - 0.06, -DT)):
            m.loft([[skin_pt(sx, dc + a, zc + b, o0) for a, b in r0], [skin_pt(sx, dc + a, zc + b, o1) for a, b in r1]], BAY, cap0=False, cap1=False)
        # ribs across the door above and below the window
        for zr in (WZ + 0.32, WZ - 0.38, DOOR_Z0 + 0.62):
            ds = drange(DOOR_D0 + 0.10, DOOR_D1 - 0.10, 0.35)
            m.loft([[skin_pt(sx, dd, zr + dz, o) for dd in ds] for dz, o in ((-0.025, -DT), (-0.025, -DT - 0.05), (0.025, -DT - 0.05), (0.025, -DT))], METAL, cap0=False, cap1=False, quads=lambda i: i < len(ds) - 1)
        # slide pack (girt bar bustle) along the bottom and the lever handle beside the window
        ds = drange(DOOR_D0 + 0.08, DOOR_D1 - 0.08, 0.37)
        m.loft([[skin_pt(sx, dd, z, o) for dd in ds] for z, o in ((DOOR_Z0 + 0.06, -DT), (DOOR_Z0 + 0.06, -DT - 0.20), (DOOR_Z0 + 0.42, -DT - 0.20), (DOOR_Z0 + 0.42, -DT))], DARK, cap0=True, cap1=True, quads=lambda i: i < len(ds) - 1)
        hp0 = skin_pt(sx, DOOR_D1 - 0.14, WZ - 0.05, -DT - 0.06); hp1 = skin_pt(sx, DOOR_D1 - 0.14, WZ + 0.22, -DT - 0.06)
        rod(m, hp0, hp1, 0.018, METAL, 6)
        # outer flush handle recess and the hinge arm fairing at the front edge
        m.box(skin_pt(sx, DOOR_D1 - 0.16, WZ - 0.30, 0.004), (0.02, 0.16, 0.05), DARK)
        hp = skin_pt(sx, DOOR_D0, zc)
        emit('fdoor_' + side, m, hp)
        # airline door arm: pivots inside the cabin ahead of the doorway and carries the door out and forward,
        # parallel to the fuselage (the door counter-rotates on the arm end), as on the real aircraft
        ap = skin_pt(sx, DOOR_D0 - 0.40, zc, -0.76); at = skin_pt(sx, dc, zc, -DT); at.z = ap.z
        m = Mesh(); a_, u_, v_ = frame(at - ap)
        for z0 in (-0.30, 0.30):
            rod(m, ap + Vector((0, 0, z0)), at + Vector((0, 0, z0 * 0.7)), 0.035, METAL, 8)
        rod(m, ap + Vector((0, 0, -0.34)), ap + Vector((0, 0, 0.34)), 0.05, DARK, 10)
        rod(m, at + Vector((0, 0, -0.24)), at + Vector((0, 0, 0.24)), 0.04, DARK, 10)
        emit('fdoor_arm_' + side, m, ap, hull=False)
        point('fdoor_' + side + '_hinge', ap); point('fdoor_' + side + '_attach', at)
    # weapons bay doors: one pair, hinged along the bay edges, shaped to the belly they close flush with
    for side, sx in (('L', -1), ('R', 1)):
        rings = []
        for dd in drange(BAY_D0 + 0.02, BAY_D1 - 0.02, 0.8):
            xs = [0.006 + (BAY_X - 0.012) * k / 5 for k in range(6)]
            lo = [Vector((sx * x, Y(dd), skin_z(fus, x, dd) - 0.004)) for x in xs]
            rings.append(lo + [Vector((p.x, p.y, p.z + 0.04)) for p in reversed(lo)])
        m = Mesh(); m.loft(rings, SKIN)
        for dd in drange(BAY_D0 + 0.4, BAY_D1 - 0.4, 0.9):      # stiffening ribs on the inner face
            xs = [0.05 + (BAY_X - 0.12) * k / 6 for k in range(7)]
            m.loft([[Vector((sx * x, Y(dd + o), skin_z(fus, x, dd) + 0.04 + zz)) for x in xs] for o, zz in ((-0.015, 0), (-0.015, 0.03), (0.015, 0.03), (0.015, 0))], BAY, cap0=False, cap1=False)   # slim (0.3.10)
        ha = Vector((sx * BAY_X, Y(BAY_D0), skin_z(fus, BAY_X, BAY_D0))); hb = Vector((sx * BAY_X, Y(BAY_D1), skin_z(fus, BAY_X, BAY_D1)))
        emit('baydoor_' + side, m, (ha + hb) / 2, hull=False)
        point('baydoor_' + side + '_hingeA', ha); point('baydoor_' + side + '_hingeB', hb)
        point('bayHardpoint_' + side, Vector((sx * 0.57, Y((BAY_D0 + BAY_D1) / 2), -1.00)))

    for side, sx in (('L', -1), ('R', 1)):
        # wing: 1a root 1.7-3.0, 1b 3.0-7.0 (gear, engine), 2 7.0-11.5 (pylon), 3 11.5-16.2 (aileron), tip 16.2-17.55.
        # Moving surfaces as on the real wing: slats 7.0-16.2 (front 13 % chord), spoilers ahead of the flaps, an inboard
        # flap from the fairing to the trailing-edge kink, an outboard flap to 12.5 and the aileron 12.5-16.2 (rear 27 %)
        FC, SC = 0.73, 0.13
        # root panels carry the main gear bay opening, so they are sampled finely across it
        fine = lambda s0, s1: sorted(set([round(x, 3) for x in drange(s0, s1, 0.25)] + [x for x in (NOTCH_X, SLOT_X1) if s0 < x < s1]))
        OPEN = (False, False) if STRUCT_ON else (True, True)      # 0.3.25: wing joints open onto the spars and ribs
        m = Mesh(); panel(m, sx, 1.7, 3.0, 0.0, FC, SKIN, ss=fine(1.7, 3.0), gearcut=True, caps=OPEN)
        panel(m, sx, 1.7, 2.45, FC - 0.01, 1.0, SKIN, ss=fine(1.7, 2.45), gearcut=True)   # fixed root trailing edge out to the inner flap (0.3.14)
        emit('wing1a_' + side, m, quarter_point(sx, 1.86, 3.0))
        # outer end stays closed: the slat in front of wing2 droops away from it
        m = Mesh(); panel(m, sx, 3.0, 7.0, 0.0, FC, SKIN, ss=fine(3.0, 3.8) + [4.6, 5.4, 6.2, 7.0], gearcut=True, caps=(OPEN[0], True))
        emit('wing1b_' + side, m, quarter_point(sx, 3.0, 7.0))
        m = Mesh(); panel(m, sx, 7.0, 11.5, SC, FC, SKIN, caps=OPEN)
        for cs in (8.4, 11.0):     # flap track fairings ("canoes") under the wing
            le, c, t, z = wing_at(cs)
            prof = [(le + c * 0.50, 0.03), (le + c * 0.62, 0.15), (le + c * 0.9, 0.17), (le + c * 1.15, 0.10), (le + c * 1.32, 0.02)]
            m.loft([[Vector((sx * cs + r * math.cos(2 * math.pi * k / 12), Y(dd), z - 0.12 - r + r * math.sin(2 * math.pi * k / 12)))
                     for k in range(12)] for dd, r in prof], SKIN)
        emit('wing2_' + side, m, quarter_point(sx, 7.0, 11.5))
        m = Mesh(); panel(m, sx, 11.5, 16.2, SC, FC, SKIN, caps=OPEN); emit('wing3_' + side, m, quarter_point(sx, 11.5, 16.2))
        # wingtip: the wing runs on to 16.75, then a raked tip that keeps going outward while it sweeps back and curves up
        m = Mesh(); panel(m, sx, 16.2, 16.75, 0.0, 1.0, SKIN, 0.55)
        le0, c0, t0, z0 = wing_at(16.75); rings = []
        for k in range(5):
            tt = k / 4; ss = 16.75 + 0.80 * tt; dz = 0.95 * tt ** 1.7
            le_k = le0 + 1.10 * tt ** 1.15; c_k = c0 + (0.40 - c0) * tt ** 0.9; zb = ZR + ss * DIH + dz
            rings.append(foil_ring(lambda u, o, ss=ss: sx * ss, lambda u, o, le_k=le_k, c_k=c_k: Y(le_k + u * c_k),
                                   lambda u, o, zb=zb: zb + o, c_k, 0.10 - 0.04 * tt, 0.0, 1.0))
        m.loft(rings, SKIN, cap0=False)
        emit('wingtip_' + side, m, quarter_point(sx, 16.2, 16.75))
        # nav light lens in the tip leading edge at the start of the raked tip (the lens is 0.5 m long: it pokes 5 cm out of the LE)
        lel, cl, tl_, zl = wing_at(16.85); point('navlight_' + side, Vector((sx * 16.85, Y(lel + 0.20), zl + 0.01)))
        def hinge_pt(ss, u, dz=0.0):
            le, c, t, z = wing_at(ss); return Vector((sx * ss, Y(le + u * c), z + dz))
        def foil_z(ss, u, upper):
            le, c, t, z = wing_at(ss)
            th = 5 * t * (0.2969 * math.sqrt(u) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4) * c
            return z + 0.02 * c * 4 * u * (1 - u) + (th if upper else -th)
        # flaps and aileron: AeroPart pivot and hinge both on the hinge line at mid span
        for nm, s0, s1 in (('flapin', 2.45, 6.1), ('flap', 6.1, 12.5), ('aileron', 12.5, 16.2)):   # 0.3.14: flapin from 2.45, clear of the 2.35 m fairing (flaps clipped the belly)
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
        engine(sx, side, cx, cz, SKIN, DARK, METAL, BAY)
        m = Mesh(); # 0.3.25: a smaller plug leaves the core exhaust annulus open onto the last turbine stage
        prof_n = [(16.32, 0.45), (16.85, 0.44), (17.3, 0.33), (17.85, 0.05)] if STRUCT_ON else [(16.5, 0.62), (16.85, 0.58), (17.3, 0.40), (17.85, 0.05)]
        m.loft(revolve(prof_n, cx, cz, 20), METAL, cap1=False)
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
        m = Mesh(); m.loft([ht_ring(s, sx, 0.0, 0.7) for s in drange(0.6, 6.16, 1.0)], SKIN, cap0=not STRUCT_ON)   # root (inside the tail cone) open onto the spars
        emit('hstab_' + side, m, Vector((sx * 3.4, Y(34.3), HZ + 3.4 * HDIH)))
        m = Mesh(); m.loft([ht_ring(s, sx, 0.7, 1.0) for s in drange(0.95, 6.16, 1.0)], SKIN)
        def hpt(s):
            le, c, t = lerp_tab(HT, s); return Vector((sx * s, Y(le + 0.7 * c), HZ + s * HDIH))
        a, b = hpt(0.95), hpt(6.16); emit('elevator_' + side, m, (a + b) / 2)
        point('elevator_' + side + '_hingeA', a); point('elevator_' + side + '_hingeB', b)
        # main gear (as on the A220: a single oleo leg pivoting fore and aft in the wing, folding 80 deg inboard so the
        # twin wheels lie almost flush in open wells in the belly fairing): strut with trunnion, side brace and leg
        # door (gear_*), oleo piston, torque links and axle (gear_*_unsprung), twin wheels (wheel_*). Track 6.7 m
        gx, gd, wr = sx * GEAR_X, GEAR_D, 0.58
        top, axle = GEAR_TOP, GROUND + wr
        oz = axle + 0.92                                   # bottom of the outer cylinder
        piv = Vector((gx, Y(gd), top))
        Rf = Matrix.Rotation(math.radians(GEAR_FOLD * sx), 3, 'Y')      # deployed -> stowed, about the trunnion
        def stow(p): return piv + Rf @ (Vector(p) - piv)
        def unstow(p): return piv + Rf.inverted() @ (Vector(p) - piv)
        m = Mesh()
        rod(m, (gx, Y(gd), top + 0.05), (gx, Y(gd), oz), 0.14, METAL, 14)   # 0.3.15: slimmer (was 0.17)
        rod(m, (gx, Y(gd), oz + 0.02), (gx, Y(gd), oz - 0.06), 0.145, METAL, 14)              # gland nut collar
        rod(m, (gx, Y(gd - 0.19), top), (gx, Y(gd + 0.19), top), 0.09, METAL, 10)              # trunnion pins (0.3.14: inside the leg door's width)
        rod(m, (gx + sx * 0.12, Y(gd + 0.10), top - 0.1), (gx + sx * 0.12, Y(gd + 0.10), oz + 0.05), 0.025, DARK, 6)  # brake lines
        for r_ in (0.60, 0.35):                                                              # side-stay and actuator lugs
            rod(m, (gx, Y(gd - 0.05), top - r_), (gx, Y(gd + 0.17), top - r_), 0.055, METAL, 8)
        # leg door: the patch of fairing and wing skin over the leg bay, built where it sits when stowed (flush with
        # the skin, 4 cm thick) and carried back to the deployed pose, where it stands on the outboard side of the leg
        xs = drange(NOTCH_X + 0.02, SLOT_X1 - 0.02, 0.1); es = drange(-SLOT_W + 0.015, SLOT_W - 0.015, 0.0725)
        LEG_CLEAR = 0.185                                    # 0.3.15: door inner face at least this far from the leg axis
        def dpt(x, e, o):
            # the stowed leg lies only a few cm inside the skin, so a flush door went through the strut: where it
            # would, the door bulges outward into a shallow blister over the leg (flush at its edges)
            p = unstow(Vector((sx * x, Y(gd + e), under_z(x, gd + e) + 0.04)))     # the inner face (4 cm in from the skin)
            xoff = sx * (p.x - gx); need = math.sqrt(max(LEG_CLEAR ** 2 - e * e, 0.0))
            shift = max(0.0, need - xoff)
            return unstow(Vector((sx * x, Y(gd + e), under_z(x, gd + e) + o))) + Vector((sx * shift, 0, 0))
        rings = [[dpt(x, e, 0.0) for e in es] + [dpt(x, e, 0.04) for e in reversed(es)] for x in xs]
        m.loft(rings, SKIN, cap0=True, cap1=True)
        for xb in (2.55, 3.15):                                                              # door brackets off the leg
            lp = Vector((sx * xb, Y(gd), 0)); leg_z = (stow(Vector((gx, Y(gd), top - abs(GEAR_X - xb) / math.sin(math.radians(GEAR_FOLD))))).z)
            rod(m, unstow(Vector((sx * xb, Y(gd), leg_z - 0.12))), unstow(Vector((sx * xb, Y(gd), under_z(xb, gd) + 0.04))), 0.03, METAL, 6)
        emit('gear_' + side, m, Vector((gx, Y(gd), top)))
        point('gearHinge_' + side, Vector((gx, Y(gd), top)))
        # folding side stay: upper link hinged in the wing root, lower link pinned to the leg, knee breaking upward
        # into the wing as the leg folds. Links are built along +Y from their pivots; the game aims them
        S = Vector((sx * 2.25, Y(gd), -1.55)); Q = Vector((gx, Y(gd), top - 0.60)); a_ = 0.60   # 0.3.14: S lower and inboard so the stowed knee stays inside the fairing (it came through the wing top)
        mid = (S + Q) / 2; dv = (Q - S); hh = math.sqrt(max(a_ * a_ - (dv.length / 2) ** 2, 0.0))
        up = Vector((-dv.z, 0, dv.x)).normalized()
        if up.z < 0: up = -up
        K = mid + up * hh; o = Vector((0, 0, 0))
        m = Mesh(); rod(m, o, o + Vector((0, a_, 0)), 0.055, METAL, 10); rod(m, o + Vector((0, a_, 0)) + Vector((-0.08, 0, 0)), o + Vector((0, a_, 0)) + Vector((0.08, 0, 0)), 0.065, METAL, 10)
        rod(m, o + Vector((-0.08, 0, 0)), o + Vector((0.08, 0, 0)), 0.06, METAL, 8)
        emit('gearstay_up_' + side, m, S, hull=False, local=True)
        m = Mesh(); rod(m, o, o + Vector((0, a_ + 0.08, 0)), 0.045, METAL, 10); rod(m, o + Vector((-0.07, 0, 0)), o + Vector((0.07, 0, 0)), 0.05, METAL, 8)
        emit('gearstay_lo_' + side, m, Q, hull=False, local=True)
        point('gearstay_up_' + side, S); point('gearstay_lo_' + side, Q); point('gearstay_knee_' + side, K)
        # retraction actuator: cylinder in the wing root, rod pinned to the leg's upper lug
        A0 = Vector((sx * 2.60, Y(gd + 0.12), -1.00)); A1 = Vector((gx, Y(gd + 0.12), top - 0.35))
        m = Mesh(); rod(m, o, o + Vector((0, 0.46, 0)), 0.075, DARK, 12); rod(m, o + Vector((-0.06, 0, 0)), o + Vector((0.06, 0, 0)), 0.05, METAL, 8)
        emit('gearact_cyl_' + side, m, A0, hull=False, local=True)
        m = Mesh(); rod(m, o, o + Vector((0, 0.50, 0)), 0.04, METAL, 10); rod(m, o + Vector((-0.06, 0, 0)), o + Vector((0.06, 0, 0)), 0.05, METAL, 8)
        emit('gearact_rod_' + side, m, A1, hull=False, local=True)
        point('gearact_cyl_' + side, A0); point('gearact_rod_' + side, A1)
        m = Mesh()
        rod(m, (gx, Y(gd), oz + 0.35), (gx, Y(gd), axle + 0.05), 0.11, METAL, 12)              # chromed piston
        rod(m, (gx - 0.30, Y(gd), axle), (gx + 0.30, Y(gd), axle), 0.075, METAL, 10)           # axle
        tl = Y(gd - 0.11)                                                                    # torque links ahead of the leg (0.3.14: kept inside the door's width)
        rod(m, (gx, tl, oz - 0.02), (gx, Y(gd - 0.17), oz - 0.30), 0.03, METAL, 6)
        rod(m, (gx, Y(gd - 0.17), oz - 0.30), (gx, tl, axle + 0.20), 0.03, METAL, 6)
        for k in (-0.17, 0.17): rod(m, (gx + k, Y(gd), axle), (gx + k * 1.2, Y(gd), axle), 0.27, DARK, 14)   # brake stacks
        emit('gear_' + side + '_unsprung', m, Vector((gx, Y(gd), axle)))
        m = Mesh()
        for k in (-0.32, 0.32): tyre(m, (gx + k, Y(gd), axle), wr, 0.38, TYRE, METAL)
        emit('wheel_' + side, m, Vector((gx, Y(gd), axle)), hull=False)
        point('axle_' + side, Vector((gx, Y(gd), axle)))

    # nose gear (d 3.5), twin wheels, retracts forward: leg with forward drag brace and taxi/landing lights,
    # chromed piston with torque links, twin wheels
    nd, wr = 3.5, 0.36; top, axle = -1.45, GROUND + wr; oz = axle + 0.72
    m = Mesh()
    rod(m, (0, Y(nd), top + 0.05), (0, Y(nd), oz), 0.10, METAL, 12)
    rod(m, (-0.32, Y(nd), top), (0.32, Y(nd), top), 0.06, METAL, 8)                     # trunnion
    rod(m, (0, Y(nd), top - 0.75), (0, Y(nd - 0.72), top + 0.25), 0.05, METAL, 8)       # drag brace forward into the bay
    m.box((0, Y(nd - 0.13), top - 0.45), (0.42, 0.10, 0.16), METAL)                     # light bar
    for x in (-0.12, 0.12): rod(m, (x, Y(nd - 0.18), top - 0.45), (x, Y(nd - 0.21), top - 0.45), 0.065, GLASS, 10)
    emit('gear_F', m, Vector((0, Y(nd), top)))
    point('gearHinge_F', Vector((0, Y(nd), top)))
    m = Mesh()
    rod(m, (0, Y(nd), oz + 0.3), (0, Y(nd), axle + 0.04), 0.075, METAL, 12)
    rod(m, (-0.42, Y(nd), axle), (0.42, Y(nd), axle), 0.05, METAL, 10)
    rod(m, (0, Y(nd + 0.12), oz - 0.02), (0, Y(nd + 0.25), oz - 0.22), 0.025, METAL, 6)   # torque links behind the leg
    rod(m, (0, Y(nd + 0.25), oz - 0.22), (0, Y(nd + 0.12), axle + 0.14), 0.025, METAL, 6)
    emit('gear_F_unsprung', m, Vector((0, Y(nd), axle)))
    m = Mesh()
    for k in (-0.21, 0.21): tyre(m, (k, Y(nd), axle), wr, 0.22, TYRE, METAL, 12)
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

    # fin: lower (vstab_L, z 1.2-FIN_SPLIT) and upper (vstab_R, z FIN_SPLIT-7.55) fixed parts, each with a rudder half (70-100 % chord).
    # The split is level with the top of the dorsal radar: the upper fin folds flat to starboard there for the hangar
    for nm, z0, z1 in (('L', 1.2, FIN_SPLIT), ('R', FIN_SPLIT, 7.55)):
        m = Mesh(); m.loft([fin_ring(z, 0.0, 0.7) for z in drange(z0, z1, 0.6)], SKIN, cap0=(nm == 'R'), cap1=(nm == 'L'))
        if nm == 'R':
            # 0.3.14 (visible seam at the fold line): a skirt 6 cm deep and 4 mm inside the skin hangs below the upper
            # fin, so the sliver of the joint that opens as the jointed upper fin flexes shows skin, not sky
            def inset_ring(z, k=0.004):
                r = fin_ring(z, 0.0, 0.7); cx = sum(p.x for p in r) / len(r); cy = sum(p.y for p in r) / len(r)
                return [Vector((p.x - math.copysign(min(k, abs(p.x - cx)), p.x - cx), p.y, p.z)) for p in r]
            m.loft([inset_ring(z0 - 0.06), inset_ring(z0 + 0.002)], SKIN, cap0=False, cap1=False)
        zm = (z0 + z1) / 2; le, c, t = lerp_tab(FIN, zm); emit('vstab_' + nm, m, Vector((0, Y(le + 0.3 * c), zm)), hull_keep=lambda p, z0=z0: p.z >= z0 - 0.001)
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
    for dd in drange(17.2 - bl / 2, 17.2 + bl / 2, 0.5):
        end = min(dd - (17.2 - bl / 2), (17.2 + bl / 2) - dd); taper = math.sqrt(max(0.0, min(1.0, end / 0.7)))
        hw, hh = bw / 2 * (0.25 + 0.75 * taper), bh / 2 * (0.45 + 0.55 * taper)
        zc = beam_z(dd); rings.append(section(dd, max(hw, 0.04), zc + hh, zc - hh, n=16, ex=6.0))
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
    # tail laser: a targeting-pod style ball held in a scooped hood at the end of the tail cone. The roll stage (collar ring with
    # two arms carrying the tilt pivots) turns about the fuselage axis, the 0.60 m ball tilts on the pivots, and the
    # flat glass emitter window faces down at rest. Both meshes are built in aircraft axes at that rest pose
    lm = Vector((0, Y(LASER_HOOD + 0.06), 0.957)); HR, CUT = 0.30, 0.215; RW = math.sqrt(HR * HR - CUT * CUT)
    m = Mesh(); dn = Vector((0, 0, -1))
    # ball, flattened where the emitter panel sits (centred on the beam axis)
    lathe(m, lm, dn, [(t, math.sqrt(max(HR * HR - t * t, 0.0))) for t in [-HR * math.cos(math.acos(-CUT / HR) * j / 10) for j in range(11)]], METAL, 16)
    # flat face: a dark face plate carrying two rectangular glass panels: the emitter panel above the optical
    # (sensor) panel, as on a turret ball. The face is level at rest (window down), so the panels are plain boxes
    lathe(m, lm, dn, [(CUT, RW), (CUT + 0.006, RW * 0.98), (CUT + 0.006, 0.0)], DARK, 16)
    lathe(m, lm, dn, [(CUT + 0.006, 0.0), (CUT + 0.006, RW * 0.98)], DARK, 16)
    fz = lm.z - CUT - 0.006
    for cy, w, h in ((0.045, 0.30, 0.14), (-0.115, 0.15, 0.065)):
        m.box((0, lm.y + cy, fz - 0.004), (w + 0.024, h + 0.024, 0.008), DARK)       # bezel
        m.box((0, lm.y + cy, fz - 0.009), (w, h, 0.004), GLASS)                      # glass pane
    for sg in (-1, 1): rod(m, lm + Vector((sg * (HR - 0.02), 0, 0)), lm + Vector((sg * (HR + 0.025), 0, 0)), 0.055, DARK, 12)
    emit('laser_head', m, lm, hull=False)
    m = Mesh(); rc = Vector((0, Y(LASER_HOOD - 0.01), lm.z))
    lathe(m, rc, (0, -1, 0), [(0, 0.30), (0, 0.318), (0.03, 0.318), (0.03, 0.30)], DARK, 28, cap0=False, cap1=False)
    for sg in (-1, 1):
        rod(m, rc + Vector((sg * 0.29, -0.02, 0)), lm + Vector((sg * (HR + 0.045), 0, 0)), 0.035, DARK, 8)
        rod(m, lm + Vector((sg * (HR + 0.02), 0, 0)), lm + Vector((sg * (HR + 0.065), 0, 0)), 0.065, METAL, 12)
    emit('laser_yoke', m, lm, hull=False)
    hm = Mesh()
    # laser housing (0.3.6): the cone continues 0.35 m aft as a hood round the ball, with a scoop cut out of
    # its underside that opens towards the back so the ball can look forward along the belly
    rings = []
    for k in range(8):
        t = k / 7; dd = 38.255 + (LASER_HOOD - 38.255) * t
        r = 0.312 + 0.040 * t ** 2; phi = math.radians(4 + 76 * t ** 1.4)   # lip flares round the ball
        outer = [(-math.pi / 2 + phi) + (2 * math.pi - 2 * phi) * j / 14 for j in range(15)]
        ring = [Vector((r * math.cos(a), Y(dd), 0.957 + r * math.sin(a))) for a in outer]
        ring += [Vector(((r - 0.022) * math.cos(a), Y(dd), 0.957 + (r - 0.022) * math.sin(a))) for a in reversed(outer)]
        rings.append(ring)
    hm.loft(rings, SKIN, cap0=False, cap1=True)
    emit('laser_hood', hm, lm, hull=False)
    point('laserMount', lm)
    point('CoM', Vector((0, Y(17.6), -0.3)))
    point('targetCamForward', Vector((0, Y(1.2), -1.25)))
    point('targetCamRear', Vector((0, Y(36.5), 1.6)))
    point('landingCamPoint', Vector((0, Y(5.0), -1.95)))
    for side, sx in (('L', -1), ('R', 1)):
        p, n = skin_frame(sx, FLARE_D0 + 0.9, FLARE_Z); c = p + n * 0.26
        point('flareEjector_' + side, Vector((c.x, Y(FLARE_D0 + 0.925), c.z - 0.13)))   # under the flare grid
    point('contactSparks', Vector((0, Y(20.0), -2.4)))

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'p220_structure.py')).read())

if __name__ == '__main__':
    build()
    out = sys.argv[sys.argv.index('--') + 1]
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print('parts', len(bpy.data.collections['MODEL'].objects), 'cols', len(bpy.data.collections['COLLISION'].objects), 'points', len(bpy.data.collections['POINTS'].objects))
