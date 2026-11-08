"""P220 Primrose skin painter, livery 1 "P-LINK" (house colours: gloss olive fuselage, gloss white tail, wings, belly
fairing and nacelles, dark red detail lines). Evaluates everything on the texel maps from tex_raster_tb.py, in 3D, so
markings run across UV seams.
Usage: python3 p220_paint.py <maps.npz> <outdir>
Writes P220_skin_b.png (sRGB), P220_skin_n.png (OpenGL normal), P220_skin_m.png (RGB metallic, A smoothness),
P220_skin_height.png (16-bit, for the damage alpha), P220_skin_dmg_b.png (colour, alpha filled by tex_dmg_alpha.py),
P220_skin_dmg_n.png."""
import sys, os, math, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, '/mnt/project-files/tu22/art/scripts/tex')
from tex_paint import vnoise

NOSE_Y = 19.35
OLIVE = np.array([86, 92, 52], np.float32) / 255          # gloss olive drab
WHITE = np.array([236, 237, 234], np.float32) / 255       # gloss white
DRED = np.array([112, 22, 24], np.float32) / 255          # dark red detail lines
CHAR = np.array([40, 42, 44], np.float32) / 255           # dark charcoal lettering
YEL = np.array([244, 214, 92], np.float32) / 255          # primrose petals
YEL2 = np.array([226, 150, 40], np.float32) / 255         # primrose eye
SM_WHITE, SM_OLIVE = 0.80, 0.72                           # gloss paint smoothness
LIVERY = os.environ.get('P220_LIVERY', 'plink')          # plink (P-LINK Demonstrator) | civil | pala | blank (Livery Bundle base: plain white, no markings)
OFFW = np.array([238, 234, 226], np.float32) / 255        # civil: warm off-white
PINK = np.array([196, 146, 148], np.float32) / 255        # civil: dusty pink
PINK_D = np.array([150, 92, 98], np.float32) / 255        # civil: deeper rose for lines and stencils
AFGREY = np.array([118, 123, 127], np.float32) / 255      # pala: tanker grey (matte)
AFLINE = np.array([62, 66, 70], np.float32) / 255         # pala: panel line / stencil dark grey
STBLK = np.array([28, 29, 30], np.float32) / 255          # pala: black stencils
PRED = np.array([146, 4, 0], np.float32) / 255            # pala red (roundel ring)
RESC = np.array([232, 180, 30], np.float32) / 255         # rescue yellow
FONT_ST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logos', 'AllertaStencil-Regular.ttf')
LOGO_PALA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logos', 'pala_roundel_color_2048.png')
FONT_B = '/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf'
FONT_S = '/usr/share/fonts/opentype/inter/Inter-Bold.otf'

# fuselage section table (same as p220_parts.FUS: d, half width, top z, bottom z) with its pchip interpolation
FUS = [(0.00, 0.05, -0.62, -0.80), (0.35, 0.62, -0.05, -1.20), (0.90, 1.00, 0.45, -1.48), (2.00, 1.42, 1.05, -1.70),
       (3.20, 1.68, 1.55, -1.82), (4.40, 1.82, 1.84, -1.90), (6.00, 1.86, 1.91, -1.93), (27.5, 1.86, 1.91, -1.93),
       (30.0, 1.80, 1.91, -1.80), (32.5, 1.62, 1.86, -1.40), (34.8, 1.30, 1.74, -0.70), (36.8, 0.82, 1.50, -0.05),
       (38.1, 0.36, 1.31, 0.60), (38.28, 0.315, 1.272, 0.642)]
def pchip_np(tab, d):
    ds = np.array([t[0] for t in tab]); out = []
    for c in range(1, 4):
        v = np.array([t[c] for t in tab]); h = np.diff(ds); dl = np.diff(v) / h; n = len(ds)
        m = np.zeros(n); m[0], m[-1] = dl[0], dl[-1]
        for i in range(1, n - 1):
            m[i] = 0.0 if dl[i - 1] * dl[i] <= 0 else 3 * (h[i - 1] + h[i]) / ((2 * h[i] + h[i - 1]) / dl[i - 1] + (h[i] + 2 * h[i - 1]) / dl[i])
        dd = np.clip(d, ds[0], ds[-1]); i = np.clip(np.searchsorted(ds, dd) - 1, 0, n - 2)
        hh = h[i]; t = (dd - ds[i]) / hh
        h00 = 2 * t ** 3 - 3 * t ** 2 + 1; h10 = t ** 3 - 2 * t ** 2 + t; h01 = -2 * t ** 3 + 3 * t ** 2; h11 = t ** 3 - t ** 2
        out.append(h00 * v[i] + h10 * hh * m[i] + h01 * v[i + 1] + h11 * hh * m[i + 1])
    return out
def fus_rho(d, x, z, ex=2.2):
    hw, zt, zb = pchip_np(FUS, d)
    # 0.4.14: blunt paraboloid radome ahead of d 0.35, as in p220_parts.fus
    h1, t1, b1 = pchip_np(FUS, np.array([0.35])); zc1, hh1 = (t1[0] + b1[0]) / 2, (t1[0] - b1[0]) / 2
    tn = np.clip(np.asarray(d, np.float64) / 0.35, 0, 1); sq = np.sqrt(tn); zcn = -0.71 + (zc1 + 0.71) * tn; tip = np.asarray(d) < 0.35
    hw = np.where(tip, np.maximum(h1[0] * sq, 1e-3), hw); zt = np.where(tip, zcn + hh1 * sq, zt); zb = np.where(tip, zcn - hh1 * sq, zb)
    zc, hh = (zt + zb) / 2, np.maximum((zt - zb) / 2, 1e-3)
    return (np.abs(x) / hw) ** ex + (np.abs(z - zc) / hh) ** ex, zt

WING = [(0.0, 12.9, 8.6, 0.13), (1.86, 13.87, 6.46, 0.13), (6.1, 16.2, 4.13, 0.12), (17.2, 22.0, 1.65, 0.10), (17.45, 22.35, 1.30, 0.09)]
HT = [(0.0, 32.6, 4.2, 0.11), (0.95, 33.1, 3.6, 0.11), (6.16, 36.3, 1.42, 0.10)]
FIN = [(1.2, 30.0, 5.75, 0.10), (1.9, 30.55, 5.30, 0.10), (7.55, 36.1, 1.45, 0.10)]
def lerp_np(tab, s, col):
    xs = np.array([t[0] for t in tab]); v = np.array([t[col] for t in tab]); return np.interp(s, xs, v)

FUSE_PARTS = ('nose', 'cockpit_F', 'cockpit_R', 'fuselage_F', 'fuselage', 'fuselage_R', 'tail', 'fdoor_', 'baydoor_', 'geardoor_F')
DOOR_RECTS = [  # (d0, d1, z0, z1, sides, label)
    (4.65, 5.55, -0.55, 1.28, (-1, 1), 'door'), (29.8, 30.7, -0.55, 1.20, (-1, 1), 'door'),
    (15.30, 15.90, -0.14, 1.08, (-1, 1), 'exit'), (16.40, 17.00, -0.14, 1.08, (-1, 1), 'exit'),
    (7.6, 9.0, -1.72, -0.88, (1,), 'cargo'), (21.2, 24.6, -0.40, 1.30, (-1,), 'cargo')]


def text_mask(text, font=FONT_B, px=360, pad=0.06, outline=0):
    f = ImageFont.truetype(font, px)
    l, t, r, b = f.getbbox(text)
    W, H = r - l, b - t; P = int(pad * H) + outline
    im = Image.new('L', (W + 2 * P, H + 2 * P), 0)
    ImageDraw.Draw(im).text((P - l, P - t), text, font=f, fill=255, stroke_width=outline, stroke_fill=255)
    return np.asarray(im, np.float32) / 255.0


def flower_masks(px=1200):
    """Primrose emblem: five notched petals, a darker eye, a dark red outline (petal mask, eye mask, outline mask)."""
    S = px; c = S / 2
    def petals(scale):
        im = Image.new('L', (S, S), 0); d = ImageDraw.Draw(im)
        for k in range(5):
            a = math.radians(90 + 72 * k); r = 0.27 * S * scale
            cx, cy = c + 0.20 * S * scale * math.cos(a), c - 0.20 * S * scale * math.sin(a)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
            # heart-shaped notch at the petal tip
            nx, ny = c + 0.47 * S * scale * math.cos(a), c - 0.47 * S * scale * math.sin(a); nr = 0.06 * S * scale
            d.ellipse((nx - nr, ny - nr, nx + nr, ny + nr), fill=0)
        return np.asarray(im, np.float32) / 255
    outer = petals(0.98); inner = petals(0.90)
    yy, xx = np.mgrid[0:S, 0:S]; rr = np.hypot(xx - c, yy - c) / S
    eye = (rr < 0.085).astype(np.float32)
    ring = ((rr > 0.085) & (rr < 0.11)).astype(np.float32)
    return inner, eye, np.clip(outer - inner, 0, 1) + ring


def sample(mask, u, v):
    """Bilinear sample of mask at normalised (u right, v up) in [0,1]; 0 outside."""
    H, W = mask.shape
    x = u * (W - 1); y = (1 - v) * (H - 1)
    ok = (x >= 0) & (x <= W - 1) & (y >= 0) & (y <= H - 1)
    x = np.clip(x, 0, W - 1.001); y = np.clip(y, 0, H - 1.001)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int); fx = x - x0; fy = y - y0
    a = mask[y0, x0] * (1 - fx) + mask[y0, x0 + 1] * fx
    b = mask[y0 + 1, x0] * (1 - fx) + mask[y0 + 1, x0 + 1] * fx
    return np.where(ok, a * (1 - fy) + b * fy, 0.0)


class Painter:
    def __init__(self, maps):
        m = np.load(maps)
        self.S = m['pos'].shape[0]
        self.C = np.flatnonzero(m['cov'].ravel())
        self.P = m['pos'].reshape(-1, 3)[self.C].astype(np.float32)
        self.N = m['nrm'].reshape(-1, 3)[self.C].astype(np.float32)
        self.T = m['tan'].reshape(-1, 3)[self.C].astype(np.float32)
        bs = m['bsg'].ravel()[self.C].astype(np.float32)
        self.B = np.cross(self.N, self.T) * bs[:, None]
        self.pid = m['pid'].ravel()[self.C]
        self.names = [str(n) for n in m['names']]
        self.idx = m['idx'].ravel(); self.ppm = float(m['ppm'])
        self.inv = np.full(self.S * self.S, -1, np.int64); self.inv[self.C] = np.arange(len(self.C))
        n = len(self.C)
        self.d = NOSE_Y - self.P[:, 1]; self.x = self.P[:, 0]; self.z = self.P[:, 2]
        self.col = np.tile(WHITE, (n, 1)); self.sm = np.full(n, SM_WHITE, np.float32); self.mt = np.zeros(n, np.float32)
        self.paint_mask = np.zeros(n, np.float32)       # lettering / decal coverage (no panel grime on it)
        # texel footprint in metres (distance to the next texel along the row), for supersampled markings
        pos = m['pos']; cv = m['cov']
        dx = np.linalg.norm(pos[:, 1:] - pos[:, :-1], axis=-1); ok = cv[:, 1:] & cv[:, :-1] & (dx < 0.08)
        fp = np.full(pos.shape[:2], 1.0 / self.ppm, np.float32); fp[:, :-1][ok] = dx[ok]
        self.fp = np.clip(fp.ravel()[self.C], 0.004, 0.06)
        print('texels', n, 'texels/m %.1f' % self.ppm)

    def part(self, *prefixes):
        ok = np.array([n.startswith(prefixes) for n in self.names]); return ok[self.pid]

    def put(self, sel, a, rgb, sm=None):
        a = np.clip(a, 0, 1) * sel
        self.col = self.col * (1 - a[:, None]) + np.asarray(rgb, np.float32)[None] * a[:, None]
        if sm is not None: self.sm = self.sm * (1 - a) + sm * a
        self.paint_mask = np.maximum(self.paint_mask, a)

    # ---------------------------------------------------------------- side and top projections
    SS = [(-0.375 + 0.25 * i, -0.375 + 0.25 * j) for i in range(4) for j in range(4)]   # 4 x 4 supersampling
    def ss_points(self, sel):
        """Sub-texel sample positions (d, x, z arrays) for the selected texels, spread over each texel's footprint."""
        P, T, B, f = self.P[sel], self.T[sel], self.B[sel], self.fp[sel][:, None]
        for a, b in self.SS:
            Q = P + (a * T + b * B) * f
            yield NOSE_Y - Q[:, 1], Q[:, 0], Q[:, 2]

    def side_uv(self, side, dc, zc, w, h, ang=0.0, d=None, z=None):
        """Normalised coordinates in a w x h box centred at (dc, zc), seen from the given side (-1 port, +1 starboard),
        reading direction ang degrees counter-clockwise from the viewer's right."""
        d = self.d if d is None else d; z = self.z if z is None else z
        vx = d * (1 if side < 0 else -1); cx = dc * (1 if side < 0 else -1)
        px, py = vx - cx, z - zc; a = math.radians(ang)
        u = px * math.cos(a) + py * math.sin(a); v = -px * math.sin(a) + py * math.cos(a)
        return u / w + 0.5, v / h + 0.5

    def facing(self, side, k=0.25): return (self.N[:, 0] * side) > k

    def stamp_side(self, mask, sel, side, dc, zc, width, ang=0.0, rgb=WHITE, sm=None):
        h = width * mask.shape[0] / mask.shape[1]
        I = np.flatnonzero(sel & self.facing(side))
        if len(I) == 0: return
        # quick reject: texels well outside the stamp's box
        u, v = self.side_uv(side, dc, zc, width, h, ang)
        I = I[(u[I] > -0.1) & (u[I] < 1.1) & (v[I] > -0.3) & (v[I] < 1.3)]
        if len(I) == 0: return
        acc = np.zeros(len(I), np.float32)
        for dd, xx, zz in self.ss_points(I):
            uu, vv = self.side_uv(side, dc, zc, width, h, ang, dd, zz); acc += sample(mask, uu, vv)
        a = np.zeros(len(self.C), np.float32); a[I] = acc / len(self.SS)
        self.put(np.ones(len(self.C), bool), a, rgb, sm)

    def stamp_side_rgba(self, img, sel, side, dc, zc, width, ang=0.0, sm=None):
        """Colour decal (float RGBA array, straight alpha) seen from the given side."""
        h = width * img.shape[0] / img.shape[1]
        I = np.flatnonzero(sel & self.facing(side))
        if len(I) == 0: return
        u, v = self.side_uv(side, dc, zc, width, h, ang)
        I = I[(u[I] > -0.1) & (u[I] < 1.1) & (v[I] > -0.3) & (v[I] < 1.3)]
        if len(I) == 0: return
        pre = img[..., :3] * img[..., 3:4]
        acc = np.zeros((len(I), 4), np.float32)
        for dd, xx, zz in self.ss_points(I):
            uu, vv = self.side_uv(side, dc, zc, width, h, ang, dd, zz)
            acc[:, 3] += sample(img[..., 3], uu, vv)
            for c in range(3): acc[:, c] += sample(pre[..., c], uu, vv)
        acc /= len(self.SS)
        a = acc[:, 3]; rgb = acc[:, :3] / np.maximum(a, 1e-6)[:, None]
        self.col[I] = self.col[I] * (1 - a[:, None]) + rgb * a[:, None]
        if sm is not None: self.sm[I] = self.sm[I] * (1 - a) + sm * a
        self.paint_mask[I] = np.maximum(self.paint_mask[I], a)

    def stamp_top_rgba(self, img, sel, xc, dc, width, up=True):
        h = width * img.shape[0] / img.shape[1]
        cx = xc if up else -xc
        def uvat(d, x):
            vx = x if up else -x; return (vx - cx) / width + 0.5, (-(d - dc)) / h + 0.5
        fac = self.N[:, 2] > 0.4 if up else self.N[:, 2] < -0.4
        I = np.flatnonzero(sel & fac)
        if len(I) == 0: return
        u, v = uvat(self.d[I], self.x[I]); I = I[(u > -0.1) & (u < 1.1) & (v > -0.3) & (v < 1.3)]
        if len(I) == 0: return
        pre = img[..., :3] * img[..., 3:4]; acc = np.zeros((len(I), 4), np.float32)
        for dd, xx, zz in self.ss_points(I):
            uu, vv = uvat(dd, xx); acc[:, 3] += sample(img[..., 3], uu, vv)
            for c in range(3): acc[:, c] += sample(pre[..., c], uu, vv)
        acc /= len(self.SS); a = acc[:, 3]; rgb = acc[:, :3] / np.maximum(a, 1e-6)[:, None]
        self.col[I] = self.col[I] * (1 - a[:, None]) + rgb * a[:, None]
        self.paint_mask[I] = np.maximum(self.paint_mask[I], a)

    def stamp_top(self, mask, sel, xc, dc, width, rgb, up=True, ang=0.0):
        """Seen from above (up=True, nose at the top of the view) or below (up=False, nose at the top, viewer under it)."""
        h = width * mask.shape[0] / mask.shape[1]
        cx = xc if up else -xc; a = math.radians(ang)
        def uvat(d, x):
            vx = x if up else -x; px, py = vx - cx, -(d - dc)
            return (px * math.cos(a) + py * math.sin(a)) / width + 0.5, (-px * math.sin(a) + py * math.cos(a)) / h + 0.5
        fac = self.N[:, 2] > 0.4 if up else self.N[:, 2] < -0.4
        I = np.flatnonzero(sel & fac)
        if len(I) == 0: return
        u, v = uvat(self.d[I], self.x[I]); I = I[(u > -0.1) & (u < 1.1) & (v > -0.3) & (v < 1.3)]
        if len(I) == 0: return
        acc = np.zeros(len(I), np.float32)
        for dd, xx, zz in self.ss_points(I):
            uu, vv = uvat(dd, xx); acc += sample(mask, uu, vv)
        al = np.zeros(len(self.C), np.float32); al[I] = acc / len(self.SS)
        self.put(np.ones(len(self.C), bool), al, rgb)


_RND = {}
def pala_roundel():
    """The PALA roundel with its open centre filled white (the faction's white field), as a float RGBA array."""
    if 'r' not in _RND:
        im = Image.open(LOGO_PALA).convert('RGBA'); im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
        a = im.getchannel('A'); w, h = im.size
        fill = Image.new('L', (w, h), 0); ImageDraw.Draw(fill)
        mask = a.point(lambda v: 255 if v > 8 else 0)
        ImageDraw.floodfill(mask, (w // 2, int(h * 0.29)), 128)        # open area inside the ring, round the triangle
        inner = mask.point(lambda v: 255 if v == 128 else 0)
        base = Image.new('RGBA', (w, h), (232, 232, 230, 0)); base.putalpha(inner)
        base.alpha_composite(im)
        _RND['r'] = np.asarray(base, np.float32) / 255
    return _RND['r']


def pala_marks(M, side, fin, on_hull):
    """PALA air force markings, one side: fin roundel, red fin-tip band, serial, fuselage wordmark, nose number, rescue."""
    d, z = M.d, M.z
    rnd = pala_roundel()
    M.stamp_side_rgba(rnd, fin, side, 35.25, 4.80, 1.55)
    fp = M.fp; aa = lambda dist: np.clip(0.5 - dist / fp, 0, 1)
    tip = fin & M.facing(side, 0.0)
    M.put(tip, aa(np.abs(z - 6.78) - 0.17), PRED)
    M.put(tip, aa(np.abs(np.abs(z - 6.78) - 0.19) - 0.018), STBLK)
    M.stamp_side(text_mask('AF 24-0220', FONT_ST), fin, side, 34.05, 3.55, 1.9, rgb=STBLK)
    M.stamp_side(text_mask('P  A  L  A', FONT_ST), on_hull, side, 9.6, 1.32, 3.4, rgb=STBLK)
    M.stamp_side(text_mask('0220', FONT_ST), on_hull, side, 2.6, -0.55, 0.62, rgb=STBLK)
    # rescue: door-ejector access panel just aft of the forward door, bottom level with the door sill, under the windows
    sel = on_hull & M.facing(side, 0.2)
    d0, d1, z0, z1 = 5.85, 6.40, -0.60, -0.17
    L = 0.11; t = 0.022
    for dc in (d0, d1):
        for zc in (z0, z1):
            hz = aa(np.abs(z - zc) - t) * aa(np.abs(d - (dc + (L / 2 if dc == d0 else -L / 2))) - L / 2)
            vt = aa(np.abs(d - dc) - t) * aa(np.abs(z - (zc + (L / 2 if zc == z0 else -L / 2))) - L / 2)
            M.put(sel, np.maximum(hz, vt), RESC)
    M.stamp_side(text_mask('RESCUE', FONT_ST), sel, side, (d0 + d1) / 2, z1 + 0.09, 0.42, rgb=RESC)
    M.stamp_side(text_mask('DOOR RELEASE', FONT_ST), sel, side, (d0 + d1) / 2, (z0 + z1) / 2, 0.48, rgb=STBLK)


def pala_wing_marks(M, wing):
    """Medium roundel on the starboard wing top and the port wing bottom (PB-22 / stock convention)."""
    rnd = pala_roundel(); s = 10.0
    dc = float(lerp_np(WING, s, 1) + 0.28 * lerp_np(WING, s, 2))
    M.stamp_top_rgba(rnd, wing, s, dc, 1.35, up=True)
    M.stamp_top_rgba(rnd, wing, -s, dc, 1.35, up=False)


def paint(maps, outdir):
    t0 = time.time()
    M = Painter(maps)
    d, x, z, N = M.d, M.x, M.z, M.N
    fuse = M.part(*FUSE_PARTS)
    rho, zt = fus_rho(d, x, z)
    on_hull = fuse & (rho < 1.06)                                       # the fuselage barrel itself (not the fairings)
    # ------------------------------------------------------------ house colours
    # olive barrel from the nose to just aft of the rear doors, ending in a forward-raked curve (the fin root fillet,
    # belly fairing, wing roots and tail cone stay white)
    zn = np.clip((z + 1.9) / 3.8, 0, 1)
    bound = 31.6 - 0.5 * zn - 0.15 * np.sin(zn * math.pi)            # d of the colour break (0.3.27b: clears the rear door)
    # belly: white below a smooth line that follows the top of the wing-to-body fairing (no ragged hull/fairing junction)
    FAIR = [(8.6, 0.80, -1.25, -1.84), (10.2, 1.35, -1.02, -1.92), (11.8, 1.85, -0.80, -1.98), (13.4, 2.18, -0.64, -2.02),
            (15.5, 2.32, -0.60, -2.03), (19.5, 2.35, -0.60, -2.03), (21.6, 2.18, -0.63, -2.01), (23.0, 1.72, -0.78, -1.96),
            (24.2, 1.12, -1.02, -1.89), (24.9, 0.75, -1.22, -1.84)]
    _, fzt, _ = pchip_np(FAIR, d)
    zline = np.where((d > 8.6) & (d < 24.9), fzt - 0.12, -9.0)
    fp = M.fp
    aa = lambda dist: np.clip(0.5 - dist / fp, 0, 1)                 # antialiased coverage of a region with signed distance dist
    band = lambda dist, hw: aa(np.abs(dist) - hw)                     # antialiased line of half width hw
    olive = on_hull & (d < bound) & (z > zline)
    olive_extra = M.part('fdoor_', 'geardoor_F') | (M.part('baydoor_') & (d < 31.0))
    cov_o = (on_hull * aa(d - bound) * np.where((d > 8.6) & (d < 24.9), aa(zline - z), 1.0)).astype(np.float32)
    cov_o = np.maximum(cov_o, olive_extra.astype(np.float32))
    olive = cov_o > 0.5
    fin = M.part('vstab_', 'rudder_', 'fintip', 'ruddertip')
    eng = M.part('engine_')
    ACC = DRED                                                         # door outlines, lip rings, small stencils
    if LIVERY == 'plink':
        M.col = M.col * (1 - cov_o[:, None]) + OLIVE[None] * cov_o[:, None]   # (0.4.14) one smoothness for every livery: the m map is shared, so paint-scheme gloss differences showed through other liveries
        # dark red pinstripe along the break, 5 cm, set 4 cm into the white
        M.put(on_hull, band(d - bound - 0.065, 0.025), DRED)
    elif LIVERY == 'civil':
        # Primeva Link line service: warm off-white overall, dusty pink fin and nacelles, a pink cheatline under the
        # windows that sweeps up into the fin root
        M.col[:] = OFFW; ACC = PINK_D
        M.put(fin, np.ones(len(d), np.float32), PINK)
        M.put(eng, np.ones(len(d), np.float32), PINK)
        zc = -0.20 + np.clip(d - 27.0, 0, None) * 0.20                 # cheatline centre, rising aft of the rear doors
        M.put(on_hull & (d > 2.2) & (d < 35.2), band(z - zc, 0.12) * aa(2.4 - d), PINK)
        M.put(on_hull & (d > 2.2) & (d < 35.2), band(z - (zc - 0.22), 0.025) * aa(2.4 - d), PINK_D)
    elif LIVERY == 'pala':
        # PALA air force tanker/transport: one matte grey overall, black and dark grey stencils
        M.col[:] = AFGREY; ACC = STBLK
    # ------------------------------------------------------------ nacelles: dark red lip ring
    for sx in (-1, 1):
        cx, cz = sx * 5.35, -2.25
        r = np.hypot(x - cx, z - cz)
        ring = eng & (np.abs(x - cx) < 1.3) & (r > 0.97)
        if LIVERY != 'pala':
            M.put(ring, aa(d - 13.08), ACC if LIVERY == 'plink' else OFFW)
            M.put(ring, band(d - 13.14, 0.02), ACC)   # thin second line
    # ------------------------------------------------------------ lettering
    t_prim = text_mask('PRIMROSE'); t_link = text_mask('P-LINK', FONT_S); t_link_m = t_link[:, ::-1].copy(); t_pds = text_mask('PDS1')
    t_fin = text_mask('P220'); t_reg = text_mask('PL-0001', FONT_S)
    lean = 38.0
    fin_ang = lambda side: (90 - lean) if side < 0 else (-90 + lean)   # starboard reads top to bottom (upright letters)
    for side in (-1, 1):
        if LIVERY == 'plink':
            M.stamp_side(t_prim, on_hull, side, 9.15, 1.30, 6.6, rgb=WHITE)
            M.stamp_side(t_link, on_hull, side, 8.10, 0.02, 1.75, rgb=WHITE)
            M.stamp_side(t_pds, on_hull, side, 27.05, 0.55, 1.9, rgb=WHITE)
            M.stamp_side(t_reg, on_hull, side, 2.55, -0.55, 0.95, rgb=WHITE)
            # fin: big dark "P220" running up the fin, leaning back with the sweep, readable from both sides
            M.stamp_side(t_fin, fin, side, 34.55, 4.45, 4.3, ang=fin_ang(side), rgb=CHAR)
        elif LIVERY == 'civil':
            # only the airline name and the type: "P-LINK" above the windows, "P220" in off-white on the pink fin
            M.stamp_side(t_link, on_hull, side, 9.6, 1.32, 4.6, rgb=PINK_D)
            M.stamp_side(t_fin, fin, side, 34.55, 4.45, 4.3, ang=fin_ang(side), rgb=OFFW)
            if side > 0:   # big "P-LINK" along the belly ahead of the wing, read from below, nose to tail
                bs = M.part('belly_') & (M.N[:, 2] < -0.4); dcb = 0.5 * (M.d[bs].min() + M.d[bs].max()) + 0.9   # visible bulge starts ~1.8 m aft of the piece's buried nose   # (16:44) centred on the belly fairing
                print('belly fairing d %.2f-%.2f centre %.2f' % (M.d[bs].min(), M.d[bs].max(), dcb))
                M.stamp_top(t_link, M.part(*FUSE_PARTS, 'belly_'), 0.0, dcb, 5.4, PINK_D, up=False, ang=-90.0)
        elif LIVERY == 'pala':
            pala_marks(M, side, fin, on_hull)
        # (0.3.27b, no fin emblem for now)
    # ------------------------------------------------------------ door and hatch outlines (dark red) and their stencils
    t_exit = text_mask('EXIT', FONT_S); t_push = text_mask('PUSH TO OPEN', FONT_S); t_cargo = text_mask('CARGO DOOR', FONT_S)
    t_res = text_mask('RESCUE', FONT_S)
    for d0, d1, z0, z1, sides, kind in DOOR_RECTS:
        dc, zc, hd, hz = (d0 + d1) / 2, (z0 + z1) / 2, (d1 - d0) / 2, (z1 - z0) / 2
        rr = 0.10                                                     # corner radius
        qx = np.abs(d - dc) - (hd + 0.05 - rr); qz = np.abs(z - zc) - (hz + 0.05 - rr)
        sdf = np.hypot(np.maximum(qx, 0), np.maximum(qz, 0)) + np.minimum(np.maximum(qx, qz), 0) - rr
        for side in sides:
            sel = fuse & M.facing(side, 0.15) & (rho < 1.06)
            M.put(sel, band(sdf, 0.022), ACC)
            if kind in ('door', 'exit'):
                M.stamp_side(t_exit, sel, side, dc, z1 + 0.19, 0.40, rgb=ACC)
            if kind == 'exit':
                M.stamp_side(t_push, sel, side, dc, z0 - 0.16, 0.95, rgb=ACC)
            if kind == 'cargo':
                M.stamp_side(t_cargo, sel, side, dc, z1 + 0.17 if z1 < 0 else z0 - 0.17, 1.05, rgb=ACC)
    # rescue arrow and label on the crown above the forward doors (cut-in point, stock-style yellow/red marking)
    for side in (-1, 1):
        sel = on_hull & M.facing(side, 0.1)
        pass
    # ------------------------------------------------------------ wing and tail stencils
    t_ns = text_mask('NO STEP', FONT_S); t_walk = None
    wing = M.part('wing1a_', 'wing1b_', 'wing2_', 'wing3_')
    flaps = M.part('flap_', 'flapin_', 'aileron_', 'spoilerin_', 'spoilerout_', 'elevator_', 'elevtip_')
    for sx in (-1, 1):
        # (the author 2026-11-08) every NO STEP runs parallel to the leading edge; the innermost leading-edge one is gone
        sweep = lambda s: math.degrees(math.atan2(lerp_np(WING, s + 0.25, 1) - lerp_np(WING, s - 0.25, 1), 0.5))
        for s, dd in ((4.4, 16.7), (8.8, 18.9), (12.5, 20.3)):
            M.stamp_top(t_ns, flaps, sx * s, dd, 0.85, CHAR, ang=-sx * sweep(s))
        for s in (5.0, 8.5, 12.5):                                    # NO STEP along the leading edge area
            le = lerp_np(WING, s, 1); c = lerp_np(WING, s, 2)
            M.stamp_top(t_ns, wing, sx * s, le + 0.20 * c, 0.80, CHAR, ang=-sx * sweep(s))
        # walkway lines on the inner wing top: two dark lines from the over-wing exits out to s 6
        for s_lo, s_hi in ((2.2, 6.0),):
            sel = wing & (N[:, 2] > 0.4) & (np.abs(x) > s_lo) & (np.abs(x) < s_hi) & (np.sign(x) == sx)
            le = lerp_np(WING, np.abs(x), 1); c = lerp_np(WING, np.abs(x), 2); u = (d - le) / np.maximum(c, 0.1)
            M.put(sel, np.maximum(band((u - 0.30) * c, 0.02), band((u - 0.58) * c, 0.02)), CHAR)
        hst = M.part('hstab_', 'hstabtip_')
        hsweep = math.degrees(math.atan2(lerp_np(HT, 2.85, 1) - lerp_np(HT, 2.35, 1), 0.5))
        M.stamp_top(t_ns, hst, sx * 2.6, 34.2, 0.75, CHAR, ang=-sx * hsweep)   # parallel to the stabiliser leading edge
    # ------------------------------------------------------------ intake danger markings (red chevron + DANGER)
    t_dng = text_mask('DANGER', FONT_S)
    chev = np.zeros((200, 200), np.float32)
    im = Image.new('L', (200, 200), 0); ImageDraw.Draw(im).polygon([(10, 10), (190, 100), (10, 190), (60, 100)], fill=255)
    chev = np.asarray(im, np.float32) / 255
    for sx in (-1, 1):
        cx, cz = sx * 5.35, -2.25
        for side in (-1, 1):
            sel = eng & ((x - cx) * side > 0.6) & (np.abs(z - cz) < 0.6)
            M.stamp_side(chev, sel, side, 13.60, cz + 0.05, 0.30, ang=180 if side < 0 else 0, rgb=DRED)
            M.stamp_side(t_dng, sel, side, 14.25, cz + 0.05, 0.80, rgb=DRED)
    # ------------------------------------------------------------ small service stencils
    t_static = text_mask('STATIC - KEEP CLEAR', FONT_S)
    for side in (-1, 1):
        sel = on_hull & M.facing(side, 0.3)
        r = np.hypot(d - 3.6, z - (-0.15))
        M.put(sel, band(r - 0.085, 0.01), ACC)
    t_fuel = text_mask('FUEL', FONT_S)
    for sx in (-1, 1):
        M.stamp_top(t_fuel, wing, sx * 9.6, 18.9, 0.45, ACC, up=False)
    if LIVERY == 'pala': pala_wing_marks(M, wing)
    if LIVERY == 'blank':   # Livery Bundle base: plain white, no markings, only the light panel-line grime below
        M.col[:] = WHITE; M.paint_mask[:] = 0
    # ------------------------------------------------------------ panel lines (height field, metres)
    def height(P, ws=1.0, painted=False):
        dd = NOSE_Y - P[:, 1]; xx = P[:, 0]; zz = P[:, 2]
        h = np.zeros(len(P), np.float32)
        g = lambda dist, w=0.006: np.clip(1 - np.abs(dist) / (w * ws), 0, 1)
        # fuselage: circumferential joints at the production breaks and every second frame; lap joints along
        rr, _ = fus_rho(dd, xx, zz)
        hull = rr < 1.06
        if painted:   # PALA painted lines: production joints and lap lines only, never through a door
            for d0, d1, z0, z1, sides, kind in DOOR_RECTS:
                for sd in sides:
                    hull = hull & ~((xx * sd > 0.05) & (dd > d0 - 0.2) & (dd < d1 + 0.2) & (zz > z0 - 0.2) & (zz < z1 + 0.2))
        for j in (0.9, 3.2, 9.5, 13.5, 22.0, 30.5, 34.4):
            h -= hull * g(dd - j)
        for k in range(1, 18):
            fr = 5.92 + 2.24 * k
            if fr < 37 and not painted: h -= 0.6 * hull * g(dd - fr, 0.004)
        for zl in (1.45, -0.95):
            h -= 0.7 * hull * (dd > 3.4) * (dd < 33.0) * g(zz - zl, 0.004)
        # wings: spar and rib lines on both skins
        s = np.abs(xx); le = np.interp(s, [w[0] for w in WING], [w[1] for w in WING]); c = np.interp(s, [w[0] for w in WING], [w[2] for w in WING])
        u = (dd - le) / np.maximum(c, 0.1)
        onw = (s > 1.7) & (s < 16.75) & (u > -0.02) & (u < 1.02) & (np.abs(zz - (-1.35 + s * math.tan(math.radians(5)))) < 0.6)
        for us in (0.16, 0.62):
            h -= onw * g((u - us) * c)
        for sr in np.arange(2.5, 16.5, 1.5):
            h -= 0.6 * onw * (u > 0.16) * (u < 0.62) * g(s - sr, 0.004)
        return h
    e = 0.5 / M.ppm
    P = M.P
    H = np.stack([height(P), height(P + e * M.T), height(P - e * M.T), height(P + e * M.B), height(P - e * M.B)])
    DEPTH = 0.0012
    dT = (H[1] - H[2]) / (2 * e) * DEPTH; dB = (H[3] - H[4]) / (2 * e) * DEPTH
    g = np.hypot(dT, dB); cap = np.where(g > 0.5, 0.5 / np.maximum(g, 1e-9), 1.0); dT *= cap; dB *= cap
    nrm = np.stack([-dT, -dB, np.ones_like(dT)], 1); nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    # light grime in the panel lines and a whisper of paint variation (stock: clean, sparse wear)
    groove = np.clip(-H[0], 0, 1)
    nz = vnoise(P, 2.5, seed=5, octaves=3)
    if LIVERY == 'pala':   # KC-135 style: every panel joint reads as a distinct dark line on the matte grey
        # (the 6 mm lines were sub-texel at 2K and read as artifacts) painted lines ~3.5 cm wide, a smooth
        # tent profile so they stay antialiased; the shared normal-map grooves stay as they are
        gw = np.clip(-height(P, 6.0, painted=True), 0, 1) ** 0.8
        gl = np.clip(gw * 1.15, 0, 1) * (1 - 0.7 * M.paint_mask)
        M.col = M.col * (1 - 0.6 * gl[:, None]) + AFLINE[None] * (0.6 * gl[:, None])
    else:
        M.col *= (1 - 0.10 * groove * (1 - M.paint_mask))[:, None]
    M.col *= (1 + 0.012 * nz)[:, None]
    M.sm -= 0.04 * groove + 0.02 * np.clip(nz, 0, 1)
    # ------------------------------------------------------------ write
    os.makedirs(outdir, exist_ok=True)
    q8 = lambda a: np.clip(np.round(a * 255), 0, 255).astype(np.uint8)
    def save(arr, name, mode):
        Image.fromarray(arr[M.inv[M.idx]].reshape((M.S, M.S) + arr.shape[1:]), mode).save(os.path.join(outdir, name), compress_level=6)
        print('wrote', name)
    if LIVERY != 'plink':   # the other liveries only change the colour map (n/m/ao/damage maps are shared, as stock)
        save(q8(np.clip(M.col, 0, 1)), 'P220_skin_%s_b.png' % LIVERY, 'RGB'); print('done', LIVERY, '%.1fs' % (time.time() - t0)); return
    save(q8(np.clip(M.col, 0, 1)), 'P220_skin_b.png', 'RGB')
    save(q8(nrm * 0.5 + 0.5), 'P220_skin_n.png', 'RGB')
    sm = np.clip(M.sm, 0, 1)
    save(q8(np.stack([M.mt, M.mt, M.mt, sm], 1)), 'P220_skin_m.png', 'RGBA')
    hh = np.clip(H[0] * 0.25 + 0.5, 0, 1)
    Image.fromarray((hh[M.inv[M.idx]].reshape(M.S, M.S) * 65535).astype(np.uint16)).save(os.path.join(outdir, 'P220_skin_height.png'))
    # ------------------------------------------------------------ damage colour and normal (PB-22 style)
    n1 = vnoise(P, 1.5, seed=21, octaves=3); n2 = vnoise(P, 0.6, seed=22, octaves=2)
    # 0.3.31: the game blends this map over the whole part as it loses health, and every stock damage colour map is
    # near white (a multiplier): only the torn rims and the soot round them are dark (added in p220_dmg_alpha.py).
    # Here: near white with a faint mottle, slightly darker panel lines, and a few rare faint heat streaks.
    streak = np.clip((vnoise(P, 0.9, seed=23, octaves=2) * 0.5 + 0.5) * 1.0 - 0.78, 0, 1) / 0.22
    v = 0.95 + 0.025 * n1 + 0.01 * n2 - 0.06 * groove - 0.12 * streak
    col = np.clip(v, 0, 1)[:, None] * np.array([1.0, 0.99, 0.975], np.float32)[None, :]
    db = np.concatenate([np.clip(col, 0, 1), np.ones((len(P), 1), np.float32)], 1)
    hd = 0.006 * vnoise(P, 0.35, seed=31, octaves=3)
    hdT = (0.006 * vnoise(P + e * 8 * M.T, 0.35, seed=31, octaves=3) - hd) / (e * 8)
    hdB = (0.006 * vnoise(P + e * 8 * M.B, 0.35, seed=31, octaves=3) - hd) / (e * 8)
    dn = np.stack([-hdT - dT * 1.6, -hdB - dB * 1.6, np.ones(len(P), np.float32)], 1); dn /= np.linalg.norm(dn, axis=1, keepdims=True)
    save(q8(db), 'P220_skin_dmg_b.png', 'RGBA')
    save(q8(dn * 0.5 + 0.5), 'P220_skin_dmg_n.png', 'RGB')
    print('olive share %.2f' % olive.mean(), 'done %.1fs' % (time.time() - t0))


if __name__ == '__main__':
    paint(sys.argv[1], sys.argv[2])
