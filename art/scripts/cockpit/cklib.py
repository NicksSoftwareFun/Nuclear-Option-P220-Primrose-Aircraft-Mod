import bpy, bmesh, math
from mathutils import Vector
def U2B(p): return (p[0], p[2], p[1])   # Unity (x,y,z) -> Blender (x,z_up)
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
COL={'PB22_skin':(0.55,0.57,0.6,1),'PB22_glass':(0.4,0.7,0.9,0.25),'aircraft_structure':(0.75,0.75,0.72,1),'jet_mechanical':(0.5,0.45,0.4,1),
     'PB22_dark':(0.15,0.15,0.16,1),'PB22_wire':(0.8,0.6,0.2,1),'pilot':(0.3,0.4,0.3,1)}
def mat(name, rgba):
    m=bpy.data.materials.get(name)
    if m: return m
    m=bpy.data.materials.new(name); m.use_nodes=True
    b=m.node_tree.nodes['Principled BSDF']; b.inputs['Base Color'].default_value=rgba; b.inputs['Roughness'].default_value=0.6
    if rgba[3]<1: b.inputs['Alpha'].default_value=rgba[3]
    return m
def load_obj(path, skip=()):
    objs=[]; V=[]; cur=None; faces={}
    order=[]
    for line in open(path):
        if line.startswith('o '):
            cur=line[2:].strip(); order.append(cur); faces.setdefault(cur,[])
        elif line.startswith('v '):
            V.append(U2B([float(x) for x in line.split()[1:4]]))
        elif line.startswith('f '):
            idx=[int(x.split('/')[0])-1 for x in line.split()[1:]]
            faces[cur].append(idx[::-1])
    out=[]
    for i,name in enumerate(dict.fromkeys(order)):
        if any(s in name for s in skip): continue
        fs=faces[name]
        if not fs: continue
        used=sorted({j for f in fs for j in f}); remap={j:k for k,j in enumerate(used)}
        me=bpy.data.meshes.new(name); me.from_pydata([V[j] for j in used],[],[[remap[j] for j in f] for f in fs])
        ob=bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(ob)
        mn=name.split('__')[-1]; ob.data.materials.append(mat(mn,COL.get(mn,(0.6,0.6,0.6,1))))
        out.append(ob)
    return out
def setup_render(w=1400,h=900):
    sc=bpy.context.scene; sc.render.engine='CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=24; sc.cycles.use_denoising=True
    sc.render.resolution_x=w; sc.render.resolution_y=h
    w_=bpy.data.worlds.new('w'); w_.use_nodes=True; w_.node_tree.nodes['Background'].inputs[0].default_value=(0.55,0.62,0.72,1); w_.node_tree.nodes['Background'].inputs[1].default_value=1.0; sc.world=w_
    ld=bpy.data.lights.new('sun','SUN'); ld.energy=3; lo=bpy.data.objects.new('sun',ld); lo.rotation_euler=(0.6,0.3,0.8); sc.collection.objects.link(lo)
    sc.view_settings.view_transform='Standard'
    sc.render.image_settings.file_format='PNG'
def cam(pos,target=None,fov=60,rot=None,ortho=None,name='cam'):
    cd=bpy.data.cameras.new(name); c=bpy.data.objects.new(name,cd); bpy.context.scene.collection.objects.link(c)
    c.location=pos
    if ortho: cd.type='ORTHO'; cd.ortho_scale=ortho
    else: cd.angle=math.radians(fov)
    cd.clip_start=0.01
    if target is not None:
        d=Vector(target)-Vector(pos); c.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    if rot: c.rotation_euler=rot
    bpy.context.scene.camera=c; return c
def render(path):
    bpy.context.scene.render.filepath=path; bpy.ops.render.render(write_still=True)
def clip(objs, keep):  # keep(face_center)->bool ; destructive on mesh
    for ob in objs:
        bm=bmesh.new(); bm.from_mesh(ob.data)
        dead=[f for f in bm.faces if not keep(f.calc_center_median())]
        bmesh.ops.delete(bm,geom=dead,context='FACES'); bm.to_mesh(ob.data); bm.free()
