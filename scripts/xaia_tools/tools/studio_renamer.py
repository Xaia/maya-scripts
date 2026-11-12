"""Studio Renamer for Autodesk Maya 2024+.

Run in Maya's Python Script Editor:
    import sys
    sys.path.insert(0, r"C:/path/to/maya_studio_renamer")
    import studio_renamer
    studio_renamer.show()

No third-party dependencies. The planning/core modules import without Maya, but all
scene operations require a running Maya session.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import os
import re
import tempfile
import uuid as uuidlib
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import maya.cmds as cmds
except ImportError:
    cmds = None

APP_NAME = "Studio Renamer"
VERSION = "1.1.0"

# This registry is data, not scattered hard-coded type rules. Unrecognized types
# are skipped unless their Maya classification clearly identifies a known type.
DEFAULT_REGISTRY = {
    "version": 1,
    "type_suffixes": {
        "mesh": "geo", "nurbsCurve": "crv", "nurbsSurface": "srf",
        "subdiv": "geo", "locator": "loc", "camera": "cam",
        "aiStandIn": "ass", "aiVolume": "vol", "volumeShape": "vol",
        "joint": "jnt", "ikHandle": "ikh", "ikEffector": "ike",
        "blendShape": "bsh", "skinCluster": "skn", "cluster": "def",
        "lattice": "def", "ffd": "def", "wire": "def", "wrap": "def",
        "deltaMush": "def", "sculpt": "def", "nonLinear": "def",
        "parentConstraint": "cns", "orientConstraint": "cns",
        "pointConstraint": "cns", "scaleConstraint": "cns",
        "aimConstraint": "cns", "geometryConstraint": "cns",
        "normalConstraint": "cns", "tangentConstraint": "cns",
        "poleVectorConstraint": "cns", "motionPath": "mp",
        "expression": "expr", "objectSet": "set",
        "shadingEngine": "sg", "displayLayer": "lyr", "renderLayer": "rl",
        "AlembicNode": "cache", "cacheFile": "cache", "gpuCache": "cache",
        "aiStandardSurface": "shd", "aiStandardHair": "shd",
        "aiStandardVolume": "shd", "aiFlat": "shd", "aiToon": "shd",
        "standardSurface": "shd", "surfaceShader": "shd",
        "lambert": "shd", "blinn": "shd", "phong": "shd",
        "phongE": "shd", "anisotropic": "shd", "rampShader": "shd",
        "layeredShader": "shd", "useBackground": "shd",
        "file": "tex", "imagePlane": "img", "aiImage": "tex",
        "place2dTexture": "place2d", "place3dTexture": "place3d",
        "ramp": "ramp", "bump2d": "bump", "bump3d": "bump",
        "displacementShader": "disp", "aiDisplacement": "disp",
        "aiNormalMap": "nrm", "aiBump2d": "bump",
        "aiColorCorrect": "cc", "aiRange": "rng",
        "aiTriplanar": "tri", "aiNoise": "noise", "aiCellNoise": "noise",
        "aiMixShader": "mix", "aiLayerShader": "layer",
        "aiRaySwitch": "raysw", "aiFacingRatio": "facing",
        "aiCurvature": "curv", "aiWireframe": "wire",
        "aiUserDataFloat": "ud", "aiUserDataColor": "ud",
        "aiUserDataVector": "ud", "aiUserDataInt": "ud",
        "aiUserDataString": "ud", "aiUserDataBool": "ud",
        "aiAOV": "aov", "aiAOVDriver": "drv", "aiAOVFilter": "flt",
        "aiUvTransform": "uv", "aiMultiply": "mult", "aiAdd": "add",
        "aiComposite": "mix", "aiLayerRgba": "layer",
        "aiSwitch": "switch", "aiColorConvert": "cc",
        "aiFloatToRgba": "conv", "aiRgbaToFloat": "conv",
        "aiShadowMatte": "shd", "aiAmbientOcclusion": "ao",
        "aiStateFloat": "state", "aiStateVector": "state",
        "aiLightBlocker": "blocker", "aiSkyDomeLight": "lgt",
        "aiAreaLight": "lgt", "aiPhotometricLight": "lgt",
        "aiMeshLight": "lgt", "aiLightPortal": "lgt",
        "directionalLight": "lgt", "pointLight": "lgt",
        "spotLight": "lgt", "areaLight": "lgt",
        "ambientLight": "lgt", "volumeLight": "lgt",
        "multiplyDivide": "mult", "plusMinusAverage": "math",
        "condition": "cond", "clamp": "clamp", "reverse": "rev",
        "remapValue": "remap", "remapColor": "remap",
        "remapHsv": "remap", "blendColors": "mix",
        "blendTwoAttr": "mix", "choice": "choice",
        "distanceBetween": "dist", "vectorProduct": "vec",
        "unitConversion": "conv", "gammaCorrect": "cc",
        "colorCorrect": "cc", "projection": "proj",
        "layeredTexture": "layer", "samplerInfo": "sampler",
        "tripleShadingSwitch": "switch", "quadShadingSwitch": "switch",
        "singleShadingSwitch": "switch", "surfaceLuminance": "lum",
        "noise": "noise", "fractal": "noise", "volumeNoise": "noise"
    },
    "transform_shape_overrides": {
        "mesh": "geo", "nurbsCurve": "crv", "nurbsSurface": "srf",
        "subdiv": "geo", "locator": "loc", "camera": "cam",
        "aiStandIn": "ass", "aiVolume": "vol", "volumeShape": "vol",
        "gpuCache": "cache", "imagePlane": "img"
    },
    "class_suffixes": {
        "shader/surface": "shd", "shader/volume": "shd",
        "shader/displacement": "disp", "texture": "tex",
        "light": "lgt"
    },
    "extra_suffixes": ["grp", "xform", "util", "shape", "orig"],
    "protected_exact": [
        "time1", "renderPartition", "renderGlobalsList1",
        "defaultRenderGlobals", "defaultResolution", "defaultLightSet",
        "defaultObjectSet", "defaultShaderList1", "defaultTextureList1",
        "defaultRenderUtilityList1", "defaultRenderingList1",
        "defaultColorMgtGlobals", "hardwareRenderingGlobals",
        "initialShadingGroup", "initialParticleSE", "lambert1",
        "particleCloud1", "shaderGlow1", "defaultArnoldDriver",
        "defaultArnoldFilter", "defaultArnoldRenderOptions",
        "persp", "top", "front", "side", "perspShape", "topShape",
        "frontShape", "sideShape", "defaultRenderLayer", "defaultLayer",
        "lightLinker1", "renderLayerManager", "displayLayerManager",
        "defaultCameraSet", "sharedReferenceNode",
        "uiConfigurationScriptNode", "sceneConfigurationScriptNode"
    ],
    "protected_types": [
        "reference", "referenceManager", "time", "renderLayerManager",
        "displayLayerManager", "objectTypeFilter", "nodeGraphEditorInfo",
        "script", "unknown", "unknownDag"
    ],
    "history_types": [
        "poly", "makeNurb", "skinCluster", "blendShape", "tweak",
        "groupParts", "groupId", "rebuild", "extrude", "subCurve",
        "nonLinear", "ffd", "wire", "wrap", "cluster",
        "deltaMush", "sculpt", "geometryFilter"
    ],
    "default_name_patterns": [
        r"^(?:pCube|pSphere|pCylinder|pPlane|pTorus|pCone|group|transform|polySurface|curve|locator|joint|file|aiStandardSurface|shadingEngine)\d+$"
    ],
    "number_padding": 3
}


def _require_maya():
    if cmds is None:
        raise RuntimeError("Studio Renamer must be run in Autodesk Maya.")


def _config_path():
    if cmds is not None:
        root = cmds.internalVar(userAppDir=True)
    else:
        root = os.path.expanduser("~")
    return os.path.join(root, "studio_renamer", "suffix_registry.json")


def _atomic_json_write(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="._studio_", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(temp_path, path)
    finally:
        if os.path.isfile(temp_path):
            os.remove(temp_path)


def load_registry():
    path = _config_path()
    if not os.path.isfile(path):
        _atomic_json_write(path, DEFAULT_REGISTRY)
        return json.loads(json.dumps(DEFAULT_REGISTRY))
    try:
        with open(path, "r", encoding="utf-8") as f:
            user_data = json.load(f)
        if not isinstance(user_data, dict):
            raise ValueError("Expected JSON object")
        registry = json.loads(json.dumps(DEFAULT_REGISTRY))
        for key, value in user_data.items():
            if key in ("type_suffixes", "transform_shape_overrides", "class_suffixes") and isinstance(value, dict):
                registry[key].update(value)
            else:
                registry[key] = value
        for key in ("type_suffixes", "transform_shape_overrides", "class_suffixes"):
            for node_type, suffix in registry[key].items():
                if not isinstance(node_type, str) or not isinstance(suffix, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", suffix):
                    raise ValueError("Invalid registry mapping: %s = %r" % (node_type, suffix))
        return registry
    except (ValueError, OSError, TypeError) as exc:
        raise RuntimeError("Invalid suffix registry at %s: %s" % (path, exc))


def short_name(path: str) -> str:
    return path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


def namespace_of(path: str) -> str:
    leaf = path.rsplit("|", 1)[-1]
    return leaf.rsplit(":", 1)[0] if ":" in leaf else ""


def make_absolute(namespace: str, bare: str) -> str:
    return ":%s:%s" % (namespace.lstrip(":"), bare) if namespace else ":" + bare


def sanitize_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
    name = re.sub(r"_+", "_", name).strip("_")
    if name and name[0].isdigit():
        name = "n_" + name
    return name


def split_trailing_suffix(name: str, known: Set[str]) -> Tuple[str, str]:
    for suffix in sorted(known, key=len, reverse=True):
        if name.endswith("_" + suffix) and len(name) > len(suffix) + 1:
            return name[:-(len(suffix) + 1)], suffix
    return name, ""


def replace_suffix(name: str, suffix: str, known: Set[str]) -> str:
    base = name
    while True:
        reduced, trailing = split_trailing_suffix(base, known)
        if not trailing:
            break
        base = reduced
    return base + ("_" + suffix if suffix else "")


def numbered_name(base: str, index: int, padding: int, known: Set[str]) -> str:
    stem, suffix = split_trailing_suffix(base, known)
    # Existing trailing index is replaced, avoiding foo_001_002_geo.
    stem = re.sub(r"_\d+$", "", stem) or stem
    return "%s_%0*d%s" % (stem, padding, index, "_" + suffix if suffix else "")


@dataclasses.dataclass
class Node:
    uid: str
    path: str
    node_type: str
    namespace: str
    bare: str
    dag: bool
    editable: bool = True
    skip_reason: str = ""


@dataclasses.dataclass
class Intent:
    uid: str
    wanted: str
    context: str = ""


@dataclasses.dataclass
class PlanRow:
    uid: str
    old_path: str
    old_name: str
    new_name: str
    node_type: str
    status: str
    note: str = ""
    shape_sync: bool = False


@dataclasses.dataclass
class RenamePlan:
    rows: List[PlanRow]
    signature: Tuple[Tuple[str, str], ...]
    action: str

    def changes(self) -> List[PlanRow]:
        return [r for r in self.rows if r.status in ("Ready", "Resolved") and r.old_name != r.new_name]


class Registry:
    def __init__(self, data: Optional[dict] = None):
        self.data = data if data is not None else load_registry()
        self.known = set(self.data["type_suffixes"].values())
        self.known.update(self.data["transform_shape_overrides"].values())
        self.known.update(self.data.get("extra_suffixes", []))
        self.known.update(self.data.get("class_suffixes", {}).values())
        self._classification = {}
        self.arnold_types = {typ for typ in self.data["type_suffixes"]
                             if re.match(r"^ai[A-Z]", typ)}
        self.refresh_arnold_types()

    def refresh_arnold_types(self):
        # Ask the installed plugin, rather than maintaining a partial shader
        # table. Do not load Arnold merely to open the renamer.
        try:
            if cmds is not None and cmds.pluginInfo("mtoa", query=True, loaded=True):
                self.arnold_types.update(cmds.pluginInfo("mtoa", query=True, dependNode=True) or [])
        except (RuntimeError, AttributeError):
            pass
        self.known.update(self.arnold_types)

    def suffix_for(self, node: Node):
        if self.is_arnold_type(node.node_type):
            self.known.add(node.node_type)
            return node.node_type
        return self.role_for(node)

    def is_arnold_type(self, typ):
        # Also supports new ai-prefixed nodes not present in old saved JSON.
        # The capital letter matters: aimConstraint and airField are Maya nodes.
        return typ in self.arnold_types or bool(re.match(r"^ai[A-Z]", typ))

    def role_for(self, node: Node):
        """Semantic category is independent of the node's naming suffix."""
        typ = node.node_type
        # Legacy Arnold mappings describe categories; custom naming mappings
        # must not change whether a material is recognized as a surface shader.
        explicit = (DEFAULT_REGISTRY["type_suffixes"].get(typ) if self.is_arnold_type(typ)
                    else self.data["type_suffixes"].get(typ))
        if explicit:
            return explicit
        if typ in ("transform", "dagContainer"):
            shapes = cmds.listRelatives(node.path, shapes=True, fullPath=True, noIntermediate=True) or []
            if not shapes:
                # If only intermediate shapes exist, this is still geometry.
                shapes = cmds.listRelatives(node.path, shapes=True, fullPath=True) or []
            if not shapes:
                return "grp"
            kinds = [cmds.nodeType(shape) for shape in shapes]
            for shape_type in kinds:
                suffix = self.data["transform_shape_overrides"].get(shape_type)
                if suffix:
                    return suffix
                if self.data["type_suffixes"].get(shape_type) == "lgt":
                    return "lgt"
                cls = self._classify(shape_type)
                if "light" in cls.lower():
                    return "lgt"
            # Unknown shape type is not an organizational group.
            return "xform"
        cls = self._classify(typ).lower()
        for prefix, suffix in self.data.get("class_suffixes", {}).items():
            if prefix.lower() in cls:
                return suffix
        if typ.lower().endswith("light") and typ not in ("lightLinker",):
            return "lgt"
        if typ.startswith("aiAOV") and typ not in ("aiAOV",):
            return "drv" if "Driver" in typ else ("flt" if "Filter" in typ else None)
        return None

    def _classify(self, typ: str):
        if typ not in self._classification:
            try:
                info = cmds.getClassification(typ) or []
                self._classification[typ] = ":".join(info) if isinstance(info, (list, tuple)) else str(info)
            except Exception:
                self._classification[typ] = ""
        return self._classification[typ]

    def is_history(self, typ: str):
        return any(typ.startswith(prefix) for prefix in self.data["history_types"])


class SceneIndex:
    """UUID-backed identity. All short names (regardless of namespace) are reserved."""

    def __init__(self, registry: Registry):
        _require_maya()
        self.registry = registry
        self.nodes: Dict[str, Node] = {}
        self.by_path: Dict[str, str] = {}
        undeletable = set(cmds.ls(undeletable=True, long=True) or [])
        names = cmds.ls(dependencyNodes=True, long=True) or []
        # Explicitly include DAG nodes (and any shape omitted by dependencyNodes).
        names.extend(cmds.ls(dag=True, long=True) or [])
        for path in dict.fromkeys(names):
            try:
                uids = cmds.ls(path, uuid=True) or []
                if not uids:
                    continue
                uid = uids[0]
                if uid in self.nodes:
                    self.by_path[path] = uid
                    continue
                typ = cmds.nodeType(path)
                bare = short_name(path)
                ns = namespace_of(path)
                reason = ""
                if bare in registry.data.get("protected_exact", []):
                    reason = "Protected Maya/default node"
                elif typ in registry.data.get("protected_types", []):
                    reason = "Protected node type"
                elif path in undeletable:
                    reason = "Undeletable Maya node"
                else:
                    try:
                        if cmds.referenceQuery(path, isNodeReferenced=True):
                            reason = "Referenced node"
                    except (RuntimeError, ValueError):
                        pass
                    if not reason:
                        try:
                            if any(cmds.lockNode(path, query=True, lock=True) or []):
                                reason = "Locked node"
                        except (RuntimeError, ValueError):
                            pass
                node = Node(uid, path, typ, ns, bare, path.startswith("|"), not bool(reason), reason)
                self.nodes[uid] = node
                self.by_path[path] = uid
            except (RuntimeError, ValueError):
                continue
        self.signature = tuple(sorted((uid, node.path) for uid, node in self.nodes.items()))

    def resolve(self, uid: str) -> Optional[str]:
        try:
            names = cmds.ls(uid, long=True) or []
            return names[0] if names else None
        except RuntimeError:
            return None

    def uid_for(self, path: str) -> Optional[str]:
        if path in self.by_path:
            return self.by_path[path]
        try:
            ids = cmds.ls(path, uuid=True) or []
            return ids[0] if ids and ids[0] in self.nodes else None
        except RuntimeError:
            return None

    def scope(self, mode: str, include_shapes=False):
        if mode == "Scene":
            nodes = list(self.nodes.values())
        else:
            selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
            paths = list(selected)
            if mode == "Hierarchy":
                for item in selected:
                    paths.extend(cmds.listRelatives(item, allDescendents=True, fullPath=True) or [])
            ids = set()
            ordered = []
            for path in paths:
                uid = self.uid_for(path)
                if uid and uid not in ids:
                    ids.add(uid)
                    ordered.append(self.nodes[uid])
            nodes = ordered
        if not include_shapes:
            nodes = [node for node in nodes if not (node.dag and node.node_type not in ("transform", "joint", "ikHandle", "dagContainer"))]
            # Non-DAG dependency nodes remain eligible.
        if mode == "Selected":
            return nodes  # Preserve Maya selection order for sequential renaming.
        return sorted(nodes, key=lambda x: (x.path.count("|"), x.path.lower(), x.uid))


def suffix_filter(node: Node, registry: Registry, category: str) -> bool:
    if category == "All":
        return True
    if category == "Transforms":
        return node.node_type in ("transform", "joint", "dagContainer")
    suffix = registry.role_for(node)
    if category == "Shaders" and registry.is_arnold_type(node.node_type):
        classification = registry._classify(node.node_type).lower()
        if any(word in classification for word in ("shader", "texture", "utility")):
            return True
    groups = {
        "Geometry": {"geo", "srf"}, "Groups": {"grp"},
        "Shaders": {"shd", "sg", "tex", "cc", "nrm", "disp", "rng", "place2d", "ramp", "bump", "mix", "tri", "noise", "layer"},
        "Lights": {"lgt"}, "Curves": {"crv"}, "Arnold": None
    }
    if category == "Arnold":
        if registry.is_arnold_type(node.node_type):
            return True
        if node.node_type in ("transform", "dagContainer"):
            shapes = cmds.listRelatives(node.path, shapes=True, fullPath=True) or []
            return any(registry.is_arnold_type(cmds.nodeType(shape)) for shape in shapes)
        return False
    return suffix in groups.get(category, set())


def _collision_base(name: str, used: Set[str], known: Set[str], padding: int, start: int = 1) -> str:
    if name not in used:
        return name
    n = max(1, start)
    while True:
        candidate = numbered_name(name, n, padding, known)
        if candidate not in used:
            return candidate
        n += 1


class Planner:
    def __init__(self, scene: SceneIndex):
        self.scene = scene
        self.registry = scene.registry

    def create(self, intents: List[Intent], action: str, resolve=True, sync_shapes=False,
               padding=3) -> RenamePlan:
        seen = set()
        requests = []
        skipped = []
        for intent in intents:
            if intent.uid in seen or intent.uid not in self.scene.nodes:
                continue
            seen.add(intent.uid)
            node = self.scene.nodes[intent.uid]
            if not node.editable:
                skipped.append(PlanRow(node.uid, node.path, node.bare, node.bare, node.node_type,
                                       "Skipped", node.skip_reason))
                continue
            valid = bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", intent.wanted))
            if not valid:
                skipped.append(PlanRow(node.uid, node.path, node.bare, intent.wanted, node.node_type,
                                       "Invalid", "Invalid or empty Maya node name"))
                continue
            requests.append(intent)

        shape_specs = []
        shape_ids = set()
        if sync_shapes:
            for intent in requests:
                parent = self.scene.nodes[intent.uid]
                if parent.node_type not in ("transform", "joint", "dagContainer"):
                    continue
                paths = cmds.listRelatives(parent.path, shapes=True, fullPath=True) or []
                regular = []
                intermediate = []
                for path in paths:
                    uid = self.scene.uid_for(path)
                    if not uid or uid in seen or uid in shape_ids:
                        continue
                    shape_node = self.scene.nodes[uid]
                    if not shape_node.editable:
                        skipped.append(PlanRow(uid, shape_node.path, shape_node.bare,
                                               shape_node.bare, shape_node.node_type,
                                               "Skipped", shape_node.skip_reason))
                        continue
                    # A shape instanced under multiple parents cannot be synced to all of them.
                    parents = cmds.listRelatives(path, allParents=True, fullPath=True) or []
                    if len(parents) > 1:
                        skipped.append(PlanRow(uid, shape_node.path, shape_node.bare,
                                               shape_node.bare, shape_node.node_type,
                                               "Skipped", "Instanced shape: ambiguous parent name"))
                        continue
                    try:
                        is_intermediate = bool(cmds.getAttr(path + ".intermediateObject"))
                    except (ValueError, RuntimeError):
                        is_intermediate = False
                    (intermediate if is_intermediate else regular).append(uid)
                    shape_ids.add(uid)
                for collection, label in ((regular, "Shape"), (intermediate, "OrigShape")):
                    for i, uid in enumerate(collection):
                        tail = label if len(collection) == 1 else label + str(i + 1).zfill(2)
                        shape_specs.append((uid, parent.uid, tail))

        requested = {i.uid for i in requests} | shape_ids
        used = {node.bare for uid, node in self.scene.nodes.items() if uid not in requested}
        rows = []
        final_bare = {}
        # Prioritize names already owned by nodes, preventing needless churn.
        requests.sort(key=lambda i: (i.wanted != self.scene.nodes[i.uid].bare,
                                     self.scene.nodes[i.uid].path.lower(), i.uid))
        for intent in requests:
            node = self.scene.nodes[intent.uid]
            wanted = intent.wanted
            name = _collision_base(wanted, used, self.registry.known, padding) if resolve else wanted
            if name in used:
                status, note = "Conflict", "Name already exists in scene"
            else:
                status = "Resolved" if name != wanted else ("Unchanged" if name == node.bare else "Ready")
                note = "Collision resolved" if status == "Resolved" else intent.context
                used.add(name)
            rows.append(PlanRow(node.uid, node.path, node.bare, name, node.node_type, status, note))
            final_bare[node.uid] = name
        for uid, parent_uid, tail in shape_specs:
            node = self.scene.nodes[uid]
            if self.registry.is_arnold_type(node.node_type):
                base = replace_suffix(final_bare[parent_uid], "", self.registry.known)
                wanted = base + "_" + self.registry.suffix_for(node)
            else:
                wanted = final_bare[parent_uid] + tail
            name = _collision_base(wanted, used, self.registry.known, padding) if resolve else wanted
            if name in used:
                status, note = "Conflict", "Shape name already exists"
            else:
                status = "Resolved" if name != wanted else ("Unchanged" if name == node.bare else "Ready")
                note = "Shape name sync"
                used.add(name)
            rows.append(PlanRow(uid, node.path, node.bare, name, node.node_type, status, note, True))
        rows.extend(skipped)
        return RenamePlan(rows, self.scene.signature, action)


class Engine:
    def __init__(self, registry=None):
        self.registry = registry or Registry()
        self.scene = None

    def scan(self):
        self.registry.refresh_arnold_types()
        self.scene = SceneIndex(self.registry)
        return self.scene

    def _nodes(self, mode, category="All", include_shapes=False, include_history=False):
        if self.scene is None:
            self.scan()
        return [n for n in self.scene.scope(mode, include_shapes=include_shapes or category == "Arnold")
                if suffix_filter(n, self.registry, category)
                and (include_history or mode == "Selected" or
                     not self.registry.is_history(n.node_type))]

    def preview(self, action, scope="Selected", category="All", base="", prefix="", suffix="auto",
                search="", replacement="", regex=False, ignore_case=False,
                start=1, padding=3, force_numbers=False, include_shapes=False,
                include_history=False, sync_shapes=False, resolve=True,
                overrides=None):
        self.scan()
        nodes = self._nodes(scope, category, include_shapes, include_history)
        known = self.registry.known
        intents = []
        if action == "Fix Duplicates":
            # Only mutate nodes in the requested scope. Collisions are nevertheless
            # detected globally, including namespaces and read-only references.
            eligible = {n.uid for n in self.scene.scope(scope, include_shapes=True)
                        if suffix_filter(n, self.registry, category)}
            duplicates = collections.defaultdict(list)
            for node in self.scene.nodes.values():
                duplicates[node.bare].append(node)
            for name, matches in duplicates.items():
                if len(matches) < 2:
                    continue
                # Prefer keeping protected/out-of-scope nodes, then a stable path.
                matches.sort(key=lambda n: (n.editable and n.uid in eligible, n.path.lower()))
                keeper = matches[0]
                for node in matches:
                    if node.uid != keeper.uid and node.uid in eligible and node.editable:
                        intents.append(Intent(node.uid, node.bare, "Duplicate short name"))
        elif action == "Shader Network":
            intents = self.shader_network_intents(base)
        else:
            for pos, node in enumerate(nodes):
                original = node.bare
                if action in ("Auto Suffix", "Quick Fix"):
                    detected = self.registry.suffix_for(node)
                    if not detected:
                        continue
                    source = sanitize_name(original) if action == "Quick Fix" else original
                    desired = replace_suffix(source, detected, known)
                elif action == "Clean Names":
                    desired = sanitize_name(original)
                    # This mode strips repeated suffixes but preserves current intended suffix.
                    temp, suffix_part = split_trailing_suffix(desired, known)
                    desired = replace_suffix(temp, suffix_part, known) if suffix_part else desired
                elif action == "Search / Replace":
                    if not search:
                        continue
                    if regex:
                        flags = re.IGNORECASE if ignore_case else 0
                        desired = re.sub(search, replacement, original, flags=flags)
                    elif ignore_case:
                        desired = re.sub(re.escape(search), lambda _: replacement, original, flags=re.IGNORECASE)
                    else:
                        desired = original.replace(search, replacement)
                elif action == "Rename From Parent":
                    if not node.dag:
                        continue
                    parents = cmds.listRelatives(node.path, parent=True, fullPath=True) or []
                    if not parents:
                        continue
                    parent_base = replace_suffix(short_name(parents[0]), "", known)
                    child_base, trailing = split_trailing_suffix(original, known)
                    if not child_base.startswith(parent_base + "_"):
                        desired = parent_base + "_" + child_base
                    else:
                        desired = child_base
                    if trailing:
                        desired += "_" + trailing
                elif action == "Sequential Renumber":
                    desired = numbered_name(original, start + pos, padding, known)
                elif action == "Batch Rename":
                    desired = sanitize_name(base) if base else original
                    if suffix == "auto":
                        detected = self.registry.suffix_for(node)
                        if detected:
                            desired = replace_suffix(desired, detected, known)
                    elif suffix and suffix != "keep":
                        desired = replace_suffix(desired, suffix.lstrip("_"), known)
                    desired = prefix + desired
                    if force_numbers:
                        desired = numbered_name(desired, start + pos, padding, known)
                else:
                    raise ValueError("Unknown operation: %s" % action)
                if (desired != original or action in ("Batch Rename", "Quick Fix") or
                        (sync_shapes and action == "Auto Suffix")):
                    intents.append(Intent(node.uid, desired))
        if overrides:
            by_id = {item.uid: item for item in intents}
            for uid, wanted in overrides.items():
                if uid in by_id:
                    by_id[uid].wanted = wanted
        planner = Planner(self.scene)
        return planner.create(intents, action, resolve=resolve, sync_shapes=sync_shapes, padding=padding)

    def shader_network_intents(self, name=""):
        _require_maya()
        selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        if not selected:
            raise ValueError("Select a shader, shading group, or mesh assigned a shader.")
        first = selected[0]
        typ = cmds.nodeType(first)
        shaders = []
        if typ == "shadingEngine":
            shaders = cmds.listConnections(first + ".surfaceShader", source=True, destination=False) or []
        elif self.registry.role_for(self.scene.nodes[self.scene.uid_for(first)]) == "shd":
            shaders = [first]
        else:
            sgs = cmds.listConnections(first, type="shadingEngine") or []
            if not sgs:
                shapes = cmds.listRelatives(first, shapes=True, fullPath=True) or []
                for shape in shapes:
                    sgs.extend(cmds.listConnections(shape, type="shadingEngine") or [])
            for sg in dict.fromkeys(sgs):
                shaders.extend(cmds.listConnections(sg + ".surfaceShader", source=True, destination=False) or [])
        shaders = list(dict.fromkeys(shaders))
        if len(shaders) != 1:
            raise ValueError("Select exactly one surface shader, or a mesh with one distinct surface material.")
        shader = shaders[0]
        shader_uid = self.scene.uid_for(shader)
        if not shader_uid:
            raise ValueError("Shader could not be resolved.")
        material_name = sanitize_name(name) if name else replace_suffix(short_name(shader), "", self.registry.known)
        if not material_name:
            raise ValueError("Enter a material name.")
        upstream = {}
        stack = [(shader, "")]
        visited = set()
        while stack and len(visited) < 500:
            node, channel = stack.pop()
            uid = self.scene.uid_for(node)
            if not uid or uid in visited:
                continue
            visited.add(uid)
            suffix = self.registry.suffix_for(self.scene.nodes[uid])
            if uid != shader_uid and not suffix:
                continue
            upstream[uid] = channel
            pairs = cmds.listConnections(node, source=True, destination=False,
                                         connections=True, plugs=True) or []
            for target_plug, source_plug in zip(pairs[::2], pairs[1::2]):
                if ".message" in target_plug or ".message" in source_plug:
                    continue
                other = source_plug.rsplit(".", 1)[0]
                if not cmds.objExists(other):
                    continue
                # Root shader inputs define semantic texture channels.
                source_channel = (target_plug.rsplit(".", 1)[-1] if uid == shader_uid else channel)
                source_channel = re.sub(r"[^A-Za-z0-9_]", "", source_channel)
                channel_map = {
                    "specularRoughness": "roughness", "normalCamera": "normal",
                    "coatNormal": "coatNormal", "emissionColor": "emission",
                    "baseColor": "baseColor", "specularColor": "specular",
                    "transmissionColor": "transmission", "subsurfaceColor": "subsurface",
                    "coatColor": "coat", "coatRoughness": "coatRoughness"
                }
                source_channel = channel_map.get(source_channel, source_channel)
                stack.append((other, source_channel))
        if stack:
            raise ValueError("Shader network traversal reached the 500-node safety limit.")
        # Shared nodes are not renamed. A node with consumers outside the captured
        # network (other than the selected root shader) is conservatively skipped.
        root_suffix = self.registry.suffix_for(self.scene.nodes[shader_uid])
        intents = [Intent(shader_uid, material_name + "_" + root_suffix, "Surface shader")]
        for uid, channel in upstream.items():
            if uid == shader_uid:
                continue
            node = self.scene.nodes[uid]
            if not node.editable:
                continue
            suffix = self.registry.suffix_for(node)
            if suffix not in self.registry.known:
                continue
            consumers = cmds.listConnections(node.path, source=False, destination=True) or []
            shared = False
            for consumer in consumers:
                consumer_uid = self.scene.uid_for(consumer)
                if consumer_uid and consumer_uid not in upstream:
                    ctype = self.scene.nodes[consumer_uid].node_type
                    if ctype not in ("defaultTextureList", "defaultRenderUtilityList"):
                        shared = True
                        break
            if shared:
                continue
            label = sanitize_name(channel) if channel else "utility"
            wanted = (material_name + "_" + suffix if self.registry.is_arnold_type(node.node_type)
                      else "%s_%s_%s" % (material_name, label, suffix))
            intents.append(Intent(uid, wanted, "Upstream shader node"))
        # Only rename SGs with an unambiguous connection to this material.
        for sg in cmds.listConnections(shader, type="shadingEngine", source=False, destination=True) or []:
            uid = self.scene.uid_for(sg)
            if not uid:
                continue
            root_shaders = cmds.listConnections(sg + ".surfaceShader", source=True, destination=False) or []
            if len(set(root_shaders)) == 1 and self.scene.uid_for(root_shaders[0]) == shader_uid:
                intents.append(Intent(uid, material_name + "_sg", "Material shading group"))
        return intents

    def apply(self, plan: RenamePlan):
        _require_maya()
        # The scene is rescanned so cached names do not silently overwrite changes.
        current = SceneIndex(self.registry)
        if current.signature != plan.signature:
            raise RuntimeError("Scene changed after preview. Refresh preview before applying.")
        issues = [r for r in plan.rows if r.status in ("Conflict", "Invalid")]
        if issues:
            raise RuntimeError("Resolve %d naming conflicts or invalid names before applying." % len(issues))
        changes = plan.changes()
        if not changes:
            return 0
        used = {node.bare for node in current.nodes.values()}
        final = []
        for row in changes:
            node = current.nodes.get(row.uid)
            if not node or not node.editable:
                raise RuntimeError("A node has become unavailable or protected: %s" % row.old_name)
        changed = False
        cmds.undoInfo(openChunk=True, chunkName="Studio Renamer")
        try:
            # Phase 1: move *every* changing node to an unoccupied temporary name.
            # UUID resolution remains stable even when parents are renamed.
            for row in changes:
                node = current.nodes[row.uid]
                temp = "_studioTmp_" + uuidlib.uuid4().hex
                while temp in used:
                    temp = "_studioTmp_" + uuidlib.uuid4().hex
                path = current.resolve(row.uid)
                if not path:
                    raise RuntimeError("Node disappeared: %s" % row.old_path)
                cmds.rename(path, make_absolute(node.namespace, temp), ignoreShape=True)
                changed = True
                if short_name(current.resolve(row.uid) or "") != temp:
                    raise RuntimeError("Maya adjusted temporary name for %s" % row.old_name)
                used.add(temp)
            # Phase 2: rename transforms/parents before their child shapes.
            # The target collision plan already accounts for ALL nodes in the scene.
            for row in sorted(changes, key=lambda r: (r.shape_sync, r.old_path.count("|"), r.old_path)):
                node = current.nodes[row.uid]
                path = current.resolve(row.uid)
                if not path:
                    raise RuntimeError("Node disappeared during rename: %s" % row.old_name)
                cmds.rename(path, make_absolute(node.namespace, row.new_name), ignoreShape=True)
                if short_name(current.resolve(row.uid) or "") != row.new_name:
                    raise RuntimeError("Maya adjusted final name for %s" % row.old_name)
        except Exception as exc:
            error = exc
        else:
            error = None
        finally:
            cmds.undoInfo(closeChunk=True)
        if error is not None:
            if changed:
                try:
                    cmds.undo()
                except Exception:
                    pass
            raise RuntimeError("Rename failed (attempted automatic undo): %s" % error)
        return len(changes)

    def audit(self, scope="Scene"):
        self.scan()
        groups = collections.defaultdict(list)
        for node in self.scene.nodes.values():
            groups[node.bare].append(node)
        rows = []
        for node in self.scene.scope(scope, include_shapes=True):
            problems = []
            if len(groups[node.bare]) > 1:
                problems.append("Duplicate global short name (%d nodes)" % len(groups[node.bare]))
            suffix = self.registry.suffix_for(node)
            # Ordinary shapes use <transform>Shape; Arnold shapes use full types.
            is_shape = node.dag and node.node_type not in ("transform", "joint", "ikHandle", "dagContainer")
            if suffix and (not is_shape or self.registry.is_arnold_type(node.node_type)):
                expected = "_" + suffix
                if not node.bare.endswith(expected):
                    problems.append("Expected suffix " + expected)
            if sanitize_name(node.bare) != node.bare:
                problems.append("Invalid characters")
            if any(re.match(pattern, node.bare) for pattern in self.registry.data.get("default_name_patterns", [])):
                problems.append("Default/generated name")
            if problems:
                rows.append(PlanRow(node.uid, node.path, node.bare, node.bare,
                                    node.node_type, "Warning" if node.editable else "Protected",
                                    "; ".join(problems)))
        return RenamePlan(rows, self.scene.signature, "Validate")

    def export_audit(self, filename: str):
        plan = self.audit("Scene")
        content = {
            "tool": APP_NAME, "version": VERSION, "issues": len(plan.rows),
            "rows": [dataclasses.asdict(row) for row in plan.rows]
        }
        _atomic_json_write(filename, content)
        return len(plan.rows)

# UI imports are deliberately optional so pure naming helpers can be tested
# outside Maya. Maya 2025+ usually uses Qt 6, older supported versions Qt 5.
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
        from shiboken2 import wrapInstance
    except ImportError:
        QtCore = QtGui = QtWidgets = None
        wrapInstance = None


def _qt(name, group):
    direct = getattr(QtCore.Qt, name, None)
    return direct if direct is not None else getattr(getattr(QtCore.Qt, group), name)


if QtWidgets is not None:
    DISPLAY = _qt("DisplayRole", "ItemDataRole")
    EDIT = _qt("EditRole", "ItemDataRole")
    FOREGROUND = _qt("ForegroundRole", "ItemDataRole")
    TOOLTIP = _qt("ToolTipRole", "ItemDataRole")
    HORIZONTAL = _qt("Horizontal", "Orientation")
    ITEM_ENABLED = _qt("ItemIsEnabled", "ItemFlag")
    ITEM_SELECTABLE = _qt("ItemIsSelectable", "ItemFlag")
    ITEM_EDITABLE = _qt("ItemIsEditable", "ItemFlag")
    CASE_INSENSITIVE = _qt("CaseInsensitive", "CaseSensitivity")
    SELECT_ROWS = QtWidgets.QAbstractItemView.SelectRows if hasattr(QtWidgets.QAbstractItemView, "SelectRows") else QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
    EXTENDED_SELECTION = QtWidgets.QAbstractItemView.ExtendedSelection if hasattr(QtWidgets.QAbstractItemView, "ExtendedSelection") else QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection

    class PreviewModel(QtCore.QAbstractTableModel):
        proposedEdited = QtCore.Signal(str, str)
        headers = ("Current Name", "Proposed Name", "Type", "Status", "Notes")

        def __init__(self, parent=None):
            super().__init__(parent)
            self.rows: List[PlanRow] = []
            self.editable = False

        def set_rows(self, rows, editable=True):
            self.beginResetModel()
            self.rows = rows
            self.editable = editable
            self.endResetModel()

        def rowCount(self, parent=QtCore.QModelIndex()):
            return 0 if parent.isValid() else len(self.rows)

        def columnCount(self, parent=QtCore.QModelIndex()):
            return 0 if parent.isValid() else len(self.headers)

        def headerData(self, section, orientation, role=DISPLAY):
            if orientation == HORIZONTAL and role == DISPLAY:
                return self.headers[section]
            return None

        def data(self, index, role=DISPLAY):
            if not index.isValid() or index.row() >= len(self.rows):
                return None
            r = self.rows[index.row()]
            if role in (DISPLAY, EDIT):
                return (r.old_name, r.new_name, r.node_type, r.status, r.note)[index.column()]
            if role == TOOLTIP:
                return "%s\nUUID: %s\n%s" % (r.old_path, r.uid, r.note)
            if role == FOREGROUND:
                colors = {"Conflict": "#E39A65", "Invalid": "#E39A65",
                          "Skipped": "#888888", "Protected": "#888888",
                          "Resolved": "#B9CFA8", "Ready": "#B9CFA8",
                          "Warning": "#D3B87D"}
                if r.status in colors and index.column() in (1, 3):
                    return QtGui.QBrush(QtGui.QColor(colors[r.status]))
            return None

        def flags(self, index):
            flags = ITEM_ENABLED | ITEM_SELECTABLE
            if self.editable and index.isValid() and index.column() == 1 and self.rows[index.row()].status not in ("Skipped", "Protected"):
                flags |= ITEM_EDITABLE
            return flags

        def setData(self, index, value, role=EDIT):
            if role != EDIT or not index.isValid() or index.column() != 1:
                return False
            uid = self.rows[index.row()].uid
            self.proposedEdited.emit(uid, str(value))
            return True

    class StudioRenamerWindow(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("studioRenamerWindow")
            self.setWindowTitle("Studio Renamer  |  Maya")
            self.setMinimumWidth(660)
            self.resize(850, 710)
            self.setAttribute(_qt("WA_DeleteOnClose", "WidgetAttribute"), True)
            self.engine = Engine()
            self.plan: Optional[RenamePlan] = None
            self.last_action = "Auto Suffix"
            self.last_kwargs = {}
            self.overrides = {}
            self._make_ui()
            self._restore_window()

        def _make_ui(self):
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(12, 12, 12, 10)
            outer.setSpacing(9)

            header = QtWidgets.QHBoxLayout()
            label = QtWidgets.QLabel("STUDIO RENAMER")
            f = label.font()
            f.setPointSize(11)
            f.setBold(True)
            label.setFont(f)
            header.addWidget(label)
            version = QtWidgets.QLabel("v" + VERSION)
            version.setStyleSheet("color:#888")
            header.addWidget(version)
            header.addStretch(1)
            self.settings_btn = QtWidgets.QPushButton("Registry / Settings")
            self.settings_btn.clicked.connect(self._settings)
            header.addWidget(self.settings_btn)
            outer.addLayout(header)

            scope_row = QtWidgets.QHBoxLayout()
            scope_row.addWidget(QtWidgets.QLabel("Scope"))
            self.scope = QtWidgets.QComboBox()
            self.scope.addItems(["Selected", "Hierarchy", "Scene"])
            scope_row.addWidget(self.scope, 1)
            scope_row.addWidget(QtWidgets.QLabel("Filter"))
            self.category = QtWidgets.QComboBox()
            self.category.addItems(["All", "Transforms", "Geometry", "Groups", "Shaders", "Arnold", "Lights", "Curves"])
            scope_row.addWidget(self.category, 1)
            outer.addLayout(scope_row)

            tabs = QtWidgets.QTabWidget()
            tabs.setDocumentMode(True)
            outer.addWidget(tabs)
            rename_tab = QtWidgets.QWidget()
            tabs.addTab(rename_tab, "Quick Rename")
            rename_layout = QtWidgets.QVBoxLayout(rename_tab)
            rename_layout.setContentsMargins(8, 9, 8, 9)
            rename_layout.setSpacing(7)
            name_row = QtWidgets.QHBoxLayout()
            name_row.addWidget(QtWidgets.QLabel("Base"))
            self.base = QtWidgets.QLineEdit()
            self.base.setPlaceholderText("Optional. Empty keeps each node's original name")
            name_row.addWidget(self.base, 1)
            rename_layout.addLayout(name_row)
            prop_row = QtWidgets.QHBoxLayout()
            prop_row.addWidget(QtWidgets.QLabel("Prefix"))
            self.prefix = QtWidgets.QLineEdit()
            self.prefix.setMaximumWidth(125)
            prop_row.addWidget(self.prefix)
            prop_row.addWidget(QtWidgets.QLabel("Suffix"))
            self.suffix = QtWidgets.QComboBox()
            self.suffix.addItem("Auto by node type", "auto")
            self.suffix.addItem("Keep existing", "keep")
            for suffix in sorted(self.engine.registry.known):
                self.suffix.addItem("_" + suffix, suffix)
            prop_row.addWidget(self.suffix, 1)
            rename_layout.addLayout(prop_row)
            index_row = QtWidgets.QHBoxLayout()
            self.force_numbers = QtWidgets.QCheckBox("Sequential numbering")
            index_row.addWidget(self.force_numbers)
            index_row.addStretch(1)
            index_row.addWidget(QtWidgets.QLabel("Start"))
            self.start = QtWidgets.QSpinBox()
            self.start.setRange(0, 999999)
            self.start.setValue(1)
            index_row.addWidget(self.start)
            index_row.addWidget(QtWidgets.QLabel("Padding"))
            self.padding = QtWidgets.QSpinBox()
            self.padding.setRange(1, 8)
            self.padding.setValue(int(self.engine.registry.data.get("number_padding", 3)))
            index_row.addWidget(self.padding)
            rename_layout.addLayout(index_row)
            self.rename_btn = QtWidgets.QPushButton("Preview Batch Rename")
            self.rename_btn.clicked.connect(lambda: self.preview_action("Batch Rename"))
            rename_layout.addWidget(self.rename_btn)

            search_tab = QtWidgets.QWidget()
            tabs.addTab(search_tab, "Find / Replace")
            search_layout = QtWidgets.QFormLayout(search_tab)
            search_layout.setContentsMargins(10, 10, 10, 9)
            self.search = QtWidgets.QLineEdit()
            self.replace = QtWidgets.QLineEdit()
            search_layout.addRow("Find", self.search)
            search_layout.addRow("Replace", self.replace)
            search_opts = QtWidgets.QHBoxLayout()
            self.regex = QtWidgets.QCheckBox("Regular expression")
            self.ignore_case = QtWidgets.QCheckBox("Ignore case")
            search_opts.addWidget(self.regex)
            search_opts.addWidget(self.ignore_case)
            search_opts.addStretch(1)
            search_layout.addRow(search_opts)
            find_btn = QtWidgets.QPushButton("Preview Find / Replace")
            find_btn.clicked.connect(lambda: self.preview_action("Search / Replace"))
            search_layout.addRow(find_btn)

            operations = QtWidgets.QHBoxLayout()
            for text, action in (("Auto Suffix", "Auto Suffix"),
                                 ("Quick Fix", "Quick Fix"),
                                 ("Clean", "Clean Names"),
                                 ("Fix Duplicates", "Fix Duplicates"),
                                 ("Shader Network", "Shader Network"),
                                 ("Validate", "Validate")):
                btn = QtWidgets.QPushButton(text)
                btn.setToolTip("Preview: " + action)
                btn.clicked.connect(lambda checked=False, a=action: self.preview_action(a))
                operations.addWidget(btn)
            self.more_btn = QtWidgets.QToolButton()
            self.more_btn.setText("More")
            self.more_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
            extra = QtWidgets.QMenu(self.more_btn)
            for text, action in (("Rename From Parent", "Rename From Parent"),
                                 ("Sequential Renumber", "Sequential Renumber")):
                entry = extra.addAction(text)
                entry.triggered.connect(lambda checked=False, a=action: self.preview_action(a))
            extra.addSeparator()
            select_matching = extra.addAction("Select Matching Node Types")
            select_matching.triggered.connect(self._select_matching)
            self.more_btn.setMenu(extra)
            operations.addWidget(self.more_btn)
            outer.addLayout(operations)

            options = QtWidgets.QHBoxLayout()
            self.sync_shapes = QtWidgets.QCheckBox("Sync shapes")
            self.sync_shapes.setChecked(True)
            options.addWidget(self.sync_shapes)
            self.include_shapes = QtWidgets.QCheckBox("Direct shape rename")
            options.addWidget(self.include_shapes)
            self.include_history = QtWidgets.QCheckBox("Include history")
            options.addWidget(self.include_history)
            self.resolve = QtWidgets.QCheckBox("Auto-resolve collisions")
            self.resolve.setChecked(True)
            options.addWidget(self.resolve)
            options.addStretch(1)
            outer.addLayout(options)

            preview_header = QtWidgets.QHBoxLayout()
            title = QtWidgets.QLabel("PREVIEW")
            title.setStyleSheet("font-weight:600")
            preview_header.addWidget(title)
            preview_header.addStretch(1)
            self.table_filter = QtWidgets.QLineEdit()
            self.table_filter.setPlaceholderText("Filter preview...")
            self.table_filter.setMaximumWidth(230)
            preview_header.addWidget(self.table_filter)
            outer.addLayout(preview_header)

            self.table = QtWidgets.QTableView()
            self.model = PreviewModel(self)
            self.proxy = QtCore.QSortFilterProxyModel(self)
            self.proxy.setSourceModel(self.model)
            self.proxy.setFilterKeyColumn(-1)
            self.proxy.setFilterCaseSensitivity(CASE_INSENSITIVE)
            self.table.setModel(self.proxy)
            self.table.setSortingEnabled(True)
            self.table.setSelectionBehavior(SELECT_ROWS)
            self.table.setSelectionMode(EXTENDED_SELECTION)
            self.table.setAlternatingRowColors(True)
            self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed if hasattr(QtWidgets.QAbstractItemView, 'DoubleClicked') else QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed)
            self.table.verticalHeader().setVisible(False)
            self.table.setShowGrid(False)
            header_view = self.table.horizontalHeader()
            header_view.setStretchLastSection(True)
            self.table.setColumnWidth(0, 210)
            self.table.setColumnWidth(1, 210)
            self.table.setColumnWidth(2, 90)
            self.table.setColumnWidth(3, 95)
            self.table.setContextMenuPolicy(_qt("CustomContextMenu", "ContextMenuPolicy"))
            self.table.customContextMenuRequested.connect(self._context_menu)
            self.model.proposedEdited.connect(self._manual_rename)
            self.table_filter.textChanged.connect(self.proxy.setFilterFixedString)
            self.table.doubleClicked.connect(self._on_double_click)
            outer.addWidget(self.table, 1)

            footer = QtWidgets.QHBoxLayout()
            self.status = QtWidgets.QLabel("Select nodes, then choose an operation to preview.")
            self.status.setStyleSheet("color:#A2A2A2")
            footer.addWidget(self.status, 1)
            self.export_btn = QtWidgets.QPushButton("Export Audit")
            self.export_btn.clicked.connect(self._export_audit)
            footer.addWidget(self.export_btn)
            self.select_btn = QtWidgets.QPushButton("Select Rows")
            self.select_btn.clicked.connect(self._select_rows)
            footer.addWidget(self.select_btn)
            self.apply_btn = QtWidgets.QPushButton("Apply Rename")
            self.apply_btn.setMinimumWidth(130)
            self.apply_btn.clicked.connect(self.apply_rename)
            self.apply_btn.setEnabled(False)
            footer.addWidget(self.apply_btn)
            outer.addLayout(footer)

        def _kwargs(self):
            return dict(scope=self.scope.currentText(), category=self.category.currentText(),
                        base=self.base.text(), prefix=self.prefix.text(),
                        suffix=self.suffix.currentData(), search=self.search.text(),
                        replacement=self.replace.text(), regex=self.regex.isChecked(),
                        ignore_case=self.ignore_case.isChecked(), start=self.start.value(),
                        padding=self.padding.value(), force_numbers=self.force_numbers.isChecked(),
                        include_shapes=self.include_shapes.isChecked(),
                        include_history=self.include_history.isChecked(),
                        sync_shapes=self.sync_shapes.isChecked(), resolve=self.resolve.isChecked())

        def preview_action(self, action):
            self.last_action = action
            self.last_kwargs = self._kwargs()
            self.overrides.clear()
            self._calculate()

        def _calculate(self):
            try:
                QtWidgets.QApplication.setOverrideCursor(_qt("WaitCursor", "CursorShape"))
                if self.last_action == "Validate":
                    new_plan = self.engine.audit(self.last_kwargs.get("scope", "Scene"))
                else:
                    new_plan = self.engine.preview(self.last_action, **self.last_kwargs,
                                                   overrides=self.overrides)
                self.plan = new_plan
                self.model.set_rows(new_plan.rows, editable=self.last_action != "Validate")
                counts = collections.Counter(row.status for row in new_plan.rows)
                total = len(new_plan.rows)
                if self.last_action == "Validate":
                    text = "%d naming issues found" % total
                else:
                    text = "%d rows   |   %d changes   |   %d skipped   |   %d conflicts" % (
                        total, len(new_plan.changes()), counts["Skipped"],
                        counts["Invalid"] + counts["Conflict"])
                self.status.setText(text)
                self.apply_btn.setEnabled(self.last_action != "Validate" and bool(new_plan.changes())
                                          and not counts["Conflict"] and not counts["Invalid"])
            except Exception as exc:
                self.plan = None
                self.model.set_rows([])
                self.apply_btn.setEnabled(False)
                QtWidgets.QMessageBox.warning(self, APP_NAME, "Preview failed:\n%s" % exc)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()

        def _manual_rename(self, uid, wanted):
            self.overrides[uid] = wanted
            # Rebuild after Qt finishes committing the active table editor.
            QtCore.QTimer.singleShot(0, self._calculate)

        def _selected_rows(self):
            seen = set()
            rows = []
            for proxy_index in self.table.selectionModel().selectedRows():
                idx = self.proxy.mapToSource(proxy_index)
                if idx.isValid() and idx.row() < len(self.model.rows):
                    r = self.model.rows[idx.row()]
                    if r.uid not in seen:
                        seen.add(r.uid)
                        rows.append(r)
            return rows

        def _select_matching(self):
            try:
                scene = self.engine.scan()
                matching = [n.path for n in self.engine._nodes(
                    self.scope.currentText(), self.category.currentText(),
                    self.include_shapes.isChecked(), self.include_history.isChecked())]
                if matching:
                    cmds.select(matching, replace=True)
                    self.status.setText("Selected %d matching nodes." % len(matching))
                else:
                    self.status.setText("No matching nodes found.")
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, APP_NAME, str(exc))

        def _select_rows(self):
            if not self.engine.scene:
                return
            paths = [self.engine.scene.resolve(row.uid) for row in self._selected_rows()]
            paths = [path for path in paths if path]
            if paths:
                cmds.select(paths, replace=True)

        def _on_double_click(self, index):
            # The proposed name column supports inline editing. Double-clicking
            # other columns locates that Maya node.
            if index.column() != 1:
                self._select_rows()

        def _context_menu(self, position):
            rows = self._selected_rows()
            if not rows:
                return
            menu = QtWidgets.QMenu(self)
            select_action = menu.addAction("Select in Maya")
            copy_old = menu.addAction("Copy current names")
            copy_new = menu.addAction("Copy proposed names")
            copy_paths = menu.addAction("Copy full paths")
            chosen = menu.exec_(self.table.viewport().mapToGlobal(position)) if hasattr(menu, "exec_") else menu.exec(self.table.viewport().mapToGlobal(position))
            if chosen == select_action:
                self._select_rows()
            elif chosen in (copy_old, copy_new, copy_paths):
                attribute = ("old_name" if chosen == copy_old else "new_name" if chosen == copy_new else "old_path")
                QtWidgets.QApplication.clipboard().setText("\n".join(getattr(r, attribute) for r in rows))

        def apply_rename(self):
            if not self.plan or self.last_action == "Validate":
                return
            amount = len(self.plan.changes())
            if not amount:
                return
            if self.last_kwargs.get("scope") == "Scene" and amount > 1000:
                choice = QtWidgets.QMessageBox.question(self, APP_NAME,
                    "Rename %d nodes across the scene? Maya Undo will restore the batch." % amount)
                yes = (QtWidgets.QMessageBox.Yes if hasattr(QtWidgets.QMessageBox, "Yes")
                       else QtWidgets.QMessageBox.StandardButton.Yes)
                if choice != yes:
                    return
            try:
                QtWidgets.QApplication.setOverrideCursor(_qt("WaitCursor", "CursorShape"))
                count = self.engine.apply(self.plan)
                self.status.setText("Successfully renamed %d nodes. One Maya Undo restores the batch." % count)
                self.plan = None
                self.apply_btn.setEnabled(False)
                self.model.set_rows([], editable=False)
                self.overrides.clear()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, APP_NAME, str(exc))
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()

        def _export_audit(self):
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export naming audit",
                os.path.expanduser("~/maya_naming_audit.json"), "JSON (*.json)")
            if filename:
                try:
                    issues = self.engine.export_audit(filename)
                    self.status.setText("Exported %d naming issues: %s" % (issues, filename))
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(self, APP_NAME, str(exc))

        def _settings(self):
            path = _config_path()
            msg = ("Suffix mappings are stored in:\n\n%s\n\n"
                   "Edit this JSON file to add custom node types and suffixes, "
                   "then click Reload Registry. Arnold nodes always use their full Maya node type "
                   "(for example oak_aiColorCorrect), including with older registries.\n\n"
                   "Changes take effect after reloading.") % path
            dialog = QtWidgets.QMessageBox(self)
            dialog.setWindowTitle("Suffix Registry")
            dialog.setText(msg)
            reload_btn = dialog.addButton("Reload Registry", QtWidgets.QMessageBox.AcceptRole if hasattr(QtWidgets.QMessageBox, 'AcceptRole') else QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            open_btn = dialog.addButton("Open JSON", QtWidgets.QMessageBox.ActionRole if hasattr(QtWidgets.QMessageBox, 'ActionRole') else QtWidgets.QMessageBox.ButtonRole.ActionRole)
            dialog.addButton("Close", QtWidgets.QMessageBox.RejectRole if hasattr(QtWidgets.QMessageBox, 'RejectRole') else QtWidgets.QMessageBox.ButtonRole.RejectRole)
            dialog.exec_() if hasattr(dialog, "exec_") else dialog.exec()
            if dialog.clickedButton() == open_btn:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))
            elif dialog.clickedButton() == reload_btn:
                try:
                    self.engine = Engine(Registry(load_registry()))
                    existing = self.suffix.currentData()
                    self.suffix.clear()
                    self.suffix.addItem("Auto by node type", "auto")
                    self.suffix.addItem("Keep existing", "keep")
                    for suffix in sorted(self.engine.registry.known):
                        self.suffix.addItem("_" + suffix, suffix)
                    index = self.suffix.findData(existing)
                    self.suffix.setCurrentIndex(index if index >= 0 else 0)
                    self.plan = None
                    self.model.set_rows([])
                    self.apply_btn.setEnabled(False)
                    self.status.setText("Registry reloaded. Preview again before applying.")
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(self, APP_NAME, str(exc))

        def _restore_window(self):
            try:
                settings = QtCore.QSettings("StudioRenamer", "StudioRenamer")
                geometry = settings.value("geometry")
                if geometry:
                    self.restoreGeometry(geometry)
            except Exception:
                pass

        def closeEvent(self, event):
            try:
                QtCore.QSettings("StudioRenamer", "StudioRenamer").setValue("geometry", self.saveGeometry())
            except Exception:
                pass
            super().closeEvent(event)


_window = None


def show():
    """Open a single instance of the artist UI, parented to Maya."""
    global _window
    _require_maya()
    if QtWidgets is None:
        raise RuntimeError("PySide6 or PySide2 is required. Run inside the Maya UI, not mayapy.")
    if _window is not None:
        try:
            _window.close()
        except RuntimeError:
            pass
    try:
        import maya.OpenMayaUI as omui
        ptr = omui.MQtUtil.mainWindow()
        maya_window = wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None
    except Exception:
        maya_window = None
    _window = StudioRenamerWindow(parent=maya_window)
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window


def launch():
    return show()


def rename_selection_auto(sync_shapes=True):
    """Headless workflow for Maya shelves/pipeline scripts."""
    engine = Engine()
    plan = engine.preview("Auto Suffix", scope="Selected", sync_shapes=sync_shapes)
    return engine.apply(plan)


def validate_scene():
    """Headless pre-publish validation. Returns issue records, does not mutate Maya."""
    engine = Engine()
    return [dataclasses.asdict(row) for row in engine.audit("Scene").rows]


if __name__ == "__main__" and cmds is not None:
    show()
