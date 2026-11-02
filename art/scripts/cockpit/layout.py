
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
# 0.3.20: displays sat at the pilot's knees; whole panel and glareshield raised 0.30 m and moved 0.19 m forward (three passes),
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
    # footwell back wall well forward of the panel foot, so the pendulum pedals hang in an open well
    boxw('cockpit_int', (0, (FLOOR + PANEL_BOT)/2, 17.78), (1.7, PANEL_BOT - FLOOR + 0.06, 0.02), paint='dark')
    boxw('cockpit_int', (0, PANEL_BOT + 0.01, 17.55), (1.7, 0.02, 0.46), paint='dark', skip=('+y',))

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
    fr = panel_frame(xe + 0.02, DISP_Y - 0.03)
    tube('cockpit_int', fr.p(0, 0, 0.012), fr.p(0, 0.03, 0.10), 0.007, 8, paint='paint')
    prism('cockpit_int', Frame(fr.p(0, 0.03, 0.10), fr.u, fr.v, fr.n), circle(0.022, 12), 0.028, chamfer=0.004, proud=0.014,
          paint='paint', back=True)                                   # wheel-shaped gear knob, white as on the real thing

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
    yb = PANEL_BOT - 0.02
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
    flat = lambda x, z, y=PED_TOP: Frame((x, y, z), (1, 0, 0), (0, 0, 1), (0, 1, 0))
    # two MCDU keypads aft of the thrust levers on a wedge tilted toward the crew
    W = Frame((0, PED_TOP + 0.03, 16.50), (1, 0, 0), (0, 0, 1), (0, 1, 0)).pitch(-14)
    prism('cockpit_int', W, rect(2*PED_HALF - 0.01, 0.27), 0.06, paint='dark', proud=0.0)
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
    for s in (-1, 1):
        x = s*SX
        # flat stem through the slot (a little narrower than it), from below the top up to the handle
        st = 0.004; y0 = QTOP - SD + 0.004; y1 = QTOP + 0.062
        boxw('throttle', (x, (y0 + y1)/2, piv[2]), (2*st, y1 - y0, 0.018), paint='dark')
        # handle: a rounded block leaning slightly forward, grip printed on the crew side, reverser latch in front
        hc = (x, QTOP + 0.075, piv[2] + 0.004)
        prism('throttle', Frame(hc, (1, 0, 0), (0, 1, 0), (0, 0, -1)).pitch(-8), rrect(0.034, 0.034, 0.010, 2), 0.05, chamfer=0.004,
              proud=0.025, paint='dark', back=True, decal='grip', decal_box=(0.034, 0.034))
        prism('throttle', Frame(vadd(hc, (0, -0.014, 0.027)), (1, 0, 0), (0, 1, 0), (0, 0, 1)), rect(0.024, 0.010), 0.012, proud=0.006,
              paint='paint', back=True)
    PIVOTS['throttle'] = piv
    # speed brake lever left of the thrust levers, flap lever right (fixed for now)
    for s, knob in ((-1, rect(0.05, 0.02)), (1, rrect(0.05, 0.03, 0.008, 2))):
        x = s*0.125
        prism('cockpit_int', flat(x, 16.84, PED_TOP + 0.004), rect(0.05, 0.26), 0.004, paint='dark', proud=0.004)
        b0 = (x, PED_TOP + 0.005, 16.78); b1 = (x, PED_TOP + 0.08, 16.76)
        tube('cockpit_int', b0, b1, 0.006, 6, paint='paint')
        prism('cockpit_int', Frame(b1, (1, 0, 0), (0, 1, 0), (0, 0, -1)), knob, 0.025, chamfer=0.003, proud=0.0125, back=True,
              paint='paint' if s > 0 else 'dark')
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
def consoles():
    for s in (-1, 1):
        xo = 1.40
        xi = s*CON_IN; xo_ = s*xo
        zs = [CON_Z0 + k*(CON_Z1 - CON_Z0)/8 for k in range(9)]
        # top: one strip of quads, the outboard edge clamped to the wall later
        for z0, z1 in zip(zs, zs[1:]):
            face_toward('cockpit_int', [(xi, CON_TOP, z0), (xo_, CON_TOP, z0), (xo_, CON_TOP, z1), (xi, CON_TOP, z1)], (0, 1, 0),
                        'P220_cockpit', None, 'dark')
            face_toward('cockpit_int', [(xi, CON_BOT, z0), (xi, CON_TOP, z0), (xi, CON_TOP, z1), (xi, CON_BOT, z1)], (-s, 0, 0),
                        'P220_cockpit', None, 'paint')
            face_toward('cockpit_int', [(xi, CON_BOT, z0), (xo_, CON_BOT, z0), (xo_, CON_BOT, z1), (xi, CON_BOT, z1)], (0, -1, 0),
                        'P220_cockpit', None, 'dark')
        for z, want in ((CON_Z0, -1), (CON_Z1, 1)):
            face_toward('cockpit_int', [(xi, CON_BOT, z), (xo_, CON_BOT, z), (xo_, CON_TOP, z), (xi, CON_TOP, z)], (0, 0, want),
                        'P220_cockpit', None, 'paint')
        flat = lambda x, z, y=CON_TOP: Frame((x, y, z), (1, 0, 0), (0, 0, 1), (0, 1, 0))
        # side stick well and boot (the stick itself moves: part stick_L / stick_R)
        px, py, pz = STICK_PIVOT[s]
        prism('cockpit_int', flat(px, pz), rrect(0.13, 0.15, 0.012, 2), 0.004, decal='ssbase', proud=0.004, decal_box=(0.13, 0.15))
        for k, r in enumerate((0.040, 0.032, 0.025)):
            prism('cockpit_int', flat(px, pz, py + 0.002 + 0.012*k), circle(r, 14), 0.012, chamfer=0.003, proud=0.012, paint='dark')
        # armrest pad outboard-aft of the stick
        # console panels aft of the stick (tiller, lights, audio)
        for k, (z, reg) in enumerate(((16.64, 'con0'),)):
            prism('cockpit_int', flat(s*1.05, z), rect(0.20, 0.22), 0.01, decal=reg if s < 0 else ('con2' if k == 0 else 'con1'),
                  chamfer=0.002, proud=0.006)
        # nose wheel tiller handwheel inboard of the armrest (pilot side) / chart holder (co-pilot side)
        if s < 0:
            c = (s*0.86, CON_TOP + 0.03, 16.64)
            prism('cockpit_int', flat(c[0], c[2], CON_TOP + 0.002), circle(0.05, 16), 0.002, decal='ssbase', proud=0.002, decal_box=(0.13, 0.15))
            tube('cockpit_int', (c[0], CON_TOP, c[2]), c, 0.01, 8)
            prism('cockpit_int', flat(c[0], c[2], c[1]), circle(0.045, 16), 0.016, chamfer=0.005, proud=0.016, paint='dark', back=True)
        stick(s)

def stick(s):
    side = 'L' if s < 0 else 'R'
    part = 'stick_' + side
    px, py, pz = STICK_PIVOT[s]
    PIVOTS[part] = (px, py, pz)
    # shaft leans forward 8 deg; grip cants outboard 6 deg, pistol style
    lean = math.radians(8.0)
    top = (px, py + 0.075, pz + 0.075*math.tan(lean))
    tube(part, (px, py, pz), top, 0.011, 8, paint='paint')
    tube(part, (px, py + 0.01, pz), (px, py + 0.022, pz), 0.022, 10, paint='dark')
    gu = vnorm((s*math.sin(math.radians(6)), math.cos(math.radians(6)), math.sin(math.radians(12))))
    G = Frame(top, (1, 0, 0), gu, vnorm(vcross((1, 0, 0), gu)))
    # grip body: stacked rounded sections, fatter at the palm
    prev = None
    for k, (h, w, d) in enumerate(((0.0, 0.030, 0.036), (0.035, 0.036, 0.044), (0.075, 0.034, 0.042), (0.105, 0.030, 0.040))):
        c = vadd(top, vmul(gu, h))
        fr = Frame(c, (1, 0, 0), vnorm(vcross(gu, (1, 0, 0))), gu)
        if prev is not None:
            A = [prev[0].p(*pt) for pt in rrect(*prev[1], 0.012, 2)()]; B_ = [fr.p(*pt) for pt in rrect(w, d, 0.012, 2)()]
            for i in range(len(A)):
                j = (i + 1) % len(A)
                face_toward(part, [A[i], A[j], B_[j], B_[i]], vsub(vmul(vadd(A[i], A[j]), 0.5), c), 'P220_cockpit', None, 'dark')
        prev = (fr, (w, d))
    capf = prev[0]
    prism(part, capf, rrect(0.030, 0.040, 0.012, 2), 0.012, chamfer=0.006, proud=0.012, paint='dark')
    # red take-over push button on top, trigger on the front, thumb switch inboard
    prism(part, capf.at(-s*0.006, -0.008), circle(0.007, 10), 0.004, proud=0.016, decal='red', decal_box=(0.3, 0.3))
    hat = capf.at(s*0.006, 0.010)
    prism(part, hat, circle(0.005, 8), 0.006, proud=0.018, paint='paint')
    fwd = vnorm(vcross(gu, (1, 0, 0)))
    fwd = fwd if fwd[2] > 0 else vmul(fwd, -1)
    trg = Frame(vadd(top, vmul(gu, 0.075)), (1, 0, 0), gu, fwd)
    prism(part, trg, rrect(0.012, 0.024, 0.004, 2), 0.012, proud=0.030, paint='paint', back=True)

# ================================================================== rudder pedals: sliding pedals on floor channels (PB-22 mechanism)
# 0.3.14: the 0.3.13 pendulum pedals hung behind the panel and could not be seen. As on the PB-22 each pedal
# rides a carriage in a floor channel, sits where the pilot can see it under the panel lip, and slides +-6 cm fore and
# aft with the rudder (the plugin moves the pedal part along its local z).
PEDAL_CZ = 17.16          # carriage centre at rest
PEDAL_TRAVEL = 0.06
PEDAL_FW = FLOOR + 0.10   # raised footrest under each pilot's pedals, so the pedals stand where the pilot can see them
def pedals():
    base = PEDAL_FW + 0.006
    for s in (-1, 1):
        x = s*0.40
        side = 'L' if s < 0 else 'R'
        boxw('cockpit_int', (x, (FLOOR + PEDAL_FW)/2, PEDAL_CZ + 0.02), (0.46, PEDAL_FW - FLOOR, 0.62), paint='dark', skip=('-y',))
        for dx in (-0.09, 0.09):
            px = x + dx
            L = 0.11 + 2*PEDAL_TRAVEL + 0.03
            boxw('cockpit_int', (px, base + 0.003, PEDAL_CZ), (0.074, 0.006, L), paint='dark', skip=('-y',))
            for rx in (-0.033, 0.033):
                boxw('cockpit_int', (px + rx, base + 0.014, PEDAL_CZ), (0.008, 0.022, L), paint='dark', skip=('-y',))
                boxw('cockpit_int', (px + rx, base + 0.027, PEDAL_CZ), (0.014, 0.004, L), paint='paint', skip=('-y',))
            for ez in (PEDAL_CZ - L/2 + 0.006, PEDAL_CZ + L/2 - 0.006):
                boxw('cockpit_int', (px, base + 0.012, ez), (0.058, 0.018, 0.012), paint='paint', skip=('-y',))
            name = 'pedal_' + side + ('L' if dx < 0 else 'R')
            PIVOTS[name] = MOVERS[name] = (px, base + 0.04, PEDAL_CZ)
            boxw(name, (px, base + 0.016, PEDAL_CZ), (0.050, 0.020, 0.11), paint='dark', skip=('-y',))
            for ez in (PEDAL_CZ - 0.045, PEDAL_CZ + 0.045):
                boxw(name, (px, base + 0.012, ez), (0.064, 0.012, 0.016), paint='paint', skip=('-y',))
            # pedal face leaning back 20 degrees on a heel hinge block and a rear brace
            fr = Frame((px, base + 0.095, PEDAL_CZ - 0.03), (1, 0, 0), (0, 1, 0), (0, 0, -1)).pitch(-20)
            prism(name, fr, rrect(0.08, 0.14, 0.012, 2), 0.025, chamfer=0.004, paint='dark', back=True, decal='pedal', decal_box=(0.08, 0.14))
            heel = fr.p(0, -0.07, -0.012)
            boxw(name, (px, (heel[1] + base + 0.026)/2, heel[2]), (0.06, max(heel[1] - base - 0.026, 0.004) + 0.012, 0.022), paint='dark', skip=('-y',))
            tube(name, fr.p(0, 0.04, -0.026), (px, base + 0.026, PEDAL_CZ + 0.05), 0.008, 6)

# ================================================================== floor, walls, ceiling, overhead, bulkhead
BULK_Z = 14.95          # 0.3.22: moved 0.47 m aft, clear of the seat backs and out of the side window view
def floor():
    flat = lambda x, y, z: Frame((x, y, z), (1, 0, 0), (0, 0, 1), (0, 1, 0))
    zs = [BULK_Z, 15.90, 16.40, 16.90, 17.40, 17.75]
    for z0, z1 in zip(zs, zs[1:]):
        w = min(hull_x(FLOOR, z0), hull_x(FLOOR, z1)) - 0.03
        prism('cockpit_int', flat(0, FLOOR, (z0 + z1)/2), rect(2*w, z1 - z0 - 0.006), 0.01, decal='carpet', decal_box=(2*w, z1 - z0 - 0.006), proud=0.0)
    for s in (-1, 1):   # heel plates under the pedals
        prism('cockpit_int', flat(s*0.40, PEDAL_FW + 0.004, 16.98), rect(0.36, 0.22), 0.004, decal='tread', decal_box=(0.36, 0.34), proud=0.004)

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
            hw, zt, zb = fus(NOSE_Y - c[2]); o = (0.0, max(min(c[1], 0.9), 0.3), c[2])
            if any(_ray_hits(o, vnorm(vsub(p, o))) for p in q + [c]): continue
            face_toward('cockpit_int', q, vsub(o, c), 'P220_cabin')

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
            A.append(vadd(p, vmul(r, 0.004))); b = vadd(p, vmul(r, 0.055)); Bq.append(b); C.append(vadd(b, vmul(t, 0.12)))
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
        p = hull_pt(a, BULK_Z, 0.03)
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
    cb = Frame((-0.62, FLOOR + 1.88, BULK_Z), (-1, 0, 0), (0, 1, 0), (0, 0, 1))
    prism('cockpit_int', cb, rect(0.34, 0.22), 0.02, chamfer=0.003, proud=0.02, paint='dark')
    for r_ in range(4):
        for c_ in range(8):
            prism('cockpit_int', cb.at(-0.14 + c_*0.04, 0.075 - r_*0.05), circle(0.007, 6), 0.012, proud=0.032, paint='paint')

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
    prism('cockpit_int', F, rect(0.68, L + 0.04), 0.12, paint='paint', proud=0.0)
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
            h = [hull_x(v[1] + dy, v[2] + dz) for dy in (-0.03, 0, 0.03) for dz in (-0.03, 0, 0.03)]
            h = [t for t in h if t]
            if not h: continue
            lim = min(h) - inset
            if abs(v[0]) > lim:
                V[i] = (math.copysign(lim, v[0]),) + tuple(v[1:]); moved += 1
    CLAMPED[0] = moved
CLAMPED = [0]

# ---- a maintenance manual page taped to the captain's panel, outboard of his outer display
def manual_page():
    fr = panel_frame(-0.742, DISP_Y + 0.048).roll(3.0)     # bigger page (23: 40), lapping just past the panel's outer edge
    prism('cockpit_int', fr, rect(0.123, 0.164), 0.0008, proud=0.0132, decal='note', decal_box=(0.123, 0.164), knobs=False)

def build_all(with_liner=True):
    PARTS.clear(); SCREENS.clear(); PIVOTS.clear(); MOVERS.clear()
    panel_body(); displays(); ys = noncritical(); lower_panels(ys); manual_page(); glareshield()
    pedestal(); consoles(); pedals(); floor(); bulkhead(); overhead()
    if with_liner: liner(); window_trim()
    simple(); clamp_to_hull()
    return PARTS

def tri_count(parts=None):
    parts = parts or PARTS
    return {k: sum(len(f[0]) - 2 for f in p['f']) for k, p in parts.items()}

if __name__ == '__main__':
    import time; t = time.time()
    build_all()
    tc = tri_count(); print(tc, 'total', sum(v for k, v in tc.items() if 'simple' not in k), 'clamped', CLAMPED[0], '%.1fs' % (time.time() - t))
