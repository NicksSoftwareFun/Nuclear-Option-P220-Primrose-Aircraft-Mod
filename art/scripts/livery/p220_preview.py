"""Livery preview renders. python3 p220_preview.py -- <uv.blend> <texdir> <outdir>
Cycles CPU; P220_skin gets the painted base colour, normal and smoothness; the rest flat material colours."""
import bpy, sys, os, math
from mathutils import Vector
a = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.open_mainfile(filepath=a[0]); tex, out = a[1], a[2]; os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
for cn in ('COLLISION', 'POINTS'):
    c = bpy.data.collections.get(cn)
    if c: c.hide_render = True
# same smoothing as the game export (smooth by angle 35 deg), so the preview shades like the game
for o in bpy.data.collections['MODEL'].objects:
    o.select_set(o.type == 'MESH')
bpy.context.view_layer.objects.active = next(o for o in bpy.data.collections['MODEL'].objects if o.type == 'MESH')
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
def img(n, cs):
    i = bpy.data.images.load(os.path.join(tex, n)); i.colorspace_settings.name = cs; return i
cols = {'P220_mech': (0.30, 0.31, 0.32), 'P220_struct': (0.45, 0.44, 0.40), 'P220_bay': (0.30, 0.31, 0.32),
        'P220_dark': (0.05, 0.05, 0.06), 'P220_metal': (0.50, 0.51, 0.52), 'P220_tyre': (0.03, 0.03, 0.03),
        'P220_glass': (0.05, 0.07, 0.09), 'P220_window': (0.04, 0.05, 0.06), 'P220_glass_int': (0.05, 0.07, 0.09)}
for m in bpy.data.materials:
    m.use_nodes = True; nt = m.node_tree; b = nt.nodes.get('Principled BSDF')
    if b is None: continue
    if m.name == 'P220_skin':
        tb = nt.nodes.new('ShaderNodeTexImage'); tb.image = img('P220_skin_b.png', 'sRGB')
        nt.links.new(tb.outputs['Color'], b.inputs['Base Color'])
        if os.path.exists(os.path.join(tex, 'P220_skin_ao.png')):
            ta = nt.nodes.new('ShaderNodeTexImage'); ta.image = img('P220_skin_ao.png', 'Non-Color')
            mix = nt.nodes.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'; mix.inputs['Fac'].default_value = 1.0
            nt.links.new(tb.outputs['Color'], mix.inputs[1]); nt.links.new(ta.outputs['Color'], mix.inputs[2])
            nt.links.new(mix.outputs[0], b.inputs['Base Color'])
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = img('P220_skin_n.png', 'Non-Color')
        nm = nt.nodes.new('ShaderNodeNormalMap'); nt.links.new(tn.outputs['Color'], nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
        tm = nt.nodes.new('ShaderNodeTexImage'); tm.image = img('P220_skin_m.png', 'Non-Color')
        inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
        sms = nt.nodes.new('ShaderNodeMath'); sms.operation = 'MULTIPLY'; sms.inputs[1].default_value = float(os.environ.get('SMSCALE', '1'))
        nt.links.new(tm.outputs['Alpha'], sms.inputs[0]); nt.links.new(sms.outputs[0], inv.inputs[1]); nt.links.new(inv.outputs[0], b.inputs['Roughness'])
    else:
        b.inputs['Base Color'].default_value = (*cols.get(m.name, tuple(m.diffuse_color)[:3]), 1); b.inputs['Roughness'].default_value = 0.6
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = int(os.environ.get('SAMP', '24')); sc.cycles.use_denoising = True
sc.world = sc.world or bpy.data.worlds.new('w'); sc.world.use_nodes = True
sc.world.node_tree.nodes['Background'].inputs[0].default_value = (0.55, 0.62, 0.72, 1)
sc.world.node_tree.nodes['Background'].inputs[1].default_value = 0.8
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 3.5
sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(-35)); sc.collection.objects.link(sun)
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x, sc.render.resolution_y = int(os.environ.get('RX', '1600')), int(os.environ.get('RY', '1000'))
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
SHOTS = {'3q_front': ((-24, 22, 9), (0, 0, -0.5), 45), '3q_rear': ((22, -26, 10), (0, -2, -0.3), 45),
         'port': ((-46, 0, 1.0), (0, 0, 0.5), 50), 'starboard': ((46, 0, 1.0), (0, 0, 0.5), 50),
         'top': ((0, 0, 50), (0, 0, 0), 50), 'fin_port': ((-14, -15, 4.5), (0, -15.6, 3.8), 50),
         'fin_stbd': ((14, -15, 4.5), (0, -15.6, 3.8), 50), 'nose': ((-9, 12, 1.5), (0, 12.5, 0.4), 40),
         'below': ((-10, 8, -30), (0, 0, -1.5), 45), 'engine': ((-11, 9.0, -1.4), (-5.35, 5.5, -2.25), 40),
         'fwd_door': ((-6.5, 14.6, 0.6), (-1.6, 14.4, 0.3), 40),
         'fin_close': ((-7.5, -15.0, 4.6), (0, -15.3, 4.4), 50), 'rear_door': ((-7.0, -9.5, 0.4), (-1.6, -11.0, 0.3), 40),
         'prim_close': ((-7.0, 9.8, 1.6), (-1.6, 10.2, 1.2), 45),
         'belly': ((0, 9.3, -24), (0, 9.3, 0), 40), 'belly_mid': ((0, 2.5, -30), (0, 2.5, 0), 40), 'nose_tip': ((-3.2, 21.6, 0.0), (0, 18.9, -0.55), 45), 'pala_close': ((-12, 4.0, 3.0), (0, 2.0, 0.6), 40), 'fwd_door_s': ((6.5, 13.6, 0.4), (1.6, 13.6, 0.1), 40)}
only = os.environ.get('SHOTS')
for nm, (loc, tgt, lens) in SHOTS.items():
    if only and nm not in only.split(','): continue
    cam.location = loc; cam.data.lens = lens
    cam.rotation_mode = 'QUATERNION'; cam.rotation_quaternion = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y')
    sc.render.filepath = os.path.join(out, nm + '.png'); bpy.ops.render.render(write_still=True)
print('done')
