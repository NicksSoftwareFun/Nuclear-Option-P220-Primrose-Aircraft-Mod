"""P220 Primrose flight deck (first pass). Unity prefab-root coordinates (x right, y up, z forward).
Builds the meshes with UVs into one 2048 atlas (regions in ATLAS, painted by p220_cockpit_tex.py).
Library pieces follow the PB-22 cockpit scripts; layout is the P220's own."""
import os, math, json
CK = os.path.dirname(os.path.abspath(__file__))

FLOOR = -0.22
EYE = (-0.38, 0.82, 16.31)

ATLAS = {
    'paint':   (0, 0, 1024, 1024),
    'dark':    (1024, 0, 512, 512),
    'mfd':     (1536, 0, 256, 300),      # portrait display bezel
    'fcu':     (1792, 0, 256, 72),       # flight control unit on the glareshield
    'caut':    (1792, 72, 64, 48),       # master caution face (amber)
    'warn':    (1856, 72, 64, 48),       # master warning face (red, unlit print)
    'red':     (1920, 72, 64, 48),
    'ncol':    (1792, 128, 128, 256),    # shared non-critical lamps: column between the middle displays
    'nstrip':  (1024, 512, 640, 96),     # shared non-critical lamps: strip under the middle displays
    'efis':    (1664, 512, 256, 144),    # EFIS control panel under each outer display
    'gear':    (1024, 608, 105, 220),   # 0.3.20: same aspect as the 0.105 x 0.22 m panels (was 200 wide: clock drawn as an oval)
    'brk':     (1224, 608, 105, 220),
    'mcdu':    (1424, 656, 240, 300),
    'quad':    (1664, 656, 200, 340),
    'ped0':    (1024, 828, 360, 120),
    'ped1':    (1024, 948, 360, 120),
    'ped2':    (1384, 956, 280, 120),
    'con0':    (0, 1024, 300, 240),
    'con1':    (300, 1024, 300, 240),
    'con2':    (600, 1024, 300, 240),
    'ovh0':    (0, 1264, 300, 380),
    'ovh1':    (300, 1264, 300, 380),
    'ovh2':    (600, 1264, 300, 380),
    'ovh3':    (900, 1264, 300, 380),
    'grip':    (1920, 128, 128, 128),
    'pedal':   (1920, 256, 96, 160),
    'tread':   (704, 1664, 496, 384),
    'carpet':  (1200, 1264, 848, 784),   # 0.3.30: one unique carpet piece for the crew floor (440 px per metre), no tiling
    'door':    (0, 1664, 400, 384),
    'ssbase':  (1920, 416, 128, 128),
    'note':    (400, 1648, 300, 400),
    # 0.4.7 cockpit detail pass: panels round the side sticks and the oxygen mask boxes on the side consoles
    'con3':    (912, 1088, 220, 176),    # captain: outboard of the side stick
    'con5':    (1136, 1088, 220, 176),   # first officer: outboard of the side stick
    'con4':    (1360, 1088, 220, 176),   # both: forward on the console top, below the panel wing
    'o2box':   (1584, 1088, 200, 160),   # oxygen mask stowage box lid    # maintenance manual page taped to the captain's panel (the author 2026-11-01)
}

# 0.3.30 carpet mapping, shared by the model and the painter: the crew floor x CARPET_X, z CARPET_Z is mapped once at
# CARPET_PPM px per metre from the top left of the 'carpet' region (forward at the top); the floor aft of it repeats the
# plain patch CARPET_PATCH (x0, x1, z0, z1, a piece under the seat pan with no wear or binding), mirrored tile to tile
CARPET_X, CARPET_Z, CARPET_PPM = (-0.95, 0.95), (16.30, 17.78), 440.0
CARPET_PATCH = (-0.85, -0.23, 16.34, 16.72)
TEX = 2048.0
PAINT_SCALE = 0.30      # UV units per metre inside the paint region (1 m = 614 px)

# ------------------------------------------------------------------ mesh store
PARTS = {}   # part -> {'v':[], 'f':[(idx tuple, uv list, mat)]}
def _part(n): return PARTS.setdefault(n, {'v': [], 'f': []})

def vadd(a, b): return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def vsub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def vmul(a, s): return (a[0]*s, a[1]*s, a[2]*s)
def vdot(a, b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def vcross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def vnorm(a):
    l = math.sqrt(vdot(a, a)) or 1.0
    return (a[0]/l, a[1]/l, a[2]/l)

def region_uv(reg, s, t):
    """s,t in 0..1 across a region (t=0 bottom) -> atlas UV (v up)."""
    x, y, w, h = ATLAS[reg]
    return ((x + s*w)/TEX, 1.0 - (y + (1.0-t)*h)/TEX)

def paint_uv(p, n, reg='paint'):
    ax = max(range(3), key=lambda i: abs(n[i]))
    a, b = [(1, 2), (0, 2), (0, 1)][ax]
    x, y, w, h = ATLAS[reg]
    span = (w/TEX)/PAINT_SCALE * (1.0 if reg == 'paint' else 1.0)
    s = ((p[a] + 0.9) % span) / span
    t = ((p[b] + 0.9) % span) / span
    return region_uv(reg, s, t)

def poly(part, pts, mat='P220_cockpit', uvs=None, paint='paint'):
    """add one polygon (world points, counter-clockwise seen from the visible side)."""
    P = _part(part)
    if uvs is None and mat == 'P220_cabin':
        # cabin lining: box-projected at 2.5 m per UV unit, the same convention as the hull's P220_cabin faces
        n = vnorm(vcross(vsub(pts[1], pts[0]), vsub(pts[2], pts[0])))
        ax = max(range(3), key=lambda i: abs(n[i])); a, b = [(2, 1), (0, 2), (0, 1)][ax]
        uvs = [(p[a]/2.5, p[b]/2.5) for p in pts]
    elif uvs is None:
        n = vnorm(vcross(vsub(pts[1], pts[0]), vsub(pts[2], pts[0])))
        if vdot(n, n) < 0.5 and len(pts) > 3:
            n = vnorm(vcross(vsub(pts[2], pts[1]), vsub(pts[3], pts[1])))
        # per-face paint projection, shifted so the face stays contiguous
        uvs = [paint_uv(p, n, paint) for p in pts]
        us = [u for u, _ in uvs]; vs = [v for _, v in uvs]
        x, y, w, h = ATLAS[paint]
        if max(us) - min(us) > (w/TEX)*0.5 or max(vs) - min(vs) > (h/TEX)*0.5:
            cen = (x + w*0.25)/TEX, 1.0 - (y + h*0.75)/TEX
            ax = max(range(3), key=lambda i: abs(n[i])); a, b = [(1, 2), (0, 2), (0, 1)][ax]
            mn_a = min(p[a] for p in pts); mn_b = min(p[b] for p in pts)
            uvs = [(cen[0] + (p[a]-mn_a)*PAINT_SCALE*(w/1024.0)*0.5, cen[1] + (p[b]-mn_b)*PAINT_SCALE*(h/1024.0)*0.5) for p in pts]
    base = len(P['v'])
    P['v'].extend(pts)
    P['f'].append((tuple(range(base, base+len(pts))), list(uvs), mat))

class Frame:
    def __init__(self, o, u, v, n): self.o, self.u, self.v, self.n = o, vnorm(u), vnorm(v), vnorm(n)
    def p(self, a, b, c=0.0): return vadd(self.o, vadd(vmul(self.u, a), vadd(vmul(self.v, b), vmul(self.n, c))))
    def at(self, a, b, c=0.0): return Frame(self.p(a, b, c), self.u, self.v, self.n)
    def yaw(self, deg):   # rotate u,n about v
        t = math.radians(deg); c, s = math.cos(t), math.sin(t)
        return Frame(self.o, vadd(vmul(self.u, c), vmul(self.n, s)), self.v, vsub(vmul(self.n, c), vmul(self.u, s)))
    def pitch(self, deg):  # rotate v,n about u (+ tips the top toward n)
        t = math.radians(deg); c, s = math.cos(t), math.sin(t)
        return Frame(self.o, self.u, vadd(vmul(self.v, c), vmul(self.n, s)), vsub(vmul(self.n, c), vmul(self.v, s)))
    def roll(self, deg):   # rotate u,v about n
        t = math.radians(deg); c, s = math.cos(t), math.sin(t)
        return Frame(self.o, vadd(vmul(self.u, c), vmul(self.v, s)), vsub(vmul(self.v, c), vmul(self.u, s)), self.n)

WORLD_FWD = Frame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, -1))   # n toward the front crew (aft)

# ------------------------------------------------------------------ 2D shapes (local a,b)
def rect(w, h):
    def f(i=0.0):
        a, b = w/2-i, h/2-i
        return [(-a, -b), (a, -b), (a, b), (-a, b)]
    return f
def rrect(w, h, r, seg=3):
    def f(i=0.0):
        a, b, rr = w/2-i, h/2-i, max(r-i, 0.001)
        pts = []
        for cx, cy, a0 in ((a-rr, -b+rr, -90), (a-rr, b-rr, 0), (-a+rr, b-rr, 90), (-a+rr, -b+rr, 180)):
            for k in range(seg+1):
                t = math.radians(a0 + 90*k/seg)
                pts.append((cx + rr*math.cos(t), cy + rr*math.sin(t)))
        return pts
    return f
def circle(r, n=16):
    def f(i=0.0):
        return [((r-i)*math.cos(2*math.pi*k/n), (r-i)*math.sin(2*math.pi*k/n)) for k in range(n)]
    return f
def ngon(pts2):
    def f(i=0.0):
        if not i: return list(pts2)
        cx = sum(p[0] for p in pts2)/len(pts2); cy = sum(p[1] for p in pts2)/len(pts2)
        out = []
        for x, y in pts2:
            dx, dy = x-cx, y-cy; l = math.hypot(dx, dy) or 1
            out.append((x - dx/l*i, y - dy/l*i))
        return out
    return f

def _rpoly(part, pts, mat='P220_cockpit', uvs=None, paint='paint'):
    """poly with reversed winding (prism builds its faces counter-clockwise in u,v, which faces -n)."""
    poly(part, list(reversed(pts)), mat, list(reversed(uvs)) if uvs else None, paint)

def prism(part, fr, shape, depth, mat='P220_cockpit', decal=None, paint='paint', chamfer=0.0, proud=0.0,
          side_paint=None, back=False, decal_box=None, front=True, knobs=True):
    """extrude shape (in frame u,v) from n*proud back to n*(proud-depth); front face faces +n.
    decal: atlas region for the front face (mapped over the shape's bounding box, or decal_box=(w,h))."""
    poly = _rpoly
    outer = shape(0.0); m = len(outer)
    inner = shape(chamfer) if chamfer else outer
    if decal_box: bw, bh = decal_box
    else:
        bw = max(p[0] for p in outer) - min(p[0] for p in outer); bh = max(p[1] for p in outer) - min(p[1] for p in outer)
    def duv(pt): return region_uv(decal, 0.5 + pt[0]/bw, 0.5 + pt[1]/bh)
    zf = proud; zc = proud - chamfer; zb = proud - depth
    F = [fr.p(a, b, zf) for a, b in inner]
    if front: poly(part, F, mat, [duv(p) for p in inner] if decal else None, paint)
    if decal and knobs:
        for name, s0, t0, s1, t1 in LAMP_MAP().get(decal, []):    # printed lamps lit through the screen texture
            pts = [((s0 - 0.5)*bw, (t0 - 0.5)*bh), ((s1 - 0.5)*bw, (t0 - 0.5)*bh), ((s1 - 0.5)*bw, (t1 - 0.5)*bh), ((s0 - 0.5)*bw, (t1 - 0.5)*bh)]
            face_toward('tacScreen', [fr.p(a, b, zf + 0.0006) for a, b in pts], fr.n, 'tacScreenDisplay',
                        [lamp_uv(name, 0, 0), lamp_uv(name, 1, 0), lamp_uv(name, 1, 1), lamp_uv(name, 0, 1)])
        for s_, t_, kind, rr_ in KNOB_MAP().get(decal, []):
            physical_knob(part, fr.at((s_ - 0.5)*bw, (t_ - 0.5)*bh), zf, kind, rr_*bw)
    sp = side_paint or paint
    if chamfer:
        for k in range(m):
            j = (k+1) % m
            q = [fr.p(*outer[k], zc), fr.p(*outer[j], zc), fr.p(*inner[j], zf), fr.p(*inner[k], zf)]
            poly(part, q, mat, [duv(outer[k]), duv(outer[j]), duv(inner[j]), duv(inner[k])] if decal else None, sp)
    if depth > chamfer:
        for k in range(m):
            j = (k+1) % m
            poly(part, [fr.p(*outer[k], zb), fr.p(*outer[j], zb), fr.p(*outer[j], zc), fr.p(*outer[k], zc)], mat, None, sp)
    if back:
        poly(part, [fr.p(a, b, zb) for a, b in reversed(outer)], mat, None, sp)

_KNOBS = {}
_LAMPS = None
def LAMP_MAP():
    global _LAMPS
    if _LAMPS is None:
        import json
        try: _LAMPS = json.load(open(os.path.join(CK, 'lamps.json')))
        except OSError: _LAMPS = {}
    return _LAMPS

def KNOB_MAP():
    """knob / toggle positions printed by pb22_cockpit_tex.py, per atlas region (2026-10-19: every printed knob gets geometry)"""
    if not _KNOBS:
        try: _KNOBS.update(json.load(open(os.path.join(CK, 'knobs.json'))))
        except OSError: _KNOBS['_none'] = []
    return _KNOBS

def physical_knob(part, fr, z, kind, r):
    if kind == 'push':      # 0.4.7: square push-button cap standing proud of its printed bezel
        # (a raised collar round the printed face, so the legend stays readable; r is half the button width)
        w = max(r, 0.004)*2.1; h = w*0.62; t = 0.0022
        for dx, dy, sw, sh in ((0, (h - t)/2, w, t), (0, -(h - t)/2, w, t), ((w - t)/2, 0, t, h), (-(w - t)/2, 0, t, h)):
            prism(part, fr.at(dx, dy), rect(sw, sh), 0.005, proud=z + 0.005, paint='dark', knobs=False)
        return
    if kind == 'knob':      # skirted rotary knob with a red index line
        r = max(r, 0.007)
        prism(part, fr, circle(r*1.30, 8), 0.003, proud=z + 0.003, paint='dark', knobs=False)
        prism(part, fr, circle(r, 8), 0.014, chamfer=0.0015, proud=z + 0.017, paint='dark', knobs=False)
        prism(part, fr.at(0, r*0.45), rect(0.0016, r*0.8), 0.001, proud=z + 0.0175, decal='red', knobs=False)
    else:                   # bat toggle on a hex nut, leaning up; guarded ones get a red guard either side
        r = max(r, 0.004)
        prism(part, fr, circle(r*0.85, 6), 0.004, proud=z + 0.004, paint='dark', knobs=False)
        p0 = fr.p(0, 0, z + 0.004); p1 = fr.p(0, 0.006, z + 0.019)
        tube(part, p0, p1, 0.0018, 6, caps=False)      # both ends hidden, in the nut and in the bat
        tube(part, p1, fr.p(0, 0.0072, z + 0.0235), 0.0030, 6)
        if kind == 'guard':
            for g in (-1, 1):
                prism(part, fr.at(g*r*1.45, -0.002), rect(0.0016, r*2.6), 0.016, proud=z + 0.016, decal='red', side_paint='dark',
                      decal_box=(0.4, 0.4), knobs=False)

def poly_shape(pts):
    """shape function for an arbitrary counter-clockwise outline (mitred inset for chamfers)"""
    def f(i=0.0):
        if not i: return list(pts)
        out = []; m = len(pts)
        for k in range(m):
            a, b, cc = pts[k-1], pts[k], pts[(k+1) % m]
            def nrm(p, q):
                dx, dy = q[0]-p[0], q[1]-p[1]; l = math.hypot(dx, dy) or 1.0
                return (-dy/l, dx/l)          # left of the edge = inside for a ccw outline
            n1, n2 = nrm(a, b), nrm(b, cc)
            bx, by = n1[0] + n2[0], n1[1] + n2[1]; bl = math.hypot(bx, by) or 1.0
            cosh = (n1[0]*bx + n1[1]*by)/bl or 1.0
            out.append((b[0] + bx/bl*i/cosh, b[1] + by/bl*i/cosh))
        return out
    return f

def face_toward(part, pts, want, mat='P220_cockpit', uvs=None, paint='paint'):
    """polygon whose visible side faces the direction want, whatever order the points came in"""
    n = vcross(vsub(pts[1], pts[0]), vsub(pts[2], pts[0]))
    if vdot(n, want) < 0:
        pts = pts[::-1]; uvs = uvs[::-1] if uvs else None
    poly(part, pts, mat, uvs, paint)

def boxw(part, c, size, mat='P220_cockpit', paint='paint', skip=()):
    """world-axis box; skip: faces to omit ('-x','+x','-y','+y','-z','+z')."""
    cx, cy, cz = c; w, h, d = size[0]/2, size[1]/2, size[2]/2
    V = lambda sx, sy, sz: (cx+sx*w, cy+sy*h, cz+sz*d)
    faces = {'-x': [V(-1,-1,-1), V(-1,-1,1), V(-1,1,1), V(-1,1,-1)], '+x': [V(1,-1,1), V(1,-1,-1), V(1,1,-1), V(1,1,1)],
             '-y': [V(-1,-1,-1), V(1,-1,-1), V(1,-1,1), V(-1,-1,1)], '+y': [V(-1,1,1), V(1,1,1), V(1,1,-1), V(-1,1,-1)],
             '-z': [V(1,-1,-1), V(-1,-1,-1), V(-1,1,-1), V(1,1,-1)], '+z': [V(-1,-1,1), V(1,-1,1), V(1,1,1), V(-1,1,1)]}
    for k, q in faces.items():
        if k not in skip: poly(part, q, mat, None, paint)

def tube(part, p0, p1, r, n=8, mat='P220_cockpit', paint='dark', caps=True):
    d = vnorm(vsub(p1, p0)); a = vnorm(vcross(d, (0, 1, 0) if abs(d[1]) < 0.9 else (1, 0, 0))); b = vcross(d, a)
    ring = lambda c: [vadd(c, vadd(vmul(a, r*math.cos(2*math.pi*k/n)), vmul(b, r*math.sin(2*math.pi*k/n)))) for k in range(n)]
    r0, r1 = ring(p0), ring(p1)
    for k in range(n):
        j = (k+1) % n
        poly(part, [r0[k], r0[j], r1[j], r1[k]], mat, None, paint)
    if caps:
        poly(part, list(reversed(r0)), mat, None, paint); poly(part, r1, mat, None, paint)


def loft(part, rings, mat='P220_cockpit', paint='dark', cap0=True, cap1=True):
    """skin through equal-length point rings (world points); faces point away from each ring's centre."""
    cen = [vmul(reduce3(r), 1.0/len(r)) for r in rings]
    for k in range(len(rings) - 1):
        A, B = rings[k], rings[k + 1]; m = len(A); c = vmul(vadd(cen[k], cen[k + 1]), 0.5)
        for i in range(m):
            j = (i + 1) % m
            q = [A[i], A[j], B[j], B[i]]
            face_toward(part, q, vsub(vmul(reduce3(q), 0.25), c), mat, None, paint)
    ax = vsub(cen[-1], cen[0])
    if cap0: face_toward(part, list(rings[0]), vmul(ax, -1), mat, None, paint)
    if cap1: face_toward(part, list(rings[-1]), ax, mat, None, paint)

def reduce3(pts):
    o = (0.0, 0.0, 0.0)
    for p in pts: o = vadd(o, p)
    return o

def lathe(part, fr, profile, n=12, mat='P220_cockpit', paint='dark', cap0=True, cap1=True):
    """surface of revolution about the frame's n axis: profile is [(radius, height along n)], bottom to top."""
    rings = [[fr.p(r*math.cos(2*math.pi*k/n), r*math.sin(2*math.pi*k/n), h) for k in range(n)] for r, h in profile]
    loft(part, rings, mat, paint, cap0, cap1)

def fr3(o, u, v):
    """frame with the front face toward v x u (the prism convention used throughout)"""
    u = vnorm(u); v = vnorm(v)
    return Frame(o, u, v, vcross(v, u))

# ------------------------------------------------------------------ render texture layout (stock tac screen, 1024x512)
RT_W, RT_H = 1024, 512
RT_REGIONS = {
    'pfd':   (0, 0, 340, 262),      # outer displays: flight display (horizon, speed, altitude, heading)
    'tac':   (340, 0, 340, 262),    # pilot's inner display: tac map / radar
    'sys':   (680, 0, 340, 262),    # co-pilot's inner display: engines, fuel, stores
    'annun': (0, 262, 512, 45),     # critical annunciator strip (one copy above each pilot's displays)
    'lamps': (512, 262, 512, 112),  # live cells for the shared non-critical panel, 8 x 4 cells of 64 x 28
}
CRIT = ['FIRE 1', 'FIRE 2', 'MISSILE', 'GEAR', 'STALL', 'FUEL', 'HYD', 'ELEC']
LAMP_CELLS = ['GEAR DN', 'FLAP', 'SPD BRK', 'REV', 'BRAKE', 'AP', 'A/THR', 'NAV',
              'RADAR', 'JAMMER', 'LASER', 'BAY', 'ENG 1', 'ENG 2', 'APU', 'ANTI ICE']
def lamp_uv(name, s, t):
    k = LAMP_CELLS.index(name); x0, y0, w, h = RT_REGIONS['lamps']
    cx, cy = x0 + (k % 8)*64, y0 + (k // 8)*28
    return ((cx + 1 + s*62)/RT_W, 1.0 - (cy + 1 + (1.0 - t)*26)/RT_H)
def rt_uv(name, s, t):
    x, y, w, h = RT_REGIONS[name]
    return ((x + s*w)/RT_W, 1.0 - (y + (1.0 - t)*h)/RT_H)

# ------------------------------------------------------------------ hull (same section law as p220_parts.py)
FUS = [(0.00, 0.05, -0.62, -0.80), (0.35, 0.62, -0.05, -1.20), (0.90, 1.00, 0.45, -1.48), (2.00, 1.42, 1.05, -1.70),
       (3.20, 1.68, 1.55, -1.82), (4.40, 1.82, 1.84, -1.90), (6.00, 1.86, 1.91, -1.93), (27.5, 1.86, 1.91, -1.93)]
NOSE_Y = 19.35
def _pchip(st):
    ds = [s[0] for s in st]; n = len(st); cols = list(zip(*[s[1:] for s in st]))
    def slopes(v):
        h = [ds[i + 1] - ds[i] for i in range(n - 1)]; dl = [(v[i + 1] - v[i]) / h[i] for i in range(n - 1)]
        return [dl[0]] + [0.0 if dl[i - 1] * dl[i] <= 0 else 3 * (h[i - 1] + h[i]) / ((2 * h[i] + h[i - 1]) / dl[i - 1] + (h[i] + 2 * h[i - 1]) / dl[i]) for i in range(1, n - 1)] + [dl[-1]]
    ms = [slopes(c) for c in cols]
    def at(d):
        for i in range(n - 1):
            if ds[i] <= d <= ds[i + 1]:
                hg = ds[i + 1] - ds[i]; tt = (d - ds[i]) / hg
                h00 = 2*tt**3 - 3*tt**2 + 1; h10 = tt**3 - 2*tt**2 + tt; h01 = -2*tt**3 + 3*tt**2; h11 = tt**3 - tt**2
                return tuple(h00*c[i] + h10*hg*m[i] + h01*c[i + 1] + h11*hg*m[i + 1] for c, m in zip(cols, ms))
        return st[0][1:] if d < ds[0] else st[-1][1:]
    return at
fus = _pchip(FUS)
def hull_x(y, z):
    """inner skin half-width at height y, station z (Unity)."""
    hw, zt, zb = fus(NOSE_Y - z); zc, hh = (zt + zb)/2, (zt - zb)/2
    t = abs((y - zc)/hh)
    if t >= 1: return 0.0
    return hw*(1 - t**2.2)**(1/2.2)
def hull_pt(a, z, inset=0.0):
    hw, zt, zb = fus(NOSE_Y - z); hw -= inset; zt -= inset; zb += inset
    zc, hh = (zt + zb)/2, (zt - zb)/2; c, s = math.cos(a), math.sin(a)
    return (hw*math.copysign(abs(c)**(2/2.2), c), zc + hh*math.copysign(abs(s)**(2/2.2), s), z)

# ================================================================== main panel
TILT = 12.0
# 0.3.20: displays sat at the pilot's knees; whole panel and glareshield raised 0.30 m and moved 0.19 m forward (three passes: remove over half the glareshield's visible depth, then again),
# wings folded further in (12 -> 22 deg) so the curve of the display array reads. Hood stays under the eye-to-sill line.
PZ, PY = 17.47, 0.42
HINGE = 0.375
WING_YAW = 22.0
PANEL_TOP, PANEL_BOT, PANEL_HALF = 0.67, 0.18, 0.80
PANEL_DEPTH = 0.16
_t = math.radians(TILT)
CENTRE = Frame((0, PY, PZ), (1, 0, 0), (0, math.cos(_t), math.sin(_t)), (0, math.sin(_t), -math.cos(_t)))
def face_z(y): return PZ + (y - PY)*math.tan(_t)
def panel_frame(x, y):
    b = (y - PY)/math.cos(_t)
    if abs(x) <= HINGE: return CENTRE.at(x, b)
    s = 1 if x > 0 else -1
    return CENTRE.at(s*HINGE, b).yaw(s*WING_YAW).at(x - s*HINGE, 0)

def panel_body():
    ym = (PANEL_TOP + PANEL_BOT)/2; hh = PANEL_TOP - PANEL_BOT
    prism('cockpit_int', panel_frame(0, ym), rect(2*HINGE, hh), PANEL_DEPTH, paint='paint', back=True)
    for s in (-1, 1):
        w = PANEL_HALF - HINGE
        prism('cockpit_int', panel_frame(s*(HINGE + w/2), ym), rect(w, hh), PANEL_DEPTH, paint='paint', back=True)
        # dark post covering the fold between the centre panel and the wing
        f = panel_frame(s*HINGE, ym)
        prism('cockpit_int', f, rect(0.03, hh + 0.01), 0.02, proud=0.008, paint='dark')
    # moulded knee bolster along the panel's lower edge, following the fold, wrapping into the side consoles
    xs_ = [-PANEL_HALF, -HINGE, HINGE, PANEL_HALF]
    for x0, x1 in zip(xs_, xs_[1:]):
        a0 = panel_frame(x0, PANEL_BOT + 0.012).p(0, 0, -0.004); a1 = panel_frame(x1, PANEL_BOT + 0.012).p(0, 0, -0.004)
        tube('cockpit_int', a0, a1, 0.024, 8, mat='P220_cabin', caps=False)
    # footwell back wall well forward of the panel foot, so the pendulum pedals hang in an open well
    boxw('cockpit_int', (0, (FLOOR + PANEL_BOT)/2, 17.78), (1.9, PANEL_BOT - FLOOR + 0.06, 0.02), paint='dark')
    boxw('cockpit_int', (0, PANEL_BOT + 0.01, 17.55), (1.9, 0.02, 0.46), paint='dark', skip=('+y',))   # 0.4.8: ends buried in the consoles

def on_panel(part, x, y, shape, depth, **kw):
    prism(part, panel_frame(x, y), shape, depth, **kw)

# ---- displays: four portrait MFDs, each glass maps one region of the tac screen render texture
DISP_Y = 0.50
DISP_X = (0.22, 0.53)
BEZEL = (0.29, 0.23); GLASS = (0.26, 0.196)
SCREENS = []
def display(fr, region):
    prism('cockpit_int', fr, rrect(*BEZEL, 0.010, 2), 0.03, decal='mfd', chamfer=0.004, proud=0.026, side_paint='dark', decal_box=BEZEL)
    g = fr.at(0, 0.0)
    gw, gh = GLASS
    pts = [g.p(-gw/2, -gh/2, 0.0275), g.p(gw/2, -gh/2, 0.0275), g.p(gw/2, gh/2, 0.0275), g.p(-gw/2, gh/2, 0.0275)]
    uv = [rt_uv(region, 0, 0), rt_uv(region, 1, 0), rt_uv(region, 1, 1), rt_uv(region, 0, 1)]
    poly('tacScreen', pts[::-1], 'tacScreenDisplay', uv[::-1])
    for side in (-1, 1):            # bezel keys down both long edges
        for b in range(4):
            prism('cockpit_int', fr.at(side*0.1335, (b - 1.5)*0.042), rect(0.008, 0.022), 0.005, proud=0.031, paint='dark')
    for b in range(4):              # and four along the bottom
        prism('cockpit_int', fr.at((b - 1.5)*0.055, -0.1045), rect(0.026, 0.008), 0.005, proud=0.031, paint='dark')
def displays():
    for s in (-1, 1):
        for i, x in enumerate(DISP_X):
            region = 'pfd' if i == 1 else ('tac' if s < 0 else 'sys')
            fr = panel_frame(s*x, DISP_Y)
            display(fr, region)
            SCREENS.append((s, i, region, fr))

# ---- shared non-critical annunciators: a column between the middle displays and a strip below them
NCOL = (0.13, 0.205)       # width, height (column between the inner bezels)
NSTRIP = (0.56, 0.084)      # strip under the inner displays
def noncritical():
    yc = DISP_Y + 0.004
    on_panel('cockpit_int', 0.0, yc, rrect(*NCOL, 0.006, 2), 0.012, decal='ncol', chamfer=0.003, proud=0.012, decal_box=NCOL)
    ys = DISP_Y - BEZEL[1]/2 - 0.012 - NSTRIP[1]/2
    on_panel('cockpit_int', 0.0, ys, rrect(*NSTRIP, 0.006, 2), 0.012, decal='nstrip', chamfer=0.003, proud=0.012, decal_box=NSTRIP)
    return ys

# ---- panels under the outer displays and at the wing ends
def lower_panels(ys):
    for s in (-1, 1):
        on_panel('cockpit_int', s*DISP_X[1], ys - 0.006, rrect(0.22, 0.10, 0.006, 2), 0.012, decal='efis', chamfer=0.003, proud=0.012,
                 decal_box=(0.22, 0.10))
    # wing ends: brake / clock panel for the pilot, landing gear panel and lever for the co-pilot
    xe = (DISP_X[1] + BEZEL[0]/2 + PANEL_HALF)/2; we = PANEL_HALF - DISP_X[1] - BEZEL[0]/2 - 0.02
    on_panel('cockpit_int', -xe, DISP_Y, rrect(we, 0.22, 0.006, 2), 0.012, decal='brk', chamfer=0.003, proud=0.012, decal_box=(we, 0.22))
    on_panel('cockpit_int', xe, DISP_Y, rrect(we, 0.22, 0.006, 2), 0.012, decal='gear', chamfer=0.003, proud=0.012, decal_box=(we, 0.22))
    gear_lever(panel_frame(xe, DISP_Y))

GEAR_SLOT = (0.0075, 0.064, -0.090)     # 0.4.11: slot 12 mm further inboard so the knob clears the console moulding at the panel edge
GEAR_TRAVEL = [None]     # slot centre across the gear panel and its UP / DN ends (the printed slot, 1 px per mm)
def gear_lever(fr):
    """landing gear lever in the DN detent: a gate with side rails and UP / DN detent pockets, side guards, a lever arm
    standing out of the slot and a wheel-shaped knob turning about a cross axis"""
    su, vt, vb = GEAR_SLOT
    vm = (vt + vb)/2; L = vt - vb
    for g in (-1, 1):       # gate rails either side of the slot
        prism('cockpit_int', fr.at(su + g*0.0095, vm), rect(0.006, L + 0.012), 0.007, chamfer=0.0015, proud=0.019, paint='paint')
    for vv in (vt + 0.009, vb - 0.009):     # end caps closing the gate
        prism('cockpit_int', fr.at(su, vv), rect(0.025, 0.006), 0.007, chamfer=0.0015, proud=0.019, paint='paint')
    for vv in (vt - 0.010, vb + 0.012):     # detent pockets: the slot jogs outboard at each end
        prism('cockpit_int', fr.at(su + 0.0045, vv), rect(0.009, 0.018), 0.001, proud=0.0128, paint='dark')
    # guards: two tapered fins either side of the lower slot, standing proud of the panel
    for g in (-1, 1):
        gf = Frame(fr.p(su + g*0.016, vb + 0.035, 0.012), fr.v, fr.n, vmul(fr.u, -g))
        fin = [(-0.045, 0.0), (0.040, 0.0), (0.028, 0.034), (-0.030, 0.042)] if g < 0 else [(-0.040, 0.0), (0.045, 0.0), (0.030, 0.042), (-0.028, 0.034)]
        prism('cockpit_int', Frame(gf.o, gf.u, gf.v, vcross(gf.v, gf.u)), poly_shape(fin), 0.003, proud=0.0015, paint='dark', back=True,
              knobs=False)
    # lever: a carriage in the DN detent, an arm angled out and slightly down, the wheel at its end
    # 0.4.11: the lever is its own part, slid by the plugin between the DN and UP detents with the gear state
    vd = vb + 0.012; root = fr.p(su + 0.0045, vd, 0.013)
    PIVOTS['gearLever'] = root
    GEAR_TRAVEL[0] = vmul(fr.v, (vt - 0.010) - vd)
    prism('gearLever', fr.at(su + 0.0045, vd), rrect(0.012, 0.016, 0.004, 1), 0.008, proud=0.021, paint='paint', knobs=False)
    tip = fr.p(su + 0.0045, vd - 0.010, 0.088)
    tube('gearLever', root, tip, 0.0055, 8, paint='paint')
    wf = Frame(tip, fr.n, fr.v, fr.u)        # wheel axis across the panel
    lathe('gearLever', wf, [(0.008, -0.0125), (0.019, -0.0125), (0.0235, -0.0085), (0.0245, 0.0), (0.0235, 0.0085), (0.019, 0.0125),
                              (0.008, 0.0125)], 16, paint='paint')

# ---- glareshield: hood over the panel with a deep lip; lip carries the FCU and each pilot's critical annunciators
HOOD_TOP = 0.735       # 0.3.20: top sits just under the eye-to-sill line, so little of it shows from the seat
HOOD_LIP = 0.085
HOOD_FWD = (0.735, 17.77)    # top front edge height and station (under the windscreen sill)
LIP_BOT = PANEL_TOP + 0.012
def hood():
    def kick(x): return 0.0
    stations = [-PANEL_HALF, -0.70, -0.55, -HINGE, -0.13, 0.0, 0.13, HINGE, 0.55, 0.70, PANEL_HALF]
    def section(x):
        fr = panel_frame(x, PANEL_TOP)
        p_under = fr.p(0, 0, HOOD_LIP)
        p_face = fr.p(0, 0, -0.002)
        R_ = 0.016
        lipb = (p_under[0], LIP_BOT, p_under[2])
        lipt = (p_under[0], HOOD_TOP - R_, p_under[2])
        arc = []
        for j in range(1, 4):
            a = math.radians(90*j/4)
            arc.append((p_under[0], HOOD_TOP - R_ + R_*math.sin(a), p_under[2] + R_ - R_*math.cos(a)))
        top2 = (p_under[0], HOOD_TOP, p_under[2] + R_)
        topf = (p_under[0]*1.0, HOOD_FWD[0], HOOD_FWD[1])
        botf = (p_under[0], PANEL_TOP - 0.03, HOOD_FWD[1] - 0.1)
        return [p_face, lipb, lipt] + arc + [top2, topf, botf]
    secs = [section(x) for x in stations]
    for i in range(len(stations) - 1):
        A, B = secs[i], secs[i + 1]
        for k in range(len(A) - 1):
            poly('cockpit_int', [A[k], A[k + 1], B[k + 1], B[k]], 'P220_cockpit', None, 'dark')
    poly('cockpit_int', list(reversed(secs[0])), 'P220_cockpit', None, 'dark')
    poly('cockpit_int', secs[-1], 'P220_cockpit', None, 'dark')

def deck():
    """coaming deck from the glareshield's front edge up under the windscreen sill, so no nose cavity shows through the glass."""
    xs = [-1.0 + k*0.1 for k in range(21)]
    for x0, x1 in zip(xs, xs[1:]):
        q = [(x0, HOOD_FWD[0] - 0.005, HOOD_FWD[1] - 0.01), (x1, HOOD_FWD[0] - 0.005, HOOD_FWD[1] - 0.01), (x1, 0.66, 18.02), (x0, 0.66, 18.02)]
        face_toward('cockpit_int', q, (0, 1, -0.3), 'P220_cockpit', None, 'dark')

def lip_frame(x, y):
    """frame on the aft face of the glareshield lip at unrolled x, height y (n toward the crew)."""
    f = panel_frame(x, PANEL_TOP)
    o = f.p(0, 0, HOOD_LIP); o = (o[0], y, o[2])
    n = (f.n[0], 0.0, f.n[2])
    return Frame(o, vcross(n, (0, 1, 0)), (0, 1, 0), n)

def lip_strip(part, x0, x1, y0, y1, mat, region, proud=0.002):
    """flat strip on the lip from unrolled x0 to x1, split at the hinge so it follows the fold; UVs across a region."""
    cuts = sorted(set([x0, x1] + [c for c in (-HINGE, HINGE) if x0 < c < x1]))
    for a, b in zip(cuts, cuts[1:]):
        fa, fb = lip_frame(a, y0), lip_frame(b, y0)
        sa, sb = (a - x0)/(x1 - x0), (b - x0)/(x1 - x0)
        pa0 = vadd(fa.o, vmul(fa.n, proud)); pb0 = vadd(fb.o, vmul(fb.n, proud))
        pa1 = (pa0[0], y1, pa0[2]); pb1 = (pb0[0], y1, pb0[2])
        if mat == 'tacScreenDisplay':
            uv = [rt_uv(region, sa, 0), rt_uv(region, sb, 0), rt_uv(region, sb, 1), rt_uv(region, sa, 1)]
        else:
            uv = [region_uv(region, sa, 0), region_uv(region, sb, 0), region_uv(region, sb, 1), region_uv(region, sa, 1)]
        face_toward(part, [pa0, pb0, pb1, pa1], fa.n, mat, uv)

CRIT_X = (0.125, 0.56)
def glareshield():
    hood(); deck()
    yc = (LIP_BOT + HOOD_TOP - 0.016)/2
    for s in (-1, 1):
        # critical annunciators: one live strip above each pilot's pair of displays, on a dark surround
        x0, x1 = sorted((s*CRIT_X[0], s*CRIT_X[1]))
        lip_strip('cockpit_int', x0 - 0.006, x1 + 0.006, yc - 0.024, yc + 0.024, 'P220_cockpit', 'red', 0.003)
        lip_strip('tacScreen', x0, x1, yc - 0.0175, yc + 0.0175, 'tacScreenDisplay', 'annun', 0.0045)
        # master warning (red, flashed by the stock CockpitWarningLights) and master caution push-lights outboard
        for k, (dx, reg) in enumerate(((0.615, 'warn'), (0.695, 'caut'))):
            f = lip_frame(s*dx, yc)
            prism('cockpit_int', f, rrect(0.064, 0.050, 0.006, 2), 0.012, chamfer=0.003, proud=0.012, paint='dark')
            if reg == 'warn':
                prism('warningLights', f, rrect(0.050, 0.036, 0.004, 2), 0.004, mat='CockpitWarningLight', proud=0.0135)
                prism('cockpit_int', f, rrect(0.050, 0.036, 0.004, 2), 0.004, decal='warn', proud=0.0130, decal_box=(0.050, 0.036))
            else:
                prism('cockpit_int', f, rrect(0.050, 0.036, 0.004, 2), 0.004, decal='caut', proud=0.0135, decal_box=(0.050, 0.036))
    # flight control unit in the middle of the lip, physical knobs from the printed layout
    f = lip_frame(0.0, yc)
    prism('cockpit_int', f, rrect(0.22, 0.064, 0.006, 2), 0.02, decal='fcu', chamfer=0.004, proud=0.02, decal_box=(0.22, 0.064))

# ================================================================== pedestal and thrust levers
PED_HALF = 0.18
PED_TOP = 0.20
PED_Z0, PED_Z1 = 16.33, 17.00          # flat top; forward slope from PED_Z1 up to the panel foot
THROTTLE_PIVOT = (0.0, PED_TOP + 0.02, 16.84)
THR_SLOT_X = 0.042                     # handle / slot centre either side of the pedestal centre line
THR_IDLE_V, THR_TOGA_V = -0.042, 0.1235  # handle travel along the quadrant (from its centre, + forward); range 0.1655 m
PIVOTS = {}
MOVERS = {}
def pedestal():
    zf = face_z(PANEL_BOT) - 0.01
    yb = PANEL_BOT + 0.005           # slope runs up into the panel's lower edge
    # side walls (pentagon: floor, flat top, slope up to the panel foot), top and slope
    side = [(PED_Z0, FLOOR), (zf + 0.02, FLOOR), (zf + 0.02, yb), (PED_Z1, PED_TOP), (PED_Z0, PED_TOP)]
    for s in (-1, 1):
        pts = [(s*PED_HALF, y, z) for z, y in side]
        face_toward('cockpit_int', pts, (s, 0, 0), 'P220_cockpit', None, 'paint')
    q = lambda z, y: [(-PED_HALF, y, z), (PED_HALF, y, z)]
    a, b = q(PED_Z0, PED_TOP); c, d = q(PED_Z1, PED_TOP)
    face_toward('cockpit_int', [a, b, d, c], (0, 1, 0), 'P220_cockpit', None, 'dark')
    e, f_ = q(zf + 0.02, yb)
    face_toward('cockpit_int', [c, d, f_, e], (0, 1, -0.6), 'P220_cockpit', None, 'dark')
    face_toward('cockpit_int', [(-PED_HALF, FLOOR, PED_Z0), (PED_HALF, FLOOR, PED_Z0), (PED_HALF, PED_TOP, PED_Z0), (-PED_HALF, PED_TOP, PED_Z0)],
                (0, 0, -1), 'P220_cockpit', None, 'paint')
    for s in (-1, 1):       # rounded trim along the top edges
        tube('cockpit_int', (s*(PED_HALF - 0.002), PED_TOP - 0.002, PED_Z0 - 0.004), (s*(PED_HALF - 0.002), PED_TOP - 0.002, PED_Z1 + 0.004), 0.007, 6,
             paint='dark', caps=False)
    flat = lambda x, z, y=PED_TOP: Frame((x, y, z), (1, 0, 0), (0, 0, 1), (0, 1, 0))
    # two MCDU keypads aft of the thrust levers on a wedge tilted toward the crew
    W = Frame((0, PED_TOP + 0.03, 16.50), (1, 0, 0), (0, 0, 1), (0, 1, 0)).pitch(-14)
    prism('cockpit_int', W, rect(2*PED_HALF - 0.01, 0.27), 0.06, chamfer=0.008, paint='dark', proud=0.0)
    for s in (-1, 1):
        prism('cockpit_int', W.at(s*0.087, 0.0), rrect(0.162, 0.25, 0.006, 2), 0.012, decal='mcdu', chamfer=0.003, proud=0.010,
              decal_box=(0.162, 0.25))
    # thrust quadrant (0.3.17): sliding handles that run fore and aft through two real slots cut in the quadrant top.
    # Stock Cockpit.throttles 'motion' mode moves the handle part along its local z by throttle x range, so the part's
    # origin is the IDLE stop and full travel ends on the TOGA mark printed on the 'quad' decal (texbody.py, same numbers).
    QX, QZ, QW, QL, QTOP = 0.16, 16.84, 0.16, 0.30, PED_TOP + 0.035
    CH = 0.006                                       # top edge chamfer, as before
    flat = lambda x, z, y=PED_TOP: Frame((x, y, z), (1, 0, 0), (0, 0, 1), (0, 1, 0))
    prism('cockpit_int', flat(0.0, QZ, QTOP), rect(QW, QL), 0.05, decal='quad', chamfer=CH, proud=0.0, front=False)
    quv = lambda u, v: region_uv('quad', 0.5 + u/QW, 0.5 + v/QL)
    def top(u0, u1, v0, v1):
        pts = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        face_toward('cockpit_int', [(u, QTOP, QZ + v) for u, v in pts], (0, 1, 0), 'P220_cockpit', [quv(u, v) for u, v in pts])
    hu, hv = QW/2 - CH, QL/2 - CH
    SX, SW, SV0, SV1, SD = THR_SLOT_X, 0.006, -0.060, 0.140, 0.032      # slot centre x, half width, aft/fwd ends, depth
    cols = [-hu, -SX - SW, -SX + SW, SX - SW, SX + SW, hu]
    top(cols[0], cols[1], -hv, hv); top(cols[2], cols[3], -hv, hv); top(cols[4], cols[5], -hv, hv)
    for s in (-1, 1):
        x0, x1 = s*SX - SW, s*SX + SW
        top(x0, x1, -hv, SV0); top(x0, x1, SV1, hv)
        # slot walls and a dark floor (the handle's carriage runs underneath)
        yb = QTOP - SD
        for xw, want in ((x0, (1, 0, 0)), (x1, (-1, 0, 0))):
            face_toward('cockpit_int', [(xw, QTOP, QZ + SV0), (xw, QTOP, QZ + SV1), (xw, yb, QZ + SV1), (xw, yb, QZ + SV0)], want, 'P220_cockpit', None, 'dark')
        for zv, want in ((SV0, (0, 0, 1)), (SV1, (0, 0, -1))):
            face_toward('cockpit_int', [(x0, QTOP, QZ + zv), (x1, QTOP, QZ + zv), (x1, yb, QZ + zv), (x0, yb, QZ + zv)], want, 'P220_cockpit', None, 'dark')
        face_toward('cockpit_int', [(x0, yb, QZ + SV0), (x1, yb, QZ + SV0), (x1, yb, QZ + SV1), (x0, yb, QZ + SV1)], (0, 1, 0), 'P220_cockpit', None, 'dark')
    piv = (0.0, QTOP, QZ + THR_IDLE_V)
    # detent ticks: small raised bars outboard of each slot at IDLE, CL, FLX/MCT and TOGA (same stations as the printed marks)
    for v in (-0.042, -0.042 + 0.1655*0.55, 0.1235 - 0.1655*0.12, 0.1235):
        for s in (-1, 1):
            boxw('cockpit_int', (s*(SX + SW + 0.007), QTOP + 0.0012, QZ + v), (0.010, 0.0024, 0.0028), paint='paint', skip=('-y',))
    for s in (-1, 1):
        x = s*SX
        sf = fr3((x, 0.0, piv[2]), (0, 0, 1), (0, 1, 0))          # side profile frame (u fore-aft, v up), front face +x
        mirror = lambda pts: [(-a, b) for a, b in reversed(pts)]
        sb = fr3((x, 0.0, piv[2]), (0, 0, -1), (0, 1, 0))         # same profile seen from -x
        def side_prism(shape_pts, xc, width, ch, paint, decal=None):
            """profile extruded across x from xc - width/2 to xc + width/2, chamfered on both side faces"""
            prism('throttle', sf.at(0, 0, xc - x + width/2), poly_shape(shape_pts), width/2, chamfer=ch, paint=paint, knobs=False)
            prism('throttle', sb.at(0, 0, x - xc + width/2), poly_shape(mirror(shape_pts)), width/2, chamfer=ch, paint=paint, knobs=False)
        # slim lever arm from the carriage under the slot up into the handle, swept back a little at the top
        y0 = QTOP - SD + 0.004
        arm = [(-0.009, y0), (0.009, y0), (0.009, QTOP + 0.060), (0.006, QTOP + 0.104), (-0.016, QTOP + 0.104), (-0.010, QTOP + 0.060)]
        side_prism(arm, x, 0.0066, 0.0, 'paint')
        # handle: rounded head set outboard of the arm, flat inner face toward the other handle, the palm wraps the aft top
        hx = x + s*0.006
        head = [(-0.030, QTOP + 0.100), (0.018, QTOP + 0.098), (0.030, QTOP + 0.106), (0.034, QTOP + 0.118), (0.028, QTOP + 0.130),
                (0.010, QTOP + 0.137), (-0.014, QTOP + 0.139), (-0.030, QTOP + 0.134), (-0.038, QTOP + 0.122), (-0.037, QTOP + 0.108)]
        side_prism(head, hx, 0.032, 0.007, 'dark')
        # ribbed grip insert on the aft top, where the palm rests
        gn = vnorm((0, 0.75, -1.0)); gc = (hx, QTOP + 0.1335, piv[2] - 0.031)
        gf = fr3(vadd(gc, vmul(gn, 0.0005)), (1, 0, 0), vcross(gn, (1, 0, 0)))
        gf = gf if vdot(gf.n, gn) > 0 else fr3(gf.o, (-1, 0, 0), vcross(gn, (1, 0, 0)))
        prism('throttle', gf, rrect(0.026, 0.018, 0.004, 1), 0.003, proud=0.0015, decal='grip', decal_box=(0.026, 0.018), knobs=False)
        # reverse thrust latch: a finger lift hooked under the front of the handle
        latch = [(0.016, QTOP + 0.094), (0.036, QTOP + 0.091), (0.044, QTOP + 0.099), (0.042, QTOP + 0.114), (0.035, QTOP + 0.117),
                 (0.034, QTOP + 0.110), (0.036, QTOP + 0.102), (0.022, QTOP + 0.102)]
        side_prism(latch, hx, 0.022, 0.0, 'paint')
        # red instinctive disconnect button on the outboard face
        bf = fr3((hx + s*0.016, QTOP + 0.120, piv[2] - 0.004), (0, 0, s), (0, 1, 0))
        prism('throttle', bf, circle(0.0055, 8), 0.003, proud=0.0025, decal='red', decal_box=(0.3, 0.3), knobs=False)
    PIVOTS['throttle'] = piv
    # speed brake lever left of the thrust levers (T-handle), flap lever right (flap-shaped handle), fixed, each in a railed gate
    for s in (-1, 1):
        x = s*0.125
        prism('cockpit_int', flat(x, 16.84, PED_TOP + 0.004), rect(0.05, 0.26), 0.004, paint='dark', proud=0.004)
        for dx in (-0.009, 0.009):
            boxw('cockpit_int', (x + dx, PED_TOP + 0.0095, 16.84), (0.004, 0.003, 0.21), paint='paint', skip=('-y',))
        b0 = (x, PED_TOP + 0.005, 16.78); b1 = (x, PED_TOP + 0.08, 16.76)
        tube('cockpit_int', b0, b1, 0.0055, 6, paint='paint', caps=False)
        if s < 0:
            tube('cockpit_int', (x - 0.030, b1[1] + 0.004, b1[2]), (x + 0.030, b1[1] + 0.004, b1[2]), 0.0085, 8, paint='dark')
            for e in (-1, 1):
                tube('cockpit_int', (x + e*0.030, b1[1] + 0.004, b1[2]), (x + e*0.033, b1[1] + 0.004, b1[2]), 0.0075, 8, paint='paint')
        else:
            prof = [(-0.024, -0.006), (0.010, -0.010), (0.024, -0.004), (0.027, 0.004), (0.013, 0.011), (-0.010, 0.013), (-0.025, 0.006)]
            for e in (-1, 1):
                fr = fr3((x + e*0.025, b1[1] + 0.006, b1[2]), (0, 0, e), (0, 1, 0))
                prism('cockpit_int', fr, poly_shape(prof if e > 0 else [(-a, b) for a, b in reversed(prof)]), 0.025, chamfer=0.004,
                      paint='paint', knobs=False)
    # radio, trim and lighting panels aft
    for k, (z, reg) in enumerate(()):
        prism('cockpit_int', flat(0.0, z, PED_TOP + 0.001), rect(0.33, 0.125), 0.01,
              decal=reg, chamfer=0.002, proud=0.006)

# ================================================================== side consoles and side sticks
CON_TOP = 0.20
CON_BOT = 0.08          # a slim ledge on the side wall, open underneath like the real side consoles
CON_IN = 0.80
CON_Z0, CON_Z1 = 16.45, 17.12
STICK_PIVOT = {-1: (-0.92, CON_TOP + 0.012, 16.95), 1: (0.92, CON_TOP + 0.012, 16.95)}
# moulded side console stations: z, inboard top edge x, top height at that edge, x where the top settles to CON_TOP.
# Aft end rolls down, the body is flat round the stick, and the front sweeps up into the outboard end of the panel wing
# while the outboard part stays low under the side window sill.
CON_STATIONS = [(16.38, 0.850, 0.165, 0.880), (16.42, 0.818, 0.192, 0.850), (16.47, 0.802, 0.200, 0.840), (16.75, 0.800, 0.200, 0.838),
                (17.02, 0.800, 0.200, 0.838), (17.09, 0.796, 0.216, 0.900), (17.16, 0.788, 0.262, 0.990), (17.24, 0.780, 0.350, 1.070),
                (17.33, 0.774, 0.460, 1.120)]
FOOTWELL_Z1 = 17.78
def dash_wrap(s):
    """0.4.8 (both sides of the dashboard one continuous piece with the centre): a moulded cheek from the outboard end
    of each panel wing and glareshield out to the side wall under the side window's front edge and down onto the console
    top, so panel, hood and console read as one moulding with no open gap between them."""
    x = s*PANEL_HALF
    A = [panel_frame(x, y).p(0, 0, 0.002) for y in (0.42, 0.50, 0.58, PANEL_TOP)]
    pu = panel_frame(x, PANEL_TOP).p(0, 0, HOOD_LIP)
    A += [(pu[0], LIP_BOT, pu[2]), (pu[0], HOOD_TOP, pu[2] + 0.016), (pu[0], HOOD_FWD[0], HOOD_FWD[1])]
    # wall line: from the console top at the wall, up under the side window's front edge to the hood's outboard front corner
    B = [(1.17, 0.205, 17.25), (1.21, 0.30, 17.31), (1.17, 0.38, 17.39), (1.10, 0.45, 17.47), (1.01, 0.51, 17.55),
         (0.92, 0.57, 17.63), (abs(pu[0]) + 0.02, HOOD_FWD[0] - 0.01, HOOD_FWD[1] - 0.02)]
    B = [(s*b[0], b[1], b[2]) for b in B]
    def dens(C, m=3):   # 0.4.8: finer chain so the smooth-shaded moulding has no facets
        out = []
        for i in range(len(C) - 1):
            p0, p1 = C[max(i - 1, 0)], C[i]; p2, p3 = C[i + 1], C[min(i + 2, len(C) - 1)]
            for j in range(m):
                t = j/m; t2 = t*t; t3 = t2*t
                out.append(tuple(0.5*((2*p1[k]) + (-p0[k] + p2[k])*t + (2*p0[k] - 5*p1[k] + 4*p2[k] - p3[k])*t2
                                      + (-p0[k] + 3*p1[k] - 3*p2[k] + p3[k])*t3) for k in range(3)))
        return out + [C[-1]]
    A, B = dens(A), dens(B)
    n = 14
    zc = CON_STATIONS[-1][0]
    C = [(0.774, 0.42), (0.778, 0.445), (0.789, 0.456), (0.804, 0.46), (0.96, 0.33), (1.12, 0.20), (1.17, 0.205)]
    C = dens([(s*c[0], c[1], zc) for c in C], 2)
    L = [0.0]
    for a, b in zip(C, C[1:]): L.append(L[-1] + math.sqrt(vdot(vsub(b, a), vsub(b, a))))
    def con_edge(t):
        d = t*L[-1]
        for i in range(len(C) - 1):
            if d <= L[i + 1] or i == len(C) - 2:
                f = (d - L[i])/max(L[i + 1] - L[i], 1e-9); return vadd(vmul(C[i], 1 - f), vmul(C[i + 1], f))
    rows = []
    for i in range(n + 1):
        t = i/n; bulge = 0.025*math.sin(math.pi*t)
        r = [vadd(vadd(vmul(a, 1 - t), vmul(b, t)), (-s*bulge*0.5, bulge*0.3, -bulge)) for a, b in zip(A, B)]
        # lower part of the cheek blends from the console's front top edge (row start) into the free surface above
        e = con_edge(t); m = 4
        for k in range(min(m, len(r))):
            w = (1 - k/m)**2
            r[k] = vadd(vmul(r[k], 1 - w), vmul(e if k == 0 else vadd(e, vmul(vsub(r[m], e), k/m)), w))
        rows.append(r)
    eye = (s*0.38, 0.82, 16.31)
    for R0, R1 in zip(rows, rows[1:]):
        for k in range(len(A) - 1):
            q = [R0[k], R0[k + 1], R1[k + 1], R1[k]]
            c = vmul(vadd(vadd(q[0], q[1]), vadd(q[2], q[3])), 0.25)
            face_toward('cockpit_int', q, vsub(eye, c), 'P220_cabin')

SWEEP_Z0 = 17.02          # 0.4.8b: from here forward the whole console top sweeps up into the display board as one loft
SWEEP_END_Z = 17.263
def sweep_sections(s, start):
    """0.4.8b (one continuous piece, not two pressed together): the console's own section is lofted forward and up.
    Each point of the console outline travels on a curve that leaves the console flat and arrives rising, ending on the
    outboard edge of the display board (its inboard rounded edge becomes the bezel round the panel's side), the glareshield's
    outboard corner and the side wall under the window. One mesh, smooth shaded, so there is no seam."""
    x = s*PANEL_HALF
    edge = lambda y: panel_frame(x, y).p(0, 0, 0.012)
    pu = panel_frame(x, PANEL_TOP).p(0, 0, HOOD_LIP)
    end = [(s*0.93, FLOOR, SWEEP_END_Z), (s*0.93, -0.06, SWEEP_END_Z), (s*0.87, -0.04, SWEEP_END_Z),
           edge(PANEL_BOT), edge(0.42), edge(0.52), edge(0.60), edge(PANEL_TOP),
           (pu[0] + s*0.012, HOOD_TOP + 0.004, pu[2] + 0.02), (s*1.0, HOOD_TOP - 0.01, pu[2] + 0.03)]
    # 0.4.9b: the outer edge follows the wall and window sill up to the glareshield corner, so the sweep faces the
    # pilot instead of twisting outward; the last section is a ledge at glareshield height from the hood corner to the wall
    assert len(end) == len(start)
    n = 14; out = []
    for k in range(1, n + 1):
        u = k/n
        row = []
        for P0, P1 in zip(start, end):
            C = (P1[0], P0[1], P1[2])            # leaves flat and forward, arrives rising
            row.append(tuple((1 - u)**2*P0[j] + 2*(1 - u)*u*C[j] + u*u*P1[j] for j in range(3)))
        # outer edge runs along the side window sill (just under it, on the wall) from the console up to the glareshield's
        # front corner, so the sweep follows the cockpit's curvature
        row[-1] = sill_point(s, u)
        out.append(row)
    return out

SILL = [(1.415, 0.244, 17.09), (1.351, 0.312, 17.201), (1.273, 0.388, 17.312), (1.176, 0.466, 17.423),
        (1.057, 0.544, 17.534), (0.915, 0.614, 17.645), (0.815, 0.650, 17.72)]   # side window lower edge (panes.json), last = hood corner
def sill_point(s, u):
    chain = [(hull_x(0.20, SWEEP_Z0) - 0.035, 0.20, SWEEP_Z0)] + [(x, y - 0.02, z) for x, y, z in SILL]
    L = [0.0]
    for a, b in zip(chain, chain[1:]): L.append(L[-1] + math.sqrt(vdot(vsub(b, a), vsub(b, a))))
    d = u*L[-1]
    for i in range(len(chain) - 1):
        if d <= L[i + 1] or i == len(chain) - 2:
            f = (d - L[i])/max(L[i + 1] - L[i], 1e-9); p = vadd(vmul(chain[i], 1 - f), vmul(chain[i + 1], f)); break
    x = min(p[0], hull_x(p[1], p[2]) - 0.035) if i < len(chain) - 2 else p[0]
    return (s*x, p[1], p[2])

def sweep_top(s):
    """fill between the glareshield's outboard end and the wall, forward of the sweep, up to the windscreen sill"""
    x = s*PANEL_HALF
    pu = panel_frame(x, PANEL_TOP).p(0, 0, HOOD_LIP)
    a = (pu[0] + s*0.012, HOOD_TOP + 0.004, pu[2] + 0.02); b = (s*1.00, 0.62, 17.62)
    f = (pu[0] + s*0.012, HOOD_FWD[0], HOOD_FWD[1]); w = (s*0.93, HOOD_FWD[0] - 0.02, HOOD_FWD[1] + 0.02)
    eye = (s*0.38, 0.82, 16.31)
    for q in ([a, b, w, f],):
        c = vmul(vadd(vadd(q[0], q[1]), vadd(q[2], q[3])), 0.25)
        face_toward('cockpit_int', q, vsub(eye, c), 'P220_cabin')

def console_section(xi, t, xs):
    """section across the console (|x|, y) from the floor at the toe recess, up the sloped inboard face, round the top edge,
    across the top to the wall (the wall end is clamped to the skin later)"""
    pts = [(0.930, FLOOR), (0.930, -0.060), (0.870, -0.040), (xi + 0.022, 0.100), (xi, t - 0.040)]
    for k in range(1, 4):                                   # top edge rounded on a 3 cm radius
        a = math.radians(180 - 30*k); pts.append((xi + 0.03 + 0.03*math.cos(a), t - 0.03 + 0.03*math.sin(a)))
    pts += [(max(xs, xi + 0.04), CON_TOP), (1.60, CON_TOP)]
    if t <= CON_TOP + 0.001: pts[-2:] = [(xi + 0.045, t), (1.60, t)]
    return pts

def consoles():
    for s in (-1, 1):
        secs = [[(s*x, y, z) for x, y in console_section(xi, t, xs)] for z, xi, t, xs in CON_STATIONS if z <= SWEEP_Z0 + 1e-6]
        secs += sweep_sections(s, secs[-1])
        m = len(secs[0])
        for A, B in zip(secs, secs[1:]):
            for i in range(m - 1):
                d = (A[i + 1][0] - A[i][0], A[i + 1][1] - A[i][1])
                want = (-d[1]*s, d[0]*s, 0.0)                  # outward side of the section outline
                if vdot(want, want) < 1e-12: continue
                face_toward('cockpit_int', [A[i], A[i + 1], B[i + 1], B[i]], want, 'P220_cabin')
        face_toward('cockpit_int', secs[0], (0, 0, -1), 'P220_cabin')
        # footwell side wall: from the console front forward under the panel to the footwell back wall
        # 0.4.8: it carries the console's own inboard profile forward, so console and footwell side are one surface
        z0 = SWEEP_END_Z
        eb = panel_frame(s*PANEL_HALF, PANEL_BOT).p(0, 0, 0.012)     # 0.4.11: same outline as the console loft's last section (gap fix)
        prof = [(0.93, FLOOR), (0.93, -0.06), (0.87, -0.04), (abs(eb[0]), eb[1]), (abs(eb[0]) - 0.004, 0.30)]   # top runs up behind the panel's lower edge: no light gap
        for (xa, ya), (xb, yb) in zip(prof, prof[1:]):
            d = (xb - xa, yb - ya)
            face_toward('cockpit_int', [(s*xa, ya, z0), (s*xb, yb, z0), (s*xb, yb, FOOTWELL_Z1), (s*xa, ya, FOOTWELL_Z1)],
                        (-d[1]*s, d[0]*s, 0.0) if False else (-s, 0.3, 0), 'P220_cabin')
        # sweep_top(s) dropped: its forward corners sat outside the hull     # 0.4.8: the console's inboard face runs on under the panel, same moulding
        flat = lambda x, z, y=CON_TOP: Frame((x, y, z), (1, 0, 0), (0, 0, 1), (0, 1, 0))
        # side stick well and boot (the stick itself moves: part stick_L / stick_R)
        px, py, pz = STICK_PIVOT[s]
        prism('cockpit_int', flat(px, pz), rrect(0.13, 0.15, 0.012, 2), 0.004, decal='ssbase', proud=0.004, decal_box=(0.13, 0.15))
        # raised bezel ring the gaiter is clamped into
        lathe('cockpit_int', flat(px, pz, CON_TOP + 0.004), [(0.050, 0.0), (0.048, 0.006), (0.041, 0.009)], 14, mat='P220_cabin', cap0=False)
        # padded hand rest aft of the stick: the wrist lies on it, sloping down toward the grip
        hr = flat(px - s*0.004, pz - 0.125, CON_TOP + 0.004).pitch(-7)
        prism('cockpit_int', hr, rrect(0.085, 0.105, 0.03, 2), 0.036, chamfer=0.012, proud=0.036, paint='dark')
        prism('cockpit_int', hr, rrect(0.095, 0.115, 0.03, 2), 0.010, chamfer=0.003, proud=0.006, paint='paint', front=False)
        # console panels aft of the stick (tiller, lights, audio)
        for k, (z, reg) in enumerate(((16.64, 'con0'),)):
            prism('cockpit_int', flat(s*1.05, z), rect(0.20, 0.22), 0.01, decal=reg if s < 0 else ('con2' if k == 0 else 'con1'),
                  chamfer=0.002, proud=0.006)
        # nose wheel tiller handwheel inboard of the armrest (pilot side) / chart holder (co-pilot side)
        # 0.4.7 detail pass (knobs and buttons round the sticks; fill the bare console tops): a side stick panel outboard
        # of each stick, a chrono / lights panel forward of it, and an oxygen mask box at the outboard aft corner
        prism('cockpit_int', flat(s*1.16, 16.95), rect(0.15, 0.12), 0.012, decal='con3' if s < 0 else 'con5', chamfer=0.002,
              proud=0.006, decal_box=(0.15, 0.12))
        prism('cockpit_int', flat(s*1.31, 16.80), rect(0.15, 0.12), 0.012, decal='con4', chamfer=0.002, proud=0.006, decal_box=(0.15, 0.12))
        boxw('cockpit_int', (s*1.30, CON_TOP + 0.034, 16.62), (0.16, 0.068, 0.128), paint='dark', skip=('-y',))
        prism('cockpit_int', flat(s*1.30, 16.62, CON_TOP + 0.068), rect(0.152, 0.120), 0.004, decal='o2box', chamfer=0.0015,
              proud=0.003, decal_box=(0.152, 0.120))
        # nose wheel tiller handwheel inboard of the armrest on both sides (0.4.7: the first officer has one too, as on the A220)
        if True:
            c = (s*0.86, CON_TOP + 0.03, 16.64)
            prism('cockpit_int', flat(c[0], c[2], CON_TOP + 0.002), circle(0.05, 16), 0.002, decal='ssbase', proud=0.002, decal_box=(0.13, 0.15))
            tube('cockpit_int', (c[0], CON_TOP, c[2]), c, 0.01, 8)
            prism('cockpit_int', flat(c[0], c[2], c[1]), circle(0.045, 16), 0.016, chamfer=0.005, proud=0.016, paint='dark', back=True)
        stick(s)

def stick(s):
    """Airbus-style side stick: rubber gaiter, short shaft, ergonomic grip leaning forward with a hooded head that
    overhangs the hand, PTT trigger under the head and the red autopilot disconnect button on the thumb side."""
    side = 'L' if s < 0 else 'R'
    part = 'stick_' + side
    px, py, pz = STICK_PIVOT[s]
    PIVOTS[part] = (px, py, pz)
    inb = -s                                   # inboard direction (toward the pedestal) along x
    # gaiter: a bellows from the bezel ring up round the shaft
    up = fr3((px, py - 0.008, pz), (1, 0, 0), (0, 0, 1))
    lathe(part, up, [(0.039, 0.000), (0.033, 0.009), (0.034, 0.013), (0.026, 0.021), (0.027, 0.025), (0.019, 0.034),
                     (0.020, 0.038), (0.013, 0.050), (0.011, 0.060)], 10, cap0=False)
    lean = math.radians(9.0)
    top = (px, py + 0.060, pz + 0.060*math.tan(lean))
    tube(part, (px, py + 0.030, pz), top, 0.0085, 8, paint='paint')
    # grip axis: forward lean, canted a little outboard as the wrist turns
    gu = vnorm((-inb*math.sin(math.radians(5)), math.cos(math.radians(12)), math.sin(math.radians(12))))
    fwd = vnorm(vcross((1, 0, 0), gu)); fwd = fwd if fwd[2] > 0 else vmul(fwd, -1)
    side_ax = vnorm(vcross(gu, fwd)); side_ax = side_ax if side_ax[0]*inb > 0 else vmul(side_ax, -1)   # toward the thumb
    # sections (height along the axis, width across, depth fore-aft, forward offset): neck, palm swell, waist, hooded head
    SEC = ((0.000, 0.026, 0.030, 0.000), (0.014, 0.032, 0.042, -0.002), (0.036, 0.038, 0.052, -0.003), (0.062, 0.036, 0.048, 0.000),
           (0.080, 0.034, 0.046, 0.006), (0.094, 0.042, 0.066, 0.016), (0.110, 0.040, 0.066, 0.018), (0.121, 0.029, 0.050, 0.014))
    rings = []
    for h, w, d, off in SEC:
        c = vadd(vadd(top, vmul(gu, h)), vmul(fwd, off))
        fr = Frame(c, side_ax, fwd, gu)
        rings.append([fr.p(a, b) for a, b in rrect(w, d, 0.45*min(w, d), 2)()])
    loft(part, rings, paint='dark')
    hcen = lambda h, off=0.0: vadd(vadd(top, vmul(gu, h)), vmul(fwd, off))
    # red autopilot disconnect push button on the thumb side of the head, facing up and inboard
    bn = vnorm(vadd(side_ax, vmul(gu, 0.9)))
    bo = vadd(hcen(0.108, 0.010), vmul(side_ax, 0.014))
    bf = fr3(vadd(bo, vmul(bn, 0.004)), fwd, vcross(bn, fwd))
    bf = bf if vdot(bf.n, bn) > 0 else fr3(bf.o, vmul(fwd, -1), vcross(bn, fwd))
    prism(part, bf, circle(0.0085, 10), 0.006, proud=0.0015, paint='paint', knobs=False)
    prism(part, bf, circle(0.0065, 10), 0.004, proud=0.0045, decal='red', decal_box=(0.3, 0.3), knobs=False)
    # radio push-to-talk trigger under the hooded front of the head, where the index finger lies
    tf = fr3(vadd(hcen(0.082, 0.006), vmul(fwd, 0.020)), fwd, gu)
    trig = [(0.000, 0.008), (0.000, -0.016), (0.008, -0.020), (0.015, -0.014), (0.016, -0.003), (0.011, 0.006)]
    prism(part, tf, poly_shape(trig), 0.013, proud=0.0065, paint='paint', back=True, knobs=False)

# ================================================================== rudder pedals: sliding pedals on floor channels (PB-22 mechanism)
# the author 2026-11-01: the 0.3.13 pendulum pedals hung behind the panel and could not be seen. As on the PB-22 each pedal
# rides a carriage in a floor channel, sits where the pilot can see it under the panel lip, and slides +-6 cm fore and
# aft with the rudder (the plugin moves the pedal part along its local z).
PEDAL_CZ = 17.16          # pedal part pivot station (the Unity builder places the parts here; unchanged)
PEDAL_GZ = 17.52          # 0.3.30: carriage centre at rest, in the footwell under the panel (the parts only slide, so the
                          # geometry sits ahead of the pivot)
PEDAL_TRAVEL = 0.06
PEDAL_FW = FLOOR + 0.10   # raised footrest under each pilot's pedals, so the pedals stand where the pilot can see them
def pedals():
    base = PEDAL_FW + 0.006
    for s in (-1, 1):
        x = s*0.40
        side = 'L' if s < 0 else 'R'
        boxw('cockpit_int', (s*0.485, (FLOOR + PEDAL_FW)/2, (17.27 + FOOTWELL_Z1)/2), (0.61, PEDAL_FW - FLOOR, FOOTWELL_Z1 - 17.27), paint='dark',
             skip=('-y', '+z', '+y'))   # raised footrest filling the footwell from the pedestal to the console
        q = [(s*0.18, PEDAL_FW, 17.27), (s*0.79, PEDAL_FW, 17.27), (s*0.79, PEDAL_FW, FOOTWELL_Z1), (s*0.18, PEDAL_FW, FOOTWELL_Z1)]
        face_toward('cockpit_int', q, (0, 1, 0), 'P220_cockpit', [carpet_uv(p[0], p[2]) for p in q])   # carpeted top, worn under the heels
        for dx in (-0.09, 0.09):
            px = x + dx
            L = 0.11 + 2*PEDAL_TRAVEL + 0.03
            boxw('cockpit_int', (px, (PEDAL_FW + base + 0.006)/2, PEDAL_GZ), (0.074, base + 0.006 - PEDAL_FW, L), paint='dark', skip=('-y',))   # channel base on the footrest
            for rx in (-0.033, 0.033):
                boxw('cockpit_int', (px + rx, base + 0.014, PEDAL_GZ), (0.008, 0.022, L), paint='dark', skip=('-y',))
                boxw('cockpit_int', (px + rx, base + 0.027, PEDAL_GZ), (0.014, 0.004, L), paint='paint', skip=('-y',))
            for ez in (PEDAL_GZ - L/2 + 0.006, PEDAL_GZ + L/2 - 0.006):
                boxw('cockpit_int', (px, base + 0.012, ez), (0.058, 0.018, 0.012), paint='paint', skip=('-y',))
            name = 'pedal_' + side + ('L' if dx < 0 else 'R')
            PIVOTS[name] = MOVERS[name] = (px, base + 0.04, PEDAL_CZ)
            PZ_ = PEDAL_GZ
            boxw(name, (px, base + 0.016, PZ_), (0.050, 0.020, 0.11), paint='dark', skip=('-y',))
            for ez in (PZ_ - 0.045, PZ_ + 0.045):
                boxw(name, (px, base + 0.012, ez), (0.064, 0.012, 0.016), paint='paint', skip=('-y',))
            # pedal face leaning back 20 degrees on a heel hinge block and a rear brace
            fr = Frame((px, base + 0.095, PZ_ - 0.03), (1, 0, 0), (0, 1, 0), (0, 0, -1)).pitch(-20)
            prism(name, fr, rrect(0.08, 0.14, 0.012, 2), 0.025, chamfer=0.004, paint='dark', back=True, decal='pedal', decal_box=(0.08, 0.14))
            heel = fr.p(0, -0.07, -0.012)
            boxw(name, (px, (heel[1] + base + 0.026)/2, heel[2]), (0.06, max(heel[1] - base - 0.026, 0.004) + 0.012, 0.022), paint='dark', skip=('-y',))
            tube(name, fr.p(0, 0.04, -0.026), (px, base + 0.026, PZ_ + 0.05), 0.008, 6)

# ================================================================== crew seats
# airliner pilot seats at the stock crew positions (the game's ejection seat renderers are hidden by the builder):
# seat reference point x +-0.40, y 0.207, z 16.45; heads at about y 0.80, z 16.24
SEAT_X, SEAT_Y, SEAT_Z = 0.40, 0.207, 16.45
SEAT_RECLINE = 13.0
def crew_seats():
    P = 'cockpit_int'
    flat = lambda x, y, z: fr3((x, y, z), (1, 0, 0), (0, 0, 1))         # front face up
    for s in (-1, 1):
        x = s*SEAT_X
        # floor rails the seat runs on, and the carriage riding them
        for dx in (-0.13, 0.13):
            boxw(P, (x + dx, FLOOR + 0.008, 16.30), (0.034, 0.016, 0.98), paint='paint', skip=('-y',))
        prism(P, flat(x, FLOOR + 0.075, 16.43), rrect(0.32, 0.40, 0.03, 1), 0.06, chamfer=0.008, proud=0.0, paint='dark', knobs=False)
        # column and seat pan shell
        prism(P, flat(x, 0.150, 16.43), rrect(0.22, 0.28, 0.04, 1), 0.150 - FLOOR - 0.075 + 0.002, proud=0.0, mat='P220_cabin', knobs=False)
        pan = flat(x, 0.205, 16.465).pitch(4.0)
        pan_out = poly_shape([(-0.205, -0.235), (0.205, -0.235), (0.195, 0.205), (0.15, 0.245), (-0.15, 0.245), (-0.195, 0.205)])
        prism(P, pan.at(0, 0, -0.012), pan_out, 0.050, chamfer=0.006, proud=0.0, mat='P220_cabin', knobs=False)
        prism(P, pan.at(0, 0.0035), rrect(0.375, 0.455, 0.05, 2), 0.062, chamfer=0.016, proud=0.050, paint='dark', knobs=False)
        # back: cushion with shoulder bolsters on a shell, reclined, front face toward the panel
        t = math.radians(SEAT_RECLINE)
        bk = fr3((x, 0.255, 16.235), (-1, 0, 0), (0, math.cos(t), -math.sin(t)))
        back = [(-0.205, 0.0), (0.205, 0.0), (0.23, 0.22), (0.225, 0.38), (0.185, 0.445), (-0.185, 0.445), (-0.225, 0.38), (-0.23, 0.22)]
        prism(P, bk, poly_shape(back), 0.075, chamfer=0.02, proud=0.0, paint='dark', knobs=False)
        prism(P, bk.at(0, -0.01, -0.070), poly_shape([(a*1.04, b) for a, b in back]), 0.045, chamfer=0.012, proud=0.0, mat='P220_cabin',
              back=True, knobs=False)
        # headrest on two stems
        prism(P, bk.at(0, 0.545, -0.012), rrect(0.27, 0.15, 0.045, 2), 0.075, chamfer=0.018, proud=0.0, paint='dark', back=True, knobs=False)
        for dx in (-0.07, 0.07):
            tube(P, bk.p(dx, 0.43, -0.05), bk.p(dx, 0.48, -0.05), 0.007, 6, paint='paint', caps=False)
        # outboard armrest down, cantilevered from the back; inboard armrest folded up beside the back
        ay = 0.415
        for k, inboard in ((s, False), (-s, True)):
            ax_ = x + k*0.258
            if not inboard:
                af = fr3((ax_, ay, 16.36), (0, 0, k), (0, 1, 0))                # side profile, front face outward
                prism(P, af, rrect(0.32, 0.050, 0.022, 1), 0.022, chamfer=0.008, proud=0.023, paint='dark', knobs=False)
                af2 = fr3((ax_, ay, 16.36), (0, 0, -k), (0, 1, 0))
                prism(P, af2, rrect(0.32, 0.050, 0.022, 1), 0.022, chamfer=0.008, proud=0.023, paint='dark', knobs=False)
                # pivot boss through the back's side, and a tapered side bracket from the seat pan frame up under the armrest
                tube(P, (x + k*0.214, ay - 0.025, 16.182), (x + k*0.280, ay - 0.025, 16.182), 0.024, 8, paint='paint')
                bf = fr3((x + k*0.200, 0.0, 0.0), (0, 0, k), (0, 1, 0))
                prism(P, bf, poly_shape([(k*a, b) for a, b in ([(16.30, 0.150), (16.56, 0.150), (16.47, 0.398), (16.37, 0.398)] if k > 0 else
                      [(16.37, 0.398), (16.47, 0.398), (16.56, 0.150), (16.30, 0.150)])]), 0.060, proud=0.060, mat='P220_cabin', back=True, knobs=False)
            else:
                fu = (0, math.cos(t), -math.sin(t))                            # standing up along the back
                o = vadd((ax_, ay - 0.035, 16.19), vmul(fu, 0.15))
                af = fr3(o, (0, -math.sin(t), -math.cos(t)), fu)
                af = af if vdot(af.n, (k, 0, 0)) > 0 else fr3(o, (0, math.sin(t), math.cos(t)), fu)
                prism(P, af, rrect(0.050, 0.32, 0.022, 1), 0.022, chamfer=0.008, proud=0.023, paint='dark', knobs=False)
                af2 = fr3(o, vmul(af.u, -1), fu)
                prism(P, af2, rrect(0.050, 0.32, 0.022, 1), 0.022, chamfer=0.008, proud=0.023, paint='dark', knobs=False)
                tube(P, (x + k*0.214, ay - 0.035, 16.185), (x + k*0.272, ay - 0.035, 16.185), 0.022, 8, paint='paint')   # pivot boss into the back's side

# ================================================================== floor, walls, ceiling, overhead, bulkhead
BULK_Z = 14.95          # 0.3.22: moved 0.47 m aft, clear of the seat backs and out of the side window view
def carpet_uv(x, z):
    """atlas UV of the crew floor carpet at (x, z): unique, 440 px per metre"""
    X, Y, W, H = ATLAS['carpet']
    px = (x - CARPET_X[0])*CARPET_PPM; py = (CARPET_Z[1] - z)*CARPET_PPM
    return ((X + px)/TEX, 1.0 - (Y + py)/TEX)
def patch_uv(a, b, flip_a, flip_b):
    """UV inside the plain carpet patch, a and b 0..1 across it (mirrored per tile so the joins match)"""
    x0, x1, z0, z1 = CARPET_PATCH
    if flip_a: a = 1 - a
    if flip_b: b = 1 - b
    return carpet_uv(x0 + a*(x1 - x0), z0 + b*(z1 - z0))
def floor():
    """0.3.30: carpet. The crew area between the console feet is one unique piece (grain, tone variation, foot wear and
    bound edges painted in place); aft of it and under the consoles the floor repeats a plain patch, mirrored tile to tile."""
    P = 'cockpit_int'; up = (0, 1, 0)
    wz = lambda z: hull_x(FLOOR, z) - 0.03
    x0, x1 = CARPET_X; z0, z1 = CARPET_Z
    q = [(x0, FLOOR, z0), (x1, FLOOR, z0), (x1, FLOOR, z1), (x0, FLOOR, z1)]
    face_toward(P, q, up, 'P220_cockpit', [carpet_uv(p[0], p[2]) for p in q])
    def tiles(xa, xb, za, zb, nx, nz):
        for i in range(nx):
            for j in range(nz):
                ua, ub = xa + (xb - xa)*i/nx, xa + (xb - xa)*(i + 1)/nx
                va, vb = za + (zb - za)*j/nz, za + (zb - za)*(j + 1)/nz
                pts = [(ua, va, 0, 0), (ub, va, 1, 0), (ub, vb, 1, 1), (ua, vb, 0, 1)]
                face_toward(P, [(u, FLOOR, v) for u, v, _, _ in pts], up, 'P220_cockpit',
                            [patch_uv(a, b, i % 2, j % 2) for _, _, a, b in pts])
    zs = [BULK_Z, 15.30, 15.65, 16.00, z0]
    for za, zb in zip(zs, zs[1:]):
        w = min(wz(za), wz(zb)); tiles(-w, w, za, zb, max(2, int(round(2*w/0.62))), 1)
    zs = [z0, 16.80, 17.30, z1]
    for za, zb in zip(zs, zs[1:]):
        w = min(wz(za), wz(zb))
        for s in (-1, 1):
            tiles(*sorted((s*x1, s*w)), za, zb, 1, 1)
    flat = lambda x, y, z: Frame((x, y, z), (1, 0, 0), (0, 0, 1), (0, 1, 0))
    for s in (-1, 1):   # rubber heel pads under the pedals
        prism('cockpit_int', flat(s*0.40, PEDAL_FW + 0.004, 17.335), rect(0.36, 0.12), 0.004, decal='tread', decal_box=(0.36, 0.34), proud=0.004)

WIN_TRIS = []
def _load_glass():
    if WIN_TRIS: return
    V = []; cur = None
    for line in open(os.path.join(CK, 'ctx.obj')):
        if line.startswith('o '): cur = line[2:].strip()
        elif line.startswith('v '): V.append(tuple(map(float, line.split()[1:4])))
        elif line.startswith('f ') and cur.startswith('canopy_glass'):
            idx = [int(t.split('/')[0]) - 1 for t in line.split()[1:]]
            for k in range(1, len(idx) - 1): WIN_TRIS.append((V[idx[0]], V[idx[k]], V[idx[k + 1]]))
def _ray_hits(o, d):
    for a, b, c in WIN_TRIS:
        e1 = vsub(b, a); e2 = vsub(c, a); p = vcross(d, e2); det = vdot(e1, p)
        if abs(det) < 1e-9: continue
        inv = 1/det; tv = vsub(o, a); u = vdot(tv, p)*inv
        if u < 0 or u > 1: continue
        q = vcross(tv, e1); v = vdot(d, q)*inv
        if v < 0 or u + v > 1: continue
        if vdot(e2, q)*inv > 0: return True
    return False
SPLIT_ROOF = True
def liner():
    """cabin lining 3 cm inside the skin from the bulkhead forward, with the window openings left open. 0.3.17 (review):
    finer faces (the coarse ones left ragged 10-16 cm gaps round the windows) and carried forward over the windscreen posts
    above the glareshield; the gaps that remain are covered by the window trim."""
    _load_glass()
    zs = [BULK_Z + k*0.06 for k in range(int((18.30 - BULK_Z)/0.06) + 1)]
    n = 128
    for z0, z1 in zip(zs, zs[1:]):
        for i in range(n):
            a0, a1 = 2*math.pi*i/n, 2*math.pi*(i + 1)/n
            q = [hull_pt(a0, z0, 0.03), hull_pt(a1, z0, 0.03), hull_pt(a1, z1, 0.03), hull_pt(a0, z1, 0.03)]
            c = vmul(vadd(vadd(q[0], q[1]), vadd(q[2], q[3])), 0.25)
            if c[1] < FLOOR: continue
            if z0 > 17.30 and c[1] < HOOD_TOP and abs(c[0]) < 0.78: continue   # forward of the panel: above the glareshield, and outboard of the panel ends
            if abs(c[0]) < 0.26 and OVH_Z[0] + 0.04 < c[2] < OVH_Z[1] - 0.04 and c[1] > 1.0: continue   # hidden inside the overhead panel box
            o = (0.0, max(min(c[1], 0.9), 0.3), c[2])
            hits = [_ray_hits(o, vnorm(vsub(p, o))) for p in q + [c]]
            if not any(hits):
                face_toward('cockpit_int', q, vsub(o, c), 'P220_cabin'); continue
            if all(hits) or c[1] < 0.95 or not SPLIT_ROOF: continue
            # a roof quad straddling a window outline: split it 2 x 2 and keep the pieces clear of the glass, so the lining
            # runs on up to the window trim instead of stopping in a saw-tooth that shows the skin above the windscreen
            for i2 in range(2):
                for j2 in range(2):
                    aa0, aa1 = a0 + (a1 - a0)*i2/2, a0 + (a1 - a0)*(i2 + 1)/2
                    zz0, zz1 = z0 + (z1 - z0)*j2/2, z0 + (z1 - z0)*(j2 + 1)/2
                    sq = [hull_pt(aa0, zz0, 0.03), hull_pt(aa1, zz0, 0.03), hull_pt(aa1, zz1, 0.03), hull_pt(aa0, zz1, 0.03)]
                    sc = vmul(reduce_add(sq), 0.25); so = (0.0, max(min(sc[1], 0.9), 0.3), sc[2])
                    if any(_ray_hits(so, vnorm(vsub(p, so))) for p in sq + [sc]): continue
                    face_toward('cockpit_int', sq, vsub(so, sc), 'P220_cabin')

# ---- window trim (0.3.17, review): a reveal round every pane from the skin's cut edge 5.5 cm in, and a 9 cm trim flange
# lying over the lining, so neither the white outer skin edge nor the back of the skin shows from the seats
def window_trim():
    import json
    panes = json.load(open(os.path.join(CK, 'panes.json')))
    for pb in panes:
        P = [(v[0], v[2], v[1]) for v in pb]           # Blender (x, Y, z) -> Unity (x, y, z)
        cen = vmul(reduce_add(P), 1.0/len(P))
        A, Bq, C = [], [], []
        for p in P:
            hw, zt, zb = fus(NOSE_Y - p[2]); zc = (zt + zb)/2
            r = vnorm((-p[0], zc - p[1], 0.0))           # inward, towards the fuselage axis
            t = vsub(p, cen); t = vnorm(vsub(t, vmul(r, vdot(t, r))))   # outward from the pane, along the skin
            A.append(vadd(p, vmul(r, 0.004))); b = vadd(p, vmul(r, 0.055)); Bq.append(b)
            # the flange widens from 12 to 20 cm along the windscreen's top edge (outward direction pointing aft, clear of the posts), where the lining's window cut-out is ragged
            cl = lambda v: min(max(v, 0.0), 1.0)
            wf = 0.12 + 0.08*cl((p[1] - 0.95)/0.10)*cl((-t[2] - 0.25)/0.25)*cl((0.80 - abs(p[0]))/0.08)
            C.append(vadd(b, vmul(t, wf)))
        m = len(P)
        for i in range(m):
            j = (i + 1) % m
            face_toward('cockpit_int', [A[i], A[j], Bq[j], Bq[i]], vsub(cen, A[i]), 'P220_cabin')
            mid = vmul(vadd(Bq[i], Bq[j]), 0.5); hw, zt, zb = fus(NOSE_Y - mid[2])
            face_toward('cockpit_int', [Bq[i], Bq[j], C[j], C[i]], vsub((0.0, (zt + zb)/2, mid[2]), mid), 'P220_cabin')
def reduce_add(pts):
    o = (0.0, 0.0, 0.0)
    for p in pts: o = vadd(o, p)
    return o

def bulkhead():
    pts = []
    for i in range(48):
        a = 2*math.pi*i/48
        p = hull_pt(a, BULK_Z, 0.02)       # 0.3.30: 2 cm inside the skin, so the edge meets the lining all round
        pts.append((p[0], max(p[1], FLOOR)))
    fr = Frame((0, 0, BULK_Z), (-1, 0, 0), (0, 1, 0), (0, 0, 1))
    prism('cockpit_int', fr, ngon([(-x, y) for x, y in pts]), 0.03, mat='P220_cabin', proud=0.0)
    # flight deck door, centred, with a frame and a peephole
    door = Frame((0, FLOOR + 0.95, BULK_Z), (-1, 0, 0), (0, 1, 0), (0, 0, 1))
    prism('cockpit_int', door, rect(0.86, 1.94), 0.03, proud=0.03, paint='dark')
    prism('cockpit_int', door, rect(0.76, 1.86), 0.02, proud=0.045, decal='door', decal_box=(0.76, 1.86))
    prism('cockpit_int', door.at(0.30, 0.0), rrect(0.03, 0.14, 0.01, 2), 0.03, proud=0.075, paint='paint', back=True)
    prism('cockpit_int', door.at(0.0, 0.45), circle(0.012, 10), 0.01, proud=0.05, decal='red', decal_box=(0.3, 0.3))
    # 0.3.22 (the bulkhead needs detail): reinforced door with a kick-out panel, viewing port and keypad, a folded
    # observer seat, fire extinguisher, crash axe, oxygen mask stowage and a circuit breaker panel
    prism('cockpit_int', door.at(0.0, -0.62), rect(0.52, 0.42), 0.004, proud=0.049, paint='dark')            # kick-out panel seam
    prism('cockpit_int', door.at(0.0, -0.62), rect(0.50, 0.40), 0.004, proud=0.050, paint='paint')
    prism('cockpit_int', door.at(0.0, 0.62), rrect(0.16, 0.10, 0.015, 2), 0.01, proud=0.052, paint='dark')    # viewing port
    prism('cockpit_int', door.at(0.0, 0.62), rrect(0.13, 0.075, 0.012, 2), 0.004, proud=0.057, paint='dark')
    kp = Frame((-0.55, FLOOR + 1.30, BULK_Z), (-1, 0, 0), (0, 1, 0), (0, 0, 1))
    prism('cockpit_int', kp, rrect(0.09, 0.13, 0.008, 2), 0.025, chamfer=0.004, proud=0.025, paint='dark')     # door keypad
    for i in range(12):
        prism('cockpit_int', kp.at((i % 3 - 1)*0.022, 0.035 - (i // 3)*0.02), rect(0.015, 0.012), 0.004, proud=0.029, paint='paint')
    prism('cockpit_int', kp.at(0.0, 0.055), rect(0.05, 0.008), 0.003, proud=0.028, decal='red', decal_box=(0.3, 0.3))
    # folded observer seat on the right of the door: frame rails, upright pan and back cushion, headrest
    js = Frame((0.66, FLOOR, BULK_Z), (-1, 0, 0), (0, 1, 0), (0, 0, 1))
    for dx in (-0.20, 0.20):
        prism('cockpit_int', js.at(dx, 0.75), rect(0.03, 1.40), 0.03, proud=0.03, paint='dark')
    prism('cockpit_int', js.at(0.0, 0.62), rrect(0.38, 0.42, 0.03, 2), 0.07, chamfer=0.012, proud=0.10, paint='dark')   # folded pan
    prism('cockpit_int', js.at(0.0, 1.05), rrect(0.36, 0.40, 0.03, 2), 0.05, chamfer=0.012, proud=0.06, paint='dark')   # back
    prism('cockpit_int', js.at(0.0, 1.36), rrect(0.24, 0.14, 0.03, 2), 0.06, chamfer=0.012, proud=0.07, paint='dark')   # headrest
    # fire extinguisher in its bracket and a crash axe, left of the door
    fx_ = -0.66
    tube('cockpit_int', (fx_, FLOOR + 0.30, BULK_Z + 0.09), (fx_, FLOOR + 0.70, BULK_Z + 0.09), 0.055, 12, paint='paint')
    prism('cockpit_int', Frame((fx_, FLOOR + 0.50, BULK_Z + 0.09), (-1, 0, 0), (0, 1, 0), (0, 0, 1)), rect(0.112, 0.36), 0.004,
          proud=0.0565, decal='red', decal_box=(0.112, 0.36))
    tube('cockpit_int', (fx_, FLOOR + 0.70, BULK_Z + 0.09), (fx_, FLOOR + 0.78, BULK_Z + 0.09), 0.018, 8, paint='dark')
    for yy in (0.40, 0.62):
        boxw('cockpit_int', (fx_, FLOOR + yy, BULK_Z + 0.03), (0.13, 0.025, 0.05), paint='dark')
    tube('cockpit_int', (-0.48, FLOOR + 0.35, BULK_Z + 0.03), (-0.48, FLOOR + 0.80, BULK_Z + 0.03), 0.014, 8, paint='dark')   # axe handle
    boxw('cockpit_int', (-0.48, FLOOR + 0.82, BULK_Z + 0.03), (0.12, 0.05, 0.015), paint='paint')                     # axe head
    # oxygen mask stowage boxes and a circuit breaker panel above them
    for x in (-0.66, 0.66):
        prism('cockpit_int', Frame((x, FLOOR + 1.62, BULK_Z), (-1, 0, 0), (0, 1, 0), (0, 0, 1)), rrect(0.20, 0.12, 0.012, 2), 0.08,
              chamfer=0.006, proud=0.08, paint='dark')
    # 0.3.30: the breaker panel sat above the bulkhead's curved top edge and showed through the cabin ceiling; it is now
    # smaller and sits on the oxygen box, its outer top corner 3 cm inside the bulkhead outline
    cb = Frame((-0.66, FLOOR + 1.78, BULK_Z), (-1, 0, 0), (0, 1, 0), (0, 0, 1))
    prism('cockpit_int', cb, rect(0.26, 0.16), 0.02, chamfer=0.003, proud=0.02, paint='dark')
    for r_ in range(3):
        for c_ in range(6):
            prism('cockpit_int', cb.at(-0.10 + c_*0.04, 0.05 - r_*0.05), rect(0.011, 0.011), 0.012, proud=0.032, paint='paint')

OVH_Z = (15.92, 16.76)
def overhead():
    """overhead panel: 2 x 2 switch panels on a box hung from the roof between the side windows."""
    z0, z1 = OVH_Z
    y0 = hull_pt(math.pi/2, z0, 0.03)[1] - 0.10; y1 = hull_pt(math.pi/2, z1, 0.03)[1] - 0.10
    a = (0, y0, z0); b = (0, y1, z1)
    v = vnorm(vsub(a, b))           # legend tops face aft: read with the head tilted back, like a real overhead
    n = vmul(vcross((1, 0, 0), v), -1)
    mid = vmul(vadd(a, b), 0.5)
    F = Frame(mid, (1, 0, 0), v, n)
    L = math.sqrt(vdot(vsub(b, a), vsub(b, a)))
    prism('cockpit_int', F, rect(0.68, L + 0.04), 0.12, chamfer=0.015, paint='paint', proud=0.0)
    for i, (dx, dy) in enumerate(((-0.165, L/4), (0.165, L/4), (-0.165, -L/4), (0.165, -L/4))):
        prism('cockpit_int', F.at(dx, dy), rect(0.31, L/2 - 0.02), 0.01, decal='ovh%d' % i, chamfer=0.002, proud=0.008)

def simple():
    P = 'cockpit_int_simple'
    ym = (PANEL_TOP + PANEL_BOT)/2
    boxw(P, (0, (HOOD_TOP + PANEL_BOT)/2, face_z(ym) + 0.12), (1.60, HOOD_TOP - PANEL_BOT, 0.36), 'Matte_black')
    boxw(P, (0, (FLOOR + PED_TOP)/2, (PED_Z0 + 17.4)/2), (2*PED_HALF, PED_TOP - FLOOR, 17.4 - PED_Z0), 'Matte_black', skip=('-y',))
    for s in (-1, 1):
        boxw(P, (s*1.0, (FLOOR + CON_TOP)/2, (CON_Z0 + CON_Z1)/2), (0.76, CON_TOP - FLOOR, CON_Z1 - CON_Z0), 'Matte_black', skip=('-y',))
    boxw(P, (0, 0.5, BULK_Z - 0.02), (2.6, 1.6, 0.03), 'Matte_black')
    boxw(P, (0, hull_pt(math.pi/2, 16.55, 0.03)[1] - 0.16, 16.55), (0.68, 0.12, 0.84), 'Matte_black')

def clamp_to_hull(inset=0.025):
    moved = 0
    for name, p in PARTS.items():
        V = p['v']
        for i, v in enumerate(V):
            if abs(v[0]) < 0.5: continue
            if v[2] <= BULK_Z + 1e-6: continue     # the bulkhead outline is already fitted to the hull section
            h = [hull_x(v[1] + dy, v[2] + dz) for dy in (-0.03, 0, 0.03) for dz in (-0.03, 0, 0.03)]
            h = [t for t in h if t]
            if not h: continue
            lim = min(h) - inset
            if abs(v[0]) > lim:
                V[i] = (math.copysign(lim, v[0]),) + tuple(v[1:]); moved += 1
    CLAMPED[0] = moved
CLAMPED = [0]

# ---- a maintenance manual page taped to the captain's panel, outboard of his outer display (the author 2026-11-01)
def manual_page():
    # 0.4.18: the outer edge clipped into the panel side and the display bezel leaves no room to slide it inboard, so the
    # page is 6% smaller with its inboard edge where it was: the outer edge moves 1.5 cm in
    k = 0.94; hw, hh = 0.123 * k, 0.164 * k
    fr = panel_frame(-0.742 + 0.123 - hw, DISP_Y + 0.048).roll(3.0)
    prism('cockpit_int', fr, rect(hw, hh), 0.0008, proud=0.0132, decal='note', decal_box=(hw, hh), knobs=False)

def build_all(with_liner=True):
    PARTS.clear(); SCREENS.clear(); PIVOTS.clear(); MOVERS.clear()
    panel_body(); displays(); ys = noncritical(); lower_panels(ys); manual_page(); glareshield()
    pedestal(); consoles(); pedals(); crew_seats(); floor(); bulkhead(); overhead()
    if with_liner: liner(); window_trim(); blinds(); aft_wall_stowage()
    simple(); clamp_to_hull()
    return PARTS

# 0.4.7 detail pass: roller sun-blind housings along the top of each side window (as in the A220 photo), with a pull tab,
# so the bare lining strip over the side panes has something on it
def blinds():
    for s in (-1, 1):
        a = (s*0.86, 1.135, 16.84); b = (s*1.38, 1.065, 15.93)
        tube('cockpit_int', a, b, 0.019, 8)
        for e in (a, b):
            tube('cockpit_int', vadd(e, (0, 0.012, 0)), vadd(e, (0, -0.012, 0)), 0.024, 8, paint='paint')
        # 0.4.11: the pull tab hanging from the middle of the housing blocked the side window; removed

# 0.4.7: the bare wall aft of each side window (seen when looking out sideways) gets a document stowage pocket and a
# flashlight in its wall clips
def aft_wall_stowage():
    for s in (-1, 1):
        x = s*1.545
        boxw('cockpit_int', (x, 0.55, 15.72), (0.07, 0.30, 0.24), paint='dark', skip=('+y',))
        boxw('cockpit_int', (x - s*0.033, 0.47, 15.72), (0.008, 0.10, 0.25), paint='paint')       # elastic front band
        boxw('cockpit_int', (x, 0.69, 15.72), (0.045, 0.012, 0.22), paint='paint')                # manuals standing in it
        tube('cockpit_int', (s*1.565, 0.42, 15.52), (s*1.565, 0.66, 15.52), 0.020, 8, paint='dark')
        tube('cockpit_int', (s*1.565, 0.66, 15.52), (s*1.565, 0.70, 15.52), 0.027, 8, paint='paint')   # lens head
        for y in (0.47, 0.60):
            boxw('cockpit_int', (s*1.58, y, 15.52), (0.03, 0.02, 0.05), paint='paint')

def tri_count(parts=None):
    parts = parts or PARTS
    return {k: sum(len(f[0]) - 2 for f in p['f']) for k, p in parts.items()}

if __name__ == '__main__':
    import time; t = time.time()
    build_all()
    tc = tri_count(); print(tc, 'total', sum(v for k, v in tc.items() if 'simple' not in k), 'clamped', CLAMPED[0], '%.1fs' % (time.time() - t))
