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
    Uses aiStandardHair (better defaults for hair/curves).
    Returns the shader node name.
    """
    if not cmds.objExists(shader_name):
        try:
            shader = cmds.shadingNode("aiStandardHair", asShader=True, name=shader_name)
        except Exception:
            # Fallback to aiStandardSurface if aiStandardHair not available
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

        # connect shader.message -> slot
        try:
            cmds.connectAttr(f"{shader}.message", slot_attr, f=True)
            connected += 1
        except Exception:
            # some very old setups accepted outColor (rare)
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
        self.chk_render = QtWidgets.QCheckBox("Enable Arnold: Render Curve on all curve shapes")
        self.chk_render.setChecked(True)

        self.ed_shader_label = QtWidgets.QLabel("Curve Shader name:")
        self.ed_shader = QtWidgets.QLineEdit("curve_shader")

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
        self.btn_apply   = QtWidgets.QPushButton("Apply to All Curves")

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)

        # Layout
        form = QtWidgets.QFormLayout()
        form.addRow(self.chk_render)
        form.addRow(self.ed_shader_label, self.ed_shader)
        form.addRow(self.spin_samples_label, self.spin_samples)
        form.addRow(self.spin_width_label, self.spin_width)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.btn_refresh)
        row.addWidget(self.btn_select)
        row.addWidget(self.btn_apply)

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(row)
        root.addWidget(self.status)

        # Signals
        self.btn_refresh.clicked.connect(self.update_status)
        self.btn_select.clicked.connect(self.select_all_curves)
        self.btn_apply.clicked.connect(self.apply_all)

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

    def apply_all(self):
        curves = list_curve_shapes()
        if not curves:
            self.status.setText("No curve shapes found in the scene.")
            return

        shader_name = (self.ed_shader.text() or "curve_shader").strip()
        shader = ensure_curve_shader(shader_name)

        # Connect shader to Curve Shader slot
        n_connected = connect_shader_to_curve_slot(curves, shader)

        # Set Arnold curve attributes
        render_on = self.chk_render.isChecked()
        samples = self.spin_samples.value()
        width = self.spin_width.value()
        set_curve_render_attrs(curves, render_on, samples, width)

        self.status.setText(
            f'Applied to {len(curves)} curve(s): '
            f'RenderCurve={render_on} | SampleRate={samples} | Width={width} | '
            f'CurveShader="{shader_name}" (connected on {n_connected} shape(s))'
        )

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
