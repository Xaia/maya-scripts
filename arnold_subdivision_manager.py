"""Arnold Subdivision Manager 1.0.0 for Maya (Python 3).

Install in your Maya scripts folder, then run:
    import arnold_subdivision_manager as asm
    asm.show()

Or execute this whole file in Maya's Python Script Editor.
Uses Maya's bundled PySide2/PySide6. No external dependencies.

Usage:
    Select rows with Ctrl / Shift. Click a column heading to sort.
    The Selected tab includes mesh descendants of selected groups.
    Disable Follow Maya selection to hold a captured list.
    Enable only the bulk-editor fields you want to change, then Apply.
    An asterisk marks mixed values; the displayed value comes from the
    first selected row and is applied only when its field is enabled.
    Quick actions affect selected rows only and form one Maya undo step.
    F5 reloads values changed externally in the Attribute Editor.
    Right-click a header to show/hide columns, or a row for mesh actions.
    Window geometry, splitter size and table columns persist across runs.

Scope:
    Polygon mesh shapes, excluding intermediate shapes. Arnold stand-ins
    are not editable mesh geometry. Instanced shapes appear once because
    their subdivision attributes are shared by every instance.
    No renderer switch, geometry conversion, unlocking or disconnection.
    The Load Arnold button loads your installed mtoa plugin explicitly.
    Reference edits require disabling Skip referenced meshes.
    Per-attribute failures are reported in Maya's Script Editor and the
    status tooltip. Successful attributes remain applied.
    Copy/paste uses an internal settings buffer; when multiple rows are
    selected, Copy uses the first row in current table order.

Validation:
    Syntax and backend behavior validated outside Maya with a mock scene.
    Live Maya / MtoA UI and rendering validation is still required.
"""
import re
from contextlib import contextmanager

from maya import cmds
from maya import OpenMayaUI
from maya.api import OpenMaya as om

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

VERSION = '1.0.0'
Qt = QtCore.Qt
WINDOW_NAME = 'artistArnoldSubdivisionManager'
_WINDOW = None

# Read enum names and integer values from the running MtoA version.
# aiSubdivPixelError is MtoA's name for Arnold's adaptive error.
FIELDS = (
    ('aiSubdivType', 'Subdivision type', 'enum'),
    ('aiSubdivIterations', 'Iterations', 'int'),
    ('aiSubdivPixelError', 'Adaptive error', 'float'),
    ('aiSubdivAdaptiveMetric', 'Adaptive metric', 'enum'),
    ('aiSubdivAdaptiveSpace', 'Adaptive space', 'enum'),
    ('aiSubdivUvSmoothing', 'UV smoothing', 'enum'),
    ('aiSubdivSmoothDerivs', 'Smooth tangents', 'bool'),
)
HEADERS = ('Mesh', 'Type', 'Iterations', 'Adaptive error', 'Metric',
           'Space', 'UV smoothing', 'Tangents', 'Maya preview', 'Status', 'Shape path')


def natural_key(value):
    return tuple((0, int(p)) if p.isdigit() else (1, p.casefold())
                 for p in re.split(r'(\d+)', str(value)))


def enum_options(node, attr):
    """Honor explicit enum indices (e.g. none=0:catclark=1:linear=2)."""
    try:
        entries = cmds.attributeQuery(attr, node=node, listEnum=True) or []
        options, number = [], 0
        for entry in (entries[0].split(':') if entries else []):
            label, sep, explicit = entry.rpartition('=')
            if sep:
                number = int(explicit)
            else:
                label = entry
            options.append((label, number))
            number += 1
        return options
    except (RuntimeError, ValueError):
        return []


def resolve(uuid):
    paths = cmds.ls(uuid, long=True) or []
    return paths[0] if paths else None


def collect_meshes(roots=None):
    """One entry per shape UUID. Instances share Arnold attributes."""
    if roots is None:
        paths = cmds.ls(type='mesh', long=True, allPaths=True) or []
    else:
        paths = []
        for root in roots:
            root = root.split('.', 1)[0]
            if not cmds.objExists(root):
                continue
            if cmds.nodeType(root) == 'mesh':
                paths.append(root)
            elif cmds.nodeType(root) == 'transform':
                paths.extend(cmds.listRelatives(root, allDescendents=True,
                                               type='mesh', fullPath=True) or [])
    unique = {}
    for path in paths:
        try:
            if cmds.getAttr(path + '.intermediateObject'):
                continue
            ids = cmds.ls(path, uuid=True) or []
            if ids:
                unique.setdefault(ids[0], path)
        except RuntimeError:
            continue
    return unique


def selected_roots():
    return cmds.ls(selection=True, long=True, objectsOnly=True) or []


def read_record(uuid, path, enum_cache=None):
    values, enums = {}, {}
    for attr, _label, kind in FIELDS:
        try:
            values[attr] = cmds.getAttr(path + '.' + attr)
            if kind == 'enum':
                if enum_cache is not None and attr in enum_cache:
                    enums[attr] = enum_cache[attr]
                else:
                    enums[attr] = enum_options(path, attr)
                    if enum_cache is not None:
                        enum_cache[attr] = enums[attr]
        except RuntimeError:
            values[attr] = None
    parents = cmds.listRelatives(path, parent=True, fullPath=True) or []
    parent = parents[0] if parents else path
    try:
        referenced = cmds.referenceQuery(path, isNodeReferenced=True)
    except RuntimeError:
        referenced = False
    try:
        preview = cmds.getAttr(path + '.displaySmoothMesh')
    except RuntimeError:
        preview = None
    blocked = []
    for attr, _label, _kind in FIELDS:
        if values[attr] is not None:
            try:
                if not cmds.getAttr(path + '.' + attr, settable=True):
                    blocked.append(attr)
            except RuntimeError:
                blocked.append(attr)
    instances = cmds.ls(uuid, long=True, allPaths=True) or [path]
    states = []
    if values['aiSubdivType'] is None:
        states.append('No Arnold attributes')
    if referenced:
        states.append('Referenced')
    if blocked:
        states.append('Locked / connected')
    if len(instances) > 1:
        states.append('Instanced x{}'.format(len(instances)))
    return dict(uuid=uuid, path=path, parent=parent, name=parent.rsplit('|', 1)[-1],
                values=values, enums=enums, referenced=referenced, preview=preview,
                status=', '.join(states) or 'Ready')


def enum_label(record, attr):
    value = record['values'].get(attr)
    return dict((number, label) for label, number in record['enums'].get(attr, [])).get(value, str(value))


@contextmanager
def undo_chunk():
    cmds.undoInfo(openChunk=True, chunkName='Arnold subdivision manager')
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


def apply_settings(uuids, settings, skip_references=True, delta=None):
    """Validate each plug, never unlock or disconnect, return a detailed report."""
    changed, skipped, errors = 0, 0, []
    with undo_chunk():
        for uuid in dict.fromkeys(uuids):
            path = resolve(uuid)
            if not path:
                skipped += 1
                errors.append('Deleted mesh: ' + uuid)
                continue
            if skip_references and cmds.referenceQuery(path, isNodeReferenced=True):
                skipped += 1
                errors.append(path + ': reference skipped')
                continue
            work = dict(settings)
            if delta is not None:
                try:
                    work['aiSubdivIterations'] = max(0, cmds.getAttr(path + '.aiSubdivIterations') + delta)
                except RuntimeError as exc:
                    errors.append('{}: {}'.format(path, exc))
                    skipped += 1
                    continue
            for attr, requested in work.items():
                plug = path + '.' + attr
                try:
                    if not cmds.objExists(plug):
                        raise ValueError('attribute unavailable')
                    if not cmds.getAttr(plug, settable=True):
                        raise ValueError('locked or connected')
                    value = requested
                    if isinstance(value, str):
                        options = dict(enum_options(path, attr))
                        if value not in options:
                            raise ValueError('enum value unavailable: ' + value)
                        value = options[value]
                    for exists_flag, limit_flag, compare in (
                        ('minExists', 'minimum', lambda v, lim: v < lim),
                        ('maxExists', 'maximum', lambda v, lim: v > lim),
                    ):
                        if cmds.attributeQuery(attr, node=path, **{exists_flag: True}):
                            limit = cmds.attributeQuery(attr, node=path, **{limit_flag: True})[0]
                            if compare(value, limit):
                                raise ValueError('outside attribute range ({})'.format(limit))
                    if cmds.getAttr(plug) == value:
                        continue
                    cmds.setAttr(plug, value)
                    changed += 1
                except (RuntimeError, ValueError, TypeError) as exc:
                    skipped += 1
                    errors.append('{}: {}'.format(plug, exc))
    return changed, skipped, errors


class MeshModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super(MeshModel, self).__init__(parent)
        self.records = []

    def replace(self, records):
        self.beginResetModel()
        self.records = records
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        record, column = self.records[index.row()], index.column()
        if role == Qt.UserRole:
            return record['uuid']
        if role == Qt.ToolTipRole:
            return record['path'] + '\n' + record['status']
        if role == Qt.TextAlignmentRole and column in (2, 3, 7, 8):
            return Qt.AlignCenter
        if role != Qt.DisplayRole:
            return None
        if column == 0:
            return record['name']
        if 1 <= column <= 7:
            attr, _label, kind = FIELDS[column - 1]
            value = record['values'][attr]
            if value is None:
                return 'N/A'
            if kind == 'enum':
                return enum_label(record, attr)
            if kind == 'bool':
                return 'On' if value else 'Off'
            return value if kind == 'int' else '{:g}'.format(value)
        if column == 8:
            return {0: 'Off', 1: 'Cage', 2: 'Smooth'}.get(record['preview'], 'N/A')
        return record['status'] if column == 9 else record['path']


class MeshProxy(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super(MeshProxy, self).__init__(parent)
        self.query = ''
        self.mode = 'All types'

    def filterAcceptsRow(self, row, parent):
        record = self.sourceModel().records[row]
        # Space separated tokens, matched against full DAG path.
        if not all(token in record['path'].casefold() for token in self.query.casefold().split()):
            return False
        label = enum_label(record, 'aiSubdivType').casefold()
        if self.mode == 'Subdivision on':
            return record['values']['aiSubdivType'] is not None and label != 'none'
        if self.mode == 'Subdivision off':
            return label == 'none'
        if self.mode == 'Needs attention':
            return record['status'] != 'Ready' or record['preview'] in (1, 2)
        return True

    def lessThan(self, left, right):
        column = left.column()
        if column in (2, 3):
            attr = FIELDS[column - 1][0]
            a = self.sourceModel().records[left.row()]['values'][attr]
            b = self.sourceModel().records[right.row()]['values'][attr]
            return (a if a is not None else -1) < (b if b is not None else -1)
        return natural_key(self.sourceModel().data(left)) < natural_key(self.sourceModel().data(right))


class MeshTab(QtWidgets.QWidget):
    def __init__(self, manager, selected=False):
        super(MeshTab, self).__init__(manager)
        self.manager = manager
        self.selected = selected
        self.scope_ids = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        row = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Filter by name, namespace or group path...')
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        self.filter = QtWidgets.QComboBox()
        self.filter.addItems(['All types', 'Subdivision on', 'Subdivision off', 'Needs attention'])
        row.addWidget(self.filter)
        layout.addLayout(row)
        if selected:
            row = QtWidgets.QHBoxLayout()
            self.follow = QtWidgets.QCheckBox('Follow Maya selection')
            self.follow.setChecked(True)
            self.follow.setToolTip('Turn off to freeze this mesh list while you select objects in Maya.')
            row.addWidget(self.follow)
            capture = QtWidgets.QPushButton('Capture selection')
            capture.clicked.connect(self.capture)
            row.addWidget(capture)
            row.addStretch()
            layout.addLayout(row)
            self.follow.toggled.connect(lambda value: self.capture() if value else None)
        self.model = MeshModel(self)
        self.proxy = MeshProxy(self)
        self.proxy.setSourceModel(self.model)
        self.view = QtWidgets.QTableView()
        self.view.setModel(self.proxy)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(0, Qt.AscendingOrder)
        self.view.setAlternatingRowColors(True)
        self.view.setShowGrid(False)
        self.view.setWordWrap(False)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(26)
        header = self.view.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        for column, width in enumerate((190, 90, 78, 100, 90, 75, 100, 75, 105, 155, 360)):
            self.view.setColumnWidth(column, width)
        self.view.setColumnHidden(10, True)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.column_menu)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(lambda _index: self.select_scene())
        self.view.selectionModel().selectionChanged.connect(lambda *_: manager.update_editor())
        layout.addWidget(self.view, 1)
        row = QtWidgets.QHBoxLayout()
        for label, callback in [('Select visible', self.view.selectAll),
                                ('Clear', self.view.clearSelection),
                                ('Select in Maya', self.select_scene),
                                ('Frame', self.frame_scene)]:
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch()
        self.count = QtWidgets.QLabel()
        row.addWidget(self.count)
        layout.addLayout(row)
        self.search.textChanged.connect(self.filter_changed)
        self.filter.currentTextChanged.connect(self.filter_changed)

    def capture(self):
        self.scope_ids = list(collect_meshes(selected_roots()))
        self.manager.refresh_selected()

    def filter_changed(self, *_):
        self.proxy.query = self.search.text()
        self.proxy.mode = self.filter.currentText()
        self.proxy.invalidateFilter()
        self.update_count()
        self.manager.update_editor()

    def update_count(self):
        self.count.setText('{} / {} meshes'.format(self.proxy.rowCount(), self.model.rowCount()))

    def ids(self):
        return [self.proxy.data(index, Qt.UserRole)
                for index in self.view.selectionModel().selectedRows()]

    def set_records(self, records):
        selected = set(self.ids())
        self.model.replace(records)
        selection = QtCore.QItemSelection()
        for row in range(self.proxy.rowCount()):
            index = self.proxy.index(row, 0)
            if self.proxy.data(index, Qt.UserRole) in selected:
                selection.select(index, self.proxy.index(row, len(HEADERS) - 1))
        self.view.selectionModel().select(selection, QtCore.QItemSelectionModel.ClearAndSelect |
                                         QtCore.QItemSelectionModel.Rows)
        self.update_count()

    def select_scene(self):
        paths = [resolve(uuid) for uuid in self.ids()]
        paths = [p for p in paths if p]
        if not paths:
            return
        # Freeze scope before this explicit selection changes the live tab.
        if self.selected:
            self.follow.setChecked(False)
        transforms = []
        for path in paths:
            transforms.extend(cmds.listRelatives(path, parent=True, fullPath=True) or [path])
        cmds.select(list(dict.fromkeys(transforms)), replace=True)

    def frame_scene(self):
        # viewFit can operate on objects without changing Maya's selection.
        paths = [resolve(uuid) for uuid in self.ids()]
        paths = [p for p in paths if p]
        if paths:
            try:
                cmds.viewFit(paths, animate=True)
            except RuntimeError as exc:
                self.manager.report('Cannot frame: ' + str(exc))

    def column_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        for column, label in enumerate(HEADERS):
            if column == 0:
                continue
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not self.view.isColumnHidden(column))
            action.toggled.connect(lambda checked, c=column: self.view.setColumnHidden(c, not checked))
        menu.exec_(self.view.horizontalHeader().mapToGlobal(pos)) if hasattr(menu, 'exec_') else menu.exec(self.view.horizontalHeader().mapToGlobal(pos))

    def context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        for label, callback in [('Select in Maya', self.select_scene), ('Frame meshes', self.frame_scene),
                                ('Copy shape paths', self.copy_paths), ('Copy settings', self.manager.copy_settings),
                                ('Paste settings', self.manager.paste_settings)]:
            menu.addAction(label, callback)
        menu.addSeparator()
        for label, value in [('Disable subdivision', 'none'), ('Catclark', 'catclark'), ('Linear', 'linear')]:
            menu.addAction(label, lambda _checked=False, v=value: self.manager.quick_type(v))
        menu.exec_(self.view.viewport().mapToGlobal(pos)) if hasattr(menu, 'exec_') else menu.exec(self.view.viewport().mapToGlobal(pos))

    def copy_paths(self):
        paths = [resolve(uuid) for uuid in self.ids()]
        QtWidgets.QApplication.clipboard().setText('\n'.join(p for p in paths if p))


class SubdivisionManager(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(SubdivisionManager, self).__init__(parent)
        self.setObjectName(WINDOW_NAME)
        self.setWindowTitle('Arnold Subdivision Manager')
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(1180, 680)
        self.setMinimumSize(830, 520)
        self.records = {}
        self.callbacks = []
        self.jobs = []
        self.clipboard_settings = None
        self._busy = False
        self._closed = False
        self._geometry_dirty = False
        self._editor_loading = False
        self.settings = QtCore.QSettings('ArtistTools', WINDOW_NAME)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(10)
        top = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel('ARNOLD  /  SUBDIVISION')
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        top.addWidget(title)
        top.addStretch()
        self.skip_refs = QtWidgets.QCheckBox('Skip referenced meshes')
        self.skip_refs.setChecked(True)
        self.skip_refs.setToolTip('Disable to permit reference edits. Locked attributes are always skipped.')
        top.addWidget(self.skip_refs)
        load = QtWidgets.QPushButton('Load Arnold')
        load.setToolTip('Load the installed mtoa plugin, then reload the mesh list.')
        load.clicked.connect(self.load_arnold)
        top.addWidget(load)
        refresh = QtWidgets.QPushButton('Refresh')
        refresh.setToolTip('Reload scene meshes and Arnold values. Shortcut: F5')
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        layout.addLayout(top)
        self.splitter = QtWidgets.QSplitter(Qt.Horizontal)
        self.tabs = QtWidgets.QTabWidget()
        self.all_tab = MeshTab(self)
        self.selected_tab = MeshTab(self, selected=True)
        self.tabs.addTab(self.all_tab, 'All meshes')
        self.tabs.addTab(self.selected_tab, 'Selected meshes / groups')
        self.tabs.currentChanged.connect(lambda *_: self.update_editor())
        self.splitter.addWidget(self.tabs)
        self.editor = QtWidgets.QWidget()
        self.editor.setMinimumWidth(275)
        edit_layout = QtWidgets.QVBoxLayout(self.editor)
        edit_layout.setContentsMargins(12, 8, 0, 0)
        self.target_label = QtWidgets.QLabel('Select rows to edit')
        edit_layout.addWidget(self.target_label)
        hint = QtWidgets.QLabel('Enable the fields you want to apply.\nOther settings are preserved.')
        hint.setWordWrap(True)
        edit_layout.addWidget(hint)
        form = QtWidgets.QGridLayout()
        self.controls = {}
        for row, (attr, label, kind) in enumerate(FIELDS):
            check = QtWidgets.QCheckBox(label)
            if kind in ('enum', 'bool'):
                widget = QtWidgets.QComboBox()
                if kind == 'bool':
                    widget.addItem('Off', False)
                    widget.addItem('On', True)
            elif kind == 'int':
                widget = QtWidgets.QSpinBox()
                widget.setRange(0, 255)
                widget.setKeyboardTracking(False)
            else:
                widget = QtWidgets.QDoubleSpinBox()
                widget.setDecimals(4)
                widget.setRange(0, 1000000)
                widget.setSingleStep(0.1)
                widget.setKeyboardTracking(False)
            widget.setEnabled(False)
            widget.setMinimumWidth(112)
            check.toggled.connect(widget.setEnabled)
            form.addWidget(check, row, 0)
            form.addWidget(widget, row, 1)
            self.controls[attr] = (check, widget, kind)
        edit_layout.addLayout(form)
        error_tip = QtWidgets.QLabel('Adaptive error 0 = uniform subdivision.\nIterations are the adaptive maximum.')
        error_tip.setWordWrap(True)
        edit_layout.addWidget(error_tip)
        self.apply_button = QtWidgets.QPushButton('Apply enabled fields')
        self.apply_button.setMinimumHeight(32)
        self.apply_button.clicked.connect(self.apply)
        edit_layout.addWidget(self.apply_button)
        quick = QtWidgets.QGroupBox('Quick actions')
        quick_layout = QtWidgets.QGridLayout(quick)
        for column, (label, value) in enumerate([('Off', 'none'), ('Catclark', 'catclark'), ('Linear', 'linear')]):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda _checked=False, v=value: self.quick_type(v))
            quick_layout.addWidget(button, 0, column)
        for column, delta in enumerate((-1, 1)):
            button = QtWidgets.QPushButton('{}1 iteration'.format('−' if delta < 0 else '+'))
            button.clicked.connect(lambda _checked=False, d=delta: self.run_edit({}, delta=d))
            quick_layout.addWidget(button, 1, column)
        reset = QtWidgets.QPushButton('Defaults')
        reset.setToolTip('Restore Arnold subdivision attributes to their runtime defaults.')
        reset.clicked.connect(self.reset_defaults)
        quick_layout.addWidget(reset, 1, 2)
        edit_layout.addWidget(quick)
        preview = QtWidgets.QGroupBox('Maya smooth preview')
        preview_layout = QtWidgets.QHBoxLayout(preview)
        for label, value in [('Off', 0), ('Cage', 1), ('Smooth', 2)]:
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda _checked=False, v=value: self.run_edit({'displaySmoothMesh': v}))
            preview_layout.addWidget(button)
        edit_layout.addWidget(preview)
        preview_tip = QtWidgets.QLabel('Smooth preview can add subdivision in Arnold. Check both before rendering.')
        preview_tip.setWordWrap(True)
        edit_layout.addWidget(preview_tip)
        row = QtWidgets.QHBoxLayout()
        for label, callback in [('Copy settings', self.copy_settings), ('Paste settings', self.paste_settings)]:
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        edit_layout.addLayout(row)
        edit_layout.addStretch()
        note = QtWidgets.QLabel('Ctrl: multi-select  |  Shift: range\nDouble-click: select in Maya\nRight-click header: show/hide columns')
        note.setWordWrap(True)
        edit_layout.addWidget(note)
        self.splitter.addWidget(self.editor)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([860, 300])
        layout.addWidget(self.splitter, 1)
        self.status = QtWidgets.QLabel('')
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(160)
        self.timer.timeout.connect(self.process_events)
        shortcut_class = getattr(QtGui, 'QShortcut', None) or QtWidgets.QShortcut
        self.refresh_shortcut = shortcut_class(QtGui.QKeySequence('F5'), self)
        self.refresh_shortcut.activated.connect(self.refresh)
        self.restore_ui()
        self.refresh()
        self.install_callbacks()

    def active_tab(self):
        return self.tabs.currentWidget()

    def report(self, message, details=None):
        self.status.setText(message)
        self.status.setToolTip('\n'.join(details or []))
        if details:
            print('\n[Arnold Subdivision Manager]\n' + '\n'.join(details))

    def refresh(self):
        if self._closed or self._busy:
            return
        self._busy = True
        try:
            enum_cache = {}
            self.records = {uuid: read_record(uuid, path, enum_cache)
                            for uuid, path in collect_meshes().items()}
            self.all_tab.set_records(list(self.records.values()))
            if self.selected_tab.follow.isChecked():
                self.selected_tab.scope_ids = list(collect_meshes(selected_roots()))
            self.refresh_selected()
            has_arnold = any(r['values']['aiSubdivType'] is not None for r in self.records.values())
            self.report('{} mesh shapes. Ready.'.format(len(self.records)) if has_arnold else
                        'No Arnold mesh attributes found. Load mtoa in Maya Plugin Manager, then Refresh.')
        finally:
            self._busy = False
        self.update_editor()

    def load_arnold(self):
        try:
            if not cmds.pluginInfo('mtoa', query=True, loaded=True):
                cmds.loadPlugin('mtoa', quiet=True)
            self.refresh()
        except RuntimeError as exc:
            self.report('Could not load Arnold: ' + str(exc))

    def refresh_edited(self, ids):
        """Re-read only edited shapes; sorting/filtering use cached records."""
        enum_cache = {}
        for uuid in ids:
            path = resolve(uuid)
            if path:
                self.records[uuid] = read_record(uuid, path, enum_cache)
            else:
                self.records.pop(uuid, None)
        self.all_tab.set_records(list(self.records.values()))
        self.refresh_selected()
        self.update_editor()

    def refresh_selected(self):
        self.selected_tab.set_records([self.records[uuid] for uuid in self.selected_tab.scope_ids if uuid in self.records])
        self.update_editor()

    def update_editor(self):
        if not hasattr(self, 'controls') or self._editor_loading:
            return
        self._editor_loading = True
        try:
            ids = self.active_tab().ids()
            records = [self.records[uuid] for uuid in ids if uuid in self.records]
            self.target_label.setText('{} selected mesh{}'.format(len(records), '' if len(records) == 1 else 'es'))
            self.apply_button.setEnabled(bool(records))
            for attr, (check, widget, kind) in self.controls.items():
                check.setChecked(False)
                supported = [r for r in records if r['values'][attr] is not None]
                check.setEnabled(bool(supported))
                if kind == 'enum':
                    widget.clear()
                    labels = list(dict.fromkeys(label for r in supported for label, _ in r['enums'].get(attr, [])))
                    for label in labels:
                        widget.addItem(label, label)
                    values = [enum_label(r, attr) for r in supported]
                else:
                    values = [r['values'][attr] for r in supported]
                mixed = bool(values) and (len(set(values)) > 1 or len(supported) != len(records))
                check.setText(dict((a, label) for a, label, _ in FIELDS)[attr] + (' *' if mixed else ''))
                check.setToolTip('Mixed values or partial support' if mixed else 'Enable this field to apply it to selected rows')
                if values:
                    value = values[0]
                    if kind == 'enum':
                        widget.setCurrentIndex(widget.findData(value))
                    elif kind == 'bool':
                        widget.setCurrentIndex(1 if value else 0)
                    else:
                        widget.setValue(value)
        finally:
            self._editor_loading = False

    def enabled_settings(self):
        values = {}
        for attr, (check, widget, kind) in self.controls.items():
            if check.isChecked():
                value = widget.currentData() if kind in ('enum', 'bool') else widget.value()
                if value is not None:
                    values[attr] = value
        return values

    def apply(self):
        values = self.enabled_settings()
        if not values:
            self.report('Enable at least one field to apply.')
            return
        self.run_edit(values)

    def quick_type(self, name):
        # Map names against each shape's actual enum, ignoring case.
        records = [self.records[u] for u in self.active_tab().ids() if u in self.records]
        settings = None
        for r in records:
            for label, _value in r['enums'].get('aiSubdivType', []):
                normalized = label.casefold().replace(' ', '').replace('-', '')
                if normalized == name or (name == 'catclark' and normalized == 'catmullclark'):
                    settings = {'aiSubdivType': label}
                    break
        if settings:
            self.run_edit(settings)
        else:
            self.report('Select meshes with supported Arnold subdivision attributes.')

    def run_edit(self, values, delta=None):
        ids = self.active_tab().ids()
        if not ids:
            self.report('Select mesh rows first. Ctrl and Shift allow multi-selection.')
            return
        self._busy = True
        try:
            changed, skipped, errors = apply_settings(ids, values, self.skip_refs.isChecked(), delta)
        finally:
            self._busy = False
        self.refresh_edited(ids)
        self.report('{} attributes changed on {} targeted meshes. {} skipped.'.format(changed, len(ids), skipped), errors)

    def copy_settings(self):
        ids = self.active_tab().ids()
        if not ids:
            self.report('Select a mesh row to copy its Arnold settings.')
            return
        record = self.records[ids[0]]
        values = {}
        for attr, _label, kind in FIELDS:
            if record['values'][attr] is not None:
                values[attr] = enum_label(record, attr) if kind == 'enum' else record['values'][attr]
        self.clipboard_settings = values
        self.report('Copied Arnold settings from {}. Paste applies these fields.'.format(record['name']))

    def paste_settings(self):
        if self.clipboard_settings:
            self.run_edit(self.clipboard_settings)
        else:
            self.report('Copy settings from a mesh first.')

    def reset_defaults(self):
        ids = self.active_tab().ids()
        if not ids:
            self.report('Select mesh rows first.')
            return
        changed = skipped = 0
        errors = []
        self._busy = True
        try:
            with undo_chunk():
                for uuid in ids:
                    path = resolve(uuid)
                    if not path:
                        skipped += 1
                        continue
                    values = {}
                    for attr, _label, _kind in FIELDS:
                        try:
                            default = cmds.attributeQuery(attr, node=path, listDefault=True)
                            if default:
                                values[attr] = default[0]
                        except RuntimeError:
                            pass
                    c, s, e = apply_settings([uuid], values, self.skip_refs.isChecked())
                    changed += c
                    skipped += s
                    errors.extend(e)
        finally:
            self._busy = False
        self.refresh_edited(ids)
        self.report('{} attributes restored to defaults. {} skipped.'.format(changed, skipped), errors)

    def schedule(self, geometry=False):
        if self._closed or self._busy:
            return
        self._geometry_dirty |= geometry
        self.timer.start()

    def process_events(self):
        if self._closed:
            return
        if self._geometry_dirty:
            self._geometry_dirty = False
            self.refresh()
        elif self.selected_tab.follow.isChecked():
            self.selected_tab.capture()

    def install_callbacks(self):
        events = set(cmds.scriptJob(listEvents=True) or [])
        for name in ('SelectionChanged', 'Undo', 'Redo', 'NameChanged'):
            if name in events:
                geometry = name != 'SelectionChanged'
                self.jobs.append(cmds.scriptJob(event=[name, lambda g=geometry: self.schedule(g)], protected=True))
        for event in (om.MSceneMessage.kAfterNew, om.MSceneMessage.kAfterOpen):
            self.callbacks.append(om.MSceneMessage.addCallback(event, lambda *_: self.scene_changed()))
        self.callbacks.append(om.MDGMessage.addNodeAddedCallback(lambda *_: self.schedule(True), 'mesh'))
        self.callbacks.append(om.MDGMessage.addNodeRemovedCallback(lambda *_: self.schedule(True), 'mesh'))
        self.callbacks.append(om.MDagMessage.addAllDagChangesCallback(lambda *_: self.schedule(True)))

    def scene_changed(self):
        self.selected_tab.scope_ids = []
        self.clipboard_settings = None
        self.schedule(True)

    def restore_ui(self):
        geometry = self.settings.value('geometry')
        if geometry is not None:
            self.restoreGeometry(geometry)
        splitter = self.settings.value('splitter')
        if splitter is not None:
            self.splitter.restoreState(splitter)
        for key, tab in [('all', self.all_tab), ('selected', self.selected_tab)]:
            state = self.settings.value(key + '_header')
            if state is not None:
                tab.view.horizontalHeader().restoreState(state)

    def closeEvent(self, event):
        self._closed = True
        self.timer.stop()
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.splitter.saveState())
        for key, tab in [('all', self.all_tab), ('selected', self.selected_tab)]:
            self.settings.setValue(key + '_header', tab.view.horizontalHeader().saveState())
        for job in self.jobs:
            if cmds.scriptJob(exists=job):
                cmds.scriptJob(kill=job, force=True)
        for callback in self.callbacks:
            try:
                om.MMessage.removeCallback(callback)
            except RuntimeError:
                pass
        self.jobs = []
        self.callbacks = []
        super(SubdivisionManager, self).closeEvent(event)


def show():
    """Open one instance. Safe to rerun or reload the module."""
    global _WINDOW
    app = QtWidgets.QApplication.instance()
    for widget in app.topLevelWidgets():
        if widget.objectName() == WINDOW_NAME:
            widget.close()
    pointer = OpenMayaUI.MQtUtil.mainWindow()
    parent = wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
    _WINDOW = SubdivisionManager(parent)
    _WINDOW.show()
    _WINDOW.raise_()
    _WINDOW.activateWindow()
    return _WINDOW


if __name__ == '__main__':
    show()
