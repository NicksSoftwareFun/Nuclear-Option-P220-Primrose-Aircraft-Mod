"""P220 (copied from the PB-22): damage alpha in the stock style: torn-panel shards at a few fixed levels, solid strips along the
engraved panel lines (1.0.5: no seam band; joints tear like the rest) and dark torn rims round every shard in the colour.
Tyres get their own small shredded chunks. Replaces only the alpha of PB22_skin_dmg_b.png (colour stays).
Usage: python3 tex_dmg_alpha.py <maps.npz> <PB22_skin_height.png> <PB22_skin_dmg_b.png in> <out.png>
Quick mode: PB22_PATCH_MASK=<mask.npy> recomputes only the masked texels; the rest keep the alpha of the input."""
import sys, os, time
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from scipy import ndimage
sys.path.insert(0, '/mnt/project-files/tu22/art/scripts/tex')
from tex_paint import vnoise
from tex_feat import hash01

# share of shards at each level (stock AB-4: ~35% mid, ~50% high, ~15% never opens)
LEVELS = np.array([0.40, 0.52, 0.66, 1.0], np.float32)
SHARE = np.array([0.06, 0.30, 0.44, 0.20], np.float32)
BIG = np.array([0.50, 0.75, 0.50], np.float32)     # shard size x, y (along the hull), z in metres
SMALL = np.array([0.20, 0.28, 0.20], np.float32)
SEAM_SOLID, SEAM_SOFT = 0.09, 0.18                  # bands at part joints that open late (high shard levels only)
NOT_SKIN = ('gear', 'wheel', 'act', 'brace', 'bogey', 'engine_body', 'fan', 'canopy', 'navlight', 'nozzle')


def cells(Q, size, seed):
    """Id of the nearest jittered-grid seed (3D Voronoi), so shard edges are straight cuts like torn panels."""
    q = Q / size
    i0 = np.floor(q).astype(np.int32)
    best = np.full(len(q), np.inf, np.float32); bid = np.zeros((len(q), 3), np.int32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = i0 + np.array([dx, dy, dz], np.int32)
                s = np.stack([hash01(c[:, 0], c[:, 1], c[:, 2] + seed * 7919 + k * 104729) for k in range(3)], 1)
                d = ((c + 0.15 + 0.7 * s - q) ** 2).sum(1)
                m = d < best
                best[m] = d[m]; bid[m] = c[m]
    return bid


def run(maps, heightpng, dmg_in, out):
    t0 = time.time()
    m = np.load(maps)
    S = m['pos'].shape[0]
    C = np.flatnonzero(m['cov'].ravel())
    P = m['pos'].reshape(-1, 3)[C].astype(np.float32)
    # the part each texel is in now: the joint bands follow the rip line (m['pid'] is the part it was built in)
    pid = (m['rpid'] if 'rpid' in m else m['pid']).ravel()[C]
    names = [str(n) for n in m['names']]
    print('texels', len(C))
    # quick mode: work on the masked texels J only (the seam test still looks at every other part's texels)
    pm = os.environ.get('PB22_PATCH_MASK')
    J = np.flatnonzero(np.load(pm).ravel()[C]) if pm else np.arange(len(C))
    Pall, pidall = P, pid
    P, pid = P[J], pid[J]
    if pm: print('patch: %d texels' % len(J))
    # torn edges: a broad warp bends the cuts, a fine one makes them ragged
    W = np.stack([0.08 * vnoise(P, 0.9, seed=41 + k, octaves=2) + 0.018 * vnoise(P, 0.05, seed=51 + k, octaves=2)
                  for k in range(3)], 1)
    Q = P + W
    big = cells(Q, BIG, 61)
    r = hash01(big[:, 0], big[:, 1], big[:, 2] + 7)
    lvl = np.searchsorted(np.cumsum(SHARE), r).clip(0, len(LEVELS) - 1)
    # smaller shards inside: a quarter of them sit one level lower, a few never open
    small = cells(Q, SMALL, 62)
    r2 = hash01(small[:, 0], small[:, 1], small[:, 2] + 11)
    lvl = np.where(r2 < 0.25, np.maximum(lvl - 1, 0), lvl)
    lvl = np.where(r2 > 0.95, len(LEVELS) - 1, lvl)
    alpha = LEVELS[lvl]
    print('shards %.1fs' % (time.time() - t0))
    # solid strips along the engraved panel lines (frames and stringers under them)
    h = np.asarray(Image.open(heightpng), np.float32) / 65535.0
    groove = (h < 0.47)
    groove = ndimage.binary_dilation(groove, iterations=1)
    alpha = np.where(groove.ravel()[C[J]], 1.0, alpha)
    # 1.0.5: no solid band at the part joints any more. Stock joints are straight cuts that tear like the rest of the
    # skin, so the break edge reads as the ragged shard pattern, not as the cut itself (the author 2026-10-27, full stock)
    if os.environ.get('PB22_SEAM_BAND') == '1':
        skin = np.array([not any(n.startswith(x) for x in NOT_SKIN) for n in names])
        onskin = skin[pid]
        sub = np.flatnonzero(skin[pidall])[::6]
        for p in np.unique(pid[onskin]):
            mine = np.flatnonzero(pid == p)
            other = sub[pidall[sub] != p]
            if len(other) == 0: continue
            d, _ = cKDTree(Pall[other]).query(P[mine], distance_upper_bound=SEAM_SOFT, workers=-1)
            a = alpha[mine]
            a = np.where(d < SEAM_SOFT, np.maximum(a, LEVELS[1]), a)
            a = np.where(d < SEAM_SOLID, np.maximum(a, LEVELS[2]), a)
            alpha[mine] = a
    print('seams %.1fs' % (time.time() - t0))
    # shredded tyres: small chunks of tread and sidewall at every level, torn along the tread blocks
    wheel = np.array([n.startswith('wheel') for n in names])[pid]
    if wheel.any():
        Tq = Q[wheel]
        ch = cells(Tq, np.array([0.07, 0.07, 0.07], np.float32), 63)
        rt = hash01(ch[:, 0], ch[:, 1], ch[:, 2] + 13)
        alpha[wheel] = np.array([0.36, 0.48, 0.60, 0.74, 1.0], np.float32)[np.searchsorted([0.14, 0.34, 0.58, 0.82], rt)]
        print('tyre texels', int(wheel.sum()))
    img = np.array(Image.open(dmg_in).convert('RGBA'))
    if img.shape[0] != S:
        raise SystemExit('size mismatch %s vs %d' % (img.shape, S))
    A = img[..., 3].ravel().copy()
    A[C[J]] = np.clip(np.round(alpha * 255), 0, 255).astype(np.uint8)
    # torn rims: stock damage colour maps draw a dark, broken outline where one shard meets a shard of another level
    # (or a never-opening strip), so an opened shard leaves a scorched ragged lip round the hole. Found in texture
    # space: texels whose neighbour is in the same island but at another alpha level; 1.4-3.4 cm each side, in dashes.
    cov = m['cov']
    Af = A.reshape(S, S).astype(np.int16)
    bnd = np.zeros((S, S), bool); bmin = np.full((S, S), 255, np.int16)
    for dy, dx in ((0, 1), (1, 0)):
        a0 = Af[:S - dy, :S - dx]; a1 = Af[dy:, dx:]; c0 = cov[:S - dy, :S - dx] & cov[dy:, dx:]
        pa = m['pos'][:S - dy, :S - dx]; pb = m['pos'][dy:, dx:]
        near = np.linalg.norm(pa - pb, axis=-1) < 0.05           # same island (atlas neighbours, not across a seam)
        e = c0 & near & (np.abs(a0 - a1) > 8)
        bnd[:S - dy, :S - dx] |= e; bnd[dy:, dx:] |= e
        mn = np.minimum(a0, a1)
        bmin[:S - dy, :S - dx] = np.where(e, np.minimum(bmin[:S - dy, :S - dx], mn), bmin[:S - dy, :S - dx])
        bmin[dy:, dx:] = np.where(e, np.minimum(bmin[dy:, dx:], mn), bmin[dy:, dx:])
    dist, (by, bx) = ndimage.distance_transform_edt(~bnd, return_indices=True)
    # how soon the border tears open: lines round shards that open early are full strength, borders between
    # late-opening shards stay faint, so a lightly damaged part shows a few scorched tears, not a crack net
    early = np.clip((215.0 - bmin[by, bx]) / 110.0, 0.12, 1.0).ravel()[C[J]]
    # texels per metre from neighbouring texel positions
    pa = m['pos'][:, :-1].reshape(-1, 3); pb = m['pos'][:, 1:].reshape(-1, 3)
    cc = (cov[:, :-1] & cov[:, 1:]).ravel()
    st = np.linalg.norm(pa[cc] - pb[cc], axis=1); st = st[st < 0.05]
    ppm = 1.0 / float(np.median(st))
    wid = (0.014 + 0.020 * np.clip(0.5 + 0.8 * vnoise(P, 0.12, seed=71, octaves=2), 0, 1)) * ppm
    dash = np.clip(0.5 + 1.4 * vnoise(P, 0.06, seed=72, octaves=2), 0, 1)
    rim = np.clip(1.0 - dist.ravel()[C[J]] / wid, 0, 1) * (0.35 + 0.65 * dash) * early
    if wheel.any(): rim[wheel] = 0
    RGB = img[..., :3].reshape(-1, 3)
    c0 = RGB[C[J]].astype(np.float32)
    soot = np.array([34, 31, 29], np.float32)
    # soot fringe: smoke staining fading out 4-8 cm from each tear line, broken up by noise, under the hard rim
    fw = (0.04 + 0.04 * np.clip(0.5 + 0.8 * vnoise(P, 0.2, seed=73, octaves=2), 0, 1)) * ppm
    fr = np.clip(1.0 - dist.ravel()[C[J]] / fw, 0, 1) ** 2 * early * (0.14 + 0.20 * np.clip(0.5 + vnoise(P, 0.05, seed=74, octaves=2), 0, 1))
    if wheel.any(): fr[wheel] = 0
    c0 = c0 * (1 - fr[:, None])
    RGB[C[J]] = np.clip(c0 * (1 - 0.65 * rim[:, None]) + soot * 0.65 * rim[:, None], 0, 255).astype(np.uint8)   # 0.4.0: 0.85 read too heavy at 35 %
    print('torn rims: %.1f%% of texels' % (100 * (rim > 0.2).mean()))
    # pad: texels outside the islands take the nearest island value, so mip levels don't bleed old alpha in
    cov = m['cov']
    _, (iy, ix) = ndimage.distance_transform_edt(~cov, return_indices=True)
    A = A.reshape(S, S)[iy, ix]
    img[..., :3] = RGB.reshape(S, S, 3)[iy, ix]
    img[..., 3] = A
    A = A.ravel()
    Image.fromarray(img, 'RGBA').save(out, compress_level=6)
    hist = np.histogram(A[C], bins=[0, 52, 104, 156, 208, 256])[0] / len(C) * 100
    print('alpha buckets %%: ' + ' / '.join('%.1f' % x for x in hist), 'mean %.2f' % (A[C].mean() / 255))
    for n in ('nose', 'cockpit', 'fuselage_FF'):
        if n not in names: continue
        I = np.flatnonzero(pid == names.index(n))
        if len(I) == 0: continue
        y = P[I, 1]; b = ((y - y.min()) / (np.ptp(y) + 1e-6) * 5).astype(int).clip(0, 4)
        print(n, 'early% by band (low y -> high y):', ' '.join('%d' % (100 * (alpha[I][b == k] < 0.45).mean()) if (b == k).any() else '-' for k in range(5)))
    print('done %.1fs' % (time.time() - t0))


if __name__ == '__main__':
    run(*sys.argv[1:5])
