"""Lazy, repeatable menu registration. Scene actions run only when clicked."""
import importlib
import traceback
from functools import partial
from maya import cmds, mel

MENU = "xaiaToolsMenu"
# A single registry defines categories, labels, modules, and entry points.
TOOLS = (
    ("Modeling", "Quad Patch", "quad_patch", "instantQPatchUI"),
    ("Curves", "Text to Curves", "text_to_curve", "show_text_curve_ui"),
    ("Curves", "Arnold Curve Rendering", "render_curves", "show_arnold_curves_tool"),
    ("Shading & Materials", "Bulk Arnold Material Editor", "arnold_bulk_edit", "show"),
    ("Shading & Materials", "Convert Shaders to Arnold", "sh_to_aiStandardSurface", "build_ui"),
    ("Shading & Materials", "Circular Ramp Creator", "circular_ramp_creator", "build_ui"),
    ("Shading & Materials", "Collect Materials into Object Set", "materials_to_object_set", "build_ui"),
    ("Arnold", "Stand-in Viewport Modes", "ass_viewport_modes", "show"),
    ("Arnold", "Subdivision Manager", "arnold_subdivision_manager", "show"),
    ("Arnold", "Stand-in & Texture Path Resolver", "arnold_path_resolver_v1_1", "show_arnold_path_resolver"),
    ("Scene & Naming", "Studio Renamer", "studio_renamer", "show"),
    ("Scene & Naming", "Group Selected Meshes by Material", "mat_to_group", "group_selected_meshes_by_material_in_their_top_group"),
    ("Scene & Naming", "Remove Non-default Namespaces", "remove_name_spaces", "remove_all_namespaces"),
    ("Viewport", "Framing & Composition Overlay", "maya_frame_overlay", "show_framing_window"),
)
_windows = {}  # Retain Qt dialogs returned by legacy tools.


def launch(module, function, *_):
    try:
        if module == "session_clipboard":
            tool = importlib.import_module("xaia_tools.session_clipboard")
        else:
            tool = importlib.import_module("xaia_tools.tools." + module)
        if module in ("mat_to_group", "remove_name_spaces"):
            cmds.undoInfo(openChunk=True, chunkName="Xaia Tools")
            try:
                return getattr(tool, function)()
            finally:
                cmds.undoInfo(closeChunk=True)
        result = getattr(tool, function)()
        if result is not None:
            _windows[module] = result
        return result
    except Exception as exc:
        traceback.print_exc()
        cmds.warning("Xaia Tools: {}".format(exc))


def remove(*_):
    if cmds.menu(MENU, exists=True):
        cmds.deleteUI(MENU)


def install(*_):
    if cmds.about(batch=True):
        return None
    remove()
    main = mel.eval("$xaiaMain = $gMainWindow")
    cmds.menu(MENU, label="Xaia Tools", parent=main, tearOff=True)
    clipboard = cmds.menuItem(label="Session Clipboard", subMenu=True, parent=MENU, tearOff=True)
    for label, function in (("Copy Selection", "copy_selection"), ("Paste into This Session", "paste"),
                            ("Clipboard Window...", "show")):
        cmds.menuItem(label=label, parent=clipboard, command=partial(launch, "session_clipboard", function))
    groups = {}
    for category, label, module, function in TOOLS:
        if category not in groups:
            groups[category] = cmds.menuItem(label=category, subMenu=True, parent=MENU, tearOff=True)
        cmds.menuItem(label=label, parent=groups[category], command=partial(launch, module, function))
    cmds.menuItem(divider=True, parent=MENU)
    cmds.menuItem(label="Rebuild Xaia Tools Menu", parent=MENU, command=install)
    return MENU
