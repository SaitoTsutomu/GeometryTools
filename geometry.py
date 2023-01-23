from functools import partial
from typing import Any, Union

import bpy
import mathutils
import yaml

"""
TODO
- Join Geometryの入力の順番が取得不可
- inputsの非表示が不明
- ShaderNodeFloatCurveの再描画
- Undoなどで不安定
"""


def dump_attr(nd: bpy.types.Node, name: str, dtype=None) -> str:
    value = getattr(nd, name)
    if dtype:
        value = dtype(value)
    elif isinstance(value, mathutils.Vector):
        value = list(value.to_tuple(3))
    return f"  {name}: {value}"


def load_attr(nd: bpy.types.Node, name: str, value: object) -> None:
    setattr(nd, name, value)


def dump_mapping(mapping: bpy.types.CurveMapping) -> str:
    res = ["  mapping:"]
    for pnt in mapping.curves[0].points:
        x, y = map(partial(round, ndigits=2), pnt.location)
        res.append(f"  - {pnt.handle_type}, {x}, {y}")
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
    if nd.type == "GROUP_OUTPUT":
        return 99999
    return nd.location.x - nd.location.y / 4


def dump_geometry_node(obj: bpy.types.Object = None) -> str:
    """ジオメトリーノードのYAMLを返す

    :param obj: オブジェクト
    :return: YAML
    """
    obj = obj or bpy.context.object
    modifiers = next(iter([m for m in obj.modifiers if m.type == "NODES"]), None)
    if not modifiers or not modifiers.node_group:
        return ""
    node_group = modifiers.node_group
    result = []
    for key, data in zip(["Inputs", "Outputs"], [node_group.inputs, node_group.outputs]):
        if data:
            result.append(f"{key}:")
            for sc in data:
                result.append(f"  {sc.name}: {sc.bl_socket_idname}")
    nodes = sorted(node_group.nodes, key=sort_node)
    for nd in nodes:
        # 未使用の出力は無視する
        if getattr(nd, "is_active_output", None) is False:
            continue
        result.append(f"{nd.name}:")
        if bl_idname := minimum_class_name(nd):
            result.append(f"  bl_idname: {bl_idname}")
        if nd.label:
            result.append(dump_attr(nd, "label"))
        result.append(dump_attr(nd, "location"))
        result.append(dump_attr(nd, "width", int))
        if nd.hide:
            result.append(dump_attr(nd, "hide"))
        n = len(nd.bl_rna.base.properties)
        for pr in nd.bl_rna.properties[n:]:
            name = pr.identifier
            value = getattr(nd, name)
            if name == "mapping":
                result.append(dump_mapping(value))
            elif not isinstance(value, bpy.types.PropertyGroup) and name != "is_active_output":
                result.append(f"  {name}: {value}")
        inputs = []
        for i, sc in enumerate(nd.inputs):
            name = i if sc.name in {"Vector"} else sc.name
            lst = [f"{link.from_node.name}/{link.from_socket.name}" for link in sc.links]
            if lst:
                inputs.append((name, "~" + ";".join(lst)))
            elif hasattr(sc, "default_value"):
                dval = sc.default_value
                if dval.__class__.__name__ == "bpy_prop_array" or isinstance(
                    dval, bpy.types.bpy_struct
                ):
                    continue
                if isinstance(dval, mathutils.Vector):
                    dval = list(dval)
                inputs.append((i, dval))
        if inputs:
            result.append("  inputs:")
            for name, dval in inputs:
                result.append(f"    {name}: {dval}")
    return "\n".join(result)


def load_geometry_node(yml: Union[dict[str, Any], str], obj: bpy.types.Object = None) -> None:
    """YAMLからジオメトリーノードを作成する

    :param yml: YAML
    :param obj: オブジェクト
    """
    yml = yaml.safe_load(yml) if isinstance(yml, str) else yml.copy()
    obj = obj or bpy.context.object
    modifiers = next(iter([m for m in obj.modifiers if m.type == "NODES"]), None)
    if not modifiers or not modifiers.node_group:
        return None
    node_group = modifiers.node_group
    node_group.inputs.clear()
    node_group.outputs.clear()
    node_group.nodes.clear()
    for key, data in zip(["Inputs", "Outputs"], [node_group.inputs, node_group.outputs]):
        if dc := yml.pop(key, None):
            for name, typ in dc.items():
                data.new(typ, name)
    nds = {}
    for key, info in yml.items():
        if not (typ := info.get("bl_idname")):
            typ = class_name(key)
        nds[key] = nd = node_group.nodes.new(typ)
        nd.select = False
    for key, info in yml.items():
        nd = nds[key]
        for name, value in info.items():
            if name == "mapping":
                load_mapping(nd.mapping, value)
            elif name == "inputs":
                for sc, dval in value.items():
                    if isinstance(dval, str) and dval.startswith("~"):
                        lst = dval[1:].split(";")
                        for pr in lst:
                            frnd, *rem = pr.split("/")
                            # 省略時は0とする
                            frsc = rem[0] if rem else 0
                            node_group.links.new(nds[frnd].outputs[frsc], nd.inputs[sc])
                    else:
                        nd.inputs[sc].default_value = dval
            else:
                load_attr(nd, name, value)


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
    "Transform": "GeometryNodeTransform",
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
    "Shortest Edge Paths": "GeometryNodeInputShortestEdgePaths",
    "Set Spline Type": "GeometryNodeCurveSplineType",
    "Set Spline Resolution": "GeometryNodeSetSplineResolution",
    "Set Spline Cyclic": "GeometryNodeSetSplineCyclic",
    "Set Shade Smooth": "GeometryNodeSetShadeSmooth",
    "Set Position": "GeometryNodeSetPosition",
    "Set Point Radius": "GeometryNodeSetPointRadius",
    "Set Material Index": "GeometryNodeSetMaterialIndex",
    "Set Material": "GeometryNodeSetMaterial",
    "Set ID": "GeometryNodeSetID",
    "Set Handle Type": "GeometryNodeCurveSetHandles",
    "Set Handle Positions": "GeometryNodeSetCurveHandlePositions",
    "Set Curve Tilt": "GeometryNodeSetCurveTilt",
    "Set Curve Radius": "GeometryNodeSetCurveRadius",
    "Set Curve Normal": "GeometryNodeSetCurveNormal",
    "Separate XYZ": "ShaderNodeSeparateXYZ",
    "Separate RGB": "ShaderNodeSeparateRGB",
    "Separate Geometry": "GeometryNodeSeparateGeometry",
    "Separate Components": "GeometryNodeSeparateComponents",
    "Separate Color": "FunctionNodeSeparateColor",
    "Self Object": "GeometryNodeSelfObject",
    "Scene Time": "GeometryNodeInputSceneTime",
    "Scale Instances": "GeometryNodeScaleInstances",
    "Scale Elements": "GeometryNodeScaleElements",
    "Sample UV Surface": "GeometryNodeSampleUVSurface",
    "Sample Nearest Surface": "GeometryNodeSampleNearestSurface",
    "Sample Nearest": "GeometryNodeSampleNearest",
    "Sample Index": "GeometryNodeSampleIndex",
    "Sample Curve": "GeometryNodeSampleCurve",
    "Rotate Instances": "GeometryNodeRotateInstances",
    "Rotate Euler": "FunctionNodeRotateEuler",
    "Reverse Curve": "GeometryNodeReverseCurve",
    "Resample Curve": "GeometryNodeResampleCurve",
    "Reroute": "NodeReroute",
    "Replace String": "FunctionNodeReplaceString",
    "Replace Material": "GeometryNodeReplaceMaterial",
    "Remove Named Attribute": "GeometryNodeRemoveAttribute",
    "Realize Instances": "GeometryNodeRealizeInstances",
    "Raycast": "GeometryNodeRaycast",
    "Random Value": "FunctionNodeRandomValue",
    "Radius": "GeometryNodeInputRadius",
    "RGB Curves": "ShaderNodeRGBCurve",
    "Quadrilateral": "GeometryNodeCurvePrimitiveQuadrilateral",
    "Quadratic Bezier": "GeometryNodeCurveQuadraticBezier",
    "Position": "GeometryNodeInputPosition",
    "Points to Volume": "GeometryNodePointsToVolume",
    "Points to Vertices": "GeometryNodePointsToVertices",
    "Points of Curve": "GeometryNodePointsOfCurve",
    "Points": "GeometryNodePoints",
    "Pack UV Islands": "GeometryNodeUVPackIslands",
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
    "Mesh to Points": "GeometryNodeMeshToPoints",
    "Mesh to Curve": "GeometryNodeMeshToCurve",
    "Mesh Line": "GeometryNodeMeshLine",
    "Mesh Island": "GeometryNodeInputMeshIsland",
    "Mesh Circle": "GeometryNodeMeshCircle",
    "Mesh Boolean": "GeometryNodeMeshBoolean",
    "Merge by Distance": "GeometryNodeMergeByDistance",
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
    "Is Shade Smooth": "GeometryNodeInputShadeSmooth",
    "Is Face Planar": "GeometryNodeInputMeshFaceIsPlanar",
    "Interpolate Domain": "GeometryNodeFieldOnDomain",
    "Integer": "FunctionNodeInputInt",
    "Instances to Points": "GeometryNodeInstancesToPoints",
    "Instance on Points": "GeometryNodeInstanceOnPoints",
    "Instance Scale": "GeometryNodeInputInstanceScale",
    "Instance Rotation": "GeometryNodeInputInstanceRotation",
    "Index": "GeometryNodeInputIndex",
    "Image Texture": "GeometryNodeImageTexture",
    "Ico Sphere": "GeometryNodeMeshIcoSphere",
    "ID": "GeometryNodeInputID",
    "Handle Type Selection": "GeometryNodeCurveHandleTypeSelection",
    "Group Output": "NodeGroupOutput",
    "Group Input": "NodeGroupInput",
    "Group": "GeometryNodeGroup",
    "Grid": "GeometryNodeMeshGrid",
    "Gradient Texture": "ShaderNodeTexGradient",
    "Geometry to Instance": "GeometryNodeGeometryToInstance",
    "Geometry Proximity": "GeometryNodeProximity",
    "Frame": "NodeFrame",
    "Float to Integer": "FunctionNodeFloatToInt",
    "Float Curve": "ShaderNodeFloatCurve",
    "Flip Faces": "GeometryNodeFlipFaces",
    "Fillet Curve": "GeometryNodeFilletCurve",
    "Fill Curve": "GeometryNodeFillCurve",
    "Field at Index": "GeometryNodeFieldAtIndex",
    "Face of Corner": "GeometryNodeFaceOfCorner",
    "Face Set Boundaries": "GeometryNodeMeshFaceSetBoundaries",
    "Face Neighbors": "GeometryNodeInputMeshFaceNeighbors",
    "Face Area": "GeometryNodeInputMeshFaceArea",
    "Extrude Mesh": "GeometryNodeExtrudeMesh",
    "Endpoint Selection": "GeometryNodeCurveEndpointSelection",
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
    "Convex Hull": "GeometryNodeConvexHull",
    "Cone": "GeometryNodeMeshCone",
    "Compare": "FunctionNodeCompare",
    "Combine XYZ": "ShaderNodeCombineXYZ",
    "Combine RGB": "ShaderNodeCombineRGB",
    "Combine Color": "FunctionNodeCombineColor",
    "ColorRamp": "ShaderNodeValToRGB",
    "Color": "FunctionNodeInputColor",
    "Collection Info": "GeometryNodeCollectionInfo",
    "Clamp": "ShaderNodeClamp",
    "Checker Texture": "ShaderNodeTexChecker",
    "Capture Attribute": "GeometryNodeCaptureAttribute",
    "Brick Texture": "ShaderNodeTexBrick",
    "Bounding Box": "GeometryNodeBoundBox",
    "Boolean Math": "FunctionNodeBooleanMath",
    "Boolean": "FunctionNodeInputBool",
    "Bezier Segment": "GeometryNodeCurvePrimitiveBezierSegment",
    "Attribute Statistic": "GeometryNodeAttributeStatistic",
    "Arc": "GeometryNodeCurveArc",
    "Align Euler to Vector": "FunctionNodeAlignEulerToVector",
    "Accumulate Field": "GeometryNodeAccumulateField",
}
