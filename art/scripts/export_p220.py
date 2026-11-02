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
    # internal structure (0.3.25): the game's shared tiling structure materials, box-projected at stock world scale
    # (about 2.5 m per UV unit, as the stock parts and the PB-22)
    st = [i for i, m in enumerate(o.data.materials) if m and m.name in ('P220_mech', 'P220_struct')]
    for f in bm.faces:
        if f.material_index in st:
            n = f.normal; ax = max(range(3), key=lambda i: abs(n[i]))
            for lp in f.loops:
                c = lp.vert.co; u, v = [(c.y, c.z), (c.x, c.z), (c.x, c.y)][ax]; lp[uvl].uv = (u / 2.5, v / 2.5)
            continue
        if f.material_index in sk_i: continue
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
