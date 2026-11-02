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
    if kind == 'knob':      # skirted rotary knob with a red index line
        r = max(r, 0.007)
        prism(part, fr, circle(r*1.30, 10), 0.003, proud=z + 0.003, paint='dark', knobs=False)
        prism(part, fr, circle(r, 8), 0.014, chamfer=0.0015, proud=z + 0.017, paint='dark', knobs=False)
        prism(part, fr.at(0, r*0.45), rect(0.0016, r*0.8), 0.001, proud=z + 0.0175, decal='red', knobs=False)
    else:                   # bat toggle on a hex nut, leaning up; guarded ones get a red guard either side
        r = max(r, 0.004)
        prism(part, fr, circle(r*0.85, 6), 0.004, proud=z + 0.004, paint='dark', knobs=False)
        p0 = fr.p(0, 0, z + 0.004); p1 = fr.p(0, 0.006, z + 0.019)
        tube(part, p0, p1, 0.0018, 6)
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

