"""Dump the P220_skin atlas geometry (UV, world position, smooth normal, part id, material) for texture painting.
Usage: python3 p220_geom.py -- <uv.blend> <out.npz>"""
import bpy, bmesh, sys, math
import numpy as np
a = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.open_mainfile(filepath=a[0])
fam = 'P220_skin'; names, mats = [], []
UV, P, N, PID, MAT = [], [], [], [], []
for o in bpy.data.collections['MODEL'].objects:
    if o.type != 'MESH' or not any(m and m.name == fam for m in o.data.materials): continue
    names.append(o.name); pid = len(names) - 1
    me = o.data.copy(); bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    me.transform(o.matrix_world)
    me.shade_smooth()
    try: me.set_sharp_from_angle(angle=math.radians(35))
    except AttributeError: pass
    me.calc_loop_triangles(); uvl = me.uv_layers.active.data
    cn = np.array([cl.vector for cl in me.corner_normals])
    for t in me.loop_triangles:
        mn = me.materials[t.material_index].name if me.materials[t.material_index] else 'x'
        if mn not in mats: mats.append(mn)
        UV.append([tuple(uvl[l].uv) for l in t.loops]); P.append([tuple(me.vertices[v].co) for v in t.vertices])
        N.append([tuple(cn[l]) for l in t.loops]); PID.append(pid); MAT.append(mats.index(mn))
    bpy.data.meshes.remove(me)
np.savez_compressed(a[1], **{fam + '_uv': np.array(UV, np.float32), fam + '_p': np.array(P, np.float32), fam + '_n': np.array(N, np.float32),
                    fam + '_pid': np.array(PID, np.int16), fam + '_mat': np.array(MAT, np.int16), 'names': np.array(names), 'mats': np.array(mats)})
print('tris', len(UV), 'parts', len(names))
