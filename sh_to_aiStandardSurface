# -*- coding: utf-8 -*-
"""
aiStandardSurface Converter (robust + simple)
- Convert Selected / Convert All
- Preserve key connections
- Update texture color spaces ONLY for textures feeding the converted shader(s),
  based on the FILE PATH:
      *_d*  -> sRGB Texture
      others -> Raw
- Skip references
- Shared textures are localized (*_LOCAL) and only the converted networks are rewired
"""

from __future__ import print_function
import maya.cmds as cmds
import os
import re

# -------------------------- Config / Globals --------------------------

WINDOW_NAME = "ASS_Converter_UI"
LOG_FIELD = WINDOW_NAME + "_logField"
DEFAULT_SKIP_SHADERS = set(["lambert1", "particleCloud1", "shaderGlow1"])

# Preferred/likely input color spaces; picked if present in current OCIO
PREFERRED_SRGB_SPACES = [
    "sRGB - Texture",
    "srgb_texture",  # ACES
    "sRGB",
]
PREFERRED_RAW_SPACES = [             # ACES
    "Raw",
]

# Detects '_d' followed by end, UDIM digits, or separators; avoids words like '_dirt'
DIFFUSE_REGEX = re.compile(r'_d(?:$|[._-]|\d)', re.IGNORECASE)

# ------------------------------ Utils --------------------------------

def log(msg):
    print("[ASS] " + msg)
    if cmds.control(LOG_FIELD, exists=True):
        cmds.scrollField(LOG_FIELD, e=True, ip=9999999, it="[ASS] " + msg + "\n")

def is_referenced(node):
    try:
        return cmds.referenceQuery(node, isNodeReferenced=True)
    except Exception:
        return False

def is_arnold_shader(node):
    try:
        return cmds.nodeType(node).startswith("ai")
    except Exception:
        return False

def is_surface_shader_node(node):
    try:
        t = cmds.nodeType(node)
        classes = cmds.getClassification(t) or []
        return any("shader/surface" in c for c in classes)
    except Exception:
        return False

def safe_node_name(base):
    base = re.sub(r"[^a-zA-Z0-9_]", "_", base)
    if not cmds.objExists(base):
        return base
    i = 1
    while cmds.objExists("{}{}".format(base, i)):
        i += 1
    return "{}{}".format(base, i)

def resolve_colorspace(preferred_list):
    try:
        spaces = cmds.colorManagementPrefs(q=True, inputColorSpaces=True) or []
    except Exception:
        spaces = []
    if not spaces:
        return preferred_list[0]
    lower_map = {s.lower(): s for s in spaces}
    for name in preferred_list:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    want = " ".join(preferred_list).lower()
    if "srgb" in want:
        for s in spaces:
            ls = s.lower()
            if "srgb" in ls and ("texture" in ls or "tex" in ls):
                return s
        for s in spaces:
            if "srgb" in s.lower():
                return s
    if "raw" in want:
        for s in spaces:
            if "raw" in s.lower():
                return s
    return spaces[0]

def get_node_colorspace_attr(node):
    if cmds.attributeQuery("colorSpace", node=node, exists=True):
        return "colorSpace"   # Maya file
    if cmds.attributeQuery("color_space", node=node, exists=True):
        return "color_space"  # Arnold aiImage
    return None

def is_diffuse_from_path(path):
    stem = os.path.splitext(os.path.basename(path or ""))[0].lower()
    return bool(DIFFUSE_REGEX.search(stem))

# --------------------------- Discovery -------------------------------

def get_all_geo_shapes(nodes=None):
    """All mesh/nurbs/subdiv shapes; skip references."""
    if nodes:
        shapes = []
        for n in nodes:
            if cmds.nodeType(n) in ("mesh", "nurbsSurface", "subdiv"):
                shapes.append(n)
            else:
                shapes += cmds.listRelatives(n, s=True, ni=True, f=True) or []
    else:
        shapes = cmds.ls(type=("mesh", "nurbsSurface", "subdiv")) or []
    return [s for s in shapes if cmds.nodeType(s) in ("mesh", "nurbsSurface", "subdiv") and not is_referenced(s)]

def shading_engines_from_shapes(shapes):
    sgs = set()
    for s in shapes:
        for sg in (cmds.listConnections(s, type="shadingEngine") or []):
            sgs.add(sg)
    return list(sgs)

def surface_shader_from_sg(sg):
    src = cmds.listConnections(sg + ".surfaceShader", d=False, s=True) or []
    return src[0] if src else None

def find_shaders_in_selection():
    """Pick up shaders from selection (geometry / SG / shader). Skips references."""
    sel = cmds.ls(sl=True, l=True) or []
    if not sel:
        return {}

    # from geometry
    shapes = get_all_geo_shapes(sel)
    sgs = set(shading_engines_from_shapes(shapes))

    # direct SG or shader
    for n in sel:
        if is_referenced(n):
            continue
        t = cmds.nodeType(n)
        if t == "shadingEngine":
            sgs.add(n)
        elif is_surface_shader_node(n):
            for sg in (cmds.listConnections(n, type="shadingEngine") or []):
                sgs.add(sg)

    shader_to_sgs = {}
    for sg in sgs:
        if is_referenced(sg):
            continue
        members = cmds.sets(sg, q=True) or []
        if not members:
            continue
        sh = surface_shader_from_sg(sg)
        if not sh or is_referenced(sh):
            continue
        shader_to_sgs.setdefault(sh, []).append(sg)
    return shader_to_sgs

def find_all_assigned_shaders():
    """All shaders assigned to any (non-ref) geometry in the scene."""
    shapes = get_all_geo_shapes(None)
    sgs = shading_engines_from_shapes(shapes)
    shader_to_sgs = {}
    for sg in sgs:
        if is_referenced(sg):
            continue
        members = cmds.sets(sg, q=True) or []
        if not members:
            continue
        sh = surface_shader_from_sg(sg)
        if not sh or is_referenced(sh):
            continue
        shader_to_sgs.setdefault(sh, []).append(sg)
    return shader_to_sgs

# ------------------------ Conversion / Wiring ------------------------

def find_upstream_connection(node, attr):
    plug = node + "." + attr
    if not cmds.objExists(plug):
        return None
    conns = cmds.listConnections(plug, s=True, d=False, p=True) or []
    return conns[0] if conns else None

def connect_if_possible(src_plug, dest_node, dest_attr):
    dest_plug = dest_node + "." + dest_attr
    if not cmds.objExists(dest_plug):
        return False
    try:
        existing = cmds.listConnections(dest_plug, s=True, d=False, p=True) or []
        if existing:
            return False
        cmds.connectAttr(src_plug, dest_plug, f=True)
        return True
    except Exception as e:
        log("WARN connect failed: {} -> {}.{} ({})".format(src_plug, dest_node, dest_attr, e))
        return False

def get_attr_value(node, attr):
    plug = node + "." + attr
    if not cmds.objExists(plug):
        return None
    try:
        return cmds.getAttr(plug)
    except Exception:
        return None

def set_attr_value(node, attr, value):
    plug = node + "." + attr
    if not cmds.objExists(plug) or value is None:
        return
    try:
        if isinstance(value, (list, tuple)):
            if len(value) == 1 and isinstance(value[0], (list, tuple)):
                value = value[0]
        if isinstance(value, (list, tuple)) and len(value) == 3:
            cmds.setAttr(plug, value[0], value[1], value[2], type="double3")
        else:
            if isinstance(value, str):
                cmds.setAttr(plug, value, type="string")
            else:
                cmds.setAttr(plug, value)
    except Exception as e:
        log("WARN setAttr failed: {} -> {} ({})".format(plug, value, e))

def attribute_map_for_node(src_node_type):
    """Input -> aiStandardSurface mapping."""
    if src_node_type in ("lambert", "phong", "phongE", "blinn", "aiStandard"):
        return {
            "color": "baseColor",
            "normalCamera": "normalCamera",
            "incandescence": "emissionColor",
            "transparency": "opacity",        # value inverted if not connected
            "specularColor": "specularColor",
            "eccentricity": "specularRoughness",
        }
    if src_node_type == "surfaceShader":
        return {
            "outColor": "baseColor",
            "normalCamera": "normalCamera",
            "incandescence": "emissionColor",
            "outTransparency": "opacity",
        }
    return {
        "color": "baseColor",
        "normalCamera": "normalCamera",
        "incandescence": "emissionColor",
        "transparency": "opacity",
        "specularColor": "specularColor",
    }

def convert_one_shader(src_shader):
    """Create aiStandardSurface and transfer key connections/values."""
    if is_arnold_shader(src_shader):
        return None  # skip

    src_type = cmds.nodeType(src_shader)
    new_name = safe_node_name(src_shader + "_aiSS")
    new_shader = cmds.shadingNode("aiStandardSurface", asShader=True, name=new_name)
    log("Created {}".format(new_shader))

    try:
        if cmds.objExists(new_shader + ".base"):
            cmds.setAttr(new_shader + ".base", 1.0)
    except Exception:
        pass

    amap = attribute_map_for_node(src_type)

    # Connect upstream sources when present
    for src_attr, dst_attr in amap.items():
        up = find_upstream_connection(src_shader, src_attr)
        if up:
            if src_attr in ("transparency", "outTransparency") and dst_attr == "opacity" and src_attr == "transparency":
                log("WARN connected transparency on {} not auto-inverted; skipping".format(src_shader))
                continue
            if connect_if_possible(up, new_shader, dst_attr):
                log("Connected {} -> {}.{}".format(up, new_shader, dst_attr))

    # Copy values (only where dest isn't connected AND src isn't an 'out*' attr)
    for src_attr, dst_attr in amap.items():
        if cmds.listConnections(new_shader + "." + dst_attr, s=True, d=False):
            continue
        if src_attr.startswith("out"):
            continue
        val = get_attr_value(src_shader, src_attr)
        if val is None:
            continue
        if src_attr == "transparency" and dst_attr == "opacity":
            try:
                if isinstance(val, (list, tuple)):
                    if len(val) == 1 and isinstance(val[0], (list, tuple)):
                        val = val[0]
                if isinstance(val, (list, tuple)) and len(val) == 3:
                    inv = (1.0 - val[0], 1.0 - val[1], 1.0 - val[2])
                    set_attr_value(new_shader, dst_attr, inv)
                else:
                    inv = 1.0 - float(val)
                    set_attr_value(new_shader, dst_attr, inv)
                log("Set {}.{} (inverted from {}.{})".format(new_shader, dst_attr, src_shader, src_attr))
            except Exception:
                pass
        else:
            set_attr_value(new_shader, dst_attr, val)
            log("Copied {}.{} -> {}.{}".format(src_shader, src_attr, new_shader, dst_attr))

    return new_shader

def reconnect_sgs(old_shader, new_shader, sgs):
    for sg in sgs:
        if is_referenced(sg):
            log("Skip referenced SG: {}".format(sg))
            continue
        try:
            old_plugs = cmds.listConnections(sg + ".surfaceShader", s=True, d=False, p=True) or []
            for p in old_plugs:
                try: cmds.disconnectAttr(p, sg + ".surfaceShader")
                except Exception: pass
            cmds.connectAttr(new_shader + ".outColor", sg + ".surfaceShader", f=True)
            log("SG {} now uses {}".format(sg, new_shader))
        except Exception as e:
            log("WARN reconnect SG failed {}: {}".format(sg, e))

# --------------------- Texture handling (path-based) -----------------

def textures_upstream_of_shaders(shaders):
    """Return file / aiImage nodes feeding into given shaders (skip references)."""
    files = set()
    for sh in shaders:
        if is_referenced(sh):
            continue
        try:
            ups = cmds.listHistory(sh, future=False, pruneDagObjects=True) or []
        except Exception:
            ups = []
        for n in ups:
            if is_referenced(n):
                continue
            nt = cmds.nodeType(n)
            if nt in ("file", "aiImage"):
                files.add(n)
    return list(files)

def texture_is_shared_outside(tex_node, allowed_shaders_set):
    """True if the texture feeds any surface shader not in allowed_shaders_set."""
    try:
        fut = cmds.listHistory(tex_node, future=True, pruneDagObjects=True) or []
    except Exception:
        fut = []
    shaders = {n for n in fut if is_surface_shader_node(n)}
    return bool(shaders and not shaders.issubset(allowed_shaders_set))

def _safe_connect(src, dst):
    try:
        exists = cmds.listConnections(dst, s=True, d=False, p=True) or []
        if src in exists:
            return
        cmds.connectAttr(src, dst, f=True)
    except Exception:
        pass

def _connect_place2d_to_tex(place2d, tex):
    """Mirror common place2dTexture → file/aiImage connections if attrs exist."""
    pairs = [
        ("coverage","coverage"), ("translateFrame","translateFrame"),
        ("rotateFrame","rotateFrame"), ("mirrorU","mirrorU"), ("mirrorV","mirrorV"),
        ("stagger","stagger"), ("wrapU","wrapU"), ("wrapV","wrapV"),
        ("repeatUV","repeatUV"), ("offset","offset"), ("rotateUV","rotateUV"),
        ("noiseUV","noiseUV"), ("vertexUvOne","vertexUvOne"),
        ("vertexUvTwo","vertexUvTwo"), ("vertexUvThree","vertexUvThree"),
        ("vertexCameraOne","vertexCameraOne"),
    ]
    for s_attr, d_attr in pairs:
        if cmds.attributeQuery(s_attr, node=place2d, exists=True) and cmds.attributeQuery(d_attr, node=tex, exists=True):
            _safe_connect("{}.{}".format(place2d, s_attr), "{}.{}".format(tex, d_attr))
    # UV links
    uv_in = "uvCoord" if cmds.attributeQuery("uvCoord", node=tex, exists=True) else ("uvcoords" if cmds.attributeQuery("uvcoords", node=tex, exists=True) else None)
    if uv_in and cmds.attributeQuery("outUV", node=place2d, exists=True):
        _safe_connect("{}.outUV".format(place2d), "{}.{}".format(tex, uv_in))
    if cmds.attributeQuery("uvFilterSize", node=tex, exists=True) and cmds.attributeQuery("outUvFilterSize", node=place2d, exists=True):
        _safe_connect("{}.outUvFilterSize".format(place2d), "{}.uvFilterSize".format(tex))

def _duplicate_texture_node(node):
    """Duplicate the texture node (values only), name it *_LOCAL."""
    dup_name = safe_node_name(node + "_LOCAL")
    try:
        dup_list = cmds.duplicate(node, n=dup_name, ic=False, rr=True)
    except Exception as e:
        log("WARN: Exception duplicating {}: {}".format(node, e))
        return None
    if not dup_list:
        log("WARN: Failed to duplicate {} (empty return)".format(node))
        return None
    dup = dup_list[0]
    # hook up same place2dTexture(s)
    for p2d in cmds.listConnections(node, type="place2dTexture") or []:
        if not is_referenced(p2d):
            _connect_place2d_to_tex(p2d, dup)
    return dup

def _rewire_texture_outputs(orig_tex, dup_tex, allowed_graph):
    """
    Rewire ONLY the connections from orig_tex going into nodes inside allowed_graph
    so they come from dup_tex instead. Robust: no pair indexing, per-attr walk.
    """
    # Discover all output attributes on the texture node
    out_attrs = set(["outColor", "outAlpha", "outTransparency", "outRGBA"])
    for a in cmds.listAttr(orig_tex, st="out*") or []:
        out_attrs.add(a)

    for attr in out_attrs:
        src_plug = "{}.{}".format(orig_tex, attr)
        if not cmds.objExists(src_plug):
            continue
        dest_plugs = cmds.listConnections(src_plug, s=False, d=True, p=True) or []
        for dst in dest_plugs:
            dst_node = dst.split(".", 1)[0]
            if dst_node not in allowed_graph:
                continue
            try:
                cmds.disconnectAttr(src_plug, dst)
            except Exception:
                pass
            dup_src = "{}.{}".format(dup_tex, attr)
            # if duplicate doesn't have same attr, fall back to common outputs
            if not cmds.objExists(dup_src):
                for cand in ("outColor", "outAlpha", "outTransparency", "outRGBA"):
                    cand_plug = "{}.{}".format(dup_tex, cand)
                    if cmds.objExists(cand_plug):
                        dup_src = cand_plug
                        break
            _safe_connect(dup_src, dst)

def set_colorspaces_for_textures_for_shaders(shaders):
    """
    For the given shaders:
      - collect upstream textures (file/aiImage)
      - duplicate & rewire any texture that is shared outside these shaders
      - set color space based on FILE PATH
    """
    if not shaders:
        return

    target_srgb = resolve_colorspace(PREFERRED_SRGB_SPACES)
    target_raw = resolve_colorspace(PREFERRED_RAW_SPACES)
    log("Using color spaces -> SRGB: '{}' | RAW: '{}'".format(target_srgb, target_raw))

    allowed = set(shaders)
    try:
        allowed_graph = set(cmds.listHistory(list(allowed), future=False, pruneDagObjects=True) or [])
    except Exception:
        allowed_graph = set()
    allowed_graph.update(allowed)

    textures = textures_upstream_of_shaders(shaders)
    final_targets = []

    for t in textures:
        if is_referenced(t):
            continue
        if texture_is_shared_outside(t, allowed):
            dup = _duplicate_texture_node(t)
            if not dup:
                log("WARN: Using original texture {} since duplication failed".format(t))
                final_targets.append(t)
                continue
            _rewire_texture_outputs(t, dup, allowed_graph)
            log("Localized shared texture '{}' -> '{}'".format(t, dup))
            final_targets.append(dup)
        else:
            final_targets.append(t)

    srgb_ct = 0
    raw_ct  = 0

    for t in final_targets:
        if is_referenced(t):
            continue
        try:
            if cmds.nodeType(t) == "file":
                path = cmds.getAttr(t + ".fileTextureName")
            else:  # aiImage
                path = cmds.getAttr(t + ".filename")
        except Exception:
            path = ""
        want_srgb = is_diffuse_from_path(path)
        desired = target_srgb if want_srgb else target_raw

        cs_attr = get_node_colorspace_attr(t)
        if not cs_attr:
            log("WARN {} has no color space attribute".format(t))
            continue

        try:
            current = cmds.getAttr("{}.{}".format(t, cs_attr))
        except Exception:
            current = ""

        if current != desired:
            try:
                cmds.setAttr("{}.{}".format(t, cs_attr), desired, type="string")
                if want_srgb: srgb_ct += 1
                else: raw_ct += 1
                log("Set {}.{} -> '{}' ({})".format(t, cs_attr, desired, os.path.basename(path or "")))
            except Exception as e:
                log("WARN could not set {}.{}: {}".format(t, cs_attr, e))

    log("Color-space update complete. SRGB set: {}, RAW set: {}".format(srgb_ct, raw_ct))

# ------------------------------ Driver -------------------------------

def convert_shaders(only_selected):
    """
    - only_selected=True: use selection; else whole scene.
    - Converts non-aiStandardSurface shaders and updates texture color spaces
      only for the converted networks (path-based, safe, non-destructive).
    """
    if only_selected:
        shader_map = find_shaders_in_selection()
        if not shader_map:
            log("No shading networks found in current selection.")
            return
    else:
        shader_map = find_all_assigned_shaders()
        if not shader_map:
            log("No shading networks found in the scene.")
            return

    targets = []
    for sh, sgs in shader_map.items():
        if is_referenced(sh): 
            continue
        if is_arnold_shader(sh): 
            continue
        if sh in DEFAULT_SKIP_SHADERS:
            continue
        sgs = [sg for sg in sgs if not is_referenced(sg)]
        if not sgs:
            continue
        targets.append((sh, sgs))

    if not targets:
        log("Nothing to convert (either aiStandardSurface, default, or referenced).")
        return

    log("Found {} non-aiStandardSurface shader(s) to convert.".format(len(targets)))

    new_shaders = []
    cmds.undoInfo(ock=True)
    try:
        for old, sgs in targets:
            try:
                new = convert_one_shader(old)
                if not new:
                    continue
                new_shaders.append(new)
                reconnect_sgs(old, new, sgs)
            except Exception as e:
                log("ERROR converting {}: {}".format(old, e))
    finally:
        cmds.undoInfo(cck=True)

    log("Converted {} shader(s).".format(len(new_shaders)))

    if new_shaders:
        set_colorspaces_for_textures_for_shaders(new_shaders)

# ------------------------------- UI ---------------------------------

def build_ui():
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME, window=True)

    win = cmds.window(WINDOW_NAME, title="aiStandardSurface Converter", widthHeight=(440, 480), sizeable=True)
    cmds.columnLayout(adj=True, rowSpacing=6)

    cmds.separator(h=6, style="none")
    cmds.text(l="Convert non-Arnold shaders to aiStandardSurface (Selected or All)", align="center", h=20)
    cmds.separator(h=6, style="in")

    cmds.separator(h=6, style="none")
    cmds.rowLayout(nc=2, adjustableColumn=1, columnWidth2=(210, 210), columnAttach2=("both", "both"))
    cmds.button(l="Convert Selected", h=44, c=lambda *_: convert_shaders(only_selected=True))
    cmds.button(l="Convert All", h=44, c=lambda *_: convert_shaders(only_selected=False))
    cmds.setParent("..")

    cmds.separator(h=8, style="none")
    cmds.text(l="Log:", align="left")
    cmds.scrollField(LOG_FIELD, editable=False, wordWrap=False, h=340)
    cmds.scrollField(LOG_FIELD, e=True, clear=True)

    cmds.separator(h=6, style="in")
    cmds.rowLayout(nc=2, adjustableColumn=1, columnWidth2=(300, 120), columnAttach2=("both", "both"))
    cmds.text(l="Tip: Undo will revert a conversion batch.")
    cmds.button(l="Close", c=lambda *_: cmds.deleteUI(WINDOW_NAME, window=True))
    cmds.setParent("..")

    cmds.showWindow(win)
    log("UI ready.")

# Run UI on load
build_ui()
