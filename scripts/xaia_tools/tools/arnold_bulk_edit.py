"""Bulk edit aiStandardSurface materials on the current Maya mesh selection.

Run this file in Maya's Python Script Editor to open the window, or import it
and call show(). No PySide dependency; uses Maya's native controls and API 2.0.
"""

import math
import numbers
from functools import partial

import maya.cmds as cmds
import maya.api.OpenMaya as om


WINDOW = "arnoldBulkMaterialEditor"
NODE_TYPE = "aiStandardSurface"

# Attribute names are MtoA names. Availability, defaults, limits, and enum
# choices are queried from the installed plugin rather than a temporary node.
SECTIONS = (
    ("Base", (("base", "Weight"), ("baseColor", "Color"),
              ("diffuseRoughness", "Diffuse Roughness"), ("metalness", "Metalness"))),
    ("Specular", (("specular", "Weight"), ("specularColor", "Color"),
                  ("specularRoughness", "Roughness"), ("specularIOR", "IOR"),
                  ("specularAnisotropy", "Anisotropy"), ("specularRotation", "Rotation"))),
    ("Transmission", (("transmission", "Weight"), ("transmissionColor", "Color"),
                      ("transmissionDepth", "Depth"), ("transmissionScatter", "Scatter"),
                      ("transmissionScatterAnisotropy", "Scatter Anisotropy"),
                      ("transmissionDispersion", "Dispersion Abbe"),
                      ("transmissionExtraRoughness", "Extra Roughness"),
                      ("transmissionShadowDensity", "Shadow Density"),
                      ("transmitAovs", "Transmit AOVs"),
                      ("dielectricPriority", "Dielectric Priority"))),
    ("Subsurface", (("subsurface", "Weight"), ("subsurfaceColor", "Color"),
                    ("subsurfaceRadius", "Radius"), ("subsurfaceScale", "Scale"),
                    ("subsurfaceType", "Type"), ("subsurfaceAnisotropy", "Anisotropy"))),
    ("Coat", (("coat", "Weight"), ("coatColor", "Color"),
              ("coatRoughness", "Roughness"), ("coatIOR", "IOR"),
              ("coatAnisotropy", "Anisotropy"), ("coatRotation", "Rotation"),
              ("coatNormal", "Normal"), ("coatAffectColor", "Affect Color"),
              ("coatAffectRoughness", "Affect Roughness"))),
    ("Sheen", (("sheen", "Weight"), ("sheenColor", "Color"),
               ("sheenRoughness", "Roughness"))),
    ("Emission", (("emission", "Weight"), ("emissionColor", "Color"))),
    ("Thin Film", (("thinFilmThickness", "Thickness"), ("thinFilmIOR", "IOR"))),
    ("Geometry", (("opacity", "Opacity"), ("thinWalled", "Thin Walled"),
                  ("normalCamera", "Normal"), ("tangent", "Tangent"))),
    ("Advanced", (("caustics", "Caustics"), ("internalReflections", "Internal Reflections"),
                  ("exitToBackground", "Exit to Background"),
                  ("indirectDiffuse", "Indirect Diffuse"),
                  ("indirectSpecular", "Indirect Specular"))),
)
VECTOR_ATTRIBUTES = {"subsurfaceRadius", "coatNormal", "normalCamera", "tangent"}


def ensure_arnold():
    """Load MtoA if necessary, without creating or modifying scene nodes."""
    if not cmds.pluginInfo("mtoa", query=True, loaded=True):
        try:
            cmds.loadPlugin("mtoa", quiet=True)
        except RuntimeError as exc:
            raise RuntimeError("Arnold for Maya (mtoa) must be installed and loadable.") from exc


def _query(attr, **flags):
    return cmds.attributeQuery(attr, type=NODE_TYPE, **flags)


def _enum_items(text):
    result, index = [], 0
    for item in text.split(":"):
        if "=" in item:
            item, number = item.rsplit("=", 1)
            index = int(number)
        result.append((item, index))
        index += 1
    return result


def attribute_specs():
    """Return supported settings using metadata from the installed MtoA."""
    ensure_arnold()
    specs = {}
    for section, attributes in SECTIONS:
        for attr, label in attributes:
            if not _query(attr, exists=True):
                continue
            attr_type = _query(attr, attributeType=True)
            kind = {"bool": "bool", "enum": "enum", "long": "int", "short": "int",
                    "byte": "int", "float3": "vector", "double3": "vector"}.get(attr_type, "float")
            if kind == "vector" and attr not in VECTOR_ATTRIBUTES and _query(attr, usedAsColor=True):
                kind = "color"
            default = _query(attr, listDefault=True)
            spec = {"section": section, "label": label, "kind": kind, "type": attr_type,
                    "default": tuple(default) if kind in ("color", "vector") else default[0]}
            if kind == "enum":
                spec["items"] = _enum_items(_query(attr, listEnum=True)[0])
            if kind not in ("color", "vector"):
                for key, exists, query in (("min", "minExists", "minimum"),
                                           ("max", "maxExists", "maximum")):
                    if _query(attr, **{exists: True}):
                        spec[key] = _query(attr, **{query: True})[0]
            specs[attr] = spec
    return specs


def _mesh_paths(path):
    """Walk this exact DAG path so instanced descendants retain their identity."""
    node = path.node()
    if node.hasFn(om.MFn.kMesh):
        if not om.MFnDagNode(path).isIntermediateObject:
            yield path
    elif node.hasFn(om.MFn.kTransform):
        fn = om.MFnDagNode(path)
        for index in range(fn.childCount()):
            child = om.MDagPath(path)
            child.push(fn.child(index))
            yield from _mesh_paths(child)


def discover_materials(selection=None):
    """Resolve direct surface assignments for meshes, groups, or mesh components.

    Face selections restrict discovery to those faces. Vertices, edges, and UVs
    are converted to touching faces. Object/group selection includes descendants.
    Discovery never changes the active selection or shader assignments.
    """
    items = cmds.ls(selection=True, long=True) if selection is None else list(selection)
    meshes, ignored = {}, []
    for item in items:
        try:
            selected = om.MSelectionList()
            selected.add(item)
            path, component = selected.getComponent(0)
            if not component.isNull():
                if not path.node().hasFn(om.MFn.kMesh):
                    ignored.append(item)
                    continue
                components = [(path, component)]
                if component.apiType() != om.MFn.kMeshPolygonComponent:
                    faces = cmds.polyListComponentConversion(item, toFace=True) or []
                    converted = om.MSelectionList()
                    for face in faces:
                        converted.add(face)
                    if converted.isEmpty():
                        ignored.append(item)
                        continue
                    components = [converted.getComponent(i) for i in range(converted.length())]
                if om.MFnDagNode(path).isIntermediateObject:
                    continue
                name = path.fullPathName()
                face_ids = set()
                for component_path, face_component in components:
                    iterator = om.MItMeshPolygon(component_path, face_component)
                    while not iterator.isDone():
                        face_ids.add(iterator.index())
                        iterator.next()
                if name not in meshes:
                    meshes[name] = (om.MDagPath(path), face_ids)
                elif meshes[name][1] is not None:
                    meshes[name][1].update(face_ids)
            else:
                found = list(_mesh_paths(path))
                if not found:
                    ignored.append(item)
                for mesh in found:
                    meshes[mesh.fullPathName()] = (mesh, None)
        except (RuntimeError, TypeError, ValueError):
            ignored.append(item)

    shading_engines, materials, unsupported = set(), set(), set()
    for path, face_ids in meshes.values():
        engines, assignments = om.MFnMesh(path).getConnectedShaders(path.instanceNumber())
        indices = set(assignments) if face_ids is None else {assignments[i] for i in face_ids}
        for index in indices:
            if index >= 0:
                shading_engines.add(om.MFnDependencyNode(engines[index]).name())
    for engine in sorted(shading_engines):
        sources = cmds.listConnections(engine + ".surfaceShader", source=True, destination=False) or []
        for shader in sources:
            if cmds.nodeType(shader) == NODE_TYPE:
                materials.add(shader)
            else:
                unsupported.add(shader)
    return {"meshes": sorted(meshes), "materials": sorted(materials),
            "unsupported": sorted(unsupported), "ignored": ignored}


def _validate(settings, specs):
    """Validate the entire request before editing any material."""
    values = {}
    for attr, value in settings.items():
        if attr not in specs:
            raise ValueError("Unsupported aiStandardSurface setting: " + attr)
        spec = specs[attr]
        kind = spec["kind"]
        if kind in ("color", "vector"):
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                raise ValueError(attr + " requires three numeric values.")
            if any(not isinstance(v, numbers.Real) or not math.isfinite(v) for v in value):
                raise ValueError(attr + " requires three finite numbers.")
            values[attr] = tuple(float(v) for v in value)
            continue
        if kind == "enum" and isinstance(value, str):
            choices = dict(spec["items"])
            if value not in choices:
                raise ValueError("Invalid choice for " + attr + ": " + value)
            value = choices[value]
        if not isinstance(value, numbers.Real) or not math.isfinite(value):
            raise ValueError(attr + " requires a finite number.")
        if kind in ("bool", "int", "enum") and int(value) != value:
            raise ValueError(attr + " requires an integer value.")
        if kind == "bool" and value not in (0, 1):
            raise ValueError(attr + " requires True or False.")
        if kind == "enum" and value not in {n for _, n in spec["items"]}:
            raise ValueError("Invalid enum value for " + attr)
        if ("min" in spec and value < spec["min"]) or ("max" in spec and value > spec["max"]):
            raise ValueError(attr + " is outside the installed shader's allowed range.")
        values[attr] = int(value) if kind in ("bool", "int", "enum") else float(value)
    return values


def _related_plugs(shader, attr):
    return [shader + "." + a for a in [attr] +
            (cmds.attributeQuery(attr, node=shader, listChildren=True) or [])]


def _incoming(plugs):
    # MPlug.connectedTo returns actual connections, including child-channel
    # inputs, without treating a compound's inherited child input as a new wire.
    pairs = set()
    for name in plugs:
        selection = om.MSelectionList()
        selection.add(name)
        destination = selection.getPlug(0)
        for source in destination.connectedTo(True, False):
            pairs.add((source.name(), destination.name()))
    return sorted(pairs)


def _set_value(plug, value, spec):
    if spec["kind"] in ("color", "vector"):
        cmds.setAttr(plug, *value, type=spec["type"])
    else:
        cmds.setAttr(plug, value)


def apply_settings(settings, selection=None, disconnect_inputs=False):
    """Apply a {MtoA_attribute: value} mapping; return a detailed result dict.

    Each unique assigned material is edited once. Shared materials remain
    shared, so unselected users of that material also see the new values.
    Locked/referenced attributes are skipped. Inputs are only disconnected
    when explicitly requested. Successful changes form one Maya undo step.
    """
    specs = attribute_specs()
    values = _validate(settings, specs)
    result = discover_materials(selection)
    result.update(changed=[], skipped=[], rollback_errors=[])
    if not values or not result["materials"]:
        return result
    cmds.undoInfo(openChunk=True, chunkName="Arnold Bulk Material Edit")
    try:
        for shader in result["materials"]:
            referenced = cmds.referenceQuery(shader, isNodeReferenced=True)
            node_locked = any(cmds.lockNode(shader, query=True, lock=True))
            for attr, value in values.items():
                plug = shader + "." + attr
                reason = None
                if referenced:
                    reason = "referenced material"
                elif node_locked:
                    reason = "locked material"
                elif not cmds.objExists(plug):
                    reason = "attribute unavailable"
                else:
                    plugs = _related_plugs(shader, attr)
                    if any(cmds.getAttr(p, lock=True) for p in plugs):
                        reason = "locked attribute/channel"
                    else:
                        wires = _incoming(plugs)
                        if wires and not disconnect_inputs:
                            reason = "connected input (preserved)"
                if reason:
                    result["skipped"].append({"plug": plug, "reason": reason})
                    continue
                old = cmds.getAttr(plug)
                old = old[0] if specs[attr]["kind"] in ("color", "vector") else old
                disconnected = []
                try:
                    for source, destination in wires:
                        cmds.disconnectAttr(source, destination)
                        disconnected.append((source, destination))
                    _set_value(plug, value, specs[attr])
                    result["changed"].append(plug)
                except RuntimeError as exc:
                    # Restore this attribute's value and original wires if a
                    # disconnect or write fails; keep other successful edits.
                    try:
                        if len(disconnected) == len(wires):
                            _set_value(plug, old, specs[attr])
                    except RuntimeError as restore_exc:
                        result["rollback_errors"].append(str(restore_exc))
                    for source, destination in disconnected:
                        try:
                            cmds.connectAttr(source, destination)
                        except RuntimeError as restore_exc:
                            result["rollback_errors"].append(str(restore_exc))
                    result["skipped"].append({"plug": plug, "reason": str(exc)})
    finally:
        cmds.undoInfo(closeChunk=True)
    return result


class BulkMaterialEditor:
    def __init__(self):
        self.specs = attribute_specs()
        self.controls = {}
        if cmds.window(WINDOW, exists=True):
            cmds.deleteUI(WINDOW)
        self.window = cmds.window(WINDOW, title="Arnold | Bulk Material Editor",
                                  widthHeight=(620, 820), sizeable=True)
        form = cmds.formLayout()
        top = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        cmds.text(label="Edit aiStandardSurface materials on selected meshes / groups / faces.", align="left")
        cmds.text(label="Shared materials also change on unselected objects using them.", align="left")
        self.targets_label = cmds.text(label="", align="left")
        self.targets = cmds.textScrollList(height=66, allowMultiSelection=False)
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=2, columnWidth2=(180, 390))
        cmds.button(label="Refresh current selection", command=self.refresh)
        cmds.button(label="Load values from highlighted material", command=self.load_values)
        cmds.setParent(top)
        cmds.text(label="Check the left box beside each setting to apply it. Unchecked settings stay as they are.", align="left")
        cmds.setParent(form)
        scroll = cmds.scrollLayout(childResizable=True)
        column = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        for section, attributes in SECTIONS:
            available = [(a, label) for a, label in attributes if a in self.specs]
            if not available:
                continue
            frame = cmds.frameLayout(label=section, collapsable=True,
                                     collapse=section not in ("Base", "Specular"), marginWidth=6)
            cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
            for attr, label in available:
                self._make_row(attr, label)
            cmds.setParent(column)
        cmds.setParent(form)
        bottom = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        self.disconnect = cmds.checkBox(label="Replace connected inputs on checked settings (disconnect textures / animation)", value=False)
        cmds.text(label="Locked and referenced materials are skipped. Apply uses the current selection.", align="left")
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnWidth2=(440, 150))
        cmds.button(label="Apply checked settings to selected meshes", height=34,
                    backgroundColor=(0.24, 0.43, 0.47), command=self.apply)
        cmds.button(label="Clear checks", command=self.clear_checks)
        cmds.setParent(bottom)
        self.report = cmds.scrollField(editable=False, wordWrap=True, height=92,
                                       text="Ready. Apply is one undo step when Maya undo is enabled.")
        cmds.formLayout(form, edit=True,
                        attachForm=[(top, "top", 8), (top, "left", 8), (top, "right", 8),
                                    (scroll, "left", 8), (scroll, "right", 8),
                                    (bottom, "left", 8), (bottom, "right", 8), (bottom, "bottom", 8)],
                        attachControl=[(scroll, "top", 8, top), (scroll, "bottom", 8, bottom)])
        self.refresh()
        cmds.showWindow(self.window)

    def _make_row(self, attr, label):
        spec = self.specs[attr]
        row = cmds.rowLayout(numberOfColumns=2, adjustableColumn=2, columnWidth2=(26, 530))
        check = cmds.checkBox(label="", value=False, annotation="Apply " + attr)
        kind, default = spec["kind"], spec["default"]
        common = dict(label=label, enable=False, annotation=attr, columnWidth2=(150, 240))
        if kind == "color":
            field = cmds.colorSliderGrp(rgbValue=default, **common)
        elif kind == "vector":
            field = cmds.floatFieldGrp(numberOfFields=3, value1=default[0], value2=default[1],
                                      value3=default[2], precision=4, **common)
        elif kind == "bool":
            field = cmds.checkBox(label=label, value=bool(default), enable=False, annotation=attr)
        elif kind == "enum":
            field = cmds.optionMenuGrp(**common)
            for text, _ in spec["items"]:
                cmds.menuItem(label=text)
            position = next(i for i, (_, number) in enumerate(spec["items"], 1) if number == default)
            cmds.optionMenuGrp(field, edit=True, select=position)
        else:
            options = dict(numberOfFields=1, value1=default, **common)
            if kind == "int":
                options["value1"] = int(default)
                field = cmds.intFieldGrp(**options)
            else:
                field = cmds.floatFieldGrp(precision=4, **options)
        cmds.checkBox(check, edit=True, changeCommand=partial(self._enable, field))
        self.controls[attr] = (check, field)
        cmds.setParent(row)
        cmds.setParent("..")

    @staticmethod
    def _enable(field, value):
        cmds.control(field, edit=True, enable=value)

    def refresh(self, *_):
        targets = discover_materials()
        cmds.textScrollList(self.targets, edit=True, removeAll=True)
        if targets["materials"]:
            cmds.textScrollList(self.targets, edit=True, append=targets["materials"], selectIndexedItem=1)
        cmds.text(self.targets_label, edit=True, label="{} mesh path(s) | {} Arnold material(s) | {} other surface shader(s) skipped".format(
            len(targets["meshes"]), len(targets["materials"]), len(targets["unsupported"])))
        return targets

    def clear_checks(self, *_):
        for check, field in self.controls.values():
            cmds.checkBox(check, edit=True, value=False)
            self._enable(field, False)

    def load_values(self, *_):
        selected = cmds.textScrollList(self.targets, query=True, selectItem=True) or []
        if not selected or not cmds.objExists(selected[0]):
            cmds.warning("Refresh and highlight an Arnold material first.")
            return
        shader = selected[0]
        for attr, (_, field) in self.controls.items():
            value = cmds.getAttr(shader + "." + attr)
            kind = self.specs[attr]["kind"]
            if kind == "color":
                cmds.colorSliderGrp(field, edit=True, rgbValue=value[0])
            elif kind == "vector":
                cmds.floatFieldGrp(field, edit=True, value1=value[0][0], value2=value[0][1], value3=value[0][2])
            elif kind == "enum":
                position = next(i for i, (_, n) in enumerate(self.specs[attr]["items"], 1) if n == value)
                cmds.optionMenuGrp(field, edit=True, select=position)
            elif kind == "bool":
                cmds.checkBox(field, edit=True, value=value)
            elif kind == "int":
                cmds.intFieldGrp(field, edit=True, value1=value)
            else:
                cmds.floatFieldGrp(field, edit=True, value1=value)
        cmds.scrollField(self.report, edit=True, text="Loaded values from {}. Checks are unchanged.".format(shader))

    def _value(self, attr):
        field = self.controls[attr][1]
        kind = self.specs[attr]["kind"]
        if kind == "color":
            return cmds.colorSliderGrp(field, query=True, rgbValue=True)
        if kind == "vector":
            return [cmds.floatFieldGrp(field, query=True, **{flag: True})
                    for flag in ("value1", "value2", "value3")]
        if kind == "bool":
            return cmds.checkBox(field, query=True, value=True)
        if kind == "enum":
            index = cmds.optionMenuGrp(field, query=True, select=True) - 1
            return self.specs[attr]["items"][index][1]
        if kind == "int":
            return cmds.intFieldGrp(field, query=True, value1=True)
        return cmds.floatFieldGrp(field, query=True, value1=True)

    def apply(self, *_):
        settings = {a: self._value(a) for a, (check, _) in self.controls.items()
                    if cmds.checkBox(check, query=True, value=True)}
        if not settings:
            cmds.warning("Check at least one setting to apply.")
            return
        try:
            result = apply_settings(settings, disconnect_inputs=cmds.checkBox(self.disconnect, query=True, value=True))
        except (ValueError, RuntimeError) as exc:
            cmds.scrollField(self.report, edit=True, text=str(exc))
            cmds.warning(str(exc))
            return
        self.refresh()
        material_count = len({p.rsplit(".", 1)[0] for p in result["changed"]})
        lines = ["Updated {} setting(s) on {} material(s); skipped {}.".format(
            len(result["changed"]), material_count, len(result["skipped"]))]
        if not result["materials"]:
            lines.append("No directly assigned aiStandardSurface materials found. Select meshes and refresh.")
        lines.extend("Skipped {}: {}".format(s["plug"], s["reason"]) for s in result["skipped"])
        lines.extend("Other surface shader: " + s for s in result["unsupported"])
        lines.extend("Ignored selection: " + s for s in result["ignored"])
        lines.extend("RESTORE FAILED: " + s for s in result["rollback_errors"])
        message = "\n".join(lines)
        cmds.scrollField(self.report, edit=True, text=message)
        print("[Arnold Bulk Editor]\n" + message)


_editor = None


def show():
    """Open (or replace) the editor window."""
    global _editor
    _editor = BulkMaterialEditor()
    return _editor


if __name__ == "__main__":
    show()
