"""Rasterise one atlas family from tex_geom.py output into per-texel maps, WITH the UV tangent frame.
Usage: python3 tex_raster_tb.py <geom.npz> <family> <size> <out.npz>
Same as tex_raster.py (pos, nrm, pid, cov; gutters filled from the nearest covered texel; image row 0 = top =
UV v 1) plus:
  tan  per-texel unit tangent  = dP/du orthogonalised against the smooth normal (MikkTSpace-like)
  bsg  bitangent sign: bitangent = bsg * cross(nrm, tan) points along dP/dv (Unity/Blender convention)
  idx  for every texel, the flat index of the covered texel it was filled from (identity on covered texels)
  ppm  texels per metre (median over the atlas)
  mat  per-texel material index into 'mats' (needs tex_geom_m.py output; 0 otherwise)"""
import sys, numpy as np
from scipy import ndimage


def raster(UV, P, N, S):
    pos = np.zeros((S, S, 3), np.float32); nrm = np.zeros((S, S, 3), np.float32)
    tan = np.zeros((S, S, 3), np.float32); bsg = np.zeros((S, S), np.int8)
    tri = np.full((S, S), -1, np.int32); cov = np.zeros((S, S), bool)
    uvp = UV.astype(np.float64) * S - 0.5          # texel centres at integer coords, v up
    # per-triangle dP/du, dP/dv
    e1 = P[:, 1] - P[:, 0]; e2 = P[:, 2] - P[:, 0]
    d1 = UV[:, 1] - UV[:, 0]; d2 = UV[:, 2] - UV[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    det = np.where(np.abs(det) < 1e-14, 1e-14, det)
    dPdu = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / det[:, None]
    dPdv = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / det[:, None]
    for t in range(len(UV)):
        a, b, c = uvp[t]
        x0 = max(int(np.floor(min(a[0], b[0], c[0]))), 0); x1 = min(int(np.ceil(max(a[0], b[0], c[0]))), S - 1)
        y0 = max(int(np.floor(min(a[1], b[1], c[1]))), 0); y1 = min(int(np.ceil(max(a[1], b[1], c[1]))), S - 1)
        if x1 < x0 or y1 < y0: continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12: continue
        w0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        w1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not m.any(): continue
        W = np.stack([w0[m], w1[m], w2[m]], 1).astype(np.float32)
        yy, xx = ys[m], xs[m]
        n = W @ N[t]
        pos[yy, xx] = W @ P[t]; nrm[yy, xx] = n; cov[yy, xx] = True; tri[yy, xx] = t
    nrm /= np.maximum(np.linalg.norm(nrm, axis=2, keepdims=True), 1e-6)
    # tangent frame per texel from its triangle
    m = cov
    T = dPdu[tri[m]].astype(np.float32); B = dPdv[tri[m]].astype(np.float32); n = nrm[m]
    T = T - n * np.sum(T * n, 1, keepdims=True)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    sg = np.sign(np.sum(np.cross(n, T) * B, 1)); sg[sg == 0] = 1
    tan[m] = T; bsg[m] = sg.astype(np.int8)
    return pos, nrm, tan, bsg, tri, cov


if __name__ == '__main__':
    g = np.load(sys.argv[1]); fam = sys.argv[2]; S = int(sys.argv[3])
    UV, P, N, PID = g[fam + '_uv'], g[fam + '_p'], g[fam + '_n'], g[fam + '_pid']
    MAT = g[fam + '_mat'] if fam + '_mat' in g else np.zeros(len(UV), np.int16)
    RPID = g[fam + '_rpid'] if fam + '_rpid' in g else PID
    mats = g['mats'] if 'mats' in g else np.array([fam])
    if fam in [str(x) for x in mats]:
        # only the faces with the family's own material own this atlas; other materials' faces overlap it
        own = MAT == [str(x) for x in mats].index(fam)
        UV, P, N, PID, MAT, RPID = UV[own], P[own], N[own], PID[own], MAT[own], RPID[own]
    pos, nrm, tan, bsg, tri, cov = raster(UV, P, N, S)
    pid = np.where(tri >= 0, PID[np.maximum(tri, 0)], -1).astype(np.int16)
    rpid = np.where(tri >= 0, RPID[np.maximum(tri, 0)], -1).astype(np.int16)[::-1]
    mat = np.where(tri >= 0, MAT[np.maximum(tri, 0)], -1).astype(np.int16)[::-1]
    # texels per metre from triangle areas
    e1 = P[:, 1] - P[:, 0]; e2 = P[:, 2] - P[:, 0]
    a3 = np.linalg.norm(np.cross(e1, e2), axis=1) / 2
    d1 = UV[:, 1] - UV[:, 0]; d2 = UV[:, 2] - UV[:, 0]
    a2 = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / 2
    ok = a3 > 1e-6
    ppm = float(np.median(np.sqrt(a2[ok] / a3[ok])) * S)
    # flip so that image row 0 = top (v = 1), then dilate (nearest covered texel) into the gutters
    pos, nrm, tan, bsg, pid, cov = pos[::-1], nrm[::-1], tan[::-1], bsg[::-1], pid[::-1], cov[::-1]
    near = ndimage.distance_transform_edt(~cov, return_distances=False, return_indices=True)
    idx = (near[0] * S + near[1]).astype(np.int32)
    np.savez(sys.argv[4], pos=pos.astype(np.float32), nrm=nrm.astype(np.float32), tan=tan.astype(np.float32),
             bsg=bsg, pid=pid, rpid=rpid, cov=cov, idx=idx, ppm=ppm, names=g['names'], mat=mat, mats=mats)
    print(fam, S, 'coverage %.3f' % cov.mean(), 'texels/m %.1f' % ppm)
