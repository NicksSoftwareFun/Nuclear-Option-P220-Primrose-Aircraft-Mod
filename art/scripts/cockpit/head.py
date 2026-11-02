"""P220 Primrose flight deck (first pass). Unity prefab-root coordinates (x right, y up, z forward).
Builds the meshes with UVs into one 2048 atlas (regions in ATLAS, painted by p220_cockpit_tex.py).
Library pieces follow the PB-22 cockpit scripts; layout is the P220's own."""
import os, math, json
CK = os.path.dirname(os.path.abspath(__file__))

FLOOR = -0.22
EYE = (-0.38, 0.82, 16.31)

ATLAS = {
    'paint':   (0, 0, 1024, 1024),
    'dark':    (1024, 0, 512, 512),
    'mfd':     (1536, 0, 256, 300),      # portrait display bezel
    'fcu':     (1792, 0, 256, 72),       # flight control unit on the glareshield
    'caut':    (1792, 72, 64, 48),       # master caution face (amber)
    'warn':    (1856, 72, 64, 48),       # master warning face (red, unlit print)
    'red':     (1920, 72, 64, 48),
    'ncol':    (1792, 128, 128, 256),    # shared non-critical lamps: column between the middle displays
    'nstrip':  (1024, 512, 640, 96),     # shared non-critical lamps: strip under the middle displays
    'efis':    (1664, 512, 256, 144),    # EFIS control panel under each outer display
    'gear':    (1024, 608, 105, 220),   # 0.3.20: same aspect as the 0.105 x 0.22 m panels (was 200 wide: clock drawn as an oval)
    'brk':     (1224, 608, 105, 220),
    'mcdu':    (1424, 656, 240, 300),
    'quad':    (1664, 656, 200, 340),
    'ped0':    (1024, 828, 360, 120),
    'ped1':    (1024, 948, 360, 120),
    'ped2':    (1384, 956, 280, 120),
    'con0':    (0, 1024, 300, 240),
    'con1':    (300, 1024, 300, 240),
    'con2':    (600, 1024, 300, 240),
    'ovh0':    (0, 1264, 300, 380),
    'ovh1':    (300, 1264, 300, 380),
    'ovh2':    (600, 1264, 300, 380),
    'ovh3':    (900, 1264, 300, 380),
    'grip':    (1920, 128, 128, 128),
    'pedal':   (1920, 256, 96, 160),
    'tread':   (1200, 1264, 512, 400),
    'carpet':  (1712, 1264, 336, 400),
    'door':    (0, 1664, 400, 384),
    'ssbase':  (1920, 416, 128, 128),
    'note':    (400, 1648, 300, 400),    # maintenance manual page taped to the captain's panel
}
