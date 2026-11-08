"""Export the complete P220 exterior for livery painting (the repo's Livery Bundle).
Usage: python3 export_livery_bundle.py -- <p220 uv blend> <texture dir> <out_dir>
Writes <out_dir>/P220 Exterior.fbx: every exterior part at its place (doors, bays and nose gear doors shut, fin upright,
reversers stowed, flaps and slats in), named by part, with the in-game UVs. Rules:
- every P220_skin face is kept, so the skin has no holes (only the reversed back face of a face pair is dropped, so
  Blender does not show two faces fighting in the same place);
- faces of the other materials (windows, glass, metal, fans) are kept only where they can be seen from outside
  (from either side, since the game draws glass from both sides);
- landing gear legs, wheels and the fan blur discs are left out (none of them take the livery);
- the GlobalEye radar fairing and the laser hood are mounts in game but take the livery, so they are included.
The livery goes on material P220_skin, which points at 'P220 Base.png' in the same folder.
Also writes <out_dir>/P220 UV Layout.png (island outlines, 2048 px, transparent) and the texture maps."""
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image, ImageDraw
a = sys.argv[sys.argv.index('--') + 1:]
src, tex, outdir = a[0], a[1], a[2]; os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=src)
SKIN = 'P220_skin'
LEAVE_OUT = ('gear_', 'gearHinge', 'gearact_', 'gearstay_', 'wheel_', 'fanblur_')
objs = [o for o in bpy.data.collections['MODEL'].objects
        if o.type == 'MESH' and len(o.data.polygons) and not o.hide_render and not o.name.startswith(LEAVE_OUT)]
vs, ps = [], []
for o in objs:
    mw = o.matrix_world; n0 = len(vs)
    vs.extend(mw @ v.co for v in o.data.vertices)
    ps.extend([n0 + i for i in p.vertices] for p in o.data.polygons)
tree = BVHTree.FromPolygons(vs, ps)
dirs = []
for i in range(96):
    z = 1 - 2 * (i + 0.5) / 96; r = math.sqrt(max(0.0, 1 - z * z)); t = i * 2.39996323
    dirs.append(Vector((r * math.cos(t), r * math.sin(t), z)))
def outside(p, n):
    for d in sorted(dirs, key=lambda d: -d.dot(n)):
        if d.dot(n) < -0.2: break                      # only look out of the face's own side
        if tree.ray_cast(p + d * 0.004, d, 120.0)[0] is None: return True
    return False
# skin face pairs (a face and its reversed copy at the same spot): keep the one that faces outside
def fkey(f): return tuple(sorted((round(v.co.x, 3), round(v.co.y, 3), round(v.co.z, 3)) for v in f.verts))
bms = {}
for o in objs:
    b = bmesh.new(); b.from_mesh(o.data); b.transform(o.matrix_world); b.normal_update(); b.faces.ensure_lookup_table(); bms[o.name] = b
sk_of = {o.name: {i for i, m in enumerate(o.data.materials) if m and m.name == SKIN} for o in objs}
pairs = {}
for o in objs:
    for f in bms[o.name].faces:
        if f.material_index in sk_of[o.name]: pairs.setdefault(fkey(f), []).append((o.name, f.index))
kill_skin = set(); npair = 0
for k, lst in pairs.items():
    if len(lst) < 2: continue
    npair += 1
    fs = [(on, bms[on].faces[fi]) for on, fi in lst]
    vis = [outside(f.calc_center_median(), f.normal) for on, f in fs]
    keep = vis.index(True) if any(vis) else 0
    for j, (on, f) in enumerate(fs):
        if j != keep: kill_skin.add((on, f.index))
col = bpy.data.collections.new('LIVERY'); bpy.context.scene.collection.children.link(col)
kept = drop = 0; parts = []
for o in objs:
    b = bms[o.name]; b.faces.ensure_lookup_table(); sk = sk_of[o.name]
    kill = [f for f in b.faces if ((o.name, f.index) in kill_skin) or
            (f.material_index not in sk and not outside(f.calc_center_median(), f.normal)
             and not outside(f.calc_center_median(), -f.normal))]
    drop += len(kill)
    bmesh.ops.delete(b, geom=kill, context='FACES')
    bmesh.ops.delete(b, geom=[v for v in b.verts if not v.link_faces], context='VERTS')
    if not b.faces: b.free(); continue
    kept += len(b.faces)
    me = bpy.data.meshes.new(o.name); b.to_mesh(me); b.free()
    for m in o.data.materials: me.materials.append(m)
    n = bpy.data.objects.new(o.name + '__lb', me); col.objects.link(n); parts.append(n)
for o in objs: o.name = o.name + '__src'; o.data.name = o.data.name + '__src'
for n in parts: n.name = n.name[:-4]; n.data.name = n.name
for n in parts:                                       # drop material slots a part no longer uses
    me = n.data; used = sorted({p.material_index for p in me.polygons})
    keep = [me.materials[i] for i in used]; remap = {u: k for k, u in enumerate(used)}
    idx = [remap[p.material_index] for p in me.polygons]
    me.materials.clear()
    for m in keep: me.materials.append(m)
    for p, k in zip(me.polygons, idx): p.material_index = k
# every skin face must survive except the reversed back copies
nsk_src = sum(len([p for p in o.data.polygons if p.material_index in sk_of[o.name[:-5]]]) for o in objs)
nsk_out = sum(len([p for p in n.data.polygons if n.data.materials[p.material_index].name == SKIN]) for n in parts)
print('skin faces in', nsk_src, 'out', nsk_out, 'reversed copies dropped', len(kill_skin), 'pairs', npair)
assert nsk_out == nsk_src - len(kill_skin)
print('exterior faces kept', kept, 'hidden faces dropped', drop, 'parts', len(parts))
# readable colours for the materials a livery does not paint
cols = {'P220_mech': (0.30, 0.31, 0.32), 'P220_struct': (0.45, 0.44, 0.40), 'P220_bay': (0.30, 0.31, 0.32),
        'P220_dark': (0.05, 0.05, 0.06), 'P220_metal': (0.50, 0.51, 0.52), 'P220_tyre': (0.03, 0.03, 0.03),
        'P220_glass': (0.05, 0.07, 0.09), 'P220_window': (0.04, 0.05, 0.06), 'P220_glass_int': (0.05, 0.07, 0.09),
        'P220_white': (0.85, 0.85, 0.85), 'P220_lining': (0.55, 0.55, 0.52), 'P220_seat': (0.2, 0.22, 0.26)}
used = {m.name for n in parts for m in n.data.materials}
for m in bpy.data.materials:
    if m.name not in used: continue
    m.use_nodes = True; nt = m.node_tree
    for x in list(nt.nodes): nt.nodes.remove(x)
    out = nt.nodes.new('ShaderNodeOutputMaterial'); bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(bsdf.outputs[0], out.inputs[0]); bsdf.inputs['Roughness'].default_value = 0.6
    if m.name == SKIN:
        img = bpy.data.images.new('P220 Base', 16, 16); img.source = 'FILE'; img.filepath = '//P220 Base.png'
        tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = img
        nt.links.new(tx.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        c = cols.get(m.name, tuple(m.diffuse_color)[:3]); bsdf.inputs['Base Color'].default_value = (*c, 1)
        m.diffuse_color = (*c, 1)
for c in list(bpy.context.scene.collection.children):
    if c.name != 'LIVERY': bpy.context.view_layer.layer_collection.children[c.name].exclude = True
bpy.ops.object.select_all(action='DESELECT')
for n in parts: n.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
bpy.ops.export_scene.fbx(filepath=os.path.join(outdir, 'P220 Exterior.fbx'), use_selection=True, apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Z', axis_up='Y', object_types={'MESH'}, mesh_smooth_type='FACE',
    use_mesh_modifiers=False, add_leaf_bones=False, use_tspace=True, path_mode='STRIP')
# UV layout of the livery atlas
S = 2048; im = Image.new('RGBA', (S, S), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
for n in parts:
    me = n.data; si = {i for i, m in enumerate(me.materials) if m and m.name == SKIN}
    if not si or not me.uv_layers: continue
    uv = me.uv_layers.active.data
    for p in me.polygons:
        if p.material_index not in si: continue
        pts = [(uv[li].uv.x * S, (1 - uv[li].uv.y) * S) for li in p.loop_indices]
        dr.line(pts + [pts[0]], fill=(255, 255, 255, 255), width=1)
im.save(os.path.join(outdir, 'P220 UV Layout.png'))
# texture maps, renamed for painters
Image.open(os.path.join(tex, 'P220_skin_b.png')).convert('RGB').save(os.path.join(outdir, 'P220 Base.png'))
Image.open(os.path.join(tex, 'P220_skin_n.png')).convert('RGB').save(os.path.join(outdir, 'P220 Normals.png'))
m = Image.open(os.path.join(tex, 'P220_skin_m.png')).convert('RGBA')
m.save(os.path.join(outdir, 'P220 Metallic Smoothness (game format).png'))
mr, _, _, ma = m.split()
mr.save(os.path.join(outdir, 'P220 Metallic.png'))
Image.fromarray(255 - np.asarray(ma)).save(os.path.join(outdir, 'P220 Roughness.png'))
Image.open(os.path.join(tex, 'P220_skin_ao.png')).convert('L').save(os.path.join(outdir, 'P220 AO.png'))
print('tris', sum(sum(len(p.vertices) - 2 for p in n.data.polygons) for n in parts))
print('parts:', ' '.join(sorted(n.name for n in parts)))
