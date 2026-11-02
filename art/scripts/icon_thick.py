import numpy as np, sys
from PIL import Image, ImageDraw
src = Image.open('current.png').convert('RGBA'); A = np.array(src)[..., 3].astype(float) / 255.0
H, W = A.shape; up = 4
big = np.array(Image.fromarray((A*255).astype(np.uint8)).resize((W*up, H*up), Image.BICUBIC)).astype(float)/255
m = big > 0.5; Hb, Wb = m.shape
cols = np.where(m.any(0))[0]; c = (cols.min() + cols.max())/2.0
hw = np.full(Hb, np.nan)
for y in range(Hb):
    row = m[y]; ci = int(round(c))
    if not row[ci]: continue
    l = ci
    while l > 0 and row[l-1]: l -= 1
    r = ci
    while r < Wb-1 and row[r+1]: r += 1
    if (r - l) < 0.16*Wb: hw[y] = (r - l + 1)/2.0      # narrow run = fuselage only
ys = np.where(~np.isnan(hw))[0]
fus = np.interp(np.arange(Hb), ys, hw[ys]); top, bot = ys.min(), ys.max()
fus[:top] = 0; fus[bot+1:] = 0
# groups of wide rows (wing, then tailplane): keep the tail cone slim, tapering the widening to x1.05 at the tailplane
wide = [y for y in range(top, bot+1) if np.isnan(hw[y])]
groups = []
for y in wide:
    if groups and y == groups[-1][-1] + 1: groups[-1].append(y)
    else: groups.append([y])
wing_end, stab_start = groups[0][-1], groups[-1][0]
print('wing ends', wing_end/up, 'stab starts', stab_start/up)
out = {}
for k in (1.4, 1.6, 1.8):
    xx = np.abs(np.arange(Wb)[None, :] - c)
    kk = np.full(Hb, k)
    t = np.clip((np.arange(Hb) - wing_end)/max(stab_start - wing_end, 1), 0, 1)
    kk = k + (1.05 - k)*t*t*(3 - 2*t)
    band = xx <= (fus*kk)[:, None]
    new = m | band
    im = Image.fromarray((new*255).astype(np.uint8)).resize((W, H), Image.LANCZOS)
    rgba = Image.new('RGBA', (W, H), (255, 255, 255, 0)); rgba.putalpha(im); out[k] = rgba
    rgba.save(f'thick_{k}.png')
sheet = Image.new('RGB', (4*280, 300), (40, 60, 90)); d = ImageDraw.Draw(sheet)
for i, (lab, im) in enumerate([('current', src)] + [(f'x{k}', out[k]) for k in out]):
    sheet.paste(im, (i*280 + 12, 12), im); d.text((i*280 + 120, 280), lab, fill=(255, 255, 255))
sheet.save('thick_sheet.png')
mini = Image.new('RGB', (4*60, 60), (40, 60, 90))
for i, im in enumerate([src] + list(out.values())):
    t = im.resize((32, 32), Image.LANCZOS); mini.paste(t, (i*60 + 14, 14), t)
mini.resize((480, 120), Image.NEAREST).save('thick_mini.png')
