"""P220: bake ambient occlusion for the P220_skin atlas (adapted from the PB-22 baker) with Cycles (CPU) and level it like the stock skins (mean ~0.85).
Usage: python3 tex_bake_ao.py <pb22_detail.blend> <maps.npz> <out PB22_skin_ao.png> [size=4096] [samples=48]
The .blend is only read (never saved). Pose: rest pose with the gear down and the gear doors closed (same as
tex_geom.py); the gear legs, wheels and struts are hidden so they leave no blobs on the skin.
Quick mode: P220_AO_ONLY=<part,...> bakes only those skin parts (each part bakes on its own anyway), and with
PB22_PATCH_MASK=<mask.npy> PB22_PATCH_FROM=<old ao png> only the masked texels replace the old AO."""
import bpy, sys, os, math
import numpy as np

def coll_objs(c):
    yield from c.objects
    for ch in c.children: yield from coll_objs(ch)

a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
blend, maps, out = a[0], a[1], a[2]
S = int(a[3]) if len(a) > 3 else 4096
SAMPLES = int(a[4]) if len(a) > 4 else 48
TARGET_MEAN = 0.85

bpy.ops.wm.open_mainfile(filepath=blend)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = SAMPLES
if sc.world is None: sc.world = bpy.data.worlds.new('w')
sc.world.light_settings.distance = 0.6
for cn in ('GUIDES', 'COLLISION', 'FX', 'PROXY'):
    c = bpy.data.collections.get(cn)
    if c:
        for o in coll_objs(c):
            if o: o.hide_render = True
HIDE = ('wheel_', 'gearstay', 'gearact', 'gear_F', 'revcyl', 'revrod', 'fdoor_arm')
model = bpy.data.collections['MODEL']
skin = []
for o in model.objects:
    if o is None or o.type != 'MESH': continue
    if o.name.startswith(HIDE):
        o.hide_render = True; continue
    if any(mm and mm.name == 'P220_skin' for mm in o.data.materials):
        skin.append(o)
    for p in o.data.polygons: p.use_smooth = True
img = bpy.data.images.new('P220_skin_ao_bake', S, S, alpha=False, float_buffer=True)
img.colorspace_settings.name = 'Non-Color'
mats = {m for o in skin for m in o.data.materials if m}
# only PB22_skin faces own the atlas; the other materials of the skin objects bake into a throwaway image
junk = bpy.data.images.new('junk_bake', 64, 64, alpha=False, float_buffer=False)
for m in mats:
    m.use_nodes = True
    n = m.node_tree.nodes.new('ShaderNodeTexImage'); n.image = img if m.name == 'P220_skin' else junk
    m.node_tree.nodes.active = n
bpy.ops.object.select_all(action='DESELECT')
for o in skin: o.select_set(True); o.hide_set(False)
bpy.context.view_layer.objects.active = skin[0]
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
# 0.4.9: bake each skin part on its own (only that part renders), so overlapping shells at part joints and
# hatches sitting on the hull no longer throw blotchy AO onto each other. No margin: gutters are filled below.
sc.render.bake.margin = 0
meshes = [o for o in model.objects if o and o.type == 'MESH' and not o.hide_render]
ONLY = [n for n in os.environ.get('P220_AO_ONLY', '').split(',') if n]
if ONLY:
    skin = [o for o in skin if o.name in ONLY]
    print('baking only', [o.name for o in skin])
for i, o in enumerate(skin):
    for q in meshes: q.hide_render = q is not o
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.bake(type='AO', margin=0, use_clear=(i == 0))
for q in meshes: q.hide_render = False
px = np.array(img.pixels[:], np.float32).reshape(S, S, 4)[::-1, :, 0]      # row 0 = top
m = np.load(maps)
cov = m['cov']
if cov.shape[0] != S:
    from PIL import Image as _I
    cov = np.array(_I.fromarray(cov.astype(np.uint8) * 255).resize((S, S), 0)) > 0
mean = float(px[cov].mean())
# level: ao' = ao ** g so that the covered mean is TARGET_MEAN; then soften a touch (stock AO is gentle)
# many atlas texels are inner faces (duct walls, inside of thin parts), which bake near black; so the strength is
# chosen to bring the covered mean to TARGET_MEAN but kept within a range that leaves the outside gently shaded
s = 0.5  # 0.4.9: fixed gentle strength; inner faces self-occlude, so the mean rule pushed them near black
g = s
ao = np.maximum(1 - s * (1 - np.clip(px, 0, 1)), 0.6)
# fill gutters from the nearest covered texel (same rule as the painter)
idx = m['idx'] if m['idx'].shape[0] == S else None
if idx is not None:
    ao = ao.ravel()[idx.ravel()].reshape(S, S)
from PIL import Image
pm, pf = os.environ.get('PB22_PATCH_MASK'), os.environ.get('PB22_PATCH_FROM')
if pm and pf:
    mk = np.load(pm)
    keep = ~mk.ravel()[m['idx'].ravel()].reshape(S, S)
    old = np.asarray(Image.open(pf).convert('L'), np.float32) / 255
    ao = np.where(keep, old, ao)
    print('patched %d texels into %s' % ((~keep).sum(), pf))
Image.fromarray(np.round(ao * 255).astype(np.uint8), 'L').save(out)
print('AO raw mean %.3f -> %.3f (strength %.2f) saved %s' % (mean, ao[cov].mean(), g, out))
