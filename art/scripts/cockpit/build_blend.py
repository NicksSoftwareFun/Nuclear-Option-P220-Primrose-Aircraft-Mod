"""Build the P220 flight deck in Blender from p220_cockpit_model; render previews or export FBX.
usage: python3 build_blend.py render <shot> <out.png> | export <dir>"""
import os, sys, math, json
CK = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, CK)
import bpy, bmesh
from mathutils import Vector
from cklib import U2B, reset, setup_render, cam, render, load_obj, clip
import p220_cockpit_model as M
TEXDIR = os.path.join(CK, 'tex')

def material(name):
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    if name == 'P220_cockpit':
        tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = bpy.data.images.load(TEXDIR + '/P220_cockpit_b.png')
        nt.links.new(tx.outputs['Color'], b.inputs['Base Color']); b.inputs['Roughness'].default_value = 0.55
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = bpy.data.images.load(TEXDIR + '/P220_cockpit_n.png'); tn.image.colorspace_settings.name = 'Non-Color'
        nm = nt.nodes.new('ShaderNodeNormalMap'); nt.links.new(tn.outputs['Color'], nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    elif name == 'tacScreenDisplay':
        tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = bpy.data.images.load(TEXDIR + '/screen_tacScreenDisplay.png')
        b.inputs['Base Color'].default_value = (0, 0, 0, 1)
        nt.links.new(tx.outputs['Color'], b.inputs['Emission Color']); b.inputs['Emission Strength'].default_value = 1.6; b.inputs['Roughness'].default_value = 0.15
    else:
        col = {'P220_cabin': (0.62, 0.64, 0.66, 1), 'CockpitWarningLight': (0.6, 0.03, 0.02, 1), 'Matte_black': (0.02, 0.02, 0.02, 1),
               'P220_skin': (0.8, 0.8, 0.8, 1), 'P220_dark': (0.1, 0.1, 0.1, 1), 'P220_bay': (0.4, 0.4, 0.4, 1)}.get(name, (0.5, 0.5, 0.5, 1))
        b.inputs['Base Color'].default_value = col; b.inputs['Roughness'].default_value = 0.6
        if name == 'P220_glass':
            b.inputs['Alpha'].default_value = 0.12; b.inputs['Roughness'].default_value = 0.05
            try: m.blend_method = 'BLEND'
            except Exception: pass
    return m

def build(parts, skip_simple=True, pivots=None):
    out = {}
    for name, P in parts.items():
        if skip_simple and 'simple' in name: continue
        me = bpy.data.meshes.new(name)
        me.from_pydata([U2B(v) for v in P['v']], [], [list(reversed(f[0])) for f in P['f']])
        uvl = me.uv_layers.new(name='UVMap'); mats = []
        for f in P['f']:
            if f[2] not in mats: mats.append(f[2])
        for mn in mats: me.materials.append(material(mn))
        for pi, pl in enumerate(me.polygons):
            f = P['f'][pi]; pl.material_index = mats.index(f[2]); uvs = list(reversed(f[1]))
            for k, loop in enumerate(pl.loop_indices): uvl.data[loop].uv = uvs[k]
        me.validate(); me.update()
        if 'P220_cabin' in mats:
            # 0.3.17 (review): the lining showed every 3 degree facet as a light band; weld its faces and shade it smooth,
            # keeping a hard edge where the window trim turns (sharp from 30 degrees)
            ci = mats.index('P220_cabin'); bm = bmesh.new(); bm.from_mesh(me)
            vs = list({v for f in bm.faces if f.material_index == ci for v in f.verts})
            bmesh.ops.remove_doubles(bm, verts=vs, dist=0.0005)
            for f in bm.faces: f.smooth = f.material_index == ci
            bm.to_mesh(me); bm.free()
            me.set_sharp_from_angle(angle=math.radians(30)); me.update()
        ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
        if pivots and name in pivots:
            pv = Vector(U2B(pivots[name]))
            for v in me.vertices: v.co -= pv
            ob.location = pv
        out[name] = ob
    return out

def skin_clamp(parts, inset=0.025):
    """Pull every vertex that pokes through the real exterior skin (ctx.obj, skin material only) back inside it, along
    the ray from the cabin axis. The analytic hull in the model misses the crown over the windscreen (0.3.13: overhead
    panel and the simple LOD box showed through the roof)."""
    from mathutils.bvhtree import BVHTree
    objs = load_obj(os.path.join(CK, 'ctx.obj')); dg = bpy.context.evaluated_depsgraph_get()
    trees = [BVHTree.FromObject(o, dg) for o in objs if 'P220_skin' in o.name]
    moved = {}
    # the window trim sits on purpose right at the skin's cut edges (0.3.17): leave anything near a pane outline alone
    from mathutils.kdtree import KDTree
    pp = [q for pane in json.load(open(os.path.join(CK, 'panes.json'))) for q in pane]
    kd = KDTree(len(pp))
    for k, q in enumerate(pp): kd.insert((q[0], q[2], q[1]), k)
    kd.balance()
    for name, P in parts.items():
        V = P['v']
        for i, v in enumerate(V):
            # 0.3.25 (triangles along the canopy edge and roof): the trim there sat only 3 mm inside the double-sided
            # skin, and the faceted skin's inner face poked through it in triangles. It now keeps 12 mm clear too.
            ins = 0.012 if (name == 'cockpit_int' and kd.find(tuple(v))[2] < 0.10) else inset
            b = Vector(U2B(v)); ax = Vector((0.0, b.y, 0.45)); d = b - ax; L = d.length
            if L < 1e-4: continue
            dn = d.normalized(); hit = None
            for t in trees:
                h = t.ray_cast(ax, dn, L + 0.05)
                if h[0] is not None: hit = h[3] if hit is None else min(hit, h[3])
            if hit is not None and hit - ins < L:
                nb = ax + dn * (hit - ins); V[i] = type(v)((nb.x, nb.z, nb.y)) if not isinstance(v, list) else [nb.x, nb.z, nb.y]
                moved[name] = moved.get(name, 0) + 1
    for o in objs: bpy.data.objects.remove(o, do_unlink=True)
    print('skin clamp moved', moved)
    return parts

def context():
    ctx = load_obj(os.path.join(CK, 'ctx.obj'))
    for o in ctx:
        mn = o.name.split('__')[-1]; o.data.materials.clear(); o.data.materials.append(material(mn))
    return ctx

def seats():
    M.PARTS.clear()
    for x in (-0.40, 0.40):     # Medusa ejection seat proxies at the stock crew positions (seat origin y 0.21, z 16.80)
        M.boxw('seats', (x, 0.21 + 0.04, 16.47), (0.50, 0.12, 0.50), 'Matte_black')
        M.boxw('seats', (x, 0.21 + 0.55, 16.21), (0.48, 1.0, 0.12), 'Matte_black')
    return build(dict(M.PARTS))

SHOTS = {   # name: (cam pos, target, fov), Unity coordinates
    'eye':     ((-0.38, 0.84, 16.29), (-0.30, 0.30, 17.40), 80),
    'centre':  ((0.0, 0.95, 16.05), (0.0, 0.15, 17.20), 70),
    'ped':     ((0.35, 0.75, 16.15), (0.0, 0.10, 16.75), 55),
    'stick':   ((-0.62, 0.62, 16.40), (-0.92, 0.22, 16.95), 55),
    'pedals':  ((-0.05, 0.45, 16.75), (-0.42, -0.05, 17.50), 55),
    'ovh':     ((0.0, 0.55, 16.10), (0.0, 1.20, 16.40), 75),
    'back':    ((0.30, 0.95, 17.00), (0.0, 0.35, 15.42), 80),
    'cut':     ((4.2, 0.55, 16.65), (0.0, 0.45, 16.65), 40),
    'ext':     ((2.6, 0.95, 16.3), (0.0, 0.45, 16.9), 50),
    'feet':    ((-0.38, 0.80, 16.30), (-0.40, -0.15, 17.15), 70),
    'extcrown': ((-3.2, 2.6, 20.6), (0.0, 1.0, 17.2), 35),
    'extfront': ((-1.4, 1.2, 21.0), (0.0, 0.75, 17.1), 32),
    'exthead': ((0.0, 0.55, 27.0), (0.0, 0.45, 17.5), 22),     # head-on, like a front screenshot
    'extside': ((-5.5, 0.9, 16.2), (0.0, 0.70, 16.9), 35),
    'eyeside': ((-0.38, 0.84, 16.29), (-1.2, 0.60, 16.90), 80),
    'eyeup':   ((-0.38, 0.84, 16.29), (-0.10, 1.10, 17.30), 80),
    'roof':    ((-0.37, 0.85, 16.30), (0.20, 1.25, 17.10), 95),
    'game':    ((-0.37, 0.85, 16.30), (-0.37, 0.85, 17.30), 75),   # in-game default head, level
    'lookright': ((-0.37, 0.85, 16.30), (1.0, 0.45, 16.25), 90),
    'extwin':  ((-3.2, 1.0, 17.2), (0.0, 0.55, 16.0), 30),
    'quad':    ((-0.30, 0.62, 16.55), (0.0, 0.24, 16.88), 45),
    'quadtop': ((0.0, 0.80, 16.86), (0.0, 0.20, 16.88), 35),
}
if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'export':
        out = sys.argv[2]; reset(); parts = skin_clamp(M.build_all()); obs = build(parts, skip_simple=False, pivots=M.PIVOTS)
        for ob in obs.values():
            bm = bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.triangulate(bm, faces=bm.faces[:]); bm.to_mesh(ob.data); bm.free()
        os.makedirs(out, exist_ok=True)
        bpy.ops.export_scene.fbx(filepath=os.path.join(out, 'P220_cockpit.fbx'), use_selection=False, apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_UNITS', axis_forward='Z', axis_up='Y', bake_space_transform=True, object_types={'MESH'},
            mesh_smooth_type='FACE', use_mesh_modifiers=False, add_leaf_bones=False, use_tspace=True)
        json.dump({'pivots': {k: list(v) for k, v in M.PIVOTS.items()}, 'eye': list(M.EYE), 'tris': M.tri_count()},
                  open(os.path.join(out, 'P220_cockpit_layout.json'), 'w'), indent=1)
        print('exported', list(obs)); sys.exit(0)
    shot, path = sys.argv[2], sys.argv[3]
    reset(); setup_render(1400, 900)
    ctx = context(); obs = build(skin_clamp(M.build_all())); seats()
    p, t, fov = SHOTS[shot]
    if os.environ.get('CULL'):   # back faces transparent like the game; the airframe skin is double-sided in the FBX
        import importlib.util; sys.path.insert(0, '/tmp/dp'); from cull import game_culling
        keep = {m.name: m.use_nodes for m in bpy.data.materials}
        dbl = [m for m in bpy.data.materials if m.name.split('.')[0] in ('P220_skin', 'P220_bay', 'P220_window')]
        for m in dbl: m.use_nodes = False if not m.use_nodes else m.use_nodes
        names = set(m.name for m in dbl)
        for m in bpy.data.materials:
            if m.name in names: m['nocull'] = 1
        _orig = [(m, m.use_nodes) for m in bpy.data.materials if m.name in names]
        for m, _ in _orig: m.use_nodes = False
        game_culling(bpy)
        for m, u in _orig: m.use_nodes = u
    if os.environ.get('THR'):   # preview the handles at a throttle setting (0..1), sliding 0.1655 m forward like Cockpit 'motion'
        bpy.data.objects['throttle'].location.y += 0.1655*float(os.environ['THR'])
    if shot.startswith('ext'):
        for o in bpy.data.objects:
            if o.name.startswith('seats'): o.hide_render = False
    else:
        for o in ctx:
            if 'glass' in o.name: o.hide_render = True
        if shot in ('ped', 'pedals', 'stick', 'centre', 'ovh', 'back', 'feet', 'lookright'):
            for o in bpy.data.objects:
                if o.name.startswith('seats'): o.hide_render = True
    if shot.startswith('ext') and os.environ.get('NOGLASS'):
        for o in ctx:
            if 'glass' in o.name: o.hide_render = True
    if os.environ.get('HIDEINT'):
        for o in bpy.data.objects:
            if o.name in ('cockpit_int', 'tacScreen', 'warningLights'): o.hide_render = True
    if shot == 'cut':      # dollhouse section: the near (starboard) wall and everything outboard of x 0.62 cut away
        for o in ctx: o.hide_render = False
        clip(ctx + [obs['cockpit_int']], lambda c: c.x < 0.62)
        clip(ctx, lambda c: c.x < 0.10)
        obs['stick_R'].hide_render = True
        for o in bpy.data.objects:
            if o.name.startswith('seats'): o.hide_render = False
    if shot == 'back':
        for o in ctx: o.hide_render = True
    bpy.context.scene.view_settings.exposure = float(os.environ.get('EXPO', '0.6'))
    if os.environ.get('FILL'):
        L = bpy.data.objects.new('fill', bpy.data.lights.new('fill', 'POINT')); L.data.energy = float(os.environ['FILL']); L.location = U2B(p); bpy.context.scene.collection.objects.link(L)
    cam(U2B(p), U2B(t), fov=fov)
    render(path)
