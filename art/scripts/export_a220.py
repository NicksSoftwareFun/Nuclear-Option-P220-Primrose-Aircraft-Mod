"""Export the A220 parts for Unity. Usage: python3 export_a220.py -- <a220_parts.blend> <out_dir>
Writes A220_parts.fbx (every MODEL and COLLISION mesh at the origin, vertices in its pivot frame, pre-rotated 180 deg
about Z so the FBX import lands Blender (x, y, z) at Unity (x, z, y)) and A220_layout.json (name, kind, Blender world
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
json.dump(layout, open(os.path.join(outdir, 'A220_layout.json'), 'w'), indent=1)
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
    skin = [i for i, m in enumerate(o.data.materials) if m and m.name in ('A220_skin', 'A220_bay', 'A220_window', 'A220_glass')]
    if skin and not o.name.endswith('_colmesh'):
        faces = [f for f in bm.faces if f.material_index in skin]
        dup = bmesh.ops.duplicate(bm, geom=faces)
        bmesh.ops.reverse_faces(bm, faces=[g for g in dup['geom'] if isinstance(g, bmesh.types.BMFace)])
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')
    # glass faces sample the clear middle of the stock canopy texture; everything else has no texture
    uvl = bm.loops.layers.uv.new('UVMap')
    gl = [i for i, m in enumerate(o.data.materials) if m and m.name == 'A220_glass']
    for f in bm.faces:
        for lp in f.loops: lp[uvl].uv = (0.25, 0.5) if f.material_index in gl else (0.0, 0.0)
    bm.faces.sort(key=lambda f: f.material_index)
    bm.to_mesh(o.data); bm.free()
    if o.name.endswith('_colmesh'):
        ca = o.data.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
        for d in ca.data: d.color_srgb = (41 / 255, 41 / 255, 41 / 255, 1.0)
bpy.ops.export_scene.fbx(filepath=os.path.join(outdir, 'A220_parts.fbx'), use_selection=False, use_active_collection=False,
    apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Z', axis_up='Y', bake_space_transform=True,
    object_types={'MESH'}, mesh_smooth_type='FACE', use_mesh_modifiers=False, add_leaf_bones=False, use_tspace=True)
print('exported', len(exp.objects), 'meshes,', len(layout), 'layout entries')
