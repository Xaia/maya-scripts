# ============================================================
# Maya Framing Window
# ------------------------------------------------------------
# Non-destructive viewport framing overlay.
#
# - Uses Maya's current render resolution / device aspect ratio
# - Draws alternate framing ratios inside that render frame
# - Does NOT modify camera, render resolution, or film settings
# - Supports Maya with PySide2 or PySide6
#
# Run:
#     show_framing_window()
# ============================================================

import math

import maya.cmds as cmds
import maya.OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
    PYSIDE_VERSION = 6
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
    PYSIDE_VERSION = 2


# ============================================================
# Qt compatibility
# ============================================================

def _qt_attr(name):
    """Return Qt enum compatible with PySide2/PySide6."""
    if hasattr(QtCore.Qt, name):
        return getattr(QtCore.Qt, name)

    enum_groups = [
        "WidgetAttribute",
        "WindowType",
        "PenStyle",
        "AlignmentFlag",
        "Orientation",
    ]

    for group in enum_groups:
        enum_obj = getattr(QtCore.Qt, group, None)
        if enum_obj and hasattr(enum_obj, name):
            return getattr(enum_obj, name)

    return None


WA_TRANSPARENT_MOUSE = _qt_attr("WA_TransparentForMouseEvents")
WA_TRANSLUCENT = _qt_attr("WA_TranslucentBackground")
WA_NO_SYSTEM_BG = _qt_attr("WA_NoSystemBackground")
WA_DELETE_ON_CLOSE = _qt_attr("WA_DeleteOnClose")
TOOL_WINDOW = _qt_attr("Tool")
DASH_LINE = _qt_attr("DashLine")
SOLID_LINE = _qt_attr("SolidLine")
HORIZONTAL = _qt_attr("Horizontal")


# ============================================================
# Maya helpers
# ============================================================

def get_maya_main_window():
    ptr = omui.MQtUtil.mainWindow()

    if ptr:
        return wrapInstance(int(ptr), QtWidgets.QWidget)

    return None


def get_active_model_panel():
    """
    Try to determine the most appropriate modelPanel.
    """

    panel = cmds.getPanel(withFocus=True)

    if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
        return panel

    panel = cmds.getPanel(underPointer=True)

    if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
        return panel

    visible = cmds.getPanel(visiblePanels=True) or []

    for p in visible:
        if cmds.getPanel(typeOf=p) == "modelPanel":
            return p

    panels = cmds.getPanel(type="modelPanel") or []

    if panels:
        return panels[0]

    return None


def get_viewport_widget(panel):
    """
    Get the actual Qt viewport widget for a Maya modelPanel.
    """

    if not panel:
        return None

    # Best method: get the M3dView's actual QWidget.
    try:
        view = omui.M3dView.getM3dViewFromModelPanel(panel)
        ptr = view.widget()

        if ptr:
            return wrapInstance(int(ptr), QtWidgets.QWidget)

    except Exception:
        pass

    # Fallback.
    try:
        ptr = omui.MQtUtil.findControl(panel)

        if ptr:
            return wrapInstance(int(ptr), QtWidgets.QWidget)

    except Exception:
        pass

    return None


def get_panel_camera(panel):
    if not panel:
        return None, None

    try:
        camera = cmds.modelPanel(panel, q=True, camera=True)
    except Exception:
        return None, None

    if not camera:
        return None, None

    if cmds.nodeType(camera) == "camera":
        camera_shape = camera

        parents = cmds.listRelatives(camera_shape, parent=True, fullPath=True)
        camera_transform = parents[0] if parents else camera_shape
    else:
        camera_transform = camera

        shapes = cmds.listRelatives(
            camera_transform,
            shapes=True,
            type="camera",
            fullPath=True
        ) or []

        camera_shape = shapes[0] if shapes else None

    return camera_transform, camera_shape


def get_render_settings():
    """
    Maya's render resolution settings.

    deviceAspectRatio is the important value here because this represents
    the final image/display aspect, including pixel aspect.
    """

    try:
        width = cmds.getAttr("defaultResolution.width")
        height = cmds.getAttr("defaultResolution.height")
        pixel_aspect = cmds.getAttr("defaultResolution.pixelAspect")
        device_aspect = cmds.getAttr(
            "defaultResolution.deviceAspectRatio"
        )
    except Exception:
        width = 1920
        height = 1080
        pixel_aspect = 1.0
        device_aspect = float(width) / float(height)

    # Safety fallback.
    if not device_aspect or device_aspect <= 0:
        device_aspect = (
            float(width) * float(pixel_aspect)
        ) / max(float(height), 1.0)

    return {
        "width": width,
        "height": height,
        "pixel_aspect": pixel_aspect,
        "device_aspect": device_aspect,
    }


# ============================================================
# Overlay widget
# ============================================================

class FramingOverlay(QtWidgets.QWidget):

    def __init__(self, viewport):
        # IMPORTANT:
        # Do NOT parent this widget to the Maya viewport.
        # It needs to be a top-level transparent window so Windows
        # composites it correctly over Viewport 2.0.
        super(FramingOverlay, self).__init__(None)

        self.viewport = viewport

        self.target_aspect = 2.39
        self.use_render_aspect = False

        self.mask_enabled = True
        self.mask_opacity = 155

        self.mask_render_outside = False
        self.render_mask_opacity = 100

        self.show_render_gate = True
        self.show_target_border = True

        self.show_thirds = False
        self.show_center = False
        self.show_golden_grid = False
        self.show_golden_spiral = False
        self.show_golden_triangles = False
        self.show_diagonal_method = False
        self.show_action_safe = False
        self.show_title_safe = False

        self.line_width = 2

        self.render_gate_color = QtGui.QColor(120, 180, 255, 210)
        self.target_color = QtGui.QColor(255, 210, 70, 255)
        self.guide_color = QtGui.QColor(255, 255, 255, 130)

        # ----------------------------------------------------
        # Transparent top-level overlay
        # ----------------------------------------------------

        flags = (
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Tool |
            QtCore.Qt.WindowStaysOnTopHint
        )

        # Qt6 / newer Qt5:
        try:
            flags |= QtCore.Qt.WindowTransparentForInput
        except AttributeError:
            pass

        self.setWindowFlags(flags)

        self.setAttribute(
            QtCore.Qt.WA_TranslucentBackground,
            True
        )

        self.setAttribute(
            QtCore.Qt.WA_NoSystemBackground,
            True
        )

        self.setAttribute(
            QtCore.Qt.WA_TransparentForMouseEvents,
            True
        )

        self.setAutoFillBackground(False)

        # Explicit transparent stylesheet helps avoid Maya/Qt
        # applying a palette background.
        self.setStyleSheet(
            "background: transparent;"
        )

        self.sync_geometry()

        self.show()
        self.raise_()

    # --------------------------------------------------------

    def sync_geometry(self):
        """
        Match the overlay window to the viewport's global screen
        position and dimensions.
        """

        if not self.viewport:
            return

        try:
            top_left = self.viewport.mapToGlobal(
                QtCore.QPoint(0, 0)
            )

            size = self.viewport.size()

            self.setGeometry(
                top_left.x(),
                top_left.y(),
                size.width(),
                size.height()
            )

            self.raise_()
            self.update()

        except RuntimeError:
            pass

    # --------------------------------------------------------

    def get_camera_overscan(self):

        panel = getattr(self, "_panel", None)

        if not panel:
            panel = get_active_model_panel()

        _, camera_shape = get_panel_camera(panel)

        if not camera_shape:
            return 1.0

        try:
            overscan = cmds.getAttr(
                camera_shape + ".overscan"
            )

            if overscan <= 0:
                return 1.0

            return float(overscan)

        except Exception:
            return 1.0

    # --------------------------------------------------------

    def calculate_render_gate(self):

        settings = get_render_settings()

        render_aspect = settings["device_aspect"]

        vw = float(self.width())
        vh = float(self.height())

        if vw <= 1 or vh <= 1:
            return QtCore.QRectF()

        viewport_aspect = vw / vh

        if viewport_aspect >= render_aspect:

            gate_h = vh
            gate_w = gate_h * render_aspect

        else:

            gate_w = vw
            gate_h = gate_w / render_aspect

        overscan = self.get_camera_overscan()

        gate_w /= overscan
        gate_h /= overscan

        x = (vw - gate_w) * 0.5
        y = (vh - gate_h) * 0.5

        return QtCore.QRectF(
            x,
            y,
            gate_w,
            gate_h
        )

    # --------------------------------------------------------

    def calculate_target_frame(self, render_rect):

        if render_rect.isNull():
            return render_rect

        settings = get_render_settings()

        if self.use_render_aspect:
            target_aspect = settings["device_aspect"]
        else:
            target_aspect = max(
                float(self.target_aspect),
                0.001
            )

        rw = render_rect.width()
        rh = render_rect.height()

        render_aspect = rw / rh

        if target_aspect >= render_aspect:

            frame_w = rw
            frame_h = frame_w / target_aspect

        else:

            frame_h = rh
            frame_w = frame_h * target_aspect

        x = (
            render_rect.center().x()
            - frame_w * 0.5
        )

        y = (
            render_rect.center().y()
            - frame_h * 0.5
        )

        return QtCore.QRectF(
            x,
            y,
            frame_w,
            frame_h
        )

    # --------------------------------------------------------

    @staticmethod
    def draw_outside_rect(
        painter,
        outer,
        inner,
        color
    ):

        if outer.isNull() or inner.isNull():
            return

        # Top
        painter.fillRect(
            QtCore.QRectF(
                outer.left(),
                outer.top(),
                outer.width(),
                max(
                    0,
                    inner.top() - outer.top()
                )
            ),
            color
        )

        # Bottom
        painter.fillRect(
            QtCore.QRectF(
                outer.left(),
                inner.bottom(),
                outer.width(),
                max(
                    0,
                    outer.bottom() - inner.bottom()
                )
            ),
            color
        )

        # Left
        painter.fillRect(
            QtCore.QRectF(
                outer.left(),
                inner.top(),
                max(
                    0,
                    inner.left() - outer.left()
                ),
                inner.height()
            ),
            color
        )

        # Right
        painter.fillRect(
            QtCore.QRectF(
                inner.right(),
                inner.top(),
                max(
                    0,
                    outer.right() - inner.right()
                ),
                inner.height()
            ),
            color
        )

    # --------------------------------------------------------

    def draw_thirds(self, painter, rect):

        pen = QtGui.QPen(
            self.guide_color
        )

        pen.setWidth(1)

        painter.setPen(pen)

        x1 = rect.left() + rect.width() / 3.0
        x2 = rect.left() + rect.width() * 2.0 / 3.0

        y1 = rect.top() + rect.height() / 3.0
        y2 = rect.top() + rect.height() * 2.0 / 3.0

        painter.drawLine(
            QtCore.QPointF(
                x1,
                rect.top()
            ),
            QtCore.QPointF(
                x1,
                rect.bottom()
            )
        )

        painter.drawLine(
            QtCore.QPointF(
                x2,
                rect.top()
            ),
            QtCore.QPointF(
                x2,
                rect.bottom()
            )
        )

        painter.drawLine(
            QtCore.QPointF(
                rect.left(),
                y1
            ),
            QtCore.QPointF(
                rect.right(),
                y1
            )
        )

        painter.drawLine(
            QtCore.QPointF(
                rect.left(),
                y2
            ),
            QtCore.QPointF(
                rect.right(),
                y2
            )
        )

    # --------------------------------------------------------

    def _guide_pen(self, alpha=130, width=1):
        color = QtGui.QColor(self.guide_color)
        color.setAlpha(alpha)
        pen = QtGui.QPen(color)
        pen.setWidth(width)
        return pen

    def draw_golden_grid(self, painter, rect):
        painter.setPen(self._guide_pen(150))
        golden = 1.0 / ((1.0 + math.sqrt(5.0)) / 2.0)
        for fraction in (1.0 - golden, golden):
            x = rect.left() + rect.width() * fraction
            y = rect.top() + rect.height() * fraction
            painter.drawLine(
                QtCore.QPointF(x, rect.top()),
                QtCore.QPointF(x, rect.bottom())
            )
            painter.drawLine(
                QtCore.QPointF(rect.left(), y),
                QtCore.QPointF(rect.right(), y)
            )

    def draw_diagonal_method(self, painter, rect):
        painter.setPen(self._guide_pen())
        length = min(rect.width(), rect.height())
        for x, x_direction in ((rect.left(), 1), (rect.right(), -1)):
            for y, y_direction in ((rect.top(), 1), (rect.bottom(), -1)):
                painter.drawLine(
                    QtCore.QPointF(x, y),
                    QtCore.QPointF(
                        x + x_direction * length,
                        y + y_direction * length
                    )
                )

    def draw_golden_triangles(self, painter, rect):
        painter.setPen(self._guide_pen(150))
        a = rect.topLeft()
        b = rect.bottomRight()
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        denominator = dx * dx + dy * dy
        if denominator <= 0:
            return
        painter.drawLine(a, b)
        for point in (rect.topRight(), rect.bottomLeft()):
            t = ((point.x() - a.x()) * dx
                 + (point.y() - a.y()) * dy) / denominator
            projection = QtCore.QPointF(a.x() + t * dx, a.y() + t * dy)
            painter.drawLine(point, projection)

    def draw_safe_area(self, painter, rect, scale, alpha=120):
        """Draw a centered safe area as a fraction of each frame dimension."""
        painter.setPen(self._guide_pen(alpha))
        painter.setBrush(QtCore.Qt.NoBrush)
        inset_x = rect.width() * (1.0 - scale) * 0.5
        inset_y = rect.height() * (1.0 - scale) * 0.5
        painter.drawRect(rect.adjusted(inset_x, inset_y, -inset_x, -inset_y))

    def draw_golden_spiral(self, painter, rect):
        """Quarter-circle approximation in nested golden rectangles.

        Build in a golden rectangle, then fit to the selected framing.
        Portrait frames rotate the construction so the first arc follows
        the long dimension. Non-golden framing scales the guide to fit.
        """
        if rect.isEmpty():
            return
        painter.save()
        painter.setClipRect(rect, QtCore.Qt.IntersectClip)
        painter.setPen(self._guide_pen(170))
        painter.setBrush(QtCore.Qt.NoBrush)

        phi = (1.0 + math.sqrt(5.0)) / 2.0
        path = QtGui.QPainterPath()
        x, y, width, height = 0.0, 0.0, phi, 1.0
        for i in range(16):
            direction = i % 4
            if direction == 0:  # Remove the left square.
                side = height
                cx, cy = x + side, y + height
                x += side
                width -= side
            elif direction == 1:  # Remove the top square.
                side = width
                cx, cy = x, y + side
                y += side
                height -= side
            elif direction == 2:  # Remove the right square.
                side = height
                cx, cy = x + width - side, y
                width -= side
            else:
                side = width  # Remove the bottom square.
                cx, cy = x + width, y + height - side
                height -= side
            arc_rect = QtCore.QRectF(cx - side, cy - side, 2 * side, 2 * side)
            start_angle = (180 - direction * 90) % 360
            if i == 0:
                path.arcMoveTo(arc_rect, start_angle)
            path.arcTo(arc_rect, start_angle, -90)

        if rect.width() >= rect.height():
            transform = QtGui.QTransform(
                rect.width() / phi, 0, 0, rect.height(), rect.left(), rect.top()
            )
        else:
            transform = QtGui.QTransform(
                0, -rect.height() / phi, rect.width(), 0, rect.left(), rect.bottom()
            )
        painter.drawPath(transform.map(path))
        painter.restore()

    # --------------------------------------------------------

    def draw_center(self, painter, rect):

        pen = QtGui.QPen(
            self.guide_color
        )

        pen.setWidth(1)

        painter.setPen(pen)

        cx = rect.center().x()
        cy = rect.center().y()

        size = (
            min(
                rect.width(),
                rect.height()
            )
            * 0.03
        )

        painter.drawLine(
            QtCore.QPointF(
                cx - size,
                cy
            ),
            QtCore.QPointF(
                cx + size,
                cy
            )
        )

        painter.drawLine(
            QtCore.QPointF(
                cx,
                cy - size
            ),
            QtCore.QPointF(
                cx,
                cy + size
            )
        )

    # --------------------------------------------------------

    def paintEvent(self, event):

        painter = QtGui.QPainter(self)

        painter.setRenderHint(
            QtGui.QPainter.Antialiasing,
            True
        )

        # Very important.
        # Clear widget completely transparent first.
        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode_Source
        )

        painter.fillRect(
            self.rect(),
            QtGui.QColor(
                0,
                0,
                0,
                0
            )
        )

        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode_SourceOver
        )

        full_rect = QtCore.QRectF(
            self.rect()
        )

        render_rect = (
            self.calculate_render_gate()
        )

        target_rect = (
            self.calculate_target_frame(
                render_rect
            )
        )

        # ----------------------------------------------------
        # Outside actual Maya render gate
        # ----------------------------------------------------

        if self.mask_render_outside:

            outside_color = QtGui.QColor(
                0,
                0,
                0,
                self.render_mask_opacity
            )

            self.draw_outside_rect(
                painter,
                full_rect,
                render_rect,
                outside_color
            )

        # ----------------------------------------------------
        # Framing matte
        # ----------------------------------------------------

        if self.mask_enabled:

            mask_color = QtGui.QColor(
                0,
                0,
                0,
                self.mask_opacity
            )

            self.draw_outside_rect(
                painter,
                render_rect,
                target_rect,
                mask_color
            )

        # ----------------------------------------------------
        # Maya render gate
        # ----------------------------------------------------

        if self.show_render_gate:

            render_pen = QtGui.QPen(
                self.render_gate_color
            )

            render_pen.setWidth(1)

            try:
                render_pen.setStyle(
                    QtCore.Qt.DashLine
                )
            except Exception:
                pass

            painter.setPen(render_pen)

            painter.setBrush(
                QtCore.Qt.NoBrush
            )

            painter.drawRect(
                render_rect
            )

        # ----------------------------------------------------
        # Framing border
        # ----------------------------------------------------

        if self.show_target_border:

            target_pen = QtGui.QPen(
                self.target_color
            )

            target_pen.setWidth(
                self.line_width
            )

            painter.setPen(
                target_pen
            )

            painter.setBrush(
                QtCore.Qt.NoBrush
            )

            painter.drawRect(
                target_rect
            )

        # ----------------------------------------------------
        # Composition guides
        # ----------------------------------------------------

        painter.save()
        painter.setClipRect(target_rect, QtCore.Qt.IntersectClip)

        if self.show_thirds:

            self.draw_thirds(
                painter,
                target_rect
            )

        if self.show_center:

            self.draw_center(
                painter,
                target_rect
            )

        if self.show_golden_grid:
            self.draw_golden_grid(painter, target_rect)
        if self.show_golden_spiral:
            self.draw_golden_spiral(painter, target_rect)
        if self.show_golden_triangles:
            self.draw_golden_triangles(painter, target_rect)
        if self.show_diagonal_method:
            self.draw_diagonal_method(painter, target_rect)
        if self.show_action_safe:
            self.draw_safe_area(painter, target_rect, 0.90, 110)
        if self.show_title_safe:
            self.draw_safe_area(painter, target_rect, 0.80, 150)

        painter.restore()
        painter.end()
# ============================================================
# Main UI
# ============================================================

class FramingWindowTool(QtWidgets.QDialog):

    PRESETS = [
        ("Current Render", None),
        ("Ultra Panavision 70   2.76:1", 2.76),
        ("CinemaScope           2.39:1", 2.39),
        ("Scope                 2.35:1", 2.35),
        ("70mm                  2.20:1", 2.20),
        ("Univisium             2.00:1", 2.00),
        ("DCI Full              1.90:1", 1.90),
        ("DCI Flat              1.85:1", 1.85),
        ("16:9                  1.78:1", 16.0 / 9.0),
        ("Golden Ratio          1.618:1", (1.0 + math.sqrt(5.0)) / 2.0),
        ("3:2                   1.50:1", 3.0 / 2.0),
        ("Academy               1.37:1", 1.375),
        ("4:3                   1.33:1", 4.0 / 3.0),
        ("5:4                   1.25:1", 5.0 / 4.0),
        ("Square                1:1", 1.0),
        ("4:5                   0.80:1", 4.0 / 5.0),
        ("2:3                   0.67:1", 2.0 / 3.0),
        ("9:16                  0.56:1", 9.0 / 16.0),
        ("Custom", "custom"),
    ]

    COMPOSITION_GUIDES = [
        ("None", None),
        ("Rule of thirds", "show_thirds"),
        ("Golden Ratio Grid", "show_golden_grid"),
        ("Golden Spiral", "show_golden_spiral"),
        ("Golden Triangles", "show_golden_triangles"),
        ("Diagonal Method", "show_diagonal_method"),
    ]

    def __init__(self, parent=get_maya_main_window()):
        super(FramingWindowTool, self).__init__(parent)

        self.setWindowTitle("Framing Window")
        self.setObjectName("FramingWindowTool")

        if TOOL_WINDOW:
            self.setWindowFlags(
                self.windowFlags() | TOOL_WINDOW
            )

        if WA_DELETE_ON_CLOSE:
            self.setAttribute(
                WA_DELETE_ON_CLOSE,
                True
            )

        self.setMinimumWidth(340)

        self.overlay = None
        self.panel = None
        self.viewport = None

        self.build_ui()
        self.connect_ui()

        # Refresh/redraw timer.
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.on_timer)
        self.timer.start(150)

        self.attach_to_active_viewport()

    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ----------------------------------------------------
        # Maya render information
        # ----------------------------------------------------

        info_group = QtWidgets.QGroupBox("Maya Render Frame")
        info_layout = QtWidgets.QVBoxLayout(info_group)

        self.resolution_label = QtWidgets.QLabel()
        self.aspect_label = QtWidgets.QLabel()
        self.camera_label = QtWidgets.QLabel()

        info_layout.addWidget(self.resolution_label)
        info_layout.addWidget(self.aspect_label)
        info_layout.addWidget(self.camera_label)

        main_layout.addWidget(info_group)

        # ----------------------------------------------------
        # Ratio
        # ----------------------------------------------------

        ratio_group = QtWidgets.QGroupBox("Framing")
        ratio_layout = QtWidgets.QVBoxLayout(ratio_group)

        self.ratio_combo = QtWidgets.QComboBox()

        for name, value in self.PRESETS:
            self.ratio_combo.addItem(name, value)

        # CinemaScope default.
        self.ratio_combo.setCurrentIndex(2)

        ratio_layout.addWidget(self.ratio_combo)

        # Custom ratio.
        custom_layout = QtWidgets.QHBoxLayout()

        custom_layout.addWidget(QtWidgets.QLabel("Custom"))

        self.custom_width = QtWidgets.QDoubleSpinBox()
        self.custom_width.setRange(0.01, 100.0)
        self.custom_width.setDecimals(3)
        self.custom_width.setValue(2.39)

        self.custom_height = QtWidgets.QDoubleSpinBox()
        self.custom_height.setRange(0.01, 100.0)
        self.custom_height.setDecimals(3)
        self.custom_height.setValue(1.0)

        custom_layout.addWidget(self.custom_width)
        custom_layout.addWidget(QtWidgets.QLabel(":"))
        custom_layout.addWidget(self.custom_height)

        ratio_layout.addLayout(custom_layout)

        self.ratio_value_label = QtWidgets.QLabel()

        ratio_layout.addWidget(self.ratio_value_label)

        main_layout.addWidget(ratio_group)

        # ----------------------------------------------------
        # Display options
        # ----------------------------------------------------

        display_group = QtWidgets.QGroupBox("Display")
        display_layout = QtWidgets.QVBoxLayout(display_group)

        self.mask_checkbox = QtWidgets.QCheckBox(
            "Darken area outside framing"
        )
        self.mask_checkbox.setChecked(True)

        self.render_mask_checkbox = QtWidgets.QCheckBox(
            "Darken outside Maya render frame"
        )
        self.render_mask_checkbox.setChecked(False)

        self.render_gate_checkbox = QtWidgets.QCheckBox(
            "Show Maya render frame"
        )
        self.render_gate_checkbox.setChecked(True)

        self.border_checkbox = QtWidgets.QCheckBox(
            "Show framing border"
        )
        self.border_checkbox.setChecked(True)

        self.guide_combo = QtWidgets.QComboBox()
        for name, attribute in self.COMPOSITION_GUIDES:
            self.guide_combo.addItem(name, attribute)
        self.guide_combo.setToolTip("Composition guide inside the selected framing")

        self.center_checkbox = QtWidgets.QCheckBox(
            "Center marker"
        )
        self.action_safe_checkbox = QtWidgets.QCheckBox("Action Safe (90%)")
        self.title_safe_checkbox = QtWidgets.QCheckBox("Title Safe (80%)")

        display_layout.addWidget(self.mask_checkbox)
        display_layout.addWidget(self.render_mask_checkbox)
        display_layout.addWidget(self.render_gate_checkbox)
        display_layout.addWidget(self.border_checkbox)
        display_layout.addWidget(QtWidgets.QLabel("Composition guide"))
        display_layout.addWidget(self.guide_combo)
        display_layout.addWidget(self.center_checkbox)
        display_layout.addWidget(self.action_safe_checkbox)
        display_layout.addWidget(self.title_safe_checkbox)

        # Opacity.
        opacity_layout = QtWidgets.QHBoxLayout()

        opacity_layout.addWidget(
            QtWidgets.QLabel("Mask opacity")
        )

        self.opacity_slider = QtWidgets.QSlider(HORIZONTAL)
        self.opacity_slider.setRange(0, 255)
        self.opacity_slider.setValue(155)

        opacity_layout.addWidget(self.opacity_slider)

        display_layout.addLayout(opacity_layout)

        main_layout.addWidget(display_group)

        # ----------------------------------------------------
        # Buttons
        # ----------------------------------------------------

        button_layout = QtWidgets.QHBoxLayout()

        self.attach_button = QtWidgets.QPushButton(
            "Attach to Active View"
        )

        self.toggle_button = QtWidgets.QPushButton(
            "Hide Overlay"
        )

        button_layout.addWidget(self.attach_button)
        button_layout.addWidget(self.toggle_button)

        main_layout.addLayout(button_layout)

    # ========================================================

    def connect_ui(self):

        self.ratio_combo.currentIndexChanged.connect(
            self.update_ratio
        )

        self.custom_width.valueChanged.connect(
            self.update_ratio
        )

        self.custom_height.valueChanged.connect(
            self.update_ratio
        )

        self.mask_checkbox.toggled.connect(
            self.update_overlay_settings
        )

        self.render_mask_checkbox.toggled.connect(
            self.update_overlay_settings
        )

        self.render_gate_checkbox.toggled.connect(
            self.update_overlay_settings
        )

        self.border_checkbox.toggled.connect(
            self.update_overlay_settings
        )

        self.guide_combo.currentIndexChanged.connect(
            self.update_overlay_settings
        )

        self.center_checkbox.toggled.connect(
            self.update_overlay_settings
        )
        self.action_safe_checkbox.toggled.connect(self.update_overlay_settings)
        self.title_safe_checkbox.toggled.connect(self.update_overlay_settings)

        self.opacity_slider.valueChanged.connect(
            self.update_overlay_settings
        )

        self.attach_button.clicked.connect(
            self.attach_to_active_viewport
        )

        self.toggle_button.clicked.connect(
            self.toggle_overlay
        )

    # ========================================================
    # Viewport
    # ========================================================

    def attach_to_active_viewport(self):

        panel = get_active_model_panel()

        if not panel:
            cmds.warning(
                "Framing Window: no Maya modelPanel found."
            )
            return

        viewport = get_viewport_widget(panel)

        if not viewport:
            cmds.warning(
                "Framing Window: could not find viewport QWidget."
            )
            return

        # Remove old overlay.
        if self.overlay:
            try:
                self.overlay.close()
                self.overlay.deleteLater()
            except Exception:
                pass

        self.panel = panel
        self.viewport = viewport

        self.overlay = FramingOverlay(viewport)
        self.overlay._panel = panel

        self.update_ratio()
        self.update_overlay_settings()
        self.update_info()

    # ========================================================

    def update_ratio(self):

        if not self.overlay:
            return

        index = self.ratio_combo.currentIndex()
        value = self.ratio_combo.itemData(index)

        if value is None:
            self.overlay.use_render_aspect = True

        elif value == "custom":
            self.overlay.use_render_aspect = False

            w = self.custom_width.value()
            h = self.custom_height.value()

            self.overlay.target_aspect = (
                w / h if h else 1.0
            )

        else:
            self.overlay.use_render_aspect = False
            self.overlay.target_aspect = float(value)

        self.update_ratio_label()
        self.overlay.update()

    # ========================================================

    def update_ratio_label(self):

        settings = get_render_settings()

        index = self.ratio_combo.currentIndex()
        value = self.ratio_combo.itemData(index)

        if value is None:
            ratio = settings["device_aspect"]

        elif value == "custom":
            h = self.custom_height.value()
            ratio = (
                self.custom_width.value() / h
                if h else 1.0
            )

        else:
            ratio = float(value)

        self.ratio_value_label.setText(
            "Framing aspect: {:.4f}".format(ratio)
        )

    # ========================================================

    def update_overlay_settings(self):

        if not self.overlay:
            return

        self.overlay.mask_enabled = (
            self.mask_checkbox.isChecked()
        )

        self.overlay.mask_render_outside = (
            self.render_mask_checkbox.isChecked()
        )

        self.overlay.show_render_gate = (
            self.render_gate_checkbox.isChecked()
        )

        self.overlay.show_target_border = (
            self.border_checkbox.isChecked()
        )

        selected_guide = self.guide_combo.currentData()
        for _, attribute in self.COMPOSITION_GUIDES:
            if attribute is not None:
                setattr(self.overlay, attribute, attribute == selected_guide)

        self.overlay.show_center = (
            self.center_checkbox.isChecked()
        )
        self.overlay.show_action_safe = self.action_safe_checkbox.isChecked()
        self.overlay.show_title_safe = self.title_safe_checkbox.isChecked()

        self.overlay.mask_opacity = (
            self.opacity_slider.value()
        )

        self.overlay.update()

    # ========================================================

    def update_info(self):

        settings = get_render_settings()

        self.resolution_label.setText(
            "Resolution: {} x {}".format(
                settings["width"],
                settings["height"]
            )
        )

        self.aspect_label.setText(
            "Device aspect: {:.4f}   Pixel aspect: {:.4f}".format(
                settings["device_aspect"],
                settings["pixel_aspect"]
            )
        )

        if self.panel:
            camera_transform, _ = get_panel_camera(
                self.panel
            )

            camera_name = (
                camera_transform
                if camera_transform
                else "Unknown"
            )

            self.camera_label.setText(
                "Camera: {}".format(camera_name)
            )

    # ========================================================

    def on_timer(self):

        if not self.overlay:
            return

        try:
            if self.viewport:
                self.overlay.sync_geometry()

            self.update_info()

            # Important because render resolution can be changed
            # while the tool is open.
            self.update_ratio_label()

        except RuntimeError:
            # Viewport may have been destroyed by workspace change.
            self.overlay = None
            self.viewport = None

    # ========================================================

    def toggle_overlay(self):

        if not self.overlay:
            self.attach_to_active_viewport()
            return

        if self.overlay.isVisible():
            self.overlay.hide()
            self.toggle_button.setText("Show Overlay")
        else:
            self.overlay.show()
            self.overlay.raise_()
            self.toggle_button.setText("Hide Overlay")

    # ========================================================

    def closeEvent(self, event):

        self.timer.stop()

        if self.overlay:
            try:
                self.overlay.close()
                self.overlay.deleteLater()
            except Exception:
                pass

        self.overlay = None

        super(FramingWindowTool, self).closeEvent(event)


# ============================================================
# Launch
# ============================================================

_FRAMING_WINDOW_TOOL = None


def show_framing_window():

    global _FRAMING_WINDOW_TOOL

    try:
        if _FRAMING_WINDOW_TOOL:
            _FRAMING_WINDOW_TOOL.close()
            _FRAMING_WINDOW_TOOL.deleteLater()
    except Exception:
        pass

    _FRAMING_WINDOW_TOOL = FramingWindowTool()
    _FRAMING_WINDOW_TOOL.show()
    _FRAMING_WINDOW_TOOL.raise_()
    _FRAMING_WINDOW_TOOL.activateWindow()

    return _FRAMING_WINDOW_TOOL


show_framing_window()
