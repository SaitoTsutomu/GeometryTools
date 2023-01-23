import bpy

from .register_class import _get_cls, operator


class CGT_OT_geometry_copy(bpy.types.Operator):
    """2つのオブジェクトの異なる点を選択"""

    bl_idname = "object.geometry_copy"
    bl_label = "Copy"
    bl_description = "Serialize geometry nodes."

    def execute(self, context):
        return {"FINISHED"}


class CGT_PT_bit(bpy.types.Panel):
    bl_label = "GeometryTools"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Edit"
    bl_options = {"HEADER_LAYOUT_EXPAND"}

    def draw(self, context):
        prop = operator(self.layout, CGT_OT_geometry_copy)


# __init__.pyで使用
ui_classes = _get_cls(__name__)
