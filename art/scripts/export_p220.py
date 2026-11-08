"""Export the P220 parts for Unity. Usage: python3 export_p220.py -- <p220_parts.blend> <out_dir>
Writes P220_parts.fbx (every MODEL and COLLISION mesh at the origin, vertices in its pivot frame, pre-rotated 180 deg
about Z so the FBX import lands Blender (x, y, z) at Unity (x, z, y)) and P220_layout.json (name, kind, Blender world
position and rotation of every MODEL / COLLISION / POINTS object)."""
import bpy, sys, os, json, math, bmesh
from mathutils import Matrix
a = sys.argv[sys.argv.index('--') + 1:]
src, outdir = a[0], a[1]; os.makedirs(outdir, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=src)
layout = []
for cname in ('MODEL', 'COLLISION', 'POINTS'):
    for o in bpy.data.collections[cname].objects:
        mw = o.matrix_world; q = mw.to_quaternion()
        e = dict(name=o.name, coll=cname, kind=o.type, pos=list(mw.translation), rot=[q.w, q.x, q.y, q.z],
                 mats=[m.name for m in o.data.materials] if o.type == 'MESH' else [])
        if o.type == 'MESH':
            e['bmin'] = [min(v.co[i] for v in o.data.vertices) for i in range(3)]
            e['bmax'] = [max(v.co[i] for v in o.data.vertices) for i in range(3)]
        layout.append(e)
json.dump(layout, open(os.path.join(outdir, 'P220_layout.json'), 'w'), indent=1)
Rz = Matrix.Rotation(math.pi, 4, 'Z')
exp = bpy.data.collections.new('EXPORT'); bpy.context.scene.collection.children.link(exp)
srcs = [o for c in ('MODEL', 'COLLISION') for o in bpy.data.collections[c].objects if o.type == 'MESH']
for o in srcs: o.data.name = o.name + '__src'
for o in srcs:
    me = o.data.copy(); me.name = o.name; me.transform(Rz)
    n = bpy.data.objects.new(o.name + '__x', me); exp.objects.link(n)
for o in srcs: o.name = o.name + '__src'
for c in bpy.context.scene.collection.children:
    if c.name != 'EXPORT': bpy.context.view_layer.layer_collection.children[c.name].exclude = True
for o in exp.objects: o.name = o.name[:-3]
bpy.ops.object.select_all(action='DESELECT')
for o in exp.objects: o.select_set(True)
bpy.context.view_layer.objects.active = exp.objects[0]
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
# 0.4.18: wheel hubs take the livery: their metal faces become P220_skin, as the FIRST material (the game sets the livery
# on a renderer's first material), with UVs inside the hub patch of the atlas (p220_paint.HUB_RC); each livery paints
# its hub colour there (gold on the royal livery). Tyres keep their own material.
HUB_UV = ((1021 + 0.5) / 2048, 1 - (616 + 0.5) / 2048); HUB_S = (16 / 2048) / 0.6     # 0.6 m of hub = 16 px
for o in exp.objects:
    if not o.name.startswith('wheel_') or o.name.endswith('_colmesh'): continue
    me = o.data; mats = list(me.materials)
    if not any(m and m.name == 'P220_metal' for m in mats): continue
    new = [bpy.data.materials['P220_skin']] + [m for m in mats if not (m and m.name == 'P220_metal')]
    remap = {i: (0 if (m and m.name == 'P220_metal') else new.index(m)) for i, m in enumerate(mats)}
    idx = [remap[p.material_index] for p in me.polygons]
    me.materials.clear()
    for m in new: me.materials.append(m)
    for p, k in zip(me.polygons, idx): p.material_index = k
    if not me.uv_layers: me.uv_layers.new(name='UVMap')
    uv = me.uv_layers.active.data
    for p in me.polygons:
        if p.material_index != 0: continue
        for li in p.loop_indices:
            c = me.vertices[me.loops[li].vertex_index].co
            uv[li].uv = (HUB_UV[0] + c.y * HUB_S, HUB_UV[1] + c.z * HUB_S)
    print('hub faces', o.name, sum(1 for p in me.polygons if p.material_index == 0))
    for e in layout:
        if e['name'] == o.name and e['coll'] == 'MODEL': e['mats'] = [m.name for m in new]   # the builder sets materials from this list
# 0.4.19: any renderer that carries livery skin must have P220_skin FIRST, or the game never puts the livery on it
# (main gear leg doors on gear_L/R kept the default texture on every livery)
for o in exp.objects:
    if o.type != 'MESH' or o.name.endswith('_colmesh'): continue
    me = o.data; mats = list(me.materials); names = [m.name if m else '' for m in mats]
    if 'P220_skin' not in names or names.index('P220_skin') == 0: continue
    k = names.index('P220_skin'); new = [mats[k]] + [m for i, m in enumerate(mats) if i != k]
    idx = [new.index(mats[p.material_index]) for p in me.polygons]
    me.materials.clear()
    for m in new: me.materials.append(m)
    for p, j in zip(me.polygons, idx): p.material_index = j
    print('skin first', o.name)
    for e in layout:
        if e['name'] == o.name and e['coll'] == 'MODEL': e['mats'] = [m.name for m in new]
json.dump(layout, open(os.path.join(outdir, 'P220_layout.json'), 'w'), indent=1)
for o in exp.objects:
    bm = bmesh.new(); bm.from_mesh(o.data)
    # skin is double-sided like the stock airframes, so a broken-off section or the cockpit view shows a solid inside
    # (the flight deck panes are not: like stock canopies, the outer pane is seen from outside only and the inner pane,
    # canopy_glass_int on the cockpit layer, from inside only; a double-sided outer pane tinted the view from the seats)
    skin = [i for i, m in enumerate(o.data.materials) if m and m.name in ('P220_skin', 'P220_bay', 'P220_window', 'P220_glass')
            and not o.name.startswith('canopy_glass')]
    # parts that already carry back faces from the parts script (emit, NOBACK) are not twinned again
    if skin and not o.name.endswith('_colmesh') and not o.name.startswith(('wheel_', 'gear_', 'engine_', 'revdoor_', 'fdoor_')):
        # 0.3.27 triangle trim: a closed shell (control surfaces, doors, reverser doors, pylons) never shows its inside,
        # so only faces in open islands (section breaks, openings, cut-outs) get the reversed twin
        seen, faces = set(), []
        for f0 in bm.faces:
            if f0.index in seen: continue
            isl, stack = [], [f0]; seen.add(f0.index)
            while stack:
                f = stack.pop(); isl.append(f)
                for e in f.edges:
                    for g in e.link_faces:
                        if g.index not in seen: seen.add(g.index); stack.append(g)
            closed = all(len(e.link_faces) == 2 for f in isl for e in f.edges)
            if not closed: faces += [f for f in isl if f.material_index in skin]
        dup = bmesh.ops.duplicate(bm, geom=faces) if faces else {'geom': []}
        bmesh.ops.reverse_faces(bm, faces=[g for g in dup['geom'] if isinstance(g, bmesh.types.BMFace)])
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')
    # glass faces sample the clear middle of the stock canopy texture; everything else has no texture
    # 0.3.27: P220_skin faces keep their livery atlas UVs from p220_unwrap.py (the reversed twins carry the same UVs, so
    # the livery shows on both sides); every other material gets the UVs set below
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new('UVMap')
    sk_i = [i for i, m in enumerate(o.data.materials) if m and m.name == 'P220_skin']
    gl = [i for i, m in enumerate(o.data.materials) if m and m.name in ('P220_glass', 'P220_glass_int')]
    keep_uv = [i for i, m in enumerate(o.data.materials) if m and m.name == 'P220_fanblur']   # 0.3.29: blur disc keeps its own UVs
    # internal structure (0.3.25): the game's shared tiling structure materials, box-projected at stock world scale
    # (about 2.5 m per UV unit, as the stock parts and the PB-22)
    st = [i for i, m in enumerate(o.data.materials) if m and m.name in ('P220_mech', 'P220_struct', 'P220_bay', 'P220_lining')]   # 0.4.7: interior maps tile the same way
    for f in bm.faces:
        if f.material_index in st:
            n = f.normal; ax = max(range(3), key=lambda i: abs(n[i]))
            for lp in f.loops:
                c = lp.vert.co; u, v = [(c.y, c.z), (c.x, c.z), (c.x, c.y)][ax]; lp[uvl].uv = (u / 2.5, v / 2.5)
            continue
        if f.material_index in sk_i or f.material_index in keep_uv: continue
        for lp in f.loops: lp[uvl].uv = (0.25, 0.5) if f.material_index in gl else (0.0, 0.0)
    bm.faces.sort(key=lambda f: f.material_index)
    bm.to_mesh(o.data); bm.free()
    if o.name.endswith('_colmesh'):
        # 0.3.19: Unity's convex MeshCollider takes at most 255 triangles and otherwise keeps only a partial hull
        # (8 parts warned in 0.3.18). Merge hull points further apart until the triangulated hull fits.
        hb = bmesh.new(); hb.from_mesh(o.data); dist = 0.08
        while True:
            bmesh.ops.triangulate(hb, faces=hb.faces[:])
            if len(hb.faces) <= 240: break
            dist *= 1.25
            pts = [v.co.copy() for v in hb.verts]; hb.free(); hb = bmesh.new()
            for c in pts: hb.verts.new(c)
            bmesh.ops.remove_doubles(hb, verts=hb.verts[:], dist=dist)
            res = bmesh.ops.convex_hull(hb, input=hb.verts[:])
            bmesh.ops.delete(hb, geom=[v for v in hb.verts if not v.link_faces], context='VERTS')
            bmesh.ops.recalc_face_normals(hb, faces=hb.faces[:])
        if dist > 0.08: print('colmesh', o.name, len(hb.faces), 'tris at merge', round(dist, 3))
        hb.to_mesh(o.data); hb.free()
        ca = o.data.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
        for d in ca.data: d.color_srgb = (41 / 255, 41 / 255, 41 / 255, 1.0)
bpy.ops.export_scene.fbx(filepath=os.path.join(outdir, 'P220_parts.fbx'), use_selection=False, use_active_collection=False,
    apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Z', axis_up='Y', bake_space_transform=True,
    object_types={'MESH'}, mesh_smooth_type='FACE', use_mesh_modifiers=False, add_leaf_bones=False, use_tspace=True)
print('exported', len(exp.objects), 'meshes,', len(layout), 'layout entries')
