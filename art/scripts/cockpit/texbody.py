YEL = (214, 176, 40)

def panel_plate(name, col=DARK):
    x, y, w, h = R(name)
    noise_region(name, col, 3, 4)
    dh.rectangle(rr(x, y, w, h), fill=128); dg.rectangle(rr(x, y, w, h), fill=100)
    bevel_edge(rr(x, y, w, h), 34, -18, 2)
    db.rectangle(rr(x, y, w, h), outline=(16, 16, 18), width=1)
    return x, y, w, h

def pushbtn(cx, cy, w, h, lab, col=None, px=10):
    rounded((cx - w//2, cy - h//2, cx + w//2, cy + h//2), 3, (28, 30, 33), 165)
    if col: fill((cx - w//2 + 4, cy - h//2 + 3, cx + w//2 - 4, cy - h//2 + 7), tuple(int(c*0.45) for c in col))
    text(cx, cy + 2, lab, px, WHITE, engrave=False)

# ================================================================== base paints
noise_region('paint', PANEL, 4, scuff=40)
noise_region('dark', DARK, 3, scuff=35)
dg.rectangle(rr(*R('paint')), fill=100); dg.rectangle(rr(*R('dark')), fill=95)
x, y, w, h = R('paint')
for k in range(1, 6):
    yy = y + k*h//6
    db.line((x, yy, x + w, yy), fill=(80, 87, 94), width=2); dh.line((x, yy, x + w, yy), fill=110, width=2)
    db.line((x, yy + 2, x + w, yy + 2), fill=(130, 138, 146), width=1)
    for xx in range(x + 20, x + w, 48):
        db.ellipse((xx - 3, yy + 7, xx + 3, yy + 13), fill=(92, 99, 106)); dh.ellipse((xx - 3, yy + 7, xx + 3, yy + 13), fill=140)
for k in range(1, 4):
    xx = x + k*w//4
    db.line((xx, y, xx, y + h), fill=(84, 91, 98), width=2); dh.line((xx, y, xx, y + h), fill=112, width=2)

# ================================================================== portrait display bezel (glass 208 x 260 mm in a 238 x 300 bezel)
x, y, w, h = R('mfd')
fill(rr(x, y, w, h), DARK, 140, 90); noise_region('mfd', DARK, 3, 6)
gx = int(w*(1 - 260/290)/2); gy = int(h*(1 - 196/230)/2)
fill((x + gx - 2, y + gy - 2, x + w - gx + 1, y + h - gy + 1), (10, 11, 13), 110, 170)
for side in (x + gx//2, x + w - gx//2):
    for k in range(6): text(side, y + h//2 + int((k - 2.5)*0.042/0.30*h) - 12, '-', 9, GREY, engrave=False)
bevel_edge(rr(x, y, w, h), 12, -10, 2)

# ================================================================== glareshield: FCU, master caution / warning
x, y, w, h = panel_plate('fcu', (40, 44, 48))
for k, (lab, val) in enumerate((('SPD', '250'), ('HDG', '090'), ('ALT', '12000'), ('V/S', '+0000'))):
    cx = int(x + w*(0.13 + k*0.25))
    fill((cx - 26, y + 8, cx + 26, y + 24), (8, 9, 10), 110, 170); text(cx, y + 16, val, 11, (240, 160, 50), engrave=False)
    text(cx, y + 31, lab, 9)
    knob_print(cx, y + 52, 9)
for k, lab in enumerate(('AP', 'A/THR')):
    pushbtn(int(x + w*(0.385 + k*0.25)) - 0, y + 52, 22, 14, lab, GREEN, 7)
x, y, w, h = R('caut'); fill(rr(x, y, w, h), (150, 96, 20), 150, 200); text(x + w/2, y + h/2 - 7, 'MASTER', 11, (40, 25, 5), engrave=False); text(x + w/2, y + h/2 + 8, 'CAUT', 12, (40, 25, 5), engrave=False)
bevel_edge(rr(x, y, w, h), 20, -20, 2)
x, y, w, h = R('warn'); fill(rr(x, y, w, h), (110, 22, 18), 150, 200); text(x + w/2, y + h/2 - 7, 'MASTER', 11, (30, 5, 5), engrave=False); text(x + w/2, y + h/2 + 8, 'WARN', 12, (30, 5, 5), engrave=False)
bevel_edge(rr(x, y, w, h), 20, -20, 2)
x, y, w, h = R('red'); fill(rr(x, y, w, h), (176, 28, 22), 150, 150)

# ================================================================== shared non-critical annunciators (live cells)
x, y, w, h = panel_plate('ncol', (34, 37, 40))
for k, lab in enumerate(LAMP_CELLS[:8]):
    c, r_ = k % 2, k // 2
    bx = (x + 8 + c*58, y + 10 + r_*60, x + 8 + c*58 + 54, y + 10 + r_*60 + 52)
    col = GREEN if lab in ('GEAR DN', 'AP', 'NAV', 'A/THR') else AMBER
    lamp(bx, col, False, lab, 10, live=lab)
x, y, w, h = panel_plate('nstrip', (34, 37, 40))
for k, lab in enumerate(LAMP_CELLS[8:]):
    bx = (x + 8 + k*78, y + 14, x + 8 + k*78 + 72, y + 14 + 54)
    col = AMBER if lab in ('LASER', 'BAY', 'JAMMER', 'ANTI ICE') else GREEN
    lamp(bx, col, False, lab, 11, live=lab)
text(x + w/2, y + h - 12, 'SYSTEM STATUS', 10, GREY)

# ================================================================== lower panels
x, y, w, h = panel_plate('efis')
text(x + w/2, y + 12, 'EFIS', 11)
for k, lab in enumerate(('BARO', 'MODE', 'RANGE')):
    knob_print(int(x + 40 + k*88), y + 70, 15, lab)
for k, lab in enumerate(('FD', 'LS', 'TERR', 'WX')):
    pushbtn(int(x + 34 + k*62), y + 126, 40, 16, lab, GREEN, 8)
# 0.3.20: the wing-end panels are 0.105 x 0.22 m, so these regions are 105 x 220 px (1 px per mm) and laid out narrow
x, y, w, h = panel_plate('gear')
text(x + w/2, y + 11, 'LDG GEAR', 10)
for k, lab in enumerate(('NOSE', 'LEFT', 'RIGHT')):
    lamp((x + 8, y + 24 + k*24, x + 52, y + 42 + k*24), GREEN, False, lab, 8)
text(x + 86, y + 34, 'UP', 10); text(x + 86, y + 196, 'DN', 10)
db.rectangle((x + 68, y + 46, x + 76, y + 200), fill=(10, 10, 11))   # lever slot (the lever stands 20 mm right of centre)
for k in range(0, w, 14):
    db.polygon([(x + k, y + h - 8), (x + k + 7, y + h - 8), (x + k + 14, y + h), (x + k + 7, y + h)], fill=YEL)
x, y, w, h = panel_plate('brk')
text(x + w/2, y + 11, 'AUTO BRK', 10)
for k, lab in enumerate(('LO', 'MED', 'MAX')):
    pushbtn(int(x + 19 + k*33), y + 34, 28, 16, lab, GREEN, 8)
cx, cy, r = x + w//2, y + 112, 40
db.ellipse((cx - r, cy - r, cx + r, cy + r), fill=DIAL, outline=GREY, width=2)
for k in range(12):
    a = math.radians(k*30); db.line((cx + (r - 7)*math.sin(a), cy - (r - 7)*math.cos(a), cx + (r - 2)*math.sin(a), cy - (r - 2)*math.cos(a)), fill=WHITE, width=2)
db.line((cx, cy, cx + 22, cy - 14), fill=WHITE, width=3); db.line((cx, cy, cx - 5, cy - 30), fill=WHITE, width=2)
text(cx, cy + 22, 'CLOCK', 8, GREY, engrave=False)
toggle(x + 24, y + h - 22, 1.0, label=None); text(x + 62, y + h - 22, 'CHR', 10)

# ================================================================== pedestal
x, y, w, h = panel_plate('mcdu', (38, 41, 45))
fill((x + 16, y + 12, x + w - 16, y + 120), (6, 9, 8), 110, 175)
for k, line in enumerate(('  INIT A        1/3', 'P220/PLINK   FL350', 'CO RTE   ALTN', '<NAV DB   ROUTE>', 'COST INDEX  35', 'CRZ  FL350  M.78')):
    text(x + 24, y + 22 + k*16, line, 11, (70, 210, 120) if k else (230, 230, 230), anchor='lm', engrave=False)
for side, xx in ((0, x + 6), (1, x + w - 18)):
    for k in range(5): rounded((xx, y + 22 + k*20, xx + 12, y + 32 + k*20), 2, (28, 30, 33), 160)
keys = ['DIR', 'PROG', 'PERF', 'INIT', 'DATA', 'F-PLN', 'RAD', 'FUEL', 'SEC', 'MENU']
for i, k in enumerate(keys):
    cx = x + 28 + (i % 5)*46; cy = y + 138 + (i // 5)*24
    pushbtn(cx, cy, 40, 18, k, None, 8)
for i in range(15):
    cx = x + 40 + (i % 5)*40; cy = y + 196 + (i // 5)*30
    rounded((cx - 15, cy - 11, cx + 15, cy + 11), 7, (210, 210, 205), 175)
    text(cx, cy, '123456789.0/+-*'[i], 12, (20, 20, 20), engrave=False)
x, y, w, h = panel_plate('quad', (30, 32, 35))
# 0.3.17: the slots are cut in the model (layout.py THR_SLOT_X 0.042, half width 0.006, v -0.060..+0.140 on a 0.16 x 0.30 top);
# print a dark lip round each cut and the detents where the handles stop: IDLE at v -0.042, TOGA at v +0.1235
QPX = lambda u: x + (0.5 + u/0.16)*w
QPY = lambda v: y + (0.5 - v/0.30)*h
for su in (-0.042, 0.042):
    fill((int(QPX(su - 0.009)), int(QPY(0.143)), int(QPX(su + 0.009)), int(QPY(-0.063))), (10, 10, 12), 70, 60)
for lab, v in (('TOGA', 0.1235), ('FLX MCT', 0.1235 - 0.1655*0.12), ('CL', -0.042 + 0.1655*0.55), ('IDLE', -0.042)):
    yy = QPY(v)
    db.line((x + w*0.40, yy, x + w*0.60, yy), fill=WHITE, width=2); text(x + w/2, yy - 9, lab, 10)
    for su in (-0.042, 0.042):
        for sg in (-1, 1): db.line((QPX(su + sg*0.008), yy, QPX(su + sg*0.013), yy), fill=WHITE, width=2)
text(x + w/2, y + h - 18, 'ENG 1      ENG 2', 11)
def ped(name, title, items):
    x, y, w, h = panel_plate(name)
    text(x + w/2, y + 12, title, 12)
    for k, (kind, lab) in enumerate(items):
        cxk = x + 40 + k*(w - 80)/(len(items) - 1); cyk = y + 60
        if kind == 'k': knob_print(int(cxk), cyk, 13, lab)
        elif kind == 't': toggle(int(cxk), cyk, 1.1); text(cxk, cyk + 28, lab, 10)
        elif kind == 'g': toggle(int(cxk), cyk, 1.1, True); text(cxk, cyk + 28, lab, 10)
        elif kind == 'd':
            fill((int(cxk - 32), cyk - 11, int(cxk + 32), cyk + 11), (8, 10, 9), 110, 170); text(cxk, cyk, lab, 12, (240, 160, 50), engrave=False)
    screws(rr(x, y, w, h))
ped('ped0', 'RADIO MANAGEMENT', [('d', '118.700'), ('k', 'VHF'), ('d', '121.500'), ('k', 'VOL')])
ped('ped1', 'ENGINE MASTER', [('g', 'ENG 1'), ('k', 'START'), ('g', 'ENG 2'), ('t', 'IGN')])
ped('ped2', 'TRIM / PARK BRK', [('k', 'RUD TRIM'), ('t', 'PARK'), ('k', 'FLOOD')])

# ================================================================== side consoles
def con(name, title, items, rows=2):
    x, y, w, h = panel_plate(name)
    text(x + w/2, y + 14, title, 12)
    per = math.ceil(len(items)/rows)
    for k, (kind, lab) in enumerate(items):
        r_, c_ = divmod(k, per)
        cxk = x + 40 + c_*(w - 80)/max(1, per - 1); cyk = y + 70 + r_*90
        if kind == 'k': knob_print(int(cxk), cyk, 14, lab)
        elif kind == 't': toggle(int(cxk), cyk, 1.1); text(cxk, cyk + 28, lab, 10)
        elif kind == 'g': toggle(int(cxk), cyk, 1.1, True); text(cxk, cyk + 28, lab, 10)
        elif kind == 'l': lamp((int(cxk - 26), cyk - 10, int(cxk + 26), cyk + 10), AMBER, False, lab, 9)
    screws(rr(x, y, w, h))
con('con0', 'AUDIO CONTROL', [('k', 'VHF 1'), ('k', 'VHF 2'), ('k', 'INT'), ('t', 'PTT'), ('t', 'VOICE'), ('l', 'CALL')])
con('con1', 'LIGHTING', [('k', 'PANEL'), ('k', 'FLOOD'), ('k', 'CONSOLE'), ('t', 'DOME'), ('t', 'READ'), ('t', 'STORM')])
con('con2', 'OXYGEN / AUDIO', [('k', 'VHF 3'), ('k', 'VOL'), ('t', 'MASK'), ('g', 'O2 ON'), ('t', 'TEST'), ('l', 'O2 LO')])

# ================================================================== overhead
def ovh(name, title, items, rows=3):
    x, y, w, h = panel_plate(name)
    text(x + w/2, y + 14, title, 13)
    per = math.ceil(len(items)/rows)
    for k, (kind, lab) in enumerate(items):
        r_, c_ = divmod(k, per)
        cxk = int(x + 50 + c_*(w - 100)/max(1, per - 1)); cyk = y + 70 + r_*110
        if kind == 'p':
            rounded((cxk - 24, cyk - 18, cxk + 24, cyk + 18), 3, (24, 26, 29), 165)
            fill((cxk - 18, cyk + 4, cxk + 18, cyk + 12), (40, 40, 38)); text(cxk, cyk - 6, 'ON', 9, (90, 160, 200), engrave=False)
            text(cxk, cyk + 32, lab, 10)
        elif kind == 'f':      # fire handle
            fill((cxk - 30, cyk - 16, cxk + 30, cyk + 16), RED, 175, 150); text(cxk, cyk, lab, 10, (30, 5, 5), engrave=False)
        elif kind == 't': toggle(cxk, cyk, 1.2); text(cxk, cyk + 30, lab, 10)
        elif kind == 'g': toggle(cxk, cyk, 1.2, True); text(cxk, cyk + 30, lab, 10)
        elif kind == 'k': knob_print(cxk, cyk, 15, lab)
    for k in range(1, rows):
        db.line((x + 8, y + 28 + k*110, x + w - 8, y + 28 + k*110), fill=WHITE, width=1)
    screws(rr(x, y, w, h))
ovh('ovh0', 'ENGINE FIRE', [('f', 'ENG 1'), ('f', 'APU'), ('f', 'ENG 2'), ('g', 'DISCH 1'), ('t', 'TEST'), ('g', 'DISCH 2'), ('p', 'APU MSTR'), ('p', 'APU START'), ('p', 'BLEED')])
ovh('ovh1', 'ELECTRICAL', [('p', 'BAT 1'), ('p', 'BAT 2'), ('p', 'EXT PWR'), ('p', 'GEN 1'), ('p', 'APU GEN'), ('p', 'GEN 2'), ('t', 'BUS TIE'), ('k', 'AC ESS'), ('t', 'GALLEY')])
ovh('ovh2', 'FUEL / HYD', [('p', 'L PUMP'), ('p', 'X FEED'), ('p', 'R PUMP'), ('p', 'HYD 1'), ('p', 'PTU'), ('p', 'HYD 2'), ('g', 'DUMP'), ('k', 'MODE'), ('t', 'AUX')])
ovh('ovh3', 'AIR / ANTI ICE / LIGHTS', [('p', 'WING AI'), ('p', 'ENG AI'), ('p', 'PROBES'), ('k', 'CKPT T'), ('k', 'CABIN T'), ('t', 'PACK'), ('t', 'NAV'), ('t', 'STROBE'), ('t', 'LAND')])

# ================================================================== grip, side stick base, pedals, floor, door
x, y, w, h = R('grip'); noise_region('grip', (30, 31, 33), 3)
for k in range(0, w, 6): dh.line((x + k, y, x + k, y + h), fill=110)
dg.rectangle(rr(x, y, w, h), fill=60)
x, y, w, h = R('ssbase'); noise_region('ssbase', (26, 27, 29), 3); bevel_edge(rr(x, y, w, h), 14, -14, 3)
db.ellipse((x + 20, y + 20, x + w - 20, y + h - 20), outline=(60, 62, 66), width=3)
x, y, w, h = R('pedal'); fill(rr(x, y, w, h), (44, 45, 47), 120, 80)
for k in range(10, h - 8, 9):
    db.rectangle((x + 8, y + k, x + w - 9, y + k + 3), fill=(70, 72, 75)); dh.rectangle((x + 8, y + k, x + w - 9, y + k + 3), fill=170)
bevel_edge(rr(x, y, w, h), 18, -18, 2)
x, y, w, h = R('tread'); noise_region('tread', (58, 60, 63), 4, 3); dg.rectangle(rr(x, y, w, h), fill=70)
for j in range(0, h // 22 + 1):
    for i in range(0, w // 22 + 1):
        cx, cy = x + i*22 + (11 if j % 2 else 0), y + j*22
        if not (x + 6 < cx < x + w - 6 and y + 6 < cy < y + h - 6): continue
        pts = [(cx - 8, cy - 6), (cx - 6, cy - 8), (cx + 8, cy + 6), (cx + 6, cy + 8)] if (i + j) % 2 else [(cx + 8, cy - 6), (cx + 6, cy - 8), (cx - 8, cy + 6), (cx - 6, cy + 8)]
        db.polygon(pts, fill=(80, 82, 85)); dh.polygon(pts, fill=175)
bevel_edge(rr(x, y, w, h), 20, -24, 3)
x, y, w, h = R('carpet')
a = np.clip(np.array((78, 84, 92), np.float32)[None, None, :] + np.random.default_rng(3).normal(0, 6, (h, w, 1)), 0, 255)
B.paste(Image.fromarray(np.uint8(a)), (x, y)); dg.rectangle(rr(x, y, w, h), fill=30)
x, y, w, h = panel_plate('door', (92, 98, 104))
fill((x + 40, y + 70, x + w - 40, y + 76), (70, 75, 80)); fill((x + 40, y + h - 76, x + w - 40, y + h - 70), (70, 75, 80))
fill((x + w//2 - 90, y + 140, x + w//2 + 90, y + 170), (205, 205, 196), 136)
text(x + w//2, y + 155, 'FLIGHT DECK', 16, (30, 30, 30), engrave=False)
for k in range(0, w, 16):
    db.polygon([(x + k, y + h - 12), (x + k + 8, y + h - 12), (x + k + 16, y + h - 2), (x + k + 8, y + h - 2)], fill=YEL)


# ---- maintenance manual page taped to the captain's panel: a slightly yellowed printed page, boxed warning,
# punched for a binder down its left edge
x, y, w, h = ATLAS['note']
paper = np.clip(np.array((226, 222, 204), np.float32)[None, None, :] + np.random.default_rng(7).normal(0, 3, (h, w, 1)), 0, 255)
B.paste(Image.fromarray(np.uint8(paper)), (x, y)); dg.rectangle((x, y, x + w - 1, y + h - 1), fill=60); dh.rectangle((x, y, x + w - 1, y + h - 1), fill=128)
INK = (34, 34, 38); FR = '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'
def ft(px, bold=False): return ImageFont.truetype(FB if bold else FR, px)
L0 = x + 34                                   # text margin clear of the punch holes
for hy in (y + 70, y + h//2, y + h - 70):     # binder punch holes: the panel shows through
    db.ellipse((x + 9, hy - 8, x + 25, hy + 8), fill=(118, 122, 127)); db.arc((x + 9, hy - 8, x + 25, hy + 8), 200, 340, fill=(80, 82, 86), width=2)
    dh.ellipse((x + 9, hy - 8, x + 25, hy + 8), fill=110); dg.ellipse((x + 9, hy - 8, x + 25, hy + 8), fill=110)
db.text((L0, y + 28), 'P220 PRIMROSE', fill=INK, font=ft(13, True))
db.text((x + w - 14, y + 30), 'AMM 23-71-00', fill=INK, font=ft(11), anchor='ra')
db.line((L0, y + 47, x + w - 14, y + 47), fill=INK, width=1)
db.text((L0, y + 54), 'TAIL LASER - CREW PROCEDURES', fill=INK, font=ft(12, True))
TXT1 = ['1. Before engine start, confirm the THORNE', '   aft laser is set to GUNNER (panel 23-71).',
        '2. When SELECTED pilot must manually queue', '   targets and fire laser when in arc and', '   range!',
        '3. Keep personnel clear of the tail arc.']
for k, t in enumerate(TXT1): db.text((L0, y + 76 + k*13), t, fill=INK, font=ft(11, 2 <= k <= 4))
bx0, by0, bx1, by1 = L0, y + 160, x + w - 14, y + 252
db.rectangle((bx0, by0, bx1, by1), outline=INK, width=4)
for i, t in enumerate(('ENSURE LASER IS', 'UNDER GUNNER', 'CONTROL!')):
    db.text(((bx0 + bx1)//2, by0 + 20 + i*26), t, fill=INK, font=ft(21, True), anchor='mm')
TXT2 = ['NOTE: the laser draws from the capacitor bank.', 'Expect reduced jammer endurance after each', 'engagement. Allow 20 s recharge between bursts.',
        '4. After landing, set laser SAFE before', '   opening the aft service door.', '5. Report any self-illumination of the', '   tail or elevators to maintenance control.',
        'Ref: SB P220-23-0041 rev C']
for k, t in enumerate(TXT2): db.text((L0, y + 262 + k*13), t, fill=INK, font=ft(10 if k < 3 else 11, k < 3))
db.text((x + w//2 + 10, y + h - 14), '23-71-00  PAGE 4', fill=INK, font=ft(11), anchor='mm')
for tx in (x + 6, x + w - 76):          # translucent tape over the top corners
    t0 = Image.new('RGBA', (70, 20), (214, 206, 170, 150)); B.paste(Image.alpha_composite(B.crop((tx, y, tx + 70, y + 20)).convert('RGBA'), t0).convert('RGB'), (tx, y))
    dg.rectangle((tx, y, tx + 69, y + 19), fill=150)
dh.line((x + 40, y + 190, x + w - 50, y + 290), fill=134, width=2)   # a soft crease

# ================================================================== write maps
B.save(OUT + '/P220_cockpit_b.png')
hh_ = np.asarray(H.filter(ImageFilter.GaussianBlur(0.8)), np.float32)/255.0
dx = np.roll(hh_, -1, 1) - np.roll(hh_, 1, 1); dy = np.roll(hh_, -1, 0) - np.roll(hh_, 1, 0)
nx, ny, nz = -dx*4.0, dy*4.0, np.ones_like(hh_)
l = np.sqrt(nx*nx + ny*ny + nz*nz)
Image.fromarray(np.uint8(np.stack([(nx/l + 1)*127.5, (ny/l + 1)*127.5, (nz/l + 1)*127.5], -1))).save(OUT + '/P220_cockpit_n.png')
g = np.asarray(G, np.uint8)
M = np.zeros((S, S, 4), np.uint8); M[..., :3] = 10; M[..., 3] = g
Image.fromarray(M, 'RGBA').save(OUT + '/P220_cockpit_m.png')
ao = 255 - np.clip((128 - np.asarray(H, np.float32))*1.2, 0, 90)
Image.fromarray(np.uint8(np.asarray(Image.fromarray(np.uint8(ao)).filter(ImageFilter.GaussianBlur(2))))).save(OUT + '/P220_cockpit_ao.png')

# ================================================================== tac screen page mock (preview only; in game the page is drawn live)
sc = Image.new('RGB', (1024, 512), (4, 6, 9)); d = ImageDraw.Draw(sc)
_snap = {}
fnt = lambda p: ImageFont.truetype(FB, p)
c = (70, 200, 120); amb = (235, 160, 40); wht = (225, 225, 225)
x0, y0, w0, h0 = RT_REGIONS['pfd']
d.rectangle((x0 + 50, y0 + 40, x0 + 270, y0 + 200), fill=(30, 70, 130)); d.rectangle((x0 + 50, y0 + 200, x0 + 270, y0 + 300), fill=(110, 70, 35))
d.line((x0 + 50, y0 + 200, x0 + 270, y0 + 200), fill=wht, width=2)
for k in (-2, -1, 1, 2): d.line((x0 + 130, y0 + 200 - k*28, x0 + 190, y0 + 200 - k*28), fill=wht, width=2)
d.line((x0 + 105, y0 + 202, x0 + 145, y0 + 202), fill=amb, width=5); d.line((x0 + 175, y0 + 202, x0 + 215, y0 + 202), fill=amb, width=5)
d.rectangle((x0 + 6, y0 + 40, x0 + 46, y0 + 300), outline=wht); d.text((x0 + 8, y0 + 160), '250', fill=wht, font=fnt(15))
d.rectangle((x0 + 274, y0 + 40, x0 + 316, y0 + 300), outline=wht); d.text((x0 + 276, y0 + 160), '120', fill=wht, font=fnt(13))
d.arc((x0 + 60, y0 + 310, x0 + 260, y0 + 510), 200, 340, fill=wht, width=2); d.text((x0 + 145, y0 + 318), '090', fill=wht, font=fnt(15))
d.text((x0 + 10, y0 + 8), 'SPD   ALT   NAV', fill=c, font=fnt(14))
x0, y0, w0, h0 = RT_REGIONS['pfd']; _snap['pfd'] = sc.crop((x0, y0, x0 + w0, y0 + h0))
x0, y0, w0, h0 = RT_REGIONS['tac']
for r_ in (60, 120, 180): d.ellipse((x0 + 160 - r_, y0 + 300 - r_, x0 + 160 + r_, y0 + 300 + r_), outline=(40, 110, 70), width=2)
d.polygon([(x0 + 160, y0 + 290), (x0 + 150, y0 + 312), (x0 + 170, y0 + 312)], fill=c)
for k in range(7):
    px_, py_ = x0 + random.randint(30, 290), y0 + random.randint(40, 280); d.rectangle((px_ - 4, py_ - 4, px_ + 4, py_ + 4), outline=c)
d.text((x0 + 10, y0 + 8), 'MAP  40', fill=c, font=fnt(14))
x0, y0, w0, h0 = RT_REGIONS['tac']; _snap['tac'] = sc.crop((x0, y0, x0 + w0, y0 + h0))
d.rectangle((640, 0, 1023, 399), fill=(4, 6, 9))
x0, y0, w0, h0 = RT_REGIONS['sys']
for k, lab in enumerate(('N1', 'EGT')):
    for e in range(2):
        cx, cy = x0 + 90 + e*140, y0 + 70 + k*110
        d.arc((cx - 42, cy - 42, cx + 42, cy + 42), 150, 390, fill=wht, width=3); d.line((cx, cy, cx + 30, cy - 20), fill=c, width=3)
        d.text((cx - 16, cy + 18), lab, fill=wht, font=fnt(13))
d.text((x0 + 14, y0 + 270), 'FOB 9.8 T', fill=c, font=fnt(16)); d.text((x0 + 14, y0 + 300), 'BAY L  RDY  BAY R  RDY', fill=c, font=fnt(13))
d.text((x0 + 14, y0 + 330), 'LASER  CHG 100%', fill=amb, font=fnt(13))
x0, y0, w0, h0 = RT_REGIONS['sys']; _snap['sys'] = sc.crop((x0, y0, x0 + w0, y0 + h0))
x0, y0, w0, h0 = RT_REGIONS['annun']
cw = w0/len(CRIT)
for k, lab in enumerate(CRIT):
    bx = (int(x0 + k*cw + 2), y0 + 2, int(x0 + (k + 1)*cw - 2), y0 + h0 - 2)
    col = (180, 30, 25) if k < 3 else (190, 120, 20)
    lit = lab == 'MISSILE'
    d.rectangle(bx, fill=col if lit else (20, 18, 16)); d.text(((bx[0] + bx[2])/2, (bx[1] + bx[3])/2), lab, fill=(20, 10, 5) if lit else (120, 105, 90), font=fnt(12), anchor='mm')
x0, y0, w0, h0 = RT_REGIONS['lamps']
for k, lab in enumerate(LAMP_CELLS):
    cx, cy = x0 + (k % 8)*64, y0 + (k // 8)*28
    on = lab in ('GEAR DN', 'NAV', 'AP', 'ENG 1', 'ENG 2', 'RADAR')
    col = (60, 200, 90) if lab in ('GEAR DN', 'AP', 'A/THR', 'NAV', 'RADAR', 'ENG 1', 'ENG 2', 'APU', 'FLAP', 'SPD BRK', 'REV', 'BRAKE') else (220, 140, 30)
    d.rectangle((cx + 1, cy + 1, cx + 62, cy + 26), fill=col if on else (16, 16, 15))
    d.text((cx + 32, cy + 14), lab, fill=(15, 15, 10) if on else (110, 100, 85), font=fnt(11), anchor='mm')
for k, im_ in _snap.items(): sc.paste(im_, RT_REGIONS[k][:2])
sc.save(OUT + '/screen_tacScreenDisplay.png')

# ================================================================== knob and lamp maps for the model
import json
def _region(cx, cy):
    hits = [(w*h, n) for n, (x, y, w, h) in ATLAS.items() if x <= cx < x + w and y <= cy < y + h and n not in ('paint', 'dark')]
    return min(hits)[1] if hits else None
_kn = {}
for cx, cy, kind, r in KNOBS:
    n = _region(cx, cy)
    if n is None: continue
    x, y, w, h = ATLAS[n]
    _kn.setdefault(n, []).append(((cx - x)/w, 1.0 - (cy - y)/h, kind, r/w))
json.dump(_kn, open(os.path.join(CK, 'knobs.json'), 'w'), indent=0)
_lm = {}
for name, (x0, y0, x1, y1) in LAMPS:
    n = _region((x0 + x1)/2, (y0 + y1)/2); x, y, w, h = ATLAS[n]
    _lm.setdefault(n, []).append((name, (x0 - x)/w, 1.0 - (y1 + 1 - y)/h, (x1 + 1 - x)/w, 1.0 - (y0 - y)/h))
json.dump(_lm, open(os.path.join(CK, 'lamps.json'), 'w'), indent=0)
print('knobs', {k: len(v) for k, v in _kn.items()}, 'lamps', {k: len(v) for k, v in _lm.items()})
# atlas overlap check
names = [n for n in ATLAS if n not in ('paint', 'dark')]
for i, a in enumerate(names):
    for b in names[i + 1:]:
        A, Bb = ATLAS[a], ATLAS[b]
        if A[0] < Bb[0] + Bb[2] and Bb[0] < A[0] + A[2] and A[1] < Bb[1] + Bb[3] and Bb[1] < A[1] + A[3]: print('OVERLAP', a, b)
print('atlas written')
