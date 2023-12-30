from functools import partial
from typing import Any, Union

import bpy
import mathutils
import yaml

"""
TODO
- Join Geometryの入力の順番が取得不可
- inputsの非表示が不明
- Selectionのリンク接続が反映されない
- ShaderNodeFloatCurveの再描画
- Undoなどで不安定
"""


def dump_attr(nd: bpy.types.Node, name: str, dtype=None) -> str:
    value = getattr(nd, name)
    if isinstance(value, (mathutils.Vector, mathutils.Euler, mathutils.Color)):
        value = [round(i, 4) for i in value]
    if dtype and isinstance(value, list):
        value = [dtype(i) for i in value]
    elif dtype:
        value = dtype(value)
        if isinstance(value, float):
            value = round(value, 4)
    return f"    {name}: {value}"


def load_attr(nd: bpy.types.Node, name: str, value: object) -> None:
    setattr(nd, name, value)


def dump_mapping(mapping: bpy.types.CurveMapping) -> str:
    res = ["    mapping:"]
    for pnt in mapping.curves[0].points:
        x, y = map(partial(round, ndigits=2), pnt.location)
        res.append(f"    - {pnt.handle_type}, {x}, {y}")
    return "\n".join(res)


def load_mapping(mapping: bpy.types.CurveMapping, value: list[str]) -> None:
    crv = mapping.curves[0]
    for _ in value[2:]:
        crv.points.new(0, 0)
    for pnt, s in zip(crv.points, value):
        pnt.handle_type, *loc = s.split(",")
        pnt.location = tuple(map(float, loc))


def class_name(name):
    """名前からクラス名を求める

    :param name: 名前
    :return: クラス名
    """
    for k, v in ALL_GEOMETRY_NODES.items():
        if name.startswith(k):
            return v
    raise ValueError(f"Not found {name}")


def minimum_class_name(nd: bpy.types.Node) -> str:
    """ノードからクラス名を求める

    :param nd: ノード
    :return: クラス名
    """
    try:
        if class_name(nd.name) == nd.bl_idname:
            return ""  # 名前からクラスが判明する場合、bl_idnameは省略する
    except ValueError:
        pass
    return nd.bl_idname


def sort_node(nd):
    if nd.type == "GROUP_INPUT":
        return -99999
    elif nd.type == "GROUP_OUTPUT":
        return 99999
    return nd.location.x - nd.location.y / 4


def is_struct(val):
    return val.__class__.__name__ == "bpy_prop_array" or isinstance(val, bpy.types.bpy_struct)


def inputs_links(sc):
    lst = []
    for link in sc.links:
        if len(link.from_node.outputs) == 1:
            lst.append(f"{link.from_node.name}")
        else:
            for i, sct in enumerate(link.from_node.outputs):
                if sct.identifier == link.from_socket.identifier:
                    break
            lst.append(f"{link.from_node.name}/{i}")
    return lst


def dump_geometry_node(
    obj: bpy.types.Object = None, simple: bool = False, idname: bool = False
) -> str:
    """ジオメトリーノードのYAMLを返す

    :param obj: オブジェクト
    :param simple: widthとlabelを出さないか
    :param idname: bl_idnameを出さないか
    :return: YAML
    """
    obj = obj or bpy.context.object
    modifiers = next(iter([m for m in obj.modifiers if m.type == "NODES"]), None)
    if not modifiers or not modifiers.node_group:
        return ""
    node_groups, remain = [], [modifiers.node_group]
    while remain:
        node_group = remain.pop()
        node_groups.append(node_group)
        for nd in node_group.nodes:
            if nd.bl_idname == "GeometryNodeGroup":
                ng = nd.node_tree
                if ng not in node_groups:
                    remain.append(ng)
    result = []
    for node_group in reversed(node_groups):
        result.append(f"{node_group.name}:")
        for key, data in zip(["Inputs", "Outputs"], [node_group.inputs, node_group.outputs]):
            if data:
                result.append(f"  {key}:")
                for sc in data:
                    typ = sc.bl_socket_idname
                    info = f"    {sc.identifier}: {sc.name}/{typ}"
                    if typ == "NodeSocketFloatFactor":
                        info += f", {sc.default_value}, {sc.min_value}, {sc.max_value}"
                    result.append(info)
        nodes = sorted(node_group.nodes, key=sort_node)
        for nd in nodes:
            # 未使用の出力は無視する
            if getattr(nd, "is_active_output", None) is False:
                continue
            result.append(f"  {nd.name}:")
            bl_idname = nd.bl_idname if idname else minimum_class_name(nd)
            if bl_idname:
                result.append(f"    bl_idname: {bl_idname}")
            if nd.label and not simple:
                result.append(dump_attr(nd, "label"))
            if nd.bl_idname == "GeometryNodeGroup":
                result.append(f"    node_tree: {nd.node_tree.name}")
            result.append(dump_attr(nd, "location", int))
            if not simple:
                result.append(dump_attr(nd, "width", int))
            if nd.hide:
                result.append(dump_attr(nd, "hide"))
            if nd.use_custom_color:
                result.append(dump_attr(nd, "color"))
            n = len(nd.bl_rna.base.properties)
            for pr in nd.bl_rna.properties[n:]:
                name = pr.identifier
                value = getattr(nd, name)
                if name == "mapping":
                    result.append(dump_mapping(value))
                elif is_struct(value):
                    continue
                elif not isinstance(value, bpy.types.PropertyGroup) and name != "is_active_output":
                    result.append(f"    {name}: {value}")
            inputs = []
            for i, sc in enumerate(nd.inputs):
                name = sc.name
                if sc.name in {"Vector", "Value"} or nd.bl_idname == "GeometryNodeGroup":
                    name = i
                if lst := inputs_links(sc):
                    inputs.append((name, "~" + ";".join(lst)))
                elif hasattr(sc, "default_value"):
                    dval = sc.default_value
                    if isinstance(dval, (bpy.types.Object, bpy.types.Material)):
                        dval = f"{dval.name}"
                    if is_struct(dval):
                        continue
                    elif isinstance(dval, (mathutils.Vector, mathutils.Euler)):
                        dval = list(dval)
                    elif isinstance(dval, float):
                        dval = round(dval, 6)
                    inputs.append((i, dval))
            if inputs:
                result.append("    inputs:")
                for name, dval in inputs:
                    result.append(f"      {name}: {dval}")
    return "\n".join(result)


def load_geometry_node(yml: Union[dict[str, Any], str], obj: bpy.types.Object = None) -> None:
    """YAMLからジオメトリーノードを作成する

    :param yml: YAML
    :param obj: オブジェクト
    """
    yml = yaml.safe_load(yml) if isinstance(yml, str) else yml
    node_group_name = list(yml)[-1] if yml else ""
    for ngkey, ngval in yml.items():
        ngval = ngval.copy()
        node_group = bpy.data.node_groups.get(ngkey)
        if not node_group:
            node_group = bpy.data.node_groups.new("Geometry Nodes", "GeometryNodeTree")
            node_group.name = ngkey
        node_group.inputs.clear()
        node_group.outputs.clear()
        node_group.nodes.clear()
        for key, data in zip(["Inputs", "Outputs"], [node_group.inputs, node_group.outputs]):
            if dc := ngval.pop(key, None):
                for idntf, ioval in dc.items():
                    name, typ = ioval.split("/")
                    if typ.startswith("NodeSocketFloatFactor"):
                        typ, dval, mnvl, mxvl = typ.split(",")
                        sct = data.new(typ, name)
                        sct.default_value = float(dval)
                        sct.min_value = float(mnvl)
                        sct.max_value = float(mxvl)
                    else:
                        sct = data.new(typ, name)
                    # sct.identifier = idntf  # read-onlyで設定不可
        nds = {}
        for key, info in ngval.items():
            if not (typ := info.get("bl_idname")):
                typ = class_name(key)
            nds[key] = nd = node_group.nodes.new(typ)
            nd.select = False
        for key, info in ngval.items():
            nd = nds[key]
            for name, value in info.items():
                if name == "mapping":
                    load_mapping(nd.mapping, value)
                elif name == "node_tree":
                    nd.node_tree = bpy.data.node_groups.get(value)
                elif name == "inputs":
                    for sc, dval in value.items():
                        sct = nd.inputs[sc]
                        if isinstance(dval, str) and dval.startswith("~"):
                            lst = dval[1:].split(";")
                            for pr in lst:
                                frnd, *rem = pr.split("/")
                                # 省略時は0とする
                                frsc = int(rem[0]) if rem else 0
                                try:
                                    node_group.links.new(nds[frnd].outputs[frsc], sct)
                                except (KeyError, IndexError) as e:
                                    print(f"\033[31mKeyError {nd.name} {name} {e}\033[0m")
                        elif sct.bl_idname == "NodeSocketObject":
                            target = bpy.data.objects.get(dval)
                            if target:
                                sct.default_value = target
                        elif sct.bl_idname == "NodeSocketMaterial":
                            target = bpy.data.materials.get(dval)
                            if target:
                                sct.default_value = target
                        else:
                            sct.default_value = dval
                else:
                    load_attr(nd, name, value)
                    if name == "color":
                        nd.use_custom_color = True
    obj = obj or bpy.context.object
    if obj:
        print(obj)
        modifier = next(iter([m for m in obj.modifiers if m.type == "NODES"]), None)
        if not modifier:
            modifier = obj.modifiers.new("GeometryNodes", "NODES")
        node_group = bpy.data.node_groups.get(node_group_name)
        if node_group:
            modifier.node_group = node_group


# https://qiita.com/SaitoTsutomu/items/1bf451085f55bde21224
# 名前→クラス名
ALL_GEOMETRY_NODES = {
    "White Noise Texture": "ShaderNodeTexWhiteNoise",
    "Wave Texture": "ShaderNodeTexWave",
    "Voronoi Texture": "ShaderNodeTexVoronoi",
    "Volume to Mesh": "GeometryNodeVolumeToMesh",
    "Volume Cube": "GeometryNodeVolumeCube",
    "Viewer": "GeometryNodeViewer",
    "Vertex of Corner": "GeometryNodeVertexOfCorner",
    "Vertex Neighbors": "GeometryNodeInputMeshVertexNeighbors",
    "Vector Rotate": "ShaderNodeVectorRotate",
    "Vector Math": "ShaderNodeVectorMath",
    "Vector Curves": "ShaderNodeVectorCurve",
    "Vector": "FunctionNodeInputVector",
    "Value to String": "FunctionNodeValueToString",
    "Value": "ShaderNodeValue",
    "UV Unwrap": "GeometryNodeUVUnwrap",
    "UV Sphere": "GeometryNodeMeshUVSphere",
    "Trim Curve": "GeometryNodeTrimCurve",
    "Triangulate": "GeometryNodeTriangulate",
    "Translate Instances": "GeometryNodeTranslateInstances",
    "Transform Geometry": "GeometryNodeTransform",
    "Switch": "GeometryNodeSwitch",
    "Subdivision Surface": "GeometryNodeSubdivisionSurface",
    "Subdivide Mesh": "GeometryNodeSubdivideMesh",
    "Subdivide Curve": "GeometryNodeSubdivideCurve",
    "String to Curves": "GeometryNodeStringToCurves",
    "String Length": "FunctionNodeStringLength",
    "String": "FunctionNodeInputString",
    "Store Named Attribute": "GeometryNodeStoreNamedAttribute",
    "Star": "GeometryNodeCurveStar",
    "Split Edges": "GeometryNodeSplitEdges",
    "Spline Resolution": "GeometryNodeInputSplineResolution",
    "Spline Parameter": "GeometryNodeSplineParameter",
    "Spline Length": "GeometryNodeSplineLength",
    "Special Characters": "FunctionNodeInputSpecialCharacters",
    "Slice String": "FunctionNodeSliceString",
    "Simulation Output": "GeometryNodeSimulationOutput",
    "Simulation Input": "GeometryNodeSimulationInput",
    "Signed Distance": "GeometryNodeInputSignedDistance",
    "Shortest Edge Paths": "GeometryNodeInputShortestEdgePaths",
    "Set Spline Type": "GeometryNodeCurveSplineType",
    "Set Spline Resolution": "GeometryNodeSetSplineResolution",
    "Set Spline Cyclic": "GeometryNodeSetSplineCyclic",
    "Set Shade Smooth": "GeometryNodeSetShadeSmooth",
    "Set Selection": "GeometryNodeToolSetSelection",
    "Set Position": "GeometryNodeSetPosition",
    "Set Point Radius": "GeometryNodeSetPointRadius",
    "Set Material Index": "GeometryNodeSetMaterialIndex",
    "Set Material": "GeometryNodeSetMaterial",
    "Set ID": "GeometryNodeSetID",
    "Set Handle Type": "GeometryNodeCurveSetHandles",
    "Set Handle Positions": "GeometryNodeSetCurveHandlePositions",
    "Set Face Set": "GeometryNodeToolSetFaceSet",
    "Set Curve Tilt": "GeometryNodeSetCurveTilt",
    "Set Curve Radius": "GeometryNodeSetCurveRadius",
    "Set Curve Normal": "GeometryNodeSetCurveNormal",
    "Separate XYZ": "ShaderNodeSeparateXYZ",
    "Separate RGB": "ShaderNodeSeparateRGB",
    "Separate Geometry": "GeometryNodeSeparateGeometry",
    "Separate Components": "GeometryNodeSeparateComponents",
    "Separate Color": "FunctionNodeSeparateColor",
    "Self Object": "GeometryNodeSelfObject",
    "Selection": "GeometryNodeToolSelection",
    "Scene Time": "GeometryNodeInputSceneTime",
    "Scale Instances": "GeometryNodeScaleInstances",
    "Scale Elements": "GeometryNodeScaleElements",
    "Sample Volume": "GeometryNodeSampleVolume",
    "Sample UV Surface": "GeometryNodeSampleUVSurface",
    "Sample Nearest Surface": "GeometryNodeSampleNearestSurface",
    "Sample Nearest": "GeometryNodeSampleNearest",
    "Sample Index": "GeometryNodeSampleIndex",
    "Sample Curve": "GeometryNodeSampleCurve",
    "SDF Volume Sphere": "GeometryNodeSDFVolumeSphere",
    "Rotation to Quaternion": "FunctionNodeRotationToQuaternion",
    "Rotation to Euler": "FunctionNodeRotationToEuler",
    "Rotation to Axis Angle": "FunctionNodeRotationToAxisAngle",
    "Rotate Vector": "FunctionNodeRotateVector",
    "Rotate Instances": "GeometryNodeRotateInstances",
    "Rotate Euler": "FunctionNodeRotateEuler",
    "Reverse Curve": "GeometryNodeReverseCurve",
    "Resample Curve": "GeometryNodeResampleCurve",
    "Reroute": "NodeReroute",
    "Replace String": "FunctionNodeReplaceString",
    "Replace Material": "GeometryNodeReplaceMaterial",
    "Repeat Output": "GeometryNodeRepeatOutput",
    "Repeat Input": "GeometryNodeRepeatInput",
    "Remove Named Attribute": "GeometryNodeRemoveAttribute",
    "Realize Instances": "GeometryNodeRealizeInstances",
    "Raycast": "GeometryNodeRaycast",
    "Random Value": "FunctionNodeRandomValue",
    "Radius": "GeometryNodeInputRadius",
    "RGB Curves": "ShaderNodeRGBCurve",
    "Quaternion to Rotation": "FunctionNodeQuaternionToRotation",
    "Quadrilateral": "GeometryNodeCurvePrimitiveQuadrilateral",
    "Quadratic Bezier": "GeometryNodeCurveQuadraticBezier",
    "Position": "GeometryNodeInputPosition",
    "Points to Volume": "GeometryNodePointsToVolume",
    "Points to Vertices": "GeometryNodePointsToVertices",
    "Points to SDF Volume": "GeometryNodePointsToSDFVolume",
    "Points to Curves": "GeometryNodePointsToCurves",
    "Points of Curve": "GeometryNodePointsOfCurve",
    "Points": "GeometryNodePoints",
    "Pack UV Islands": "GeometryNodeUVPackIslands",
    "Offset SDF Volume": "GeometryNodeOffsetSDFVolume",
    "Offset Point in Curve": "GeometryNodeOffsetPointInCurve",
    "Offset Corner in Face": "GeometryNodeOffsetCornerInFace",
    "Object Info": "GeometryNodeObjectInfo",
    "Normal": "GeometryNodeInputNormal",
    "Noise Texture": "ShaderNodeTexNoise",
    "Named Attribute": "GeometryNodeInputNamedAttribute",
    "Musgrave Texture": "ShaderNodeTexMusgrave",
    "MixRGB": "ShaderNodeMixRGB",
    "Mix": "ShaderNodeMix",
    "Mesh to Volume": "GeometryNodeMeshToVolume",
    "Mesh to SDF Volume": "GeometryNodeMeshToSDFVolume",
    "Mesh to Points": "GeometryNodeMeshToPoints",
    "Mesh to Curve": "GeometryNodeMeshToCurve",
    "Mesh Line": "GeometryNodeMeshLine",
    "Mesh Island": "GeometryNodeInputMeshIsland",
    "Mesh Circle": "GeometryNodeMeshCircle",
    "Mesh Boolean": "GeometryNodeMeshBoolean",
    "Merge by Distance": "GeometryNodeMergeByDistance",
    "Mean Filter SDF Volume": "GeometryNodeMeanFilterSDFVolume",
    "Math": "ShaderNodeMath",
    "Material Selection": "GeometryNodeMaterialSelection",
    "Material Index": "GeometryNodeInputMaterialIndex",
    "Material": "GeometryNodeInputMaterial",
    "Map Range": "ShaderNodeMapRange",
    "Magic Texture": "ShaderNodeTexMagic",
    "Join Strings": "GeometryNodeStringJoin",
    "Join Geometry": "GeometryNodeJoinGeometry",
    "Is Viewport": "GeometryNodeIsViewport",
    "Is Spline Cyclic": "GeometryNodeInputSplineCyclic",
    "Is Face Smooth": "GeometryNodeInputShadeSmooth",
    "Is Face Planar": "GeometryNodeInputMeshFaceIsPlanar",
    "Is Edge Smooth": "GeometryNodeInputEdgeSmooth",
    "Invert Rotation": "FunctionNodeInvertRotation",
    "Interpolate Curves": "GeometryNodeInterpolateCurves",
    "Integer": "FunctionNodeInputInt",
    "Instances to Points": "GeometryNodeInstancesToPoints",
    "Instance on Points": "GeometryNodeInstanceOnPoints",
    "Instance Scale": "GeometryNodeInputInstanceScale",
    "Instance Rotation": "GeometryNodeInputInstanceRotation",
    "Index of Nearest": "GeometryNodeIndexOfNearest",
    "Index": "GeometryNodeInputIndex",
    "Image Texture": "GeometryNodeImageTexture",
    "Image Info": "GeometryNodeImageInfo",
    "Image": "GeometryNodeInputImage",
    "Ico Sphere": "GeometryNodeMeshIcoSphere",
    "ID": "GeometryNodeInputID",
    "Handle Type Selection": "GeometryNodeCurveHandleTypeSelection",
    "Group Output": "NodeGroupOutput",
    "Group Input": "NodeGroupInput",
    "Grid": "GeometryNodeMeshGrid",
    "Gradient Texture": "ShaderNodeTexGradient",
    "GeometryNodeGroup": "GeometryNodeGroup",
    "Geometry to Instance": "GeometryNodeGeometryToInstance",
    "Geometry Proximity": "GeometryNodeProximity",
    "Frame": "NodeFrame",
    "Float to Integer": "FunctionNodeFloatToInt",
    "Float Curve": "ShaderNodeFloatCurve",
    "Flip Faces": "GeometryNodeFlipFaces",
    "Fillet Curve": "GeometryNodeFilletCurve",
    "Fill Curve": "GeometryNodeFillCurve",
    "Face of Corner": "GeometryNodeFaceOfCorner",
    "Face Set": "GeometryNodeToolFaceSet",
    "Face Neighbors": "GeometryNodeInputMeshFaceNeighbors",
    "Face Group Boundaries": "GeometryNodeMeshFaceSetBoundaries",
    "Face Area": "GeometryNodeInputMeshFaceArea",
    "Extrude Mesh": "GeometryNodeExtrudeMesh",
    "Evaluate on Domain": "GeometryNodeFieldOnDomain",
    "Evaluate at Index": "GeometryNodeFieldAtIndex",
    "Euler to Rotation": "FunctionNodeEulerToRotation",
    "Endpoint Selection": "GeometryNodeCurveEndpointSelection",
    "Edges to Face Groups": "GeometryNodeEdgesToFaceGroups",
    "Edges of Vertex": "GeometryNodeEdgesOfVertex",
    "Edges of Corner": "GeometryNodeEdgesOfCorner",
    "Edge Vertices": "GeometryNodeInputMeshEdgeVertices",
    "Edge Paths to Selection": "GeometryNodeEdgePathsToSelection",
    "Edge Paths to Curves": "GeometryNodeEdgePathsToCurves",
    "Edge Neighbors": "GeometryNodeInputMeshEdgeNeighbors",
    "Edge Angle": "GeometryNodeInputMeshEdgeAngle",
    "Duplicate Elements": "GeometryNodeDuplicateElements",
    "Dual Mesh": "GeometryNodeDualMesh",
    "Domain Size": "GeometryNodeAttributeDomainSize",
    "Distribute Points on Faces": "GeometryNodeDistributePointsOnFaces",
    "Distribute Points in Volume": "GeometryNodeDistributePointsInVolume",
    "Delete Geometry": "GeometryNodeDeleteGeometry",
    "Deform Curves on Surface": "GeometryNodeDeformCurvesOnSurface",
    "Cylinder": "GeometryNodeMeshCylinder",
    "Curve to Points": "GeometryNodeCurveToPoints",
    "Curve to Mesh": "GeometryNodeCurveToMesh",
    "Curve of Point": "GeometryNodeCurveOfPoint",
    "Curve Tilt": "GeometryNodeInputCurveTilt",
    "Curve Tangent": "GeometryNodeInputTangent",
    "Curve Spiral": "GeometryNodeCurveSpiral",
    "Curve Line": "GeometryNodeCurvePrimitiveLine",
    "Curve Length": "GeometryNodeCurveLength",
    "Curve Handle Positions": "GeometryNodeInputCurveHandlePositions",
    "Curve Circle": "GeometryNodeCurvePrimitiveCircle",
    "Cube": "GeometryNodeMeshCube",
    "Corners of Vertex": "GeometryNodeCornersOfVertex",
    "Corners of Face": "GeometryNodeCornersOfFace",
    "Corners of Edge": "GeometryNodeCornersOfEdge",
    "Convex Hull": "GeometryNodeConvexHull",
    "Cone": "GeometryNodeMeshCone",
    "Compare": "FunctionNodeCompare",
    "Combine XYZ": "ShaderNodeCombineXYZ",
    "Combine RGB": "ShaderNodeCombineRGB",
    "Combine Color": "FunctionNodeCombineColor",
    "Color Ramp": "ShaderNodeValToRGB",
    "Color": "FunctionNodeInputColor",
    "Collection Info": "GeometryNodeCollectionInfo",
    "Clamp": "ShaderNodeClamp",
    "Checker Texture": "ShaderNodeTexChecker",
    "Capture Attribute": "GeometryNodeCaptureAttribute",
    "Brick Texture": "ShaderNodeTexBrick",
    "Bounding Box": "GeometryNodeBoundBox",
    "Boolean Math": "FunctionNodeBooleanMath",
    "Boolean": "FunctionNodeInputBool",
    "Blur Attribute": "GeometryNodeBlurAttribute",
    "Bezier Segment": "GeometryNodeCurvePrimitiveBezierSegment",
    "Axis Angle to Rotation": "FunctionNodeAxisAngleToRotation",
    "Attribute Statistic": "GeometryNodeAttributeStatistic",
    "Arc": "GeometryNodeCurveArc",
    "Align Euler to Vector": "FunctionNodeAlignEulerToVector",
    "Accumulate Field": "GeometryNodeAccumulateField",
    "3D Cursor": "GeometryNodeTool3DCursor",
}
