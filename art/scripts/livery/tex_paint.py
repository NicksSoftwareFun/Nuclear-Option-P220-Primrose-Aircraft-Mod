"""PB-22 skin painter: evaluates the feature spec (default pb22_panels.py) on the texel maps from tex_raster_tb.py
and writes the skin textures.
Usage: python3 tex_paint.py <maps.npz> <outdir> [spec_module] [--geom=<geom.npz>]
Writes  PB22_skin_b.png    base colour = default livery (sRGB)
        PB22_skin_n.png    tangent-space normal map, OpenGL / Unity convention (+Y = +V)
        PB22_skin_m.png    RGB metallic, A smoothness
        PB22_skin_dmg_b.png  burnt / bare-metal damage colour with alpha
        PB22_skin_dmg_n.png  damage normal map
        PB22_skin_height.png (16-bit engraving height, for checking only)
AO comes from tex_bake_ao.py (Blender).
PB22_DECALS=1 leaves out every Decal feature (stencils then live on the decal meshes, see tex_decals.py).
Quick mode (tex_quick.sh): PB22_PATCH_MASK=<mask.npy> PB22_PATCH_FROM=<old outdir> paints the features only on the
masked texels and writes the old images with just those texels (and their gutters) replaced."""
import sys, os, time, importlib, fnmatch
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tex_feat as TF


class Model:
    def __init__(self, maps, geom=None):
        m = np.load(maps)
        self.geom = np.load(geom) if geom else None
        self.mats = [str(s) for s in m['mats']] if 'mats' in m else ['PB22_skin']
        self.S = m['pos'].shape[0]
        cov = m['cov'].ravel()
        self.C = np.flatnonzero(cov)
        self.P = m['pos'].reshape(-1, 3)[self.C].astype(np.float32)
        self.N = m['nrm'].reshape(-1, 3)[self.C].astype(np.float32)
        T = m['tan'].reshape(-1, 3)[self.C].astype(np.float32)
        bs = m['bsg'].ravel()[self.C].astype(np.float32)
        self.T = T
        self.B = (np.cross(self.N, T) * bs[:, None]).astype(np.float32)
        self.pid = m['pid'].ravel()[self.C]
        self.mat = m['mat'].ravel()[self.C] if 'mat' in m else np.zeros(len(self.C), np.int16)
        self.names = [str(n) for n in m['names']]
        self.idx = m['idx'].ravel()
        self.ppm = float(m['ppm'])
        self.inv = np.full(self.S * self.S, -1, np.int64); self.inv[self.C] = np.arange(len(self.C))
        # per part: texel indices sorted by d for fast range queries
        self.parts = {}
        order = np.argsort(self.pid, kind='stable')
        bounds = np.searchsorted(self.pid[order], np.arange(len(self.names) + 1))
        for i, n in enumerate(self.names):
            I = order[bounds[i]:bounds[i + 1]]
            if len(I) == 0: continue
            d = 17.0 - self.P[I, 1]
            o = np.argsort(d)
            self.parts[n] = (I[o], d[o])
        print('texels', len(self.C), 'parts', len(self.parts), 'texels/m %.1f' % self.ppm)

    def select(self, parts, box=None, margin=0.0):
        out = []
        for n, (I, d) in self.parts.items():
            if not any(fnmatch.fnmatchcase(n, p) for p in parts): continue
            if box and 'd' in box:
                lo, hi = box['d']
                a, b = np.searchsorted(d, lo - margin), np.searchsorted(d, hi + margin, 'right')
                J = I[a:b]
            else:
                J = I
            if box and len(J):
                P = self.P[J]; m = np.ones(len(J), bool)
                for k, (lo, hi) in box.items():
                    if k == 'd': continue
                    v = {'x': P[:, 0], 'ax': np.abs(P[:, 0]), 'z': P[:, 2]}[k]
                    m &= (v >= lo - margin) & (v <= hi + margin)
                J = J[m]
            out.append(J)
        return np.concatenate(out) if out else np.zeros(0, np.int64)

    def coarse(self, fn, factor=4):
        """Evaluate fn(P) on every factor-th texel of the gutter-filled position image and bilinearly upsample:
        cheap for low-frequency noise. Returns (values on covered texels, full-resolution image)."""
        from scipy import ndimage
        if not hasattr(self, '_posfull'):
            self._posfull = self.P[self.inv[self.idx]].reshape(self.S, self.S, 3)
        o = factor // 2
        Pc = self._posfull[o::factor, o::factor].reshape(-1, 3)
        v = fn(Pc).reshape(self.S // factor, self.S // factor).astype(np.float32)
        full = ndimage.zoom(v, factor, order=1, mode='nearest', grid_mode=True)
        return full.ravel()[self.C], full

    def to_image(self, arr):
        """Covered-texel array -> full S x S image, gutters filled from the nearest covered texel."""
        full = arr[self.inv[self.idx]]
        return full.reshape((self.S, self.S) + arr.shape[1:])


class Layers:
    def __init__(self, n, base, sm):
        self.col = np.tile(np.array(base, np.float32) / 255.0, (n, 1))
        self.sm = np.full(n, sm, np.float32)
        self.mt = np.zeros(n, np.float32)
        self.hneg = np.zeros((5, n), np.float32)
        self.hpos = np.zeros((5, n), np.float32)
        self.tags = {}
        self.n = n

    def tag(self, name, I, a):
        t = self.tags.setdefault(name, np.zeros(self.n, np.float32))
        t[I] = np.maximum(t[I], a)


# ------------------------------------------------------------------ 3D value noise (continuous across UV seams)
_LAT = {}
def _lattice(seed, n=96):
    if seed not in _LAT:
        _LAT[seed] = np.random.default_rng(1000 + seed).random((n, n, n)).astype(np.float32)
    return _LAT[seed]


def vnoise(P, scale, seed=0, octaves=3):
    """Smooth 3D value noise in [-1, 1] on world position (a random lattice, trilinear + smoothstep)."""
    out = np.zeros(len(P), np.float32); amp = 1.0; tot = 0.0
    for o in range(octaves):
        lat = _lattice(seed * 7 + o); n = lat.shape[0]; flat = lat.ravel()
        q = P.astype(np.float32) * np.float32(2 ** o / scale) + np.float32(o * 3.7 + seed * 1.3)
        i = np.floor(q); f = q - i
        f = f * f * (3 - 2 * f)
        i = i.astype(np.int32) % n
        i1 = (i + 1) % n
        X = (i[:, 0] * n * n, i1[:, 0] * n * n); Y = (i[:, 1] * n, i1[:, 1] * n); Z = (i[:, 2], i1[:, 2])
        W = ((1 - f[:, 0], f[:, 0]), (1 - f[:, 1], f[:, 1]), (1 - f[:, 2], f[:, 2]))
        acc = np.zeros(len(P), np.float32)
        for dx in (0, 1):
            for dy in (0, 1):
                xy = X[dx] + Y[dy]; wxy = W[0][dx] * W[1][dy]
                acc += np.take(flat, xy + Z[0]) * (wxy * W[2][0]) + np.take(flat, xy + Z[1]) * (wxy * W[2][1])
        out += amp * (acc * 2 - 1); tot += amp; amp *= 0.5
    return out / tot


def run(maps, outdir, specname='pb22_panels', geom=None):
    t0 = time.time()
    spec = importlib.import_module(specname)
    M = Model(maps, geom)
    patch = os.environ.get('PB22_PATCH_MASK'), os.environ.get('PB22_PATCH_FROM')
    mk = np.load(patch[0]).ravel()[M.C] if patch[0] else None
    if mk is not None: print('patch: %d of %d texels' % (mk.sum(), len(mk)))
    noise = vnoise
    if mk is not None:                                # per-texel noise only where it is kept
        def noise(P, *a, **k):
            if len(P) != len(mk): return vnoise(P, *a, **k)
            r = np.zeros(len(P), np.float32); r[mk] = vnoise(P[mk], *a, **k); return r
    for pl in TF.Planform.REG + TF.Centreline.REG:
        pl.build(M)
    feats = spec.features(M)
    if os.environ.get('PB22_DECALS') == '1':           # stencils go on the decal meshes (tex_decals.py) instead
        feats = [f for f in feats if not isinstance(f, TF.Decal)]
    L = Layers(len(M.C), spec.BASE, spec.SMOOTH)
    if hasattr(spec, 'base_paint'):
        spec.vnoise_ref[0] = noise
        spec.base_paint(M, L)
    e = 0.5 / M.ppm                                   # half a texel: central-difference step for the normal map
    nfe = 0
    for f in feats:
        if hasattr(f, 'prepare'): f.prepare(M)
    times = []
    for k, f in enumerate(feats):
        tf = time.time()
        I = M.select(f.parts, f.bbox, f.margin)
        if mk is not None: I = I[mk[I]]
        if len(I) == 0: continue
        P, N = M.P[I], M.N[I]
        if f.where is not None:
            m = f.where(P, N); I, P, N = I[m], P[m], N[m]
            if len(I) == 0: continue
        nfe += 1
        if f.kind == 'height':
            T, B = M.T[I], M.B[I]
            P5 = np.concatenate([P, P + e * T, P - e * T, P + e * B, P - e * B])
            N5 = np.concatenate([N] * 5)
            h = f.height(P5, N5).reshape(5, -1).astype(np.float32)
            L.hneg[:, I] = np.minimum(L.hneg[:, I], np.minimum(h, 0))
            L.hpos[:, I] = np.maximum(L.hpos[:, I], np.maximum(h, 0))
        f.paint(P, N, L, I)
        times.append((time.time() - tf, len(I), k, type(f).__name__, getattr(f.shape, '__class__', type(None)).__name__, f.parts[:2]))
    if os.environ.get('TEX_PROFILE'):
        for t in sorted(times, key=lambda t: -t[0])[:15]: print('  %.2fs %8d #%d %s %s %s' % t)
    print('features', len(feats), 'applied', nfe, '%.1fs' % (time.time() - t0))
    spec.finish(M, L, noise)
    # ---------------------------------------------------------- normal map
    H = L.hneg + L.hpos
    k = spec.DEPTH_M
    dT = (H[1] - H[2]) / (2 * e) * k; dB = (H[3] - H[4]) / (2 * e) * k
    # cap the slope (about 30 deg): steep samples at small-island borders otherwise show as hard glints
    g = np.hypot(dT, dB); cap = np.where(g > 0.58, 0.58 / np.maximum(g, 1e-9), 1.0)
    dT = dT * cap; dB = dB * cap
    n = np.stack([-dT, -dB, np.ones_like(dT)], 1)
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    os.makedirs(outdir, exist_ok=True)
    keep = None
    if mk is not None:                                # texels (gutters included) whose source texel is not repainted
        keep = ~mk[M.inv[M.idx]].reshape(M.S, M.S)
    def patched(im, name):
        if keep is None: return im
        old = np.asarray(Image.open(os.path.join(patch[1], name)))
        if old.shape != im.shape: raise SystemExit('patch: %s shape %s vs %s' % (name, old.shape, im.shape))
        return np.where(keep.reshape(keep.shape + (1,) * (im.ndim - 2)), old, im).astype(im.dtype)
    def save(arr, name, mode):
        im = patched(M.to_image(arr), name)
        Image.fromarray(im, mode).save(os.path.join(outdir, name), optimize=False, compress_level=6)
        print('wrote', name)
    q8 = lambda a: np.clip(np.round(a * 255), 0, 255).astype(np.uint8)
    save(q8(n * 0.5 + 0.5), 'PB22_skin_n.png', 'RGB')
    save(q8(np.clip(L.col, 0, 1)), 'PB22_skin_b.png', 'RGB')
    sm = np.clip(L.sm, 0, 1); mt = np.clip(L.mt, 0, 1)
    save(q8(np.stack([mt, mt, mt, sm], 1)), 'PB22_skin_m.png', 'RGBA')
    hh = np.clip(H[0] * 0.25 + 0.5, 0, 1)
    Image.fromarray(patched((M.to_image(hh) * 65535).astype(np.uint16), 'PB22_skin_height.png')).save(os.path.join(outdir, 'PB22_skin_height.png'))
    # ---------------------------------------------------------- damage maps
    db, dn = spec.damage(M, L, noise, H, e)
    save(q8(db), 'PB22_skin_dmg_b.png', 'RGBA')
    save(q8(dn * 0.5 + 0.5), 'PB22_skin_dmg_n.png', 'RGB')
    # stats
    lum = L.col @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    print('albedo lum p5/50/95 %.3f %.3f %.3f' % tuple(np.percentile(lum, [5, 50, 95])),
          'smooth mean %.3f' % sm.mean(), 'normal z mean %.4f' % n[:, 2].mean(), 'total %.1fs' % (time.time() - t0))


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    geom = next((x.split('=', 1)[1] for x in sys.argv if x.startswith('--geom=')), None)
    run(a[0], a[1], a[2] if len(a) > 2 else 'pb22_panels', geom)
