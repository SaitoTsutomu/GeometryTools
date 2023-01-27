import bpy

from .geometry import dump_geometry_node, load_geometry_node
from .register_class import _get_cls, operator


class CGT_OT_geometry_copy(bpy.types.Operator):
    """Copy nodes"""

    bl_idname = "object.geometry_copy"
    bl_label = "Copy"
    bl_description = "Serialize geometry nodes."

    simple: bpy.props.BoolProperty() = bpy.props.BoolProperty()  # type: ignore

    def execute(self, context):
        if not (obj := bpy.context.object):
            self.report({"WARNING"}, "Select object.")
            return {"CANCELLED"}
        modifiers = next(iter([m for m in obj.modifiers if m.type == "NODES"]), None)
        if not modifiers or not modifiers.node_group:
            self.report({"WARNING"}, "Add geometry node.")
            return {"CANCELLED"}
        bpy.context.window_manager.clipboard = dump_geometry_node(simple=self.simple)
        self.report({"INFO"}, "Copied to clipboard.")
        return {"FINISHED"}


class CGT_OT_geometry_paste(bpy.types.Operator):
    """Paste nodes"""

    bl_idname = "object.geometry_paste"
    bl_label = "Paste"
    bl_description = "Deserialize geometry nodes."

    def execute(self, context):
        if not (obj := bpy.context.object):
            self.report({"WARNING"}, "Select object.")
            return {"CANCELLED"}
        modifiers = next(iter([m for m in obj.modifiers if m.type == "NODES"]), None)
        if not modifiers:
            modifiers = bpy.context.object.modifiers.new("GeometryNodes", "NODES")
        if not modifiers.node_group:
            modifiers.node_group = bpy.data.node_groups.new("Geometry Nodes", "GeometryNodeTree")
        load_geometry_node(str(bpy.context.window_manager.clipboard))
        ops_func(bpy.ops.node.view_all, "NODE_EDITOR")
        return {"FINISHED"}


class CGT_PT_bit(bpy.types.Panel):
    bl_label = "GeometryTools"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Edit"

    def draw(self, context):
        self.layout.prop(context.scene, "simple", text="Simple")
        prop = operator(self.layout, CGT_OT_geometry_copy)
        prop.simple = context.scene.simple
        operator(self.layout, CGT_OT_geometry_paste)


def ops_func(func, area_type, region_type="WINDOW"):
    for area in bpy.context.screen.areas:
        if area.type == area_type:
            for region in area.regions:
                if region.type == region_type:
                    ctx = bpy.context.copy()
                    ctx["area"] = area
                    ctx["region"] = region
                    try:
                        func(ctx)
                    except RuntimeError:
                        pass
                    return


# __init__.pyで使用
ui_classes = _get_cls(__name__)
