import bpy

from .register_class import _get_cls, operator


class CDO_OT_diff_obj(bpy.types.Operator):
    """2つのオブジェクトの異なる点を選択"""

    bl_idname = "object.diff_obj"
    bl_label = "Select Diff 2 Obj"
    bl_description = "Select the different vertices of 2 objects."

    limit: bpy.props.IntProperty() = bpy.props.IntProperty(default=1000)  # type: ignore

    def execute(self, context):
        objs = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if len(objs) != 2:
            self.report({"INFO"}, "Select 2 objects.")
            return {"CANCELLED"}
        bpy.ops.object.mode_set(mode="EDIT")  # for deselect
        bpy.ops.mesh.select_mode(type="VERT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode="OBJECT")  # for select
        dif = set(tuple(vtx.co) for vtx in objs[0].data.vertices) ^ set(
            tuple(vtx.co) for vtx in objs[1].data.vertices
        )
        for obj in objs:
            count = 0
            for i, vtx in enumerate(obj.data.vertices):
                if tuple(vtx.co) in dif:
                    if count >= self.limit:
                        break
                    count += 1
                    obj.data.vertices[i].select = True
        bpy.ops.object.mode_set(mode="EDIT")  # for confirm
        # show wireframe
        for area in bpy.context.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.type = "WIREFRAME"
        return {"FINISHED"}


class CDO_PT_bit(bpy.types.Panel):
    bl_label = "DiffObj"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Edit"

    def draw(self, context):
        self.layout.prop(context.scene, "limit", text="Limit")
        prop = operator(self.layout, CDO_OT_diff_obj)
        prop.limit = context.scene.limit


# __init__.pyで使用
ui_classes = _get_cls(__name__)
