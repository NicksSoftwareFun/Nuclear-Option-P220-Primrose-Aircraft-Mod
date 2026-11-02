import bpy, sys
out = open('/tmp/ck220/ctx.obj', 'w'); base = 1
for ob in bpy.data.objects:
    if ob.type != 'MESH': continue
    if not ob.name.startswith(('nose', 'cockpit_F', 'cockpit_R', 'canopy_glass')) or ob.name.endswith(('_int','colmesh')): continue
    me = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    mw = ob.matrix_world
    mats = [m.name if m else 'x' for m in ob.data.materials] or ['x']
    groups = {}
    for p in me.polygons: groups.setdefault(p.material_index, []).append(p)
    for mi, ps in groups.items():
        out.write('o %s__%s\n' % (ob.name, mats[min(mi, len(mats)-1)]))
        vi = {}
        for p in ps:
            for v in p.vertices:
                if v not in vi:
                    c = mw @ me.vertices[v].co; out.write('v %.5f %.5f %.5f\n' % (c.x, c.z, c.y)); vi[v] = base; base += 1
            out.write('f ' + ' '.join(str(vi[v]) for v in p.vertices) + '\n')
    print(ob.name, len(me.polygons), mats)
out.close()
