# Executed inside p220_parts.py (shares its namespace). The internal structure that shows when a part breaks away,
# following the PB-22 convention (stock aircraft carry their insides in every breakable part): frames and stringers in
# the fuselage, floor beams and stanchions under the cabin floor, the wing centre box, spars and ribs in the wings and
# tail, the radar in the nose and stiffened pressure bulkheads. An airliner is a much plainer structure than the
# bomber, so this is deliberately light: frames every second window pitch, a few stringers, no systems.
# Materials: P220_mech (frames, spars, ribs: the game's jet_mechanical) and P220_struct (floor beams, bulkhead
# stiffeners, centre box skins: the game's aircraft_structure). Everything stays at least 6 mm inside the skin.
STRUCT_ON = not os.environ.get('NOSTRUCT')
FPR = {'nose': (0.0, 0.9), 'cockpit_F': (0.9, 3.2), 'cockpit_R': (3.2, 9.5), 'fuselage_F': (9.5, 13.5),
       'fuselage': (13.5, 22.0), 'fuselage_R': (22.0, 30.5), 'tail': (30.5, 38.28)}
JOINTS = (9.5, 13.5, 22.0, 30.5)
FRAME_P = 2 * WIN_P                               # 1.12 m, every second window pitch
FR_D0, FR_D1 = CAB_D0 + 0.30, 37.6                # no frames in the flight deck (the cockpit lining covers it)
FR_IN, FR_DEPTH, FR_W = 0.006, 0.045, 0.03       # inset from the skin, depth, width (inside the cargo liner at 5 cm)
BOX_DF, BOX_DR, BOX_X = 14.2, 18.45, 1.70        # wing centre box: front and rear spar stations, half span (wing root)
BOX_TOP, BOX_BOT = -0.78, -1.82
WSPAR_F, WSPAR_R_IN, WSPAR_R_OUT = 0.16, 0.60, 0.66   # spar chord fractions (inner rear spar ahead of the gear bay)


def S_MECH(): return material('P220_mech', (0.36, 0.38, 0.40))
def S_STR(): return material('P220_struct', (0.55, 0.53, 0.47))


def fus_pt(d, a, off):
    """Point on the fuselage section at station d and section angle a, `off` metres inside the skin."""
    _, hw, zt, zb = fus(d); zc, hh = (zt + zb) / 2, (zt - zb) / 2; ex = 2.2
    c, s = math.cos(a), math.sin(a)
    x = hw * math.copysign(abs(c) ** (2 / ex), c); z = hh * math.copysign(abs(s) ** (2 / ex), s)
    r = math.hypot(x, z) or 1.0; k = max(0.0, 1 - off / r)
    return Vector((x * k, Y(d), zc + z * k))


def no_go(c, pad=0.05):
    """True where structure would cross an opening or a bay: doors, cabin windows, weapons bay, gear wells, nose bay."""
    dd = NOSE_Y - c.y; x = abs(c.x)
    if x > 0.5 and DOOR_D0 - pad < dd < DOOR_D1 + pad and DOOR_Z0 - pad < c.z < DOOR_Z1 + pad: return True
    if x > 0.5 and WIN_D0 < dd < WIN_D0 + WIN_P * WIN_N and ZA - pad < c.z < ZB + pad:
        k = (dd - WIN_D0) / WIN_P; f = k - math.floor(k)
        if 0.18 < f < 0.82: return True          # window openings sit in the middle of each pitch
    if BAY_D0 - pad < dd < BAY_D1 + pad and x < BAY_X + pad and c.z < BAY_TOP + pad: return True
    if abs(dd - GEAR_D) < WELL_R + pad + 0.03 and WELL_CX - WELL_RX - pad < x < SLOT_X1 + pad and c.z < WELL_ROOF + pad: return True
    if NB_D0 - pad < dd < NB_D1 + pad and x < NB_X + pad and c.z < NB_TOP + pad: return True
    return False


def lined(dd): return CAB_D0 - 0.05 < dd < CAB_D1 + 0.05 or CARGO_D0 - 0.05 < dd < CARGO_D1 + 0.05
def open_spans(a, b):
    """Pieces of [a, b] outside the crew cabin and the cargo bay."""
    out = [(a, b)]
    for c0, c1 in ((CAB_D0, CAB_D1), (CARGO_D0, CARGO_D1)):
        nxt = []
        for x0, x1 in out:
            if x1 <= c0 or x0 >= c1: nxt.append((x0, x1)); continue
            if x0 < c0: nxt.append((x0, c0))
            if x1 > c1: nxt.append((c1, x1))
        out = nxt
    return out


def ring_frame(m, d, depth, width, mat, n=24, mask=True):
    """Ring frame hugging the skin at station d (rectangular section), interrupted at openings."""
    angs = [2 * math.pi * i / n for i in range(n)]
    rings = [[fus_pt(dd, a, off) for a in angs] for dd, off in ((d - width / 2, FR_IN), (d + width / 2, FR_IN),
                                                                    (d + width / 2, FR_IN + depth), (d - width / 2, FR_IN + depth))]
    m.loft(rings, mat, wrap=True, keep=(lambda c: not no_go(c)) if mask else None)


def stringers(m, d0, d1, mat):
    """Longitudinal stringers: square 22 mm bars just inside the skin, kept clear of the window band."""
    angs = []
    for k in range(10):
        a = 2 * math.pi * (k + 0.5) / 10; z = fus_pt(15.0, a, 0).z
        if not (ZA - 0.10 < z < ZB + 0.10): angs.append(a)
    ds = sorted(set([d0, d1] + [x for x in drange(d0, d1, 1.2) if not (6.2 < x < 27.3)] + [x for x in (6.2, 27.3) if d0 < x < d1]))
    for a in angs:
        def sq(dd, a=a):
            p0 = fus_pt(dd, a, FR_IN); p1 = fus_pt(dd, a, FR_IN + 0.022)
            t = (fus_pt(dd, a + 0.01, FR_IN) - p0).normalized() * 0.011
            return [p0 - t, p0 + t, p1 + t, p1 - t]
        m.loft([sq(dd) for dd in ds], mat, keep=lambda c: not no_go(c))


def floor_beams(m, d0, d1, MECH, STR):
    """Transverse beams under the cabin floor at every frame, with a stanchion each side down to the lower frame."""
    for dd in frame_stations(d0, d1):
        if not (CAB_D0 + 0.1 < dd < CARGO_D1 - 0.1) or abs(dd - CAB_D1) < 0.08: continue
        zt = FLOOR_Z - 0.045; zb = zt - 0.12
        hw = skin_pt(1, dd, zb, -0.03).x
        m.box((0, Y(dd), (zt + zb) / 2), (2 * hw, 0.03, zt - zb), STR)
        m.box((0, Y(dd), zt - 0.01), (2 * hw, 0.09, 0.02), STR)       # top flange the floor panels sit on
        in_box = BOX_DF - 0.1 < dd < BOX_DR + 0.1
        for sx in (-1, 1):
            x = sx * 0.95; zl = skin_z(fus, 0.95, dd) + 0.05
            c = Vector((x, Y(dd), (zb + zl) / 2))
            if in_box or zl > zb - 0.1 or no_go(Vector((x, Y(dd), zl)), 0.08): continue
            m.box(c, (0.04, 0.04, zb - zl), MECH)


def frame_stations(d0, d1):
    out = []
    k0 = math.floor((FR_D0 - WIN_D0) / FRAME_P)
    for k in range(k0, 60):
        dd = WIN_D0 + k * FRAME_P
        if dd < FR_D0: continue
        if dd > FR_D1: break
        if not (d0 + 0.08 < dd < d1 - 0.08): continue
        if any(abs(dd - b) < 0.12 for b in (CAB_D0, CAB_D1, CARGO_D1)): continue
        out.append(dd)
    return out


def bulkhead_ribs(m, d, face, STR, n=8):
    """Radial stiffeners and a ring on one face of a flat pressure bulkhead (face = -1 forward, +1 aft)."""
    _, hw, zt, zb = fus(d); zc = (zt + zb) / 2; dd = d + face * 0.03
    ring_frame(m, d + face * 0.03, 0.06, 0.04, STR, n=24, mask=False)
    for k in range(n):
        a = 2 * math.pi * k / n; p = fus_pt(dd, a, 0.08); q = Vector((0, Y(dd), zc))
        mid = (p + q) / 2; L = (p - q).length
        ang = math.atan2(p.z - q.z, p.x - q.x)
        ob = Mesh(); ob.box((0, 0, 0), (L, 0.04, 0.05), STR)
        for v in ob.bm.verts:
            v.co = Matrix.Rotation(-ang, 3, 'Y') @ v.co + mid
        for f in ob.bm.faces:
            m.bm.faces.new([m.bm.verts.new(v.co) for v in f.verts]).material_index = m.mat(STR)
        ob.bm.free()
    m.cyl((0, Y(dd), zc), 'Y', 0.14, 0.05, STR, seg=16)


def centre_box(m, MECH, STR):
    """Wing centre box under the cabin floor: front and rear spar webs, upper and lower skins, three ribs."""
    xs = drange(-BOX_X, BOX_X, BOX_X / 6)
    def web(dd, x0, x1, z0, z1):
        m.box(((x0 + x1) / 2, Y(dd), (z0 + z1) / 2), (x1 - x0, 0.03, z1 - z0), MECH)
        for z in (z0 + 0.03, z1 - 0.03):
            m.box(((x0 + x1) / 2, Y(dd), z), (x1 - x0, 0.14, 0.03), MECH)          # spar caps
        for x in drange(x0 + 0.15, x1 - 0.15, 0.35):
            m.box((x, Y(dd + 0.03), (z0 + z1) / 2), (0.03, 0.05, z1 - z0 - 0.08), MECH)   # web stiffeners
    web(BOX_DF, -BOX_X, BOX_X, BOX_BOT, BOX_TOP)
    web(BOX_DR, -0.55, 0.55, BOX_BOT + 0.05, WELL_ROOF - 0.04)
    rear = GEAR_D - WELL_R - 0.10
    L = rear - BOX_DF
    for z in (BOX_TOP - 0.015, BOX_BOT + 0.015):
        m.box((0, Y(BOX_DF + L / 2), z), (2 * BOX_X, L, 0.02), STR)
    for x in (-BOX_X + 0.02, -0.9, 0.0, 0.9, BOX_X - 0.02):
        m.box((x, Y(BOX_DF + L / 2), (BOX_TOP + BOX_BOT) / 2), (0.03, L, BOX_TOP - BOX_BOT - 0.04), MECH)
    m.box((0, Y(BOX_DF + L), (BOX_TOP + BOX_BOT) / 2), (2 * BOX_X, 0.03, BOX_TOP - BOX_BOT), MECH)   # closing rib ahead of the wells


# ------------------------------------------------------------------ wings and tail
def foil_zs(le, c, t, z0, u, camber=0.02):
    th = 5 * t * (0.2969 * math.sqrt(max(u, 0)) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4) * c
    cz = camber * c * 4 * u * (1 - u)
    return z0 + cz + th, z0 + cz - th


def spar(m, sec, ss, u, mat, ins=0.012, keep=None):
    """I-section spar along the stations ss at chord fraction u. sec(s) -> (point(u, z), le, c, t, zref, camber)."""
    web, caps = [], []
    for s in ss:
        P, le, c, t, z0, cam = sec(s)
        up, lo = foil_zs(le, c, t, z0, u, cam); up -= ins; lo += ins
        web.append([P(u - 0.012 / c, lo), P(u + 0.012 / c, lo), P(u + 0.012 / c, up), P(u - 0.012 / c, up)])
        caps.append([[P(u - 0.05 / c, z), P(u + 0.05 / c, z), P(u + 0.05 / c, z - sg * 0.018), P(u - 0.05 / c, z - sg * 0.018)]
                     for z, sg in ((up, 1), (lo, -1))])
    m.loft(web, mat, keep=keep)
    for j in range(2): m.loft([cp[j] for cp in caps], mat, keep=keep)


def rib(m, sec, s, ua, ub, mat, ins=0.012, depth=0.05, w=0.02, posts=3, keep=None):
    """Rib at station s from chord fraction ua to ub: a flange band round the inset aerofoil plus vertical posts."""
    rings = []
    for ds_, dep in ((-w / 2, 0), (w / 2, 0), (w / 2, depth), (-w / 2, depth)):
        P, le, c, t, z0, cam = sec(s + ds_)
        us = [ua + (ub - ua) * (1 - math.cos(math.pi * i / 6)) / 2 for i in range(7)]
        top = []; bot = []
        for u in us:
            up, lo = foil_zs(le, c, t, z0, u, cam)
            if up - lo < 2 * (ins + depth) + 0.01: up = lo = (up + lo) / 2
            top.append(P(u, up - ins - dep)); bot.append(P(u, lo + ins + dep))
        # ends: pull the band in from the end fractions by the depth
        rings.append(top + list(reversed(bot)))
    m.loft(rings, mat, wrap=True, keep=keep)
    P, le, c, t, z0, cam = sec(s)
    for k in range(posts):
        u = ua + (ub - ua) * (k + 1) / (posts + 1)
        up, lo = foil_zs(le, c, t, z0, u, cam)
        a, b = P(u, lo + ins + depth), P(u, up - ins - depth)
        if (b - a).length < 0.05: continue
        if keep and not keep((a + b) / 2): continue
        m.box((a + b) / 2, (0.03, 0.03, (b - a).length), mat)


def wing_sec(sx):
    def sec(s):
        le, c, t, z = wing_at(s)
        return (lambda u, zz: Vector((sx * s, Y(le + u * c), zz))), le, c, t, z, 0.02
    return sec


def wing_struct(m, name, sx):
    MECH = S_MECH(); sec = wing_sec(sx)
    def keep(c):
        x = abs(c.x); dd = NOSE_Y - c.y
        return not (abs(dd - GEAR_D) < SLOT_W + 0.10 and WELL_CX - WELL_RX - 0.1 < x < SLOT_X1 + 0.10) and not no_go(c)
    span = {'wing1a': (1.7, 3.0, 0.0), 'wing1b': (3.0, 7.0, 0.0), 'wing2': (7.0, 11.5, SC_), 'wing3': (11.5, 16.2, SC_)}
    s0, s1, u0 = span[name]
    ur = WSPAR_R_IN if s1 <= 7.0 else WSPAR_R_OUT
    ss = sorted([s0 + 0.01, s1 - 0.01] + [b for b in (1.86, 6.1) if s0 + 0.05 < b < s1 - 0.05])
    spar(m, sec, ss, max(WSPAR_F, u0 + 0.03), MECH, keep=keep)
    spar(m, sec, ss, ur, MECH, keep=keep)
    n = max(1, int(round((s1 - s0) / 1.5)))
    for k in range(n + 1):
        s = s0 + 0.03 + (s1 - s0 - 0.06) * k / n
        rib(m, sec, s, max(u0 + 0.02, 0.025), ur + 0.02, MECH, keep=keep)
SC_ = 0.13


def ht_sec(sx):
    def sec(s):
        le, c, t = lerp_tab(HT, s)
        return (lambda u, zz: Vector((sx * s, Y(le + u * c), zz))), le, c, t, HZ + s * HDIH, 0.0
    return sec


def fin_sec():
    def sec(z):
        le, c, t = lerp_tab(FIN, z)
        return (lambda u, xx: Vector((xx, Y(le + u * c), z))), le, c, t, 0.0, 0.0
    return sec


def tail_struct(m, name):
    MECH = S_MECH()
    if name.startswith('hstab_'):
        sx = -1 if name.endswith('_L') else 1; sec = ht_sec(sx)
        ss = [0.62, 0.95, 6.10]
        spar(m, sec, ss, 0.14, MECH, ins=0.008); spar(m, sec, ss, 0.62, MECH, ins=0.008)
        for s in drange(0.65, 6.0, 1.8): rib(m, sec, s, 0.04, 0.66, MECH, ins=0.008, depth=0.03, posts=2)
    elif name.startswith('vstab_'):
        z0, z1 = (1.2, FIN_SPLIT) if name.endswith('_L') else (FIN_SPLIT, 7.55)
        sec = fin_sec(); zs = sorted([z0 + 0.02, z1 - 0.05] + ([1.9] if z0 + 0.05 < 1.9 < z1 - 0.05 else []))
        spar(m, sec, zs, 0.14, MECH, ins=0.008); spar(m, sec, zs, 0.62, MECH, ins=0.008)
        for z in drange(max(z0, 1.85) + 0.05, z1 - 0.08, 1.6): rib(m, sec, z, 0.04, 0.66, MECH, ins=0.008, depth=0.03, posts=2)


def nose_radar(m):
    MECH = S_MECH(); STR = S_STR()
    c = Vector((0, Y(0.62), -0.15))
    lathe(m, c, (0, 1, 0), [(0.0, 0.0), (0.0, 0.34), (-0.03, 0.34), (-0.03, 0.0)], MECH, 16)     # flat plate antenna
    m.box(c + Vector((0, -0.12, 0)), (0.16, 0.20, 0.16), STR)                                   # drive unit
    m.box(c + Vector((0, -0.24, 0)), (0.30, 0.06, 0.30), STR)                                   # mount on the bulkhead


def structure(name, m):
    if not STRUCT_ON: return
    MECH, STR = S_MECH(), S_STR()
    if name in FPR:
        d0, d1 = FPR[name]
        # 0.3.27: structure behind the cargo liner and the crew cabin is only seen when a section breaks up, so
        # those spaces keep every second frame and no stringers or floor beams
        for i, dd in enumerate(frame_stations(d0, d1)):
            if lined(dd) and round((dd - WIN_D0) / FRAME_P) % 2: continue
            ring_frame(m, dd, FR_DEPTH, FR_W, MECH)
        for j in JOINTS[:3]:                         # heavy frames either side of a production break
            if abs(d0 - j) < 1e-6: ring_frame(m, j + 0.045, 0.085, 0.05, MECH)
            if abs(d1 - j) < 1e-6: ring_frame(m, j - 0.045, 0.085, 0.05, MECH)
        a, b = max(d0, FR_D0 - 0.3), min(d1, FR_D1)
        for sa, sb in open_spans(a, b):
            if sa < sb - 0.3: stringers(m, sa + 0.03, sb - 0.03, MECH)
        floor_beams(m, d0, d1, MECH, STR)
        if name == 'fuselage': centre_box(m, MECH, STR)
        if name == 'cockpit_F': bulkhead_ribs(m, 0.9, -1, STR)
        if name == 'fuselage_R':
            bulkhead_ribs(m, 30.5, 1, STR); ring_frame(m, 30.5 - 0.05, 0.085, 0.05, MECH)
        if name == 'tail': ring_frame(m, 30.5 + 0.05, 0.085, 0.05, MECH)
        if name == 'nose': nose_radar(m)
    for w in ('wing1a', 'wing1b', 'wing2', 'wing3'):
        if name in (w + '_L', w + '_R'): wing_struct(m, w, -1 if name.endswith('_L') else 1)
    if name.startswith(('hstab_', 'vstab_')): tail_struct(m, name)
    if name in ('engine_L', 'engine_R'): engine_struct(m, (-1 if name.endswith('_L') else 1) * 5.35, -2.25)


# ------------------------------------------------------------------ engine core (the engine inside each nacelle)
# The core sits inside the core cowl (13.36-16.5, r 0.42-0.62): compressor, combustor and turbine cases with flanges, fuel
# manifold, accessory gearbox, pipes, and the mounts: a forward mount on the fan case top, upper and lower bifurcation
# struts across the bypass duct carrying the aft mount and the services, and a last turbine stage seen in the core exhaust
# annulus round the (now smaller) exhaust plug. Material P220_mech = the game's jet_mechanical engine texture.
def engine_struct(m, cx, cz):
    MECH = S_MECH(); STR = S_STR(); DARK = material('P220_dark', (0.05, 0.05, 0.06))
    ax = Vector((0, -1, 0)); c0 = lambda dd: Vector((cx, Y(dd), cz))
    # cases: (axial offset from 13.45, radius)
    prof = [(0.0, 0.30), (0.25, 0.33), (0.6, 0.36), (1.15, 0.40), (1.25, 0.45), (1.75, 0.46), (1.95, 0.42), (2.55, 0.40), (2.85, 0.47), (2.95, 0.47)]
    lathe(m, c0(13.45), ax, prof, MECH, 16, cap0=True)
    for dd, r in ((14.05, 0.355), (15.2, 0.46), (15.85, 0.41)):
        lathe(m, c0(dd - 0.012), ax, [(0, r), (0, r + 0.022), (0.024, r + 0.022), (0.024, r)], MECH, 16)   # case flanges
    # fuel manifold ring round the combustor and its injector feeds
    k = 6; tube = [(0.025 * math.cos(2 * math.pi * j / k), 0.495 + 0.025 * math.sin(2 * math.pi * j / k)) for j in range(k + 1)]
    lathe(m, c0(14.85), ax, tube, DARK, 16)
    for j in range(6):
        a = math.radians(60 * j + 30)
        p0 = c0(14.85) + Vector((0.495 * math.sin(a), 0, 0.495 * math.cos(a))); p1 = c0(14.85) + Vector((0.455 * math.sin(a), 0, 0.455 * math.cos(a)))
        rod(m, p0, p1, 0.012, DARK, 6)
    # accessory gearbox under the compressor, with two drive pads
    m.box(c0(14.05) + Vector((0, 0, -0.395)), (0.34, 0.55, 0.09), MECH)
    for dd in (13.9, 14.2): m.cyl(c0(dd) + Vector((0, 0, -0.355)), 'Z', 0.05, 0.05, DARK, seg=10)
    # pipes and harnesses along the core
    for a_deg, r, d0, d1, rr in ((60, 0.43, 13.9, 15.9, 0.014), (-60, 0.43, 13.9, 15.9, 0.014), (120, 0.44, 14.1, 15.7, 0.011), (-130, 0.44, 14.1, 15.7, 0.011)):
        a = math.radians(a_deg); rod(m, c0(d0) + Vector((r * math.sin(a), 0, r * math.cos(a))), c0(d1) + Vector((r * math.sin(a), 0, r * math.cos(a))), rr, DARK, 6)
    # forward mount: a yoke on the fan case top up to the cowl crown
    for sg in (-1, 1): m.box(c0(13.55) + Vector((sg * 0.12, 0, 1.015)), (0.05, 0.22, 0.10), MECH)
    m.box(c0(13.55) + Vector((0, 0, 1.06)), (0.32, 0.26, 0.04), MECH)
    # bifurcation struts across the bypass duct (top carries the aft mount, bottom the services): thin streamlined walls
    for top in (1, -1):
        rings = []
        for dd in drange(14.9, 16.3, 0.35):
            r0 = prof_r([(13.36, 0.42), (14.06, 0.52), (14.96, 0.60), (16.5, 0.62)], dd) - 0.01; r1 = prof_r(NAC_IN, dd) + 0.01
            t = 0.035 * math.sin(math.pi * min(1, max(0, (dd - 14.9) / 1.4))) + 0.006
            rings.append([c0(dd) + Vector((x, 0, top * r)) for x, r in ((-t, r0), (t, r0), (t, r1), (-t, r1))])
        m.loft(rings, STR if top > 0 else MECH)
    # aft mount: links from the turbine case up to the top bifurcation
    for sg in (-1, 1): rod(m, c0(15.5) + Vector((sg * 0.18, 0, 0.40)), c0(15.6) + Vector((sg * 0.04, 0, 0.60)), 0.025, MECH, 8)
    # last turbine stage in the core exhaust: a dark disc and forty short blades between the plug and the cowl lip
    lathe(m, c0(16.30), ax, [(0, 0.60), (0, 0.0)], DARK, 16)
    for b in range(20):
        ph = 360.0 * b / 20
        rows = [[nac_pt(cx, cz, 16.24, r, ph - 2.0), nac_pt(cx, cz, 16.29, r, ph + 2.0)] for r in (0.46, 0.60)]
        m.loft([row + [p + Vector((0, 0.006, 0)) for p in reversed(row)] for row in rows], MECH, cap0=True, cap1=True)
    lathe(m, c0(16.0), ax, [(0, 0.605), (0.5, 0.61)], MECH, 16)          # turbine case lining inside the cowl lip
