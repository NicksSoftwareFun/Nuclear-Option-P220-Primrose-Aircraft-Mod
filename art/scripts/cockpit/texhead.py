"""Paints the P220 flight deck atlas (original art, stock cockpit style with Airbus-like blue-grey panels):
albedo, normal, metallic/smoothness, AO, plus a preview of the tac screen page."""
import os
CK = os.path.dirname(os.path.abspath(__file__))  # scripts, ctx.obj and tex/ output live next to this file
import sys, math, os, random
sys.path.insert(0, CK)
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from p220_cockpit_model import ATLAS, CRIT, LAMP_CELLS, RT_REGIONS

S = 2048
OUT = os.path.join(CK, 'tex')
os.makedirs(OUT, exist_ok=True)
random.seed(220)

PANEL = (140, 145, 150)     # light Airbus grey panel paint
DARK = (64, 68, 73)
DIAL = (20, 21, 23)
WHITE = (222, 222, 216)
GREY = (150, 152, 152)
AMBER = (226, 150, 40)
RED = (186, 32, 26)
GREEN = (60, 170, 80)
YEL = (214, 176, 40)

B = Image.new('RGB', (S, S), PANEL)     # albedo
H = Image.new('L', (S, S), 128)         # height for the normal map
G = Image.new('L', (S, S), 110)         # smoothness
db, dh, dg = ImageDraw.Draw(B), ImageDraw.Draw(H), ImageDraw.Draw(G)
FB = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'
_fc = {}
def font(px):
    if px not in _fc: _fc[px] = ImageFont.truetype(FB, px)
    return _fc[px]

def R(name): return ATLAS[name]
def rr(x, y, w, h): return (x, y, x + w - 1, y + h - 1)

def text(x, y, s, px, col=WHITE, anchor='mm', squeeze=0.82, rot=0, engrave=True):
    """condensed bold legend centred at x,y (atlas px)."""
    f = font(px)
    bb = f.getbbox(s)
    w, h = bb[2] - bb[0] + 4, bb[3] - bb[1] + 4
    tile = Image.new('L', (w, h), 0)
    ImageDraw.Draw(tile).text((2 - bb[0], 2 - bb[1]), s, font=f, fill=255)
    tile = tile.resize((max(1, int(w*squeeze)), h), Image.LANCZOS)
    if rot: tile = tile.rotate(rot, expand=True, resample=Image.BICUBIC)
    tw, th = tile.size
    ox = int(x - tw/2) if anchor[0] == 'm' else (int(x) if anchor[0] == 'l' else int(x - tw))
    oy = int(y - th/2)
    B.paste(Image.new('RGB', tile.size, col), (ox, oy), tile)
    if engrave:
        H.paste(Image.new('L', tile.size, 120), (ox, oy), tile)

def fill(box, col, h=None, g=None):
    db.rectangle(box, fill=col)
    if h is not None: dh.rectangle(box, fill=h)
    if g is not None: dg.rectangle(box, fill=g)

def rounded(box, r, col, h=None, outline=None, width=1):
    db.rounded_rectangle(box, r, fill=col, outline=outline, width=width)
    if h is not None: dh.rounded_rectangle(box, r, fill=h)

def noise_region(name, base, amp=5, scuff=0):
    x, y, w, h = R(name)
    n = np.random.default_rng(hash(name) & 0xffff).normal(0, amp, (h, w, 1))
    # low-frequency mottling
    low = Image.fromarray(np.uint8(np.clip(128 + np.random.default_rng(7).normal(0, 40, (h//32 + 1, w//32 + 1)), 0, 255))).resize((w, h), Image.BICUBIC)
    low = (np.asarray(low, np.float32)[:, :, None] - 128)/128*amp*0.8
    a = np.clip(np.array(base, np.float32)[None, None, :] + n + low, 0, 255)
    B.paste(Image.fromarray(np.uint8(a)), (x, y))
    d = ImageDraw.Draw(B)
    for _ in range(scuff):   # sparse light scuffs (stock: light, sparse)
        sx, sy = x + random.randint(0, w - 1), y + random.randint(0, h - 1)
        L = random.randint(4, 18); ang = random.uniform(0, math.pi)
        c = tuple(int(v + 14) for v in base)
        d.line((sx, sy, sx + L*math.cos(ang), sy + L*math.sin(ang)), fill=c, width=1)

def bevel_edge(box, light=14, dark=-14, w=2):
    """thin painted edge highlight like the stock worn panel edges."""
    x0, y0, x1, y1 = box
    def shade(b, d):
        reg = B.crop(b); a = np.asarray(reg, np.int16) + d
        B.paste(Image.fromarray(np.uint8(np.clip(a, 0, 255))), b[:2])
    shade((x0, y0, x1 + 1, y0 + w), light); shade((x0, y0, x0 + w, y1 + 1), light)
    shade((x0, y1 - w + 1, x1 + 1, y1 + 1), dark); shade((x1 - w + 1, y0, x1 + 1, y1 + 1), dark)

def screws(box, inset=6, r=2):
    x0, y0, x1, y1 = box
    for cx, cy in ((x0 + inset, y0 + inset), (x1 - inset, y0 + inset), (x0 + inset, y1 - inset), (x1 - inset, y1 - inset)):
        db.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(95, 98, 102)); dh.ellipse((cx - r, cy - r, cx + r, cy + r), fill=150)
        db.line((cx - r + 1, cy, cx + r - 1, cy), fill=(50, 52, 55))

KNOBS = []    # every printed knob / toggle, so the model can put real geometry on top (2026-10-19)
def toggle(cx, cy, s=1.0, guard=False, label=None, lab_px=11):
    KNOBS.append((cx, cy, 'guard' if guard else 'toggle', 7*s))
    r = int(7*s)
    db.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(28, 29, 31)); dh.ellipse((cx - r, cy - r, cx + r, cy + r), fill=100)
    r2 = int(3*s)
    db.ellipse((cx - r2, cy - r2 - 2, cx + r2, cy + r2 - 2), fill=(190, 190, 186)); dh.ellipse((cx - r2, cy - r2 - 2, cx + r2, cy + r2 - 2), fill=200)
    if guard:
        g = int(10*s)
        db.rectangle((cx - g, cy - int(14*s), cx + g, cy + int(12*s)), outline=RED, width=2)
        for k in range(-g, g, 6): db.line((cx + k, cy + int(12*s), cx + k + 4, cy + int(12*s)), fill=YEL, width=2)
    if label: text(cx, cy - int(19*s), label, lab_px)

LAMPS = []
def lamp(box, col, lit=False, label=None, px=10, live=None):
    if live: LAMPS.append((live, box)); lit = False
    fill(box, tuple(int(c*(0.95 if lit else 0.35)) for c in col), 150, 200)
    db.rectangle(box, outline=(20, 20, 22), width=1)
    if label: text((box[0] + box[2])/2, (box[1] + box[3])/2, label, px, (25, 22, 18) if lit else (150, 148, 138), engrave=False)

def knob_print(cx, cy, r, label=None):
    KNOBS.append((cx, cy, 'knob', r))
    db.ellipse((cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3), outline=GREY, width=1)
    for k in range(9):
        a = math.radians(-135 + k*270/8)
        db.line((cx + (r + 4)*math.sin(a), cy - (r + 4)*math.cos(a), cx + (r + 8)*math.sin(a), cy - (r + 8)*math.cos(a)), fill=WHITE, width=1)
