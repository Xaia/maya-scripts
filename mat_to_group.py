import maya.cmds as cmds

def _shading_engines_from_shape(shape):
    return cmds.listConnections(shape, type="shadingEngine") or []

def _materials_from_shading_engine(sg):
    return cmds.listConnections(sg + ".surfaceShader", s=True, d=False) or []

def _top_group_under_world(xform):
    """
    Returns the top-most transform under world for this transform.
    Example: |group1|sub|mesh -> |group1
    If the transform is directly under world: returns itself.
    """
    cur = xform
    while True:
        parent = cmds.listRelatives(cur, parent=True, fullPath=True)
        if not parent:
            return cur
        cur = parent[0]

def _find_or_create_child_group(parent_xform, child_name):
    """
    Finds a direct child transform of parent_xform with short name child_name.
    If not found, creates it. Returns full path.
    """
    kids = cmds.listRelatives(parent_xform, children=True, type="transform", fullPath=True) or []
    for k in kids:
        if k.split("|")[-1] == child_name:
            return k
    return cmds.group(em=True, name=child_name, parent=parent_xform)

def group_selected_meshes_by_material_in_their_top_group(prefix="MAT_GRP_"):
    sel = cmds.ls(sl=True, long=True) or []
    if not sel:
        cmds.warning("Nothing selected.")
        return []

    # Collect mesh shapes from selection (transforms or shapes)
    shapes = cmds.listRelatives(sel, allDescendents=True, type="mesh", fullPath=True) or []
    shapes += [s for s in sel if cmds.nodeType(s) == "mesh"]
    shapes = list(dict.fromkeys(shapes))  # unique

    if not shapes:
        cmds.warning("Selection contains no mesh shapes.")
        return []

    # Map: (rootGroupFullPath, materialName) -> set(meshTransformsFullPath)
    bucket = {}

    for shape in shapes:
        xform = cmds.listRelatives(shape, parent=True, fullPath=True)
        if not xform:
            continue
        xform = xform[0]

        root = _top_group_under_world(xform)

        sgs = _shading_engines_from_shape(shape)
        mats = []
        for sg in sgs:
            mats.extend(_materials_from_shading_engine(sg))

        mats = sorted(set(mats)) or ["NoMaterial"]

        for mat in mats:
            bucket.setdefault((root, mat), set()).add(xform)

    created = []

    for (root, mat), xforms in bucket.items():
        safe_mat = mat.replace("|", "_").replace(":", "_")
        grp_short = prefix + safe_mat

        grp = _find_or_create_child_group(root, grp_short)
        if grp not in created:
            created.append(grp)

        for x in sorted(xforms):
            if not cmds.objExists(x):
                continue
            # avoid cycles / weirdness
            if x == grp or grp.startswith(x + "|"):
                continue
            try:
                cmds.parent(x, grp)
            except RuntimeError:
                pass

    return created

# Run on current selection:
group_selected_meshes_by_material_in_their_top_group(prefix="MAT_GRP_")
