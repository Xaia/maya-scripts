# Maya + Arnold (MtoA) — Curves Utility UI
# - Toggle "Render Curve" on all NURBS curve shapes
# - Assign "curve_shader" into the Curve Shader slot (message connection)
# - Set Sample Rate and Curve Width (defaults 50 / 0.3)
# Works on typical MtoA attribute names; tries fallbacks where needed.

from maya import cmds
from maya import OpenMayaUI as omui

# PySide2 ships with Maya 2017+
from shiboken2 import wrapInstance
from PySide2 import QtWidgets, QtCore

WINDOW_TITLE = "Arnold Curves Tool"

# ---------- core helpers ----------

def get_maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)

def get_base_name(name):
    """Get base name by removing trailing digits and common suffixes like _crv."""
    import re
    # Remove common curve suffixes first
    name = re.sub(r'_(crv|curve|shape)(\d*)$', '', name, flags=re.IGNORECASE)
    # Remove trailing digits
    name = re.sub(r'_?\d+$', '', name)
    return name

def list_curve_shapes():
    """Return unique NURBS curve shapes (non-intermediate) as long names."""
    shapes = cmds.ls(type="nurbsCurve", long=True) or []
    out = []
    for s in shapes:
        try:
            if cmds.attributeQuery("intermediateObject", node=s, exists=True):
                if cmds.getAttr(s + ".intermediateObject"):
                    continue
        except Exception:
            pass
        out.append(s)
    # unique while preserving order
    seen = set()
    uniq = []
    for s in out:
        if s not in seen:
            uniq.append(s)
            seen.add(s)
    return uniq

def ensure_curve_shader(shader_name="curve_shader"):
    """
    Ensure a shader node exists for the Curve Shader slot.
    Uses aiStandardSurface for curves.
    Returns the shader node name.
    """
    if not cmds.objExists(shader_name):
        shader = cmds.shadingNode("aiStandardSurface", asShader=True, name=shader_name)
    else:
        shader = shader_name
    return shader

def connect_shader_to_curve_slot(curve_shapes, shader):
    """
    Connect shader.message -> curveShape.aiCurveShader (or variants).
    This is NOT a shadingGroup assignment; it's a message connection used by Arnold.
    """
    if not curve_shapes:
        return 0

    slot_variants = ["aiCurveShader", "aiHairShader", "aiCurveMat", "aiCurveMaterial"]

    connected = 0
    for shape in curve_shapes:
        # find a valid slot attribute on this shape
        slot_attr = None
        for a in slot_variants:
            if cmds.attributeQuery(a, node=shape, exists=True):
                slot_attr = f"{shape}.{a}"
                break
        if not slot_attr:
            continue

        # break existing input connections
        try:
            incoming = cmds.listConnections(slot_attr, plugs=True, s=True, d=False) or []
            for src in incoming:
                try:
                    cmds.disconnectAttr(src, slot_attr)
                except Exception:
                    pass
        except Exception:
            pass

        # connect shader.outColor -> slot
        try:
            cmds.connectAttr(f"{shader}.outColor", slot_attr, f=True)
            connected += 1
        except Exception:
            pass
    return connected

def safe_set_attr(node, attr, value):
    """Set attribute if it exists; returns True on success, False otherwise."""
    if not cmds.objExists(node):
        return False
    if not cmds.attributeQuery(attr, node=node, exists=True):
        return False
    try:
        if isinstance(value, bool):
            cmds.setAttr(f"{node}.{attr}", int(value))
        elif isinstance(value, (tuple, list)) and len(value) == 3:
            # Handle color attributes (RGB)
            cmds.setAttr(f"{node}.{attr}", value[0], value[1], value[2], type="double3")
        else:
            cmds.setAttr(f"{node}.{attr}", value)
        return True
    except Exception:
        return False

def set_curve_render_attrs(curve_shapes, render_curve, sample_rate, curve_width):
    """
    Apply Arnold curve attributes to shapes. Tries common MtoA variants.
    """
    render_variants = ["aiRenderCurve", "aiRenderableCurves", "aiRenderAsCurves"]
    sample_variants = ["aiSampleRate", "aiCurveSampleRate", "aiCurveSamples"]
    width_variants  = ["aiCurveWidth", "aiWidth", "aiHairWidth"]

    for s in curve_shapes:
        # Render Curve toggle
        for a in render_variants:
            if safe_set_attr(s, a, bool(render_curve)):
                break
        # Sample Rate
        for a in sample_variants:
            if safe_set_attr(s, a, int(sample_rate)):
                break
        # Curve Width
        for a in width_variants:
            if safe_set_attr(s, a, float(curve_width)):
                break

# ---------- UI ----------

class ArnoldCurvesTool(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(ArnoldCurvesTool, self).__init__(parent or get_maya_main_window())
        self.setObjectName(WINDOW_TITLE.replace(" ", "_"))
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumWidth(360)
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)

        # Controls
        self.chk_render = QtWidgets.QCheckBox("Enable Arnold: Render Curve")
        self.chk_render.setChecked(True)

        self.chk_assign_shader = QtWidgets.QCheckBox("Assign Shader")
        self.chk_assign_shader.setChecked(True)

        self.rb_same = QtWidgets.QRadioButton("All same shader")
        self.rb_similar = QtWidgets.QRadioButton("Per similar name")
        self.rb_group = QtWidgets.QRadioButton("Per group")
        self.rb_similar.setChecked(True)

        self.spin_samples_label = QtWidgets.QLabel("Sample Rate:")
        self.spin_samples = QtWidgets.QSpinBox()
        self.spin_samples.setRange(1, 8192)
        self.spin_samples.setValue(50)

        self.spin_width_label = QtWidgets.QLabel("Curve Width:")
        self.spin_width = QtWidgets.QDoubleSpinBox()
        self.spin_width.setRange(0.0, 1000.0)
        self.spin_width.setDecimals(4)
        self.spin_width.setSingleStep(0.01)
        self.spin_width.setValue(0.3)

        self.btn_refresh = QtWidgets.QPushButton("Refresh Count")
        self.btn_select  = QtWidgets.QPushButton("Select All Curves")
        self.btn_apply_all   = QtWidgets.QPushButton("Apply to All")
        self.btn_apply_selected = QtWidgets.QPushButton("Apply to Selected")

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)

        # Layout
        form = QtWidgets.QFormLayout()
        form.addRow(self.chk_render)
        form.addRow(self.chk_assign_shader)
        form.addRow(self.rb_same)
        form.addRow(self.rb_similar)
        form.addRow(self.rb_group)
        form.addRow(self.spin_samples_label, self.spin_samples)
        form.addRow(self.spin_width_label, self.spin_width)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.btn_refresh)
        row.addWidget(self.btn_select)
        row.addWidget(self.btn_apply_all)
        row.addWidget(self.btn_apply_selected)

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(row)
        root.addWidget(self.status)

        # Signals
        self.btn_refresh.clicked.connect(self.update_status)
        self.btn_select.clicked.connect(self.select_all_curves)
        self.btn_apply_all.clicked.connect(self.apply_all)
        self.btn_apply_selected.clicked.connect(self.apply_selected)

        self.update_status()

    # ---- actions ----

    def update_status(self):
        curves = list_curve_shapes()
        self.status.setText(f"Found {len(curves)} curve shape(s).")

    def select_all_curves(self):
        curves = list_curve_shapes()
        if curves:
            cmds.select(curves, r=True)
        self.update_status()

    def apply_curves(self, curves):
        if not curves:
            self.status.setText("No curve shapes found.")
            return

        # Determine grouping
        if self.rb_same.isChecked():
            # For "all same shader", use a generic name
            groups = {"curve_shader": curves}
        else:
            from collections import defaultdict
            groups = defaultdict(list)
            for c in curves:
                if self.rb_similar.isChecked():
                    # Get the parent transform's name for grouping
                    parent = cmds.listRelatives(c, parent=True, fullPath=True)
                    if parent:
                        parent_short = cmds.ls(parent[0], shortNames=True)[0]
                        key = get_base_name(parent_short)
                    else:
                        # Fallback to shape name if no parent
                        short_name = cmds.ls(c, shortNames=True)[0]
                        key = get_base_name(short_name)
                    if not key:  # if name is only digits
                        key = parent_short if parent else short_name
                elif self.rb_group.isChecked():
                    # Get the parent of the curve transform (the group)
                    transform_parent = cmds.listRelatives(c, parent=True, fullPath=True)
                    if transform_parent:
                        group_parent = cmds.listRelatives(transform_parent[0], parent=True, fullPath=True)
                        if group_parent:
                            # Use the group's full path to ensure unique grouping
                            key = group_parent[0]
                        else:
                            # The transform itself is the top-level group
                            key = transform_parent[0]
                    else:
                        key = "root"
                groups[key].append(c)

        total_connected = 0
        shader_names = []
        
        # Only create/assign shaders if checkbox is enabled
        if self.chk_assign_shader.isChecked():
            for group_name, group_curves in groups.items():
                # Extract clean name for shader
                if self.rb_group.isChecked() and "|" in group_name:
                    # For full paths, get the short name (don't remove digits for groups)
                    short_name = cmds.ls(group_name, shortNames=True)[0]
                    clean_name = short_name
                elif self.rb_similar.isChecked():
                    # For similar names, the key is already clean
                    clean_name = group_name
                else:
                    clean_name = group_name
                
                shader_name = clean_name + "_shader"
                shader = ensure_curve_shader(shader_name)
                shader_names.append(shader_name)

                # Set emission to 1.0 and random bright emission color
                import random
                safe_set_attr(shader, "emission", 1.0)
                safe_set_attr(shader, "specular", 0.0)
                
                # Generate highly saturated colors by ensuring at least one channel is at max
                # and others vary, avoiding muddy middle-range colors
                color_choice = random.randint(0, 2)  # Which channel to max out
                colors = [0, 0, 0]
                
                # Set the dominant channel to full
                colors[color_choice] = 1.0
                
                # Set other channels to create variety (lower values for saturation)
                for i in range(3):
                    if i != color_choice:
                        colors[i] = random.uniform(0.0, 0.6)
                
                r, g, b = colors
                
                # Set emission color (not base color)
                safe_set_attr(shader, "emissionColor", (r, g, b))

                # Connect shader (this will overwrite existing connections)
                n_connected = connect_shader_to_curve_slot(group_curves, shader)
                total_connected += n_connected

        # Set Arnold curve attributes to all curves
        render_on = self.chk_render.isChecked()
        samples = self.spin_samples.value()
        width = self.spin_width.value()
        set_curve_render_attrs(curves, render_on, samples, width)

        status_msg = f'Applied to {len(curves)} curve(s) in {len(groups)} group(s): '
        status_msg += f'RenderCurve={render_on} | SampleRate={samples} | Width={width}'
        if self.chk_assign_shader.isChecked() and shader_names:
            status_msg += f' | Shaders: {", ".join(shader_names)} (connected on {total_connected} shape(s))'
        
        self.status.setText(status_msg)

    def apply_all(self):
        curves = list_curve_shapes()
        self.apply_curves(curves)

    def apply_selected(self):
        # Get all selected objects and find their curve shapes
        selected = cmds.ls(selection=True, long=True) or []
        curves = []
        
        for obj in selected:
            # Check if selected object is a transform
            if cmds.nodeType(obj) == "transform":
                # Get curve shapes under this transform
                shapes = cmds.listRelatives(obj, shapes=True, type="nurbsCurve", fullPath=True) or []
                for s in shapes:
                    try:
                        if cmds.attributeQuery("intermediateObject", node=s, exists=True):
                            if cmds.getAttr(s + ".intermediateObject"):
                                continue
                    except Exception:
                        pass
                    curves.append(s)
            # Check if selected object is already a curve shape
            elif cmds.nodeType(obj) == "nurbsCurve":
                try:
                    if cmds.attributeQuery("intermediateObject", node=obj, exists=True):
                        if cmds.getAttr(obj + ".intermediateObject"):
                            continue
                except Exception:
                    pass
                curves.append(obj)
        
        self.apply_curves(curves)

# ---------- launcher ----------

def show_arnold_curves_tool():
    # Close previous instance if open
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == WINDOW_TITLE.replace(" ", "_"):
            try:
                w.close()
                w.deleteLater()
            except Exception:
                pass
    dlg = ArnoldCurvesTool()
    dlg.show()
    return dlg

# Launch UI
show_arnold_curves_tool()
