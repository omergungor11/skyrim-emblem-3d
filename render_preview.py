# Blender headless: blender -b -P render_preview.py -- out.png [angle_deg]
import bpy, sys, math, os
argv = sys.argv[sys.argv.index("--") + 1:]
out = os.path.abspath(argv[0]); ang = float(argv[1]) if len(argv) > 1 else 0
here = os.path.dirname(os.path.abspath(__file__))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(here, "emblem.glb"))
ob = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
ob.rotation_mode = "XYZ"; ob.rotation_euler = (0, 0, math.radians(ang))

mat = bpy.data.materials.new("steel"); mat.use_nodes = True
nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Metallic"].default_value = 1.0
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load(os.path.join(here, "texture.png")); tex.image.colorspace_settings.name = "Non-Color"
ramp = nt.nodes.new("ShaderNodeMapRange")
ramp.inputs["To Min"].default_value = 0.62; ramp.inputs["To Max"].default_value = 0.2
nt.links.new(tex.outputs["Color"], ramp.inputs["Value"]); nt.links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
col = nt.nodes.new("ShaderNodeMapRange")
col.inputs["To Min"].default_value = 0.12; col.inputs["To Max"].default_value = 0.6
nt.links.new(tex.outputs["Color"], col.inputs["Value"]); nt.links.new(col.outputs["Result"], bsdf.inputs["Base Color"])
ob.data.materials.clear(); ob.data.materials.append(mat)

sc = bpy.context.scene
world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.02, 0.025, 1)
for loc, e in [((-1.6, -1.6, 1.4), 260), ((1.8, -1.0, -0.6), 60), ((0.6, -0.2, 2.0), 120)]:
    l = bpy.data.lights.new("l", "AREA"); l.energy = e; l.size = 1.5
    lo = bpy.data.objects.new("l", l); lo.location = loc; sc.collection.objects.link(lo)
    c = lo.constraints.new("TRACK_TO"); c.target = ob
cam = bpy.data.cameras.new("c"); cam.lens = 85
co = bpy.data.objects.new("c", cam); co.location = (0, -2.45, 0); co.rotation_euler = (math.radians(90), 0, 0)
sc.collection.objects.link(co); sc.camera = co
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 800, 1300
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
