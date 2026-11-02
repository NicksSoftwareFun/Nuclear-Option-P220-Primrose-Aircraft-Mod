"""UV-unwrap every P220_skin face of the airframe into one shared atlas (the livery texture). Other materials keep
whatever the export gives them. Usage: python3 p220_unwrap.py <in.blend> <out.blend>"""
import bpy, bmesh, sys, math
a = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.open_mainfile(filepath=a[0])
objs = [o for o in bpy.data.collections['MODEL'].objects if o.type == 'MESH' and any(m and m.name == 'P220_skin' for m in o.data.materials)]
# the separate canopy panes and laser parts have their own materials; only objects with skin take part
for o in objs:
    if not o.data.uv_layers: o.data.uv_layers.new(name='UVMap')
bpy.context.view_layer.objects.active = objs[0]
for o in bpy.data.objects: o.select_set(False)
for o in objs: o.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bpy.context.scene.tool_settings.use_uv_select_sync = False
bpy.ops.mesh.select_mode(type='FACE')
n = 0
for o in objs:
    bm = bmesh.from_edit_mesh(o.data)
    si = [i for i, m in enumerate(o.data.materials) if m and m.name == 'P220_skin']
    for v in bm.verts: v.select = False
    for e in bm.edges: e.select = False
    for f in bm.faces: f.select = f.material_index in si; n += f.select
    bm.select_flush_mode(); bmesh.update_edit_mesh(o.data)
print('skin faces', n, 'objects', len(objs))
bpy.ops.uv.smart_project(angle_limit=math.radians(62), island_margin=0.0, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.average_islands_scale()
# 0.3.27b (lettering too coarse at 2K): islands carrying the big lettering get more of the atlas. The fin and
# rudder at 2x and the fuselage side islands at 1.8x texel density; everything else shrinks a little in the pack.
FUSE = ('nose', 'cockpit_F', 'cockpit_R', 'fuselage_F', 'fuselage', 'fuselage_R', 'tail')
nup = 0
for o in objs:
    bm = bmesh.from_edit_mesh(o.data); uv = bm.loops.layers.uv.active
    si = [i for i, m in enumerate(o.data.materials) if m and m.name == 'P220_skin']
    faces = [f for f in bm.faces if f.material_index in si]
    key = lambda l: (round(l[uv].uv.x, 6), round(l[uv].uv.y, 6))
    seen = set()
    for f0 in faces:
        if f0.index in seen: continue
        isl, st = [], [f0]; seen.add(f0.index)
        while st:
            f = st.pop(); isl.append(f)
            for l in f.loops:
                e = l.edge
                for g in e.link_faces:
                    if g.index in seen or g.material_index not in si: continue
                    # same island only if the edge's UVs match on both faces
                    la = [x for x in g.loops if x.edge == e]
                    if la and {key(l), key(l.link_loop_next)} == {key(la[0]), key(la[0].link_loop_next)}:
                        seen.add(g.index); st.append(g)
        mw = o.matrix_world
        cs = [mw @ f.calc_center_median() for f in isl]; ns = [(mw.to_3x3() @ f.normal).normalized() for f in isl]
        k = 1.0
        if o.name.startswith(('vstab_', 'rudder_')): k = 2.0
        elif o.name in FUSE:
            ax = sum(abs(n.x) for n in ns) / len(ns); zc = sum(c.z for c in cs) / len(cs)
            if ax > 0.45 and -0.8 < zc < 2.0: k = 1.8
        if k == 1.0: continue
        ls = [l for f in isl for l in f.loops]
        cu = sum(l[uv].uv.x for l in ls) / len(ls); cv = sum(l[uv].uv.y for l in ls) / len(ls)
        for l in ls: l[uv].uv = ((l[uv].uv.x - cu) * k + cu, (l[uv].uv.y - cv) * k + cv)
        nup += 1
    bmesh.update_edit_mesh(o.data)
print('islands scaled', nup)
bpy.ops.uv.pack_islands(rotate=True, margin_method='FRACTION', margin=0.002, shape_method='CONCAVE')
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.wm.save_as_mainfile(filepath=a[1])
print('saved', a[1])
