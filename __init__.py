bl_info = {
    "name": "Icicle Generator",
    "author": "MagmaVR",
    "version": (4, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Add > Mesh / Sidebar > Icicle Generator",
    "description": "Add icicles of varying widths & heights to selected non-vertical edges, with preview.",
    "category": "Add Mesh",
}

import bpy
import bmesh
import math
import mathutils
import random
from bpy.props import (
    BoolProperty, FloatProperty, IntProperty, EnumProperty, PointerProperty
)
from bpy.types import (
    Operator, Panel, PropertyGroup
)
import gpu
from gpu_extras.batch import batch_for_shader

# -----------------------------------------------------------------------------
# Properties
# -----------------------------------------------------------------------------

class IcicleProperties(PropertyGroup):
    min_rad: FloatProperty(
        name="Min Radius", default=0.025, min=0.01, max=10.0, unit='LENGTH',
        description="Minimum radius of a cone"
    )
    max_rad: FloatProperty(
        name="Max Radius", default=0.15, min=0.01, max=10.0, unit='LENGTH',
        description="Maximum radius of a cone"
    )
    min_depth: FloatProperty(
        name="Min Depth", default=1.5, min=0.01, max=100.0, unit='LENGTH',
        description="Minimum depth (height) of a cone"
    )
    max_depth: FloatProperty(
        name="Max Depth", default=2.0, min=0.01, max=100.0, unit='LENGTH',
        description="Maximum depth (height) of a cone"
    )
    num_verts: IntProperty(
        name="Vertices", default=8, min=3, max=24,
        description="Number of vertices at base of cone"
    )
    subdivs: IntProperty(
        name="Subdivides", default=3, min=0, max=8,
        description="Max number of kinks on a cone"
    )
    max_its: IntProperty(
        name="Iterations", default=50, min=1, max=5000,
        description="Number of iterations before giving up, prevents freezing/crashing."
    )
    delete_previous: BoolProperty(
        name="Delete previous generations", default=False,
        description="Deletes everything except the currently selected base mesh"
    )
    add_cap: EnumProperty(
        name="Fill", default='NGON',
        description="Fill the icicle cone base",
        items=[
            ('NGON', 'Ngon', 'Fill with Ngons'),
            ('NOTHING', 'None', 'Do not fill'),
            ('TRIFAN', 'Triangle fan', 'Fill with triangles')
        ]
    )
    direction: EnumProperty(
        name="Points", default='Down',
        description="Set whether icicles point up or down",
        items=[
            ('Up', 'Up', 'Icicles point upwards'),
            ('Down', 'Down', 'Icicles point downwards (default)')
        ]
    )
    preview_btn_tgl: BoolProperty(
        name="PreviewTgl", default=False,
        description="Toggle preview of max/min dimensions in 3D view"
    )
    apply_to: EnumProperty(
        name="Apply To", default='ALL',
        description="Choose whether to generate icicles on all selected edges or only the active edge",
        items=[
            ('ALL', 'All Selected Edges', 'Generate icicles on all selected edges'),
            ('ACTIVE', 'Active Edge Only', 'Generate icicles only on the active edge')
        ]
    )
    gravity_curve: FloatProperty(
        name="Gravity Curve",
        default=0.3, min=0.0, max=1.0,
        description="How much icicles curve downward due to gravity"
    )
    wind_strength: FloatProperty(
        name="Wind Strength",
        default=0.0, min=0.0, max=1.0,
        description="How much wind bends the icicle"
    )
    wind_angle: FloatProperty(
        name="Wind Direction",
        default=0.0, min=-3.1416, max=3.1416,
        subtype='ANGLE',
        description="Direction of wind (radians, 0 = +X, pi/2 = +Y)"
    )
    waviness: FloatProperty(
        name="Waviness",
        default=0.1, min=0.0, max=1.0,
        description="How much random waviness is added to the icicle"
    )
    icicles_per_edge: IntProperty(
        name="Icicles per Edge",
        default=1, min=1, max=10,
        description="Number of icicles to generate per edge"
    )

# -----------------------------------------------------------------------------
# Operators
# -----------------------------------------------------------------------------

def check_same_2d(m_edge, min_rad):
    e1_2d = mathutils.Vector((m_edge.verts[0].co.x, m_edge.verts[0].co.y))
    e2_2d = mathutils.Vector((m_edge.verts[1].co.x, m_edge.verts[1].co.y))
    d_2d = (e1_2d - e2_2d).length
    return d_2d <= 2 * min_rad

def vertical_difference_check(edge):
    return abs(edge.verts[0].co.z - edge.verts[1].co.z) > 0.01

def get_vertex_z(vert):
    return vert.co.z

class OT_GenerateIcicles(Operator):
    bl_idname = "mesh.generate_icicles"
    bl_label = "Generate Icicles"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.icicle_properties
        obj = context.object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Select a mesh in Edit mode.")
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        if props.delete_previous:
            bpy.ops.mesh.select_all(action='INVERT')
            bpy.ops.mesh.delete(type='EDGE')
        edges = [e for e in bm.edges if e.select]
        if props.apply_to == 'ACTIVE':
            active = bm.select_history.active if hasattr(bm.select_history, 'active') else None
            edges = [active] if active and active in edges else []
        for edge in edges:
            v1 = edge.verts[0].co
            v2 = edge.verts[1].co
            for _ in range(props.icicles_per_edge):
                t = random.uniform(0.0, 1.0)
                base_point = v1.lerp(v2, t)
                # Randomize radius and depth
                rad = random.uniform(props.min_rad, props.max_rad)
                depth = random.uniform(props.min_depth, props.max_depth)
                self.add_cone(context, context.object.matrix_world @ base_point, rad, depth)
        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}

    def add_icicles(self, context, bm, edge):
        props = context.scene.icicle_properties
        obj = context.object
        world_matrix = obj.matrix_world
        v1, v2 = edge.verts[0].co, edge.verts[1].co
        pos1, pos2 = world_matrix @ v1, world_matrix @ v2
        total_length = (pos1 - pos2).length
        c_length = 0.0
        rad_dif = props.max_rad - props.min_rad
        depth_dif = props.max_depth - props.min_depth
        iterations = props.max_its
        c = 0
        while c_length < total_length:
            rand_rad = min(props.min_rad + (rad_dif * random.random()), props.max_rad)
            rand_depth = min(props.min_depth + (depth_dif * random.random()), props.max_depth)
            if (total_length - c_length) < (2 * props.min_rad):
                break
            if c_length + (2 * rand_rad) <= total_length:
                c_length += rand_rad
                t_co = pos2 + (c_length / total_length) * (pos1 - pos2)
                c_length += rand_rad
                self.add_cone(context, t_co, rand_rad, rand_depth)
                c = 0
            c += 1
            if c >= iterations:
                break

    def add_cone(self, context, loc_vector, base_rad, cone_depth):
        # Register an undo step before mesh creation
        try:
            bpy.ops.ed.undo_push(message="Add Icicle")
        except Exception:
            pass
        props = context.scene.icicle_properties
        obj = context.object
        bm = bmesh.from_edit_mesh(obj.data)
        segments = 12
        gravity = props.gravity_curve
        wind = props.wind_strength
        wind_angle = props.wind_angle
        waviness = props.waviness
        up_vec = mathutils.Vector((0, 0, -1 if props.direction == 'Down' else 1))
        wind_vec = mathutils.Vector((math.cos(wind_angle), math.sin(wind_angle), 0))
        path_points = []
        # Convert loc_vector from world to local coordinates
        inv_matrix = obj.matrix_world.inverted()
        for i in range(segments + 1):
            t = i / segments
            curve_offset = gravity * (t ** 2) * cone_depth * 0.5
            wind_offset = wind * t * cone_depth * wind_vec
            wave = waviness * base_rad * (random.random() - 0.5)
            wave_vec = mathutils.Vector((math.cos(8 * math.pi * t), math.sin(8 * math.pi * t), 0))
            pos_world = loc_vector + t * cone_depth * up_vec
            pos_world += curve_offset * mathutils.Vector((0, 0, -1))
            pos_world += wind_offset
            pos_world += wave * wave_vec
            pos_local = inv_matrix @ pos_world
            radius = base_rad * (1 - t)
            path_points.append((pos_local, radius))
        # Create vertices and faces in bmesh
        circle_verts = props.num_verts
        bm_verts = []
        for i, (center, radius) in enumerate(path_points):
            ring = []
            for j in range(circle_verts):
                angle = 2 * math.pi * j / circle_verts
                pt = center + radius * mathutils.Vector((math.cos(angle), math.sin(angle), 0))
                v = bm.verts.new(pt)
                ring.append(v)
            bm_verts.append(ring)
        bm.verts.index_update()
        # Create faces
        for i in range(segments):
            for j in range(circle_verts):
                v1 = bm_verts[i][j]
                v2 = bm_verts[i][(j + 1) % circle_verts]
                v3 = bm_verts[i + 1][(j + 1) % circle_verts]
                v4 = bm_verts[i + 1][j]
                try:
                    bm.faces.new([v1, v2, v3, v4])
                except ValueError:
                    pass  # face exists
        # Cap the tip
        tip_center = bm_verts[-1][0].co
        tip = bm.verts.new(tip_center)
        for j in range(circle_verts):
            v1 = bm_verts[-1][j]
            v2 = bm_verts[-1][(j + 1) % circle_verts]
            try:
                bm.faces.new([v1, v2, tip])
            except ValueError:
                pass
        bm.verts.index_update()
        bm.faces.index_update()
        bmesh.update_edit_mesh(obj.data)

# -----------------------------------------------------------------------------
# Preview Operator
# -----------------------------------------------------------------------------

class OT_IciclePreview(Operator):
    bl_idname = "view3d.icicle_preview"
    bl_label = "Icicle Preview"
    bl_options = {'REGISTER'}

    _handle = None
    _timer = None

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob and ob.mode == 'EDIT' and hasattr(context.scene, 'icicle_properties')

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()
        props = context.scene.icicle_properties
        if not props.preview_btn_tgl:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type == 'ESC':
            props.preview_btn_tgl = False
            self.cancel(context)
            return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if OT_IciclePreview._handle is None:
            OT_IciclePreview._handle = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback, (context,), 'WINDOW', 'POST_VIEW')
            OT_IciclePreview._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if OT_IciclePreview._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(OT_IciclePreview._handle, 'WINDOW')
            OT_IciclePreview._handle = None
        if OT_IciclePreview._timer is not None:
            context.window_manager.event_timer_remove(OT_IciclePreview._timer)
            OT_IciclePreview._timer = None

    def draw_callback(self, context):
        props = context.scene.icicle_properties
        obj = context.object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            return
        bm = bmesh.from_edit_mesh(obj.data)
        wm = obj.matrix_world
        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.line_width_set(1.5)
        s_edges = [e for e in bm.edges if e.select and not check_same_2d(e, props.min_rad)]
        m_dir = -1 if props.direction == 'Up' else 1
        for e in s_edges:
            v_dir = (e.verts[0].co - e.verts[1].co).normalized()
            mid_point = (e.verts[0].co + e.verts[1].co) * 0.5
            mid_point_w = wm @ mid_point
            # Draw curved preview path
            segments = 12
            path_pts = []
            up_vec = wm.to_3x3() @ mathutils.Vector((0, 0, -1 if props.direction == 'Down' else 1))
            wind_vec = wm.to_3x3() @ mathutils.Vector((math.cos(props.wind_angle), math.sin(props.wind_angle), 0))
            for i in range(segments + 1):
                t = i / segments
                curve_offset = props.gravity_curve * (t ** 2) * props.max_depth * 0.5
                wind_offset = props.wind_strength * t * props.max_depth * wind_vec
                wave = props.waviness * props.max_rad * (random.random() - 0.5)
                wave_vec = wm.to_3x3() @ mathutils.Vector((math.cos(8 * math.pi * t), math.sin(8 * math.pi * t), 0))
                pos = mid_point_w + t * props.max_depth * up_vec
                pos += curve_offset * mathutils.Vector((0, 0, -1))
                pos += wind_offset
                pos += wave * wave_vec
                path_pts.append(pos)
            shader.bind()
            shader.uniform_float('color', (1, 0.7, 0.2, 1))
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": path_pts})
            batch.draw(shader)
        gpu.state.depth_test_set('NONE')
        gpu.state.line_width_set(1.0)

# -----------------------------------------------------------------------------
# UI Panel
# -----------------------------------------------------------------------------

class VIEW3D_PT_IciclePanel(Panel):
    bl_label = "Icicle Generator"
    bl_idname = "VIEW3D_PT_icicle_generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Icicle Generator'
    bl_context = 'mesh_edit'

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'MESH' and context.object.mode == 'EDIT'

    def draw(self, context):
        layout = self.layout
        props = context.scene.icicle_properties
        col = layout.column(align=True)
        col.label(text='Radius:')
        col.prop(props, 'min_rad')
        col.prop(props, 'max_rad')
        col.label(text='Depth:')
        col.prop(props, 'min_depth')
        col.prop(props, 'max_depth')
        col.label(text='Icicles per Edge:')
        col.prop(props, 'icicles_per_edge')
        col.label(text='Loop cuts:')
        col.prop(props, 'subdivs')
        col.label(text='Cap')
        col.prop(props, 'num_verts')
        col.prop(props, 'add_cap')
        layout.prop(props, 'max_its')
        layout.prop(props, 'delete_previous')
        layout.prop(props, 'direction')
        layout.prop(props, 'gravity_curve')
        layout.prop(props, 'wind_strength')
        layout.prop(props, 'wind_angle')
        layout.prop(props, 'waviness')
        layout.prop(props, 'apply_to')
        label = "Preview On" if props.preview_btn_tgl else "Preview Off"
        row = layout.row(align=True)
        row.prop(props, 'preview_btn_tgl', text=label, toggle=True, icon='HIDE_OFF')
        layout.operator('view3d.icicle_preview', text='Preview', icon='HIDE_OFF')
        layout.operator('mesh.generate_icicles', text='Generate', icon='PHYSICS')

# -----------------------------------------------------------------------------
# Topbar Menu
# -----------------------------------------------------------------------------

def menu_func(self, context):
    self.layout.operator("mesh.generate_icicles", text="Icicle Generator")

# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

classes = [
    IcicleProperties,
    OT_GenerateIcicles,
    OT_IciclePreview,
    VIEW3D_PT_IciclePanel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.icicle_properties = PointerProperty(type=IcicleProperties)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)

def unregister():
    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    del bpy.types.Scene.icicle_properties
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register() 