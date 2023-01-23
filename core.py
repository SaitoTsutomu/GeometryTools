import bpy

from .geometry import dump_geometry_node, load_geometry_node
from .register_class import _get_cls, operator


class CGT_OT_geometry_copy(bpy.types.Operator):
    """Copy nodes"""

    bl_idname = "object.geometry_copy"
    bl_label = "Copy"
    bl_description = "Serialize geometry nodes."

    def execute(self, context):
        if not (obj := bpy.context.object):
            self.report({"WARNING"}, "Select object.")
            return {"CANCELLED"}
        modifiers = next(iter([m for m in obj.modifiers if m.type == "NODES"]), None)
        if not modifiers or not modifiers.node_group:
            self.report({"WARNING"}, "Add geometry node.")
            return {"CANCELLED"}
        bpy.context.window_manager.clipboard = dump_geometry_node()
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
        return {"FINISHED"}


class CGT_PT_bit(bpy.types.Panel):
    bl_label = "GeometryTools"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Edit"

    def draw(self, context):
        operator(self.layout, CGT_OT_geometry_copy)
        operator(self.layout, CGT_OT_geometry_paste)


# __init__.pyで使用
ui_classes = _get_cls(__name__)
