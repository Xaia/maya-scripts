"""
Material Collector for Maya
Gathers all materials assigned to selected meshes (or groups) into a Maya Object Set.
"""

import maya.cmds as cmds


# ─────────────────────────────────────────────────────────────────────────────
# Core logic
# ─────────────────────────────────────────────────────────────────────────────

# Shader types to ignore – internal Maya defaults that are never user-assigned
_IGNORED_SHADERS = {"lambert1", "particleCloud1", "shaderGlow1"}
_IGNORED_TYPES   = {"defaultShader", "lambert"}   # lambert1 is the only default lambert


def get_meshes_from_selection():
    """
    Returns all mesh transform nodes reachable from the current selection.
    Handles:
      - Directly selected mesh transforms
      - Groups (recursively finds all mesh descendants)
      - Directly selected mesh shapes (returns their parent transform)
    """
    selection = cmds.ls(selection=True, long=True)
    if not selection:
        return []

    mesh_transforms = set()

    for node in selection:
        node_type = cmds.nodeType(node)

        if node_type == "mesh":
            # A shape was selected directly – get its transform parent
            parent = cmds.listRelatives(node, parent=True, fullPath=True)
            if parent:
                mesh_transforms.add(parent[0])

        elif node_type == "transform":
            # Could be a mesh transform or a group – check descendants
            shapes = cmds.listRelatives(
                node, allDescendents=True, type="mesh", fullPath=True
            ) or []

            if shapes:
                # Collect the transform parent of each found shape
                for shape in shapes:
                    parent = cmds.listRelatives(shape, parent=True, fullPath=True)
                    if parent:
                        mesh_transforms.add(parent[0])
            else:
                # No mesh descendants – node itself might still have a shape
                own_shapes = cmds.listRelatives(
                    node, shapes=True, type="mesh", fullPath=True
                ) or []
                if own_shapes:
                    mesh_transforms.add(node)

    return list(mesh_transforms)


def get_materials_from_meshes(mesh_transforms):
    """
    Returns a list of unique material (shader) nodes assigned to the given
    mesh transform nodes, excluding Maya built-in defaults.
    """
    materials = set()

    for transform in mesh_transforms:
        shapes = cmds.listRelatives(
            transform, shapes=True, type="mesh", fullPath=True
        ) or []

        for shape in shapes:
            # Get all shading groups connected to this shape
            shading_groups = cmds.listConnections(
                shape, type="shadingEngine"
            ) or []

            for sg in shading_groups:
                # Surface shader connection → the actual material
                shader_conn = cmds.listConnections(
                    "{}.surfaceShader".format(sg)
                ) or []

                for shader in shader_conn:
                    if shader not in _IGNORED_SHADERS:
                        materials.add(shader)

    return list(materials)


def collect_materials_to_set(set_name="materialCollection"):
    """
    Main function: collects materials from selection and puts them in a Set.
    Returns the name of the created set, or None on failure.
    """
    mesh_transforms = get_meshes_from_selection()

    if not mesh_transforms:
        cmds.warning("[Material Collector] No meshes found in selection.")
        return None

    materials = get_materials_from_meshes(mesh_transforms)

    if not materials:
        cmds.warning("[Material Collector] No materials found on selected meshes.")
        return None

    # Sanitise set name – Maya doesn't allow spaces or leading numbers
    safe_name = set_name.strip().replace(" ", "_") or "materialCollection"

    # Create the object set and add the materials
    result_set = cmds.sets(materials, name=safe_name)

    print("\n[Material Collector] ──────────────────────────────")
    print("  Set created  : {}".format(result_set))
    print("  Meshes scanned: {}".format(len(mesh_transforms)))
    print("  Materials collected ({}):" .format(len(materials)))
    for m in sorted(materials):
        print("    • {}  [{}]".format(m, cmds.nodeType(m)))
    print("────────────────────────────────────────────────────\n")

    return result_set


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────
WINDOW_ID = "materialCollectorWin"


def build_ui():
    if cmds.window(WINDOW_ID, exists=True):
        cmds.deleteUI(WINDOW_ID)

    cmds.window(
        WINDOW_ID,
        title="Material Collector",
        widthHeight=(340, 210),
        sizeable=False,
    )

    cmds.columnLayout(adjustableColumn=True, rowSpacing=7, columnOffset=("both", 14))
    cmds.separator(height=10, style="none")

    # Header
    cmds.text(label="Material Collector", font="boldLabelFont", align="center")
    cmds.text(
        label="Collects all materials from selected meshes\nor groups into a Maya Object Set.",
        align="center",
    )
    cmds.separator(height=8)

    # Set name field
    cmds.rowLayout(
        numberOfColumns=2, columnWidth2=(120, 170),
        columnAlign2=("right", "left"), adjustableColumn=2,
    )
    cmds.text(label="Set name :  ", align="right")
    set_name_field = cmds.textField(
        "setNameField",
        text="materialCollection",
        width=168,
        annotation="Name for the new Maya Object Set",
    )
    cmds.setParent("..")

    cmds.separator(height=4)

    # Info text (updated after collection)
    info_text = cmds.text(
        "infoText",
        label="Select meshes or a group, then click Collect.",
        align="center",
        font="smallPlainLabelFont",
    )

    cmds.separator(height=4)

    # Collect button
    cmds.button(
        label="Collect Materials into Set",
        height=40,
        backgroundColor=(0.22, 0.45, 0.65),
        command=lambda *_: on_collect(set_name_field, info_text),
        annotation="Scan selection and create a Set containing all found materials",
    )

    cmds.separator(height=10, style="none")
    cmds.showWindow(WINDOW_ID)


def on_collect(set_name_field, info_text):
    set_name = cmds.textField(set_name_field, query=True, text=True)
    result   = collect_materials_to_set(set_name=set_name)

    if result:
        members  = cmds.sets(result, query=True) or []
        msg      = "✔  Set '{}' created with {} material(s).".format(result, len(members))
        cmds.text(info_text, edit=True, label=msg)
        cmds.inViewMessage(
            assistMessage="<hl>Material Collector</hl>  →  '{}' | {} material(s) collected.".format(
                result, len(members)
            ),
            position="midCenter", fade=True,
        )
        # Select the new set so it's visible in the Outliner
        cmds.select(result)
    else:
        cmds.text(info_text, edit=True,
                  label="⚠  Nothing collected. Check Script Editor.")


# ── Entry point ───────────────────────────────────────────────────────────────
build_ui()
