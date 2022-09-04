import importlib
from importlib import import_module
from inspect import getmembers

import bpy
from bpy.types import Operator, Panel


def operator(layout, cls, **kwargs):
    return layout.operator(cls.bl_idname, text=cls.bl_label, **kwargs)


def _get_cls(module_name: str) -> list[type]:
    """モジュール内のUIクラスのリストを取得

    :param module_name: モジュール名
    :return: UIクラスのリスト
    """
    mdl = import_module(module_name)
    ui_classes = []
    for name in dir(mdl):
        if not name.startswith("_"):
            cls = getattr(mdl, name)
            if isinstance(cls, type):
                if issubclass(cls, (Operator, Panel)):
                    ui_classes.append(cls)
    return ui_classes


def _isprop(pr: object) -> bool:
    return isinstance(pr, bpy.props._PropertyDeferred)


# core.py内のOperatorクラスとPanelクラス
ui_classes: list[type] = []


def register():
    global ui_classes
    try:
        from . import core

        importlib.reload(core)
        ui_classes[:] = core.ui_classes
    except (ModuleNotFoundError, AttributeError):
        ui_classes[:] = []

    for ui_class in ui_classes:
        bpy.utils.register_class(ui_class)
        for k, v in getmembers(ui_class, _isprop):
            setattr(bpy.types.Scene, k, v)
    try:
        from .core import register as _register

        _register()
    except ImportError:
        pass


def unregister():
    for ui_class in ui_classes:
        for k, _ in getmembers(ui_class, _isprop):
            delattr(bpy.types.Scene, k)
        bpy.utils.unregister_class(ui_class)
    try:
        from .core import unregister as _unregister

        _unregister()
    except ImportError:
        pass
