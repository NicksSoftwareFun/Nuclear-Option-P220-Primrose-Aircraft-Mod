"""Feature library for the PB-22 skin painter (tex_paint.py). Everything is evaluated from 3D position and normal,
never from UVs, so it survives every re-unwrap of the model.

Coordinates: Blender world at rest pose. x right (+x = right wing), y = 17 - d (d = metres aft of the nose tip),
z up (ground z 0). Fields below use d, x, ax = |x| (both sides at once) and z.

Building blocks
  F            a scalar field of position (axis fields F('d'), F('x'), F('ax'), F('z') or F(fn)).
  Shapes       give a signed distance in metres along the surface (negative inside):
                 Line(field, value, lim=[(field, lo, hi), ...])        open curve field == value, ends rounded
                 Box(u, v, (u0, u1), (v0, v1), r)                      rounded rectangle in two fields
                 Disc(centre_dxz, r)                                   circle (sphere cut through the skin)
                 Custom(fn)                                            fn(P, N) -> signed distance (m)
                 Union(a, b, ..), Inter(a, b, ..), Minus(a, b)
  Features     what a shape does to the maps:
                 Groove     engraved line along the shape's edge (normal map + optional slight albedo darkening),
                            optional fastener rows (rivets=Rivets(...))
                 Fill       colour / smoothness / metallic inside the shape (soft edge)
                 Relief     raised (+) or recessed (-) plateau with a bevel (mechanism detail)
                 Dots       lattice of dots inside the shape (perforations, dispenser cartridges)
                 Decal      PIL-drawn stencil projected onto the skin
                 Tone       per-panel tone / smoothness variation from a cell-id function
  Every feature takes parts= (glob or list of globs on part names), where=fn(P, N)->bool (hard mask, e.g. upper
  surface only) and box=dict(d=(lo, hi), ax=(lo, hi), x=..., z=...) to limit the texels it looks at.
"""
import fnmatch, math, zlib
import numpy as np

# ------------------------------------------------------------------ fields
class F:
    """Scalar field of position. Axis fields have analytic gradients and give automatic bounding boxes."""
    AX = {'d': np.array([0, -1, 0], np.float32), 'x': np.array([1, 0, 0], np.float32), 'z': np.array([0, 0, 1], np.float32)}

    def __init__(self, f, name=None):
        if isinstance(f, str):
            self.axis = f; self.fn = None; self.name = f
        else:
            self.axis = None; self.fn = f; self.name = name or getattr(f, '__name__', 'field')

    def __call__(self, P):
        a = self.axis
        if a == 'd': return 17.0 - P[:, 1]
        if a == 'x': return P[:, 0]
        if a == 'ax': return np.abs(P[:, 0])
        if a == 'z': return P[:, 2]
        return self.fn(P)

    def grad(self, P, h=0.004):
        a = self.axis
        if a in self.AX: return np.broadcast_to(self.AX[a], P.shape)
        if a == 'ax':
            g = np.zeros_like(P); g[:, 0] = np.where(P[:, 0] >= 0, 1.0, -1.0); return g
        g = np.empty_like(P)
        for i in range(3):
            dp = np.zeros(3, np.float32); dp[i] = h
            g[:, i] = (self.fn(P + dp) - self.fn(P - dp)) / (2 * h)
        return g

    def tgrad(self, P, N):
        """|gradient projected into the surface tangent plane| (field units per metre along the skin)."""
        g = self.grad(P)
        gt = g - N * np.sum(g * N, 1, keepdims=True)
        return np.maximum(np.linalg.norm(gt, axis=1), 0.05 * np.linalg.norm(g, axis=1) + 1e-6)


def as_field(f):
    return f if isinstance(f, F) else F(f)

# ------------------------------------------------------------------ shapes
class Shape:
    closed = True
    def box(self): return {}
    def sdf(self, P, N): raise NotImplementedError
    def along(self, P, N):
        """Metric coordinate along the shape's edge (used to space fasteners)."""
        return np.zeros(len(P), np.float32)


class Line(Shape):
    """Open curve where field == value; lim = [(field, lo, hi), ...] trims it (rounded ends).
    along = field used to space fasteners along the line (default: the first lim field, or d)."""
    closed = False
    def __init__(self, field, value, lim=(), along=None):
        self.f = as_field(field); self.v = value
        self.lim = [(as_field(a), lo, hi) for a, lo, hi in lim]
        self.al = as_field(along) if along is not None else (self.lim[0][0] if self.lim else F('d'))

    def box(self):
        b = {}
        if self.f.axis: b[self.f.axis] = (self.v, self.v)
        for f, lo, hi in self.lim:
            if f.axis:
                o = b.get(f.axis, (-1e9, 1e9)); b[f.axis] = (max(o[0], lo), min(o[1], hi))
        return b

    def signed(self, P, N):
        return (self.f(P) - self.v) / self.f.tgrad(P, N)

    def sdf(self, P, N):
        s = np.abs(self.signed(P, N))
        o2 = 0
        for f, lo, hi in self.lim:
            g = f(P); o = np.maximum(np.maximum(lo - g, g - hi), 0) / f.tgrad(P, N)
            o2 = o2 + o * o
        return np.sqrt(s * s + o2)

    def along(self, P, N):
        return self.al(P)


class Box(Shape):
    """Rounded rectangle u0..u1 x v0..v1 in two fields; r = corner radius (m)."""
    def __init__(self, u, v, ur, vr, r=0.03):
        self.u = as_field(u); self.v = as_field(v); self.ur = ur; self.vr = vr; self.r = r

    def box(self):
        b = {}
        if self.u.axis: b[self.u.axis] = self.ur
        if self.v.axis: b[self.v.axis] = self.vr
        return b

    def _q(self, P, N):
        u, v = self.u(P), self.v(P)
        uc, hu = (self.ur[0] + self.ur[1]) / 2, (self.ur[1] - self.ur[0]) / 2
        vc, hv = (self.vr[0] + self.vr[1]) / 2, (self.vr[1] - self.vr[0]) / 2
        gu, gv = self.u.tgrad(P, N), self.v.tgrad(P, N)
        return (np.abs(u - uc) - hu) / gu, (np.abs(v - vc) - hv) / gv, (u - uc) / gu, (v - vc) / gv

    def sdf(self, P, N):
        qu, qv, _, _ = self._q(P, N)
        r = self.r
        a, b = qu + r, qv + r
        return np.sqrt(np.maximum(a, 0) ** 2 + np.maximum(b, 0) ** 2) + np.minimum(np.maximum(a, b), 0) - r

    def along(self, P, N):
        qu, qv, su, sv = self._q(P, N)
        return np.where(qv > qu, su, sv + 1000.0)     # offset keeps the two edge families from sharing a phase


class Disc(Shape):
    """Circle: sphere of radius r about centre (d, x, z) cut through the skin. axis = rough surface normal there."""
    def __init__(self, c, r, axis=(0, 0, 1)):
        d, x, z = c
        self.C = np.array([x, 17.0 - d, z], np.float32); self.r = r
        a = np.array(axis, np.float32); a /= np.linalg.norm(a)
        t = np.cross(a, [0, 1, 0] if abs(a[1]) < 0.9 else [1, 0, 0]); t /= np.linalg.norm(t)
        self.e1, self.e2 = t.astype(np.float32), np.cross(a, t).astype(np.float32)
        self.c = c

    def box(self):
        d, x, z = self.c; r = self.r
        return {'d': (d - r, d + r), 'x': (x - r, x + r), 'z': (z - r, z + r)}

    def sdf(self, P, N):
        return np.linalg.norm(P - self.C, axis=1) - self.r

    def along(self, P, N):
        q = P - self.C
        return np.arctan2(q @ self.e2, q @ self.e1) * self.r


class Custom(Shape):
    def __init__(self, fn, along=None, box=None, closed=True):
        self.fn = fn; self.al = along; self.b = box or {}; self.closed = closed
    def box(self): return dict(self.b)
    def sdf(self, P, N): return self.fn(P, N)
    def along(self, P, N): return self.al(P, N) if self.al else np.zeros(len(P), np.float32)


class Union(Shape):
    def __init__(self, *s): self.s = s
    def box(self):
        bs = [x.box() for x in self.s]; out = {}
        for k in set.intersection(*[set(b) for b in bs]) if bs else ():
            out[k] = (min(b[k][0] for b in bs), max(b[k][1] for b in bs))
        return out
    def sdf(self, P, N): return np.min([x.sdf(P, N) for x in self.s], axis=0)


class Inter(Shape):
    def __init__(self, *s): self.s = s
    def box(self):
        out = {}
        for b in (x.box() for x in self.s):
            for k, (lo, hi) in b.items():
                o = out.get(k, (-1e9, 1e9)); out[k] = (max(o[0], lo), min(o[1], hi))
        return out
    def sdf(self, P, N): return np.max([x.sdf(P, N) for x in self.s], axis=0)


class Minus(Shape):
    def __init__(self, a, b): self.a, self.b = a, b
    def box(self): return self.a.box()
    def sdf(self, P, N): return np.maximum(self.a.sdf(P, N), -self.b.sdf(P, N))

# ------------------------------------------------------------------ profiles
DARK_GAIN = 1.6        # 0.4.0 raised to 2.1 (too faint at game distance); 0.4.7 back to 1.6 (too strong at the sharper 2k maps)
LINE_SM_GAIN = float(__import__("os").environ.get("PB22_LINE_SM_GAIN", "4.5"))     # 0.4.0: lines go matte (grime) so they also read in reflections, not only in albedo
RIVET_SM = -0.09       # 0.4.0: rivet dimples hold dirt: duller than the paint around them
_LIV = __import__("os").environ.get("PB22_LIVERY", "grey")
# 0.4.0 seam grime per skin: the default grey is the cleanest, Low-Level is dirtier, Maritime shows rust
GRIME_HALO = {'grey': 0.05, 'lowlevel': 0.11, 'maritime': 0.08}.get(_LIV, 0.07)   # albedo darkening either side of a seam (x depth)
GRIME_W = {'grey': 1.25, 'lowlevel': 1.7, 'maritime': 1.6}.get(_LIV, 1.25)        # halo half-width / line half-width
RUST = np.array((0.42, 0.22, 0.11), np.float32) if _LIV == 'maritime' else None    # seam rust tint (sRGB 0-1)
RIVET_MT = 0.12        # 0.4.0: and a hint of bare fastener metal so they catch the light

def groove_prof(t):
    """Engraved-line cross-section, t = distance / half width; 1 at the centre, 0 for |t| >= 1."""
    t = np.minimum(np.abs(t), 1.0)
    return (1 - t * t) ** 2

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)

def hash01(*ints):
    """Deterministic pseudo-random value in [0, 1) per integer tuple (vectorised)."""
    h = np.uint64(1469598103934665603)
    out = np.full(np.broadcast(*ints).shape if len(ints) > 1 else np.shape(ints[0]), h, np.uint64)
    for a in ints:
        a = np.asarray(a).astype(np.int64).astype(np.uint64)
        out = (out ^ (a + np.uint64(0x9E3779B97F4A7C15))) * np.uint64(1099511628211)
        out ^= out >> np.uint64(29)
    return (out % np.uint64(1 << 24)).astype(np.float64) / float(1 << 24)

# ------------------------------------------------------------------ features
class Feature:
    kind = 'paint'
    def __init__(self, shape, parts='*', where=None, box=None, margin=0.05):
        self.shape = shape; self.parts = [parts] if isinstance(parts, str) else list(parts)
        self.where = where; self.margin = margin
        b = shape.box() if shape is not None else {}
        if box: b.update(box)
        self.bbox = b

    def match(self, name):
        return any(fnmatch.fnmatchcase(name, p) for p in self.parts)


class Rivets:
    """Fastener dimples along a shape edge: rows at the given signed offsets (m; negative = inside a closed shape),
    pitch (m) along the edge, dot radius r (m), depth relative to a major groove (1.0)."""
    def __init__(self, pitch=0.075, offsets=(0.03,), r=0.011, depth=0.55, dark=0.035):
        self.pitch, self.offsets, self.r, self.depth, self.dark = pitch, tuple(offsets), r, depth, dark


class Groove(Feature):
    """Engraved line along the edge of a shape. width (m, full), depth (1.0 = major panel break),
    dark = albedo darkening at the line centre (0.06 = 6 %), rivets = Rivets(...) or None,
    smooth = smoothness change in the line (grime collects there)."""
    kind = 'height'
    def __init__(self, shape, parts='*', width=0.03, depth=1.0, dark=0.0, rivets=None, where=None, box=None, smooth=-0.03,
                 bias=0.0):
        m = width * 1.7 + (max(abs(o) for o in rivets.offsets) + rivets.r if rivets else 0) + 0.02
        super().__init__(shape, parts, where, box, m)
        self.w, self.depth, self.dark, self.rivets, self.smooth, self.bias = width, depth, dark, rivets, smooth, bias

    def height(self, P, N):
        sd = self.shape.sdf(P, N)
        h = -self.depth * groove_prof((sd - self.bias) / (self.w / 2))
        if self.rivets is not None:
            h = np.minimum(h, self.rivet_h(P, N, sd))
        return h

    def rivet_h(self, P, N, sd, ret_mask=False):
        R = self.rivets
        if not self.shape.closed:
            sd = self.shape.signed(P, N) if hasattr(self.shape, 'signed') else sd
            if getattr(self.shape, 'lim', None):     # keep rivets inside the trimmed line
                inside = self.shape.sdf(P, N) - np.abs(sd) < 1e-3
            else:
                inside = np.ones(len(P), bool)
        else:
            inside = np.ones(len(P), bool)
        a = self.shape.along(P, N)
        ph = a / R.pitch
        da = (ph - np.floor(ph) - 0.5) * R.pitch
        h = np.zeros(len(P), np.float32)
        for o in R.offsets:
            r = np.sqrt((sd - o) ** 2 + da ** 2)
            h = np.minimum(h, -R.depth * groove_prof(r / R.r) * inside)
        return h

    def paint(self, P, N, L, I):
        sd = self.shape.sdf(P, N)
        g = groove_prof((sd - self.bias) / (self.w / 2))
        if self.dark:
            L.col[I] *= (1 - np.minimum(self.dark * DARK_GAIN, 0.6) * g)[:, None]
        if self.smooth:
            L.sm[I] += self.smooth * LINE_SM_GAIN * g
        if GRIME_HALO and self.depth > 0:
            h = groove_prof((sd - self.bias) / (self.w * GRIME_W))
            L.col[I] *= (1 - GRIME_HALO * min(self.depth, 1.0) * h)[:, None]
            if RUST is not None:
                a = (0.24 * min(self.depth, 1.0) * h)[:, None]
                L.col[I] = L.col[I] * (1 - a) + RUST * a
            L.sm[I] -= 0.04 * min(self.depth, 1.0) * h
        if self.rivets is not None:
            rh = self.rivet_h(P, N, sd) / max(self.rivets.depth, 1e-6)     # 0 .. -1 at the rivet centre
            if self.rivets.dark:
                L.col[I] *= (1 + self.rivets.dark * rh)[:, None]
            L.sm[I] += RIVET_SM * -rh
            L.mt[I] = np.maximum(L.mt[I], RIVET_MT * -rh)


class Fill(Feature):
    """Colour (sRGB 0-255 tuple) / smoothness / metallic inside a shape. alpha = opacity, soft = edge width (m),
    sm = smoothness to set (None = keep) or sm_add = add, mt = metallic, mul = albedo multiplier instead of colour,
    noise = (scale m, amount) mottling, grad = fn(P)->0..1 that scales alpha."""
    def __init__(self, shape, parts='*', col=None, alpha=1.0, soft=0.01, sm=None, sm_add=0.0, mt=None, mul=None,
                 where=None, box=None, grad=None, ao=None, tag=None):
        super().__init__(shape, parts, where, box, soft + 0.02)
        self.col = None if col is None else np.array(col, np.float32) / 255.0
        self.alpha, self.soft, self.sm, self.sm_add, self.mt, self.mul, self.grad, self.tag = alpha, soft, sm, sm_add, mt, mul, grad, tag

    def mask(self, P, N):
        sd = self.shape.sdf(P, N)
        a = (1 - smoothstep(-self.soft / 2, self.soft / 2, sd)) * self.alpha
        if self.grad is not None: a = a * self.grad(P)
        return a

    def paint(self, P, N, L, I):
        a = self.mask(P, N)
        if self.col is not None:
            L.col[I] = L.col[I] * (1 - a[:, None]) + self.col * a[:, None]
        if self.mul is not None:
            L.col[I] *= (1 - a * (1 - self.mul))[:, None]
        if self.sm is not None:
            L.sm[I] = L.sm[I] * (1 - a) + self.sm * a
        if self.sm_add:
            L.sm[I] += self.sm_add * a
        if self.mt is not None:
            L.mt[I] = L.mt[I] * (1 - a) + self.mt * a
        if self.tag is not None:
            L.tag(self.tag, I, a)


class Relief(Feature):
    """Raised (height > 0) or recessed (height < 0) plateau inside a shape with a bevel (m). Height is relative to a
    major groove depth (1.0). col / mul optionally tint it."""
    kind = 'height'
    def __init__(self, shape, parts='*', height=0.6, bevel=0.012, where=None, box=None, col=None, mul=None, edge_dark=0.0):
        super().__init__(shape, parts, where, box, bevel + 0.02)
        self.hgt, self.bevel = height, bevel
        self.col = None if col is None else np.array(col, np.float32) / 255.0
        self.mul, self.edge_dark = mul, edge_dark

    def height(self, P, N):
        sd = self.shape.sdf(P, N)
        return self.hgt * (1 - smoothstep(-self.bevel, 0, sd))

    def paint(self, P, N, L, I):
        sd = self.shape.sdf(P, N)
        a = 1 - smoothstep(-self.bevel * 0.5, 0.0, sd)
        if self.col is not None:
            L.col[I] = L.col[I] * (1 - a[:, None]) + self.col * a[:, None]
        if self.mul is not None:
            L.col[I] *= (1 - a * (1 - self.mul))[:, None]
        if self.edge_dark:
            e = groove_prof(sd / (self.bevel * 1.5))
            L.col[I] *= (1 - self.edge_dark * e)[:, None]


class Dots(Feature):
    """Lattice of round dots (holes or cartridges) inside a shape, laid out in two metric fields u, v.
    pitch = (pu, pv) m, r = dot radius, depth (negative height, 1 = major groove), col = dot colour, stagger rows."""
    kind = 'height'
    def __init__(self, shape, u, v, pitch=(0.08, 0.08), r=0.02, depth=0.8, col=None, parts='*', where=None, box=None,
                 stagger=True, square=False, inset=0.02):
        super().__init__(shape, parts, where, box, 0.02)
        self.u, self.v = as_field(u), as_field(v)
        self.pitch, self.r, self.depth, self.stagger, self.square, self.inset = pitch, r, depth, stagger, square, inset
        self.col = None if col is None else np.array(col, np.float32) / 255.0

    def _r(self, P, N):
        pu, pv = self.pitch
        u = self.u(P) / self.u.tgrad(P, N); v = self.v(P) / self.v.tgrad(P, N)
        jv = np.floor(v / pv)
        u2 = u + (0.5 * pu * (jv % 2) if self.stagger else 0)
        du = (u2 / pu - np.floor(u2 / pu) - 0.5) * pu
        dv = (v / pv - jv - 0.5) * pv
        if self.square:
            r = np.maximum(np.abs(du), np.abs(dv) * (self.pitch[0] / self.pitch[1]))
        else:
            r = np.sqrt(du * du + dv * dv)
        inside = self.shape.sdf(P, N) < -self.inset
        return r, inside

    def height(self, P, N):
        r, inside = self._r(P, N)
        return -self.depth * smoothstep(self.r + 0.006, self.r - 0.006, r) * inside

    def paint(self, P, N, L, I):
        if self.col is None: return
        r, inside = self._r(P, N)
        a = smoothstep(self.r + 0.006, self.r - 0.006, r) * inside
        L.col[I] = L.col[I] * (1 - a[:, None]) + self.col * a[:, None]


class Decal(Feature):
    """A small PIL-drawn image (RGBA, straight alpha) projected onto the skin.
    centre (d, x, z); right, up = world 3D unit vectors of the image axes; size = (width, height) m;
    facing = world direction the decal faces (texels whose normal points away are skipped); tol = max distance
    from the decal plane (m). img = PIL.Image RGBA (colours are used as drawn). opacity scales alpha."""
    def __init__(self, img, centre, right, up, size, parts='*', facing=None, tol=0.35, opacity=1.0, box=None):
        d, x, z = centre
        self.C = np.array([x, 17.0 - d, z], np.float32)
        self.R = np.array(right, np.float32); self.U = np.array(up, np.float32)
        self.Fc = np.array(facing if facing is not None else np.cross(right, up), np.float32)
        self.size, self.tol, self.op = size, tol, opacity
        self.img = np.asarray(img.convert('RGBA'), np.float32) / 255.0
        w, h = size
        ext = max(w, h) / 2 + 0.02
        b = {'d': (d - ext, d + ext), 'x': (x - ext - tol, x + ext + tol), 'z': (z - ext - tol, z + ext + tol)}
        if box: b.update(box)
        super().__init__(None, parts, None, b, 0.02)

    def paint(self, P, N, L, I):
        q = P - self.C
        w, h = self.size
        u = q @ self.R / w + 0.5; v = 0.5 - q @ self.U / h
        dist = np.abs(q @ self.Fc)
        ok = (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1) & (dist < self.tol) & (N @ self.Fc > 0.35)
        if not ok.any(): return
        H, W = self.img.shape[:2]
        fx = np.clip(u[ok] * W - 0.5, 0, W - 1.001); fy = np.clip(v[ok] * H - 0.5, 0, H - 1.001)
        x0 = fx.astype(int); y0 = fy.astype(int); tx = (fx - x0)[:, None]; ty = (fy - y0)[:, None]
        im = self.img
        c = (im[y0, x0] * (1 - tx) * (1 - ty) + im[y0, x0 + 1] * tx * (1 - ty) +
             im[y0 + 1, x0] * (1 - tx) * ty + im[y0 + 1, x0 + 1] * tx * ty)
        a = c[:, 3:4] * self.op
        J = I[ok]
        L.col[J] = L.col[J] * (1 - a) + c[:, :3] * a
        L.sm[J] += -0.04 * a[:, 0]          # paint is a touch flatter


class Tone(Feature):
    """Per-panel tone variation: cell = fn(P, N) -> integer id per texel (texels with the same id are one panel).
    amp = albedo luminance +- (0.025 = 2.5 %), sm_amp = smoothness +-, seed separates zones."""
    def __init__(self, cell, parts='*', amp=0.025, sm_amp=0.03, seed=0, where=None, box=None):
        super().__init__(None, parts, where, box, 0.0)
        self.cell, self.amp, self.sm_amp, self.seed = cell, amp, sm_amp, seed

    def paint(self, P, N, L, I):
        c = self.cell(P, N)
        r1 = hash01(c, np.full_like(c, self.seed), np.full_like(c, 7)) * 2 - 1
        r2 = hash01(c, np.full_like(c, self.seed), np.full_like(c, 13)) * 2 - 1
        L.col[I] *= (1 + self.amp * r1)[:, None]
        L.sm[I] += self.sm_amp * r2

# ------------------------------------------------------------------ data-driven helpers (built from the raster)
class Planform:
    """Leading / trailing edge of a lifting surface measured from the geometry itself: for parts matching `parts`,
    per bin of the span field the min / max of the chord field. frac(P) = 0 at the LE, 1 at the TE."""
    REG = []
    def __init__(self, parts, span='ax', chord='d', step=0.05, where=None):
        self.parts = [parts] if isinstance(parts, str) else list(parts)
        self.span, self.chord = F(span), F(chord); self.step = step; self.where = where
        self.ok = False; Planform.REG.append(self)

    def build(self, model):
        I = model.select(self.parts)
        if len(I) == 0: self.ok = False; return
        P = model.P[I]
        s = self.span(P); c = self.chord(P)
        lo, hi = s.min(), s.max()
        nb = max(int((hi - lo) / self.step) + 1, 2)
        b = np.clip(((s - lo) / self.step).astype(int), 0, nb - 1)
        le = np.full(nb, np.inf); te = np.full(nb, -np.inf)
        np.minimum.at(le, b, c); np.maximum.at(te, b, c)
        good = np.isfinite(le) & np.isfinite(te)
        xs = lo + (np.arange(nb) + 0.5) * self.step
        self.xs, self.le, self.te = xs[good], le[good], te[good]
        self.lo, self.hi = lo, hi; self.ok = True

    def frac(self, P):
        s = self.span(P); c = self.chord(P)
        le = np.interp(s, self.xs, self.le); te = np.interp(s, self.xs, self.te)
        return (c - le) / np.maximum(te - le, 1e-3)

    def chord_len(self, P):
        s = self.span(P)
        return np.interp(s, self.xs, self.te) - np.interp(s, self.xs, self.le)

    def field(self):
        return F(self.frac, 'frac')


class Centreline:
    """Body centre height zc(d) and half width per d bin, measured as the z where the body is widest."""
    REG = []
    def __init__(self, parts, step=0.1):
        self.parts = [parts] if isinstance(parts, str) else list(parts); self.step = step; self.ok = False
        Centreline.REG.append(self)

    def build(self, model):
        I = model.select(self.parts)
        P = model.P[I]
        d = 17.0 - P[:, 1]; ax = np.abs(P[:, 0]); z = P[:, 2]
        lo, hi = d.min(), d.max(); nb = int((hi - lo) / self.step) + 1
        b = np.clip(((d - lo) / self.step).astype(int), 0, nb - 1)
        wmax = np.zeros(nb); np.maximum.at(wmax, b, ax)
        sel = ax > wmax[b] * 0.97
        zs = np.zeros(nb); cnt = np.zeros(nb)
        np.add.at(zs, b[sel], z[sel]); np.add.at(cnt, b[sel], 1)
        good = cnt > 0
        self.ds = (lo + (np.arange(nb) + 0.5) * self.step)[good]
        zc = zs[good] / cnt[good]
        k = np.ones(5) / 5
        self.zc = np.convolve(np.pad(zc, 2, mode='edge'), k, 'valid')
        self.hw = wmax[good]; self.ok = True

    def z(self, d): return np.interp(d, self.ds, self.zc)
    def halfwidth(self, d): return np.interp(d, self.ds, self.hw)


class Surround(Feature):
    """Engraved gap / seal line round inserts made of another material or part (glazing, mech doors, hatches):
    the insert outline is taken from the geometry (boundary edges of its triangles), so it follows the model.
    src_fam = atlas family in the geometry dump ('PB22_glass', 'PB22_skin', ...), src_mat = material name of the
    insert triangles (None = any), src_parts = part globs of the insert. The groove runs on `parts` at distance
    `offset` (m) from the outline; rivets = (pitch, distance) adds a fastener ring at that distance."""
    kind = 'height'
    def __init__(self, src_fam, src_mat=None, src_parts='*', parts='*', width=0.024, depth=0.8, offset=0.008, dark=0.05,
                 rivet_ring=None, where=None, smooth=-0.03, max_dist=0.12, band=0.0, band_mul=1.0, band_sm=0.0, band_h=0.0):
        super().__init__(None, parts, where, None, 0.0)
        self.band, self.band_mul, self.band_sm, self.band_h = band, band_mul, band_sm, band_h
        self.src = (src_fam, src_mat, [src_parts] if isinstance(src_parts, str) else list(src_parts))
        self.w, self.depth, self.off, self.dark, self.ring, self.smooth, self.maxd = width, depth, offset, dark, rivet_ring, smooth, max_dist
        self.tree = None

    def prepare(self, M):
        from scipy.spatial import cKDTree
        fam, mat, sp = self.src
        g = M.geom
        if g is None or fam + '_p' not in g: return
        P = g[fam + '_p']; pid = g[fam + '_pid']; names = [str(n) for n in g['names']]
        keep = np.array([any(fnmatch.fnmatchcase(names[i], p) for p in sp) for i in range(len(names))])
        m = keep[pid]
        if mat is not None and fam + '_mat' in g:
            mats = [str(s) for s in g['mats']]
            if mat not in mats: return
            m &= g[fam + '_mat'] == mats.index(mat)
        T = P[m]
        if len(T) == 0: return
        # sample the insert's surface on a ~4 mm barycentric grid (works for open plates and closed slabs alike)
        Lmax = np.max(np.linalg.norm(T - np.roll(T, 1, axis=1), axis=2), axis=1)
        nn = np.clip(np.ceil(Lmax / 0.004).astype(int), 1, 200)
        chunks = []
        for n in np.unique(nn):
            tri = T[nn == n]
            i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
            ok = i + j <= n
            u = (i[ok] / n).astype(np.float32); v = (j[ok] / n).astype(np.float32)
            pts_ = tri[:, None, 0] + (tri[:, None, 1] - tri[:, None, 0]) * u[None, :, None] + (tri[:, None, 2] - tri[:, None, 0]) * v[None, :, None]
            chunks.append(pts_.reshape(-1, 3))
        pts = np.unique(np.round(np.concatenate(chunks) / 0.001).astype(np.int64), axis=0).astype(np.float32) * 0.001
        self.tree = cKDTree(pts)
        lo, hi = pts.min(0), pts.max(0); r = self.maxd
        self.bbox = {'x': (lo[0] - r, hi[0] + r), 'd': (17 - hi[1] - r, 17 - lo[1] + r), 'z': (lo[2] - r, hi[2] + r)}
        self.pts = pts

    def dist(self, P):
        if self.tree is None: return np.full(len(P), 1e3, np.float32)
        dd, _ = self.tree.query(P, k=1, distance_upper_bound=self.maxd + 0.05)
        return np.minimum(dd, 1e3).astype(np.float32)

    def height(self, P, N):
        dd = self.dist(P)
        h = -self.depth * groove_prof((dd - self.off) / (self.w / 2))
        if self.band_h:
            h = h + self.band_h * self.band_mask(dd)
        return h

    def band_mask(self, dd):
        # flat frame / sealant band from the insert outline out to `band` (m), soft 4 mm edge
        return 1 - smoothstep(self.band - 0.004, self.band + 0.004, dd)

    def paint(self, P, N, L, I):
        if self.tree is None: return
        dd = self.dist(P)
        g = groove_prof((dd - self.off) / (self.w / 2))
        L.col[I] *= (1 - self.dark * g)[:, None]
        L.sm[I] += self.smooth * g
        if self.band:
            a = self.band_mask(dd)
            L.col[I] *= (1 - a * (1 - self.band_mul))[:, None]
            L.sm[I] += self.band_sm * a
