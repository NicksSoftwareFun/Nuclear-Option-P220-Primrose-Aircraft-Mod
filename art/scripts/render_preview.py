"""Detail close-ups. Usage: python render_preview.py -- <blend> <outdir>"""
import bpy, sys, math
from mathutils import Vector
args = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.open_mainfile(filepath=args[0]); out = args[1]
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 20; sc.cycles.use_denoising = True
sc.world = sc.world or bpy.data.worlds.new('w'); sc.world.use_nodes = True
sc.world.node_tree.nodes['Background'].inputs[0].default_value = (0.75, 0.80, 0.88, 1)
sc.world.node_tree.nodes['Background'].inputs[1].default_value = 0.9
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 3.5
sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35)); sc.collection.objects.link(sun)
for m in bpy.data.materials:
    m.use_nodes = True; b = m.node_tree.nodes.get('Principled BSDF')
    if b:
        b.inputs['Base Color'].default_value = m.diffuse_color; b.inputs['Roughness'].default_value = 0.5
        if m.name == 'A220_glass': b.inputs['Alpha'].default_value = 0.25
sc.view_settings.view_transform = 'Standard'
for cn in ('COLLISION', 'POINTS'):
    c = bpy.data.collections.get(cn)
    if c: c.hide_render = True
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
def shot(name, loc, look, ortho=None, lens=40, up='Y'):
    sc.render.resolution_x, sc.render.resolution_y = 1000, 620
    cam.location = loc
    cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat('-Z', up).to_euler()
    if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else: cam.data.type = 'PERSP'; cam.data.lens = lens
    sc.render.filepath = f'{out}/{name}.png'; bpy.ops.render.render(write_still=True)
N = 19.35
shot('nose_left', (-7.5, 13.5, 1.6), (0, 14.5, 0.2), lens=30)
shot('cockpit_close', (-3.2, 19.5, 2.2), (0, 16.9, 0.4), lens=35)
shot('bay_belly', (-6, -2, -7), (0, -8.0, -1.6), lens=35)
shot('radar_side', (-24, 2.2, 3.5), (0, 2.2, 2.4), lens=45)
shot('rear_right', (9, -16, 0.5), (0, -11.5, 0.0), lens=35)
