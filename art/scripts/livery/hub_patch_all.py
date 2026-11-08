"""Write the wheel-hub patch (see HUB_RC in p220_paint.py) into every finished skin map, after the AO bake and the damage
alpha pass (both pad empty texels from the nearest island, which would cover it).
Usage: python3 hub_patch_all.py <dir> [<dir> ...]"""
import sys, os
os.environ.setdefault('P220_LIVERY', 'plink')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p220_paint as P
import numpy as np
q8 = lambda c: tuple(int(round(v * 255)) for v in c)
VAL = {'P220_skin_b.png': q8(P.HUB_GREY), 'P220_skin_civil_b.png': q8(P.HUB_GREY), 'P220_skin_pala_b.png': q8(P.HUB_GREY),
       'P220_skin_royal_b.png': q8(P.GOLD), 'P220_skin_blank_b.png': q8(P.HUB_COL['blank']),
       'P220_skin_n.png': (128, 128, 255), 'P220_skin_m.png': (255, 255, 255, 190), 'P220_skin_ao.png': 255,
       'P220_skin_dmg_b.png': (255, 255, 255, 255), 'P220_skin_dmg_n.png': (128, 128, 255)}
for d in sys.argv[1:]:
    for n, v in VAL.items():
        p = os.path.join(d, n)
        if os.path.exists(p): P.hub_patch(p, v)
