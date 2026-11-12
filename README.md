# Xaia Tools for Maya

An installable Maya module with a **Xaia Tools** menu, organized artist tools,
and a clipboard shared between Maya sessions on the same computer.

## Install

Clone or download this repository to a permanent folder. In Maya, drag
`install.py` into a viewport, or run this in the Python Script Editor:

```python
import runpy
runpy.run_path(r"D:\GitHub\maya-scripts\install.py", run_name="__main__")
```

Change the path if you installed elsewhere. Installation writes only
`XaiaTools.mod` into your Maya user `modules` directory, pointing at this checkout.
It also opens the menu in the current session. The module's own deferred
`userSetup.py` creates the menu on subsequent starts; your existing startup
files and Maya.env are not overwritten. Existing module descriptors are backed
up before replacement. Startup scripts must be enabled in Maya's preferences.

Run the installer snippet in each **already-open** Maya session. After that,
use the top-level **Xaia Tools** menu. Updates are pulled into this checkout;
restart Maya after updating Python code. Rebuild Menu is useful after a menu
was removed, but does not reload existing tool modules.

Manual module install: copy `XaiaTools.mod` to a Maya module search directory
and replace `.` on its first line with this repository's absolute path.

Uninstall: remove the installed `XaiaTools.mod` and restart Maya. To remove
only the current menu, run `from xaia_tools import menu; menu.remove()`.

## Menu

| Group | Tools |
| --- | --- |
| Session Clipboard | Copy Selection, Paste into This Session, Clipboard Window |
| Modeling | Quad Patch |
| Curves | Text to Curves, Arnold Curve Rendering |
| Shading & Materials | Bulk Arnold Material Editor, Convert Shaders to Arnold, Circular Ramp Creator, Collect Materials into Object Set |
| Arnold | Stand-in Viewport Modes, Subdivision Manager, Stand-in & Texture Path Resolver |
| Scene & Naming | Studio Renamer, Group Selected Meshes by Material, Remove Non-default Namespaces |
| Viewport | Framing & Composition Overlay |

Menu entries import tools lazily. Starting Maya and rebuilding the menu do
not load Arnold or run scene cleanup actions. The namespace and grouping
commands act on the scene when clicked; other entries open their respective
windows. Existing behavior of those tools is retained.

## Copy in one session, paste in another

1. In the source Maya, select whole objects, groups, or dependency nodes.
2. Choose **Xaia Tools > Session Clipboard > Copy Selection**.
3. In the destination Maya, choose **Paste into This Session**.

The clipboard exports a Maya ASCII snapshot with hierarchy, materials,
construction history, animation and related dependencies. Source selection,
scene filename and modified state are preserved. Components and attribute
selections are rejected; select whole objects instead.

Paste creates independent objects under a unique `xaiaPaste_001` namespace
(and subsequent numbers), keeps target frame rate and playback range, and
selects the imported hierarchy roots. Existing same-named objects are preserved.
Script-node execution is disabled during import. Required node plugins must
be available in the destination Maya; use compatible Maya/plugin versions.

**Undo limitation:** Maya's scene import clears earlier undo history. The
clipboard plugin makes the latest paste undoable/redoable, but does not restore
history preceding an import. Undo leaves an empty paste namespace reserved so
redo can restore the imported graph. Different frame rates preserve animation
in time, so key positions can become fractional in the destination frame rate.

Textures, stand-in ASS files, simulations and other external dependencies are
not embedded or copied. They must remain accessible to the destination Maya;
relative asset paths require the appropriate Maya project/workspace.

Clipboard files live in `<Maya user directory>/xaia_tools/clipboard`, shared
across Maya versions. Each export has an immutable unique filename and the
latest snapshot is published atomically, so failed/empty copies do not replace
the last successful copy. Concurrent copies use the last successfully published
snapshot. Old snapshots remain on disk; remove them manually when no Maya
session needs them. To choose a different location, set `XAIA_CLIPBOARD_DIR`
to the same directory for both sessions before launching Maya.

The clipboard window displays the last copy's source scene, Maya version,
objects and time. Use Refresh to see a copy made in another session. This is
an object clipboard, separate from Windows text/image clipboard contents.

Python API:

```python
from xaia_tools import session_clipboard
session_clipboard.copy_selection()  # source session
session_clipboard.paste()           # destination session
```

## Arnold tools added here

**Bulk Arnold Material Editor:** Check only the settings you want to apply to
materials on selected meshes, groups or faces. Supports 51 settings in the
installed MtoA version. Shared materials also affect unselected objects using
them. Texture inputs are preserved by default; explicit replacement disconnects
them. Locked and referenced materials are skipped. One undo step per apply.

**Stand-in Viewport Modes:** Selected to Shaded, Selected to Bounding Box,
and ALL in scene to Bounding Box. Multiple selected stand-ins and groups are
supported. Locked/connected settings are skipped. Each action is undoable.

See [Studio Renamer documentation](maya_studio_renamer/README.md) for its naming
workflow, registry and validation tools. The path resolver retains its ASS-file
backup behavior; the viewport overlay retains its non-destructive guides.

## Layout and compatibility

```text
XaiaTools.mod                Maya module descriptor
install.py                   Drag/drop and Script Editor installer
scripts/userSetup.py         Deferred menu startup (skips batch)
scripts/xaia_tools/menu.py    Grouped tool registry and lazy launchers
scripts/xaia_tools/session_clipboard.py
scripts/xaia_tools/clipboard_command.py  Undoable paste command plugin
scripts/xaia_tools/tools/     Canonical implementations of all artist tools
*.py                         Compatibility launchers for old root paths
maya_studio_renamer/          Existing documentation, config example and tests
 tests/                      Native and GUI integration checks
```

Existing root script paths and Studio Renamer's legacy import path remain
available through compatibility launchers. Run them as files or explicitly
call their documented UI functions after import. Imports no longer open
windows or perform scene operations. New integrations should import from
`xaia_tools.tools`, for example:

```python
from xaia_tools.tools import arnold_bulk_edit
arnold_bulk_edit.show()
```

The module requires Python 3 (Maya 2022+). Maya 2026 / PySide6 is the tested
configuration; Qt tools also retain PySide2 fallbacks for earlier Python 3
Maya releases. Arnold-specific tools require MtoA. No pip packages are needed.
The Quad Patch author's original attribution is retained in its source.

## Validation

See [tests/README.md](tests/README.md) for native Maya, separate-process clipboard,
GUI-startup and existing renamer checks. Test scene files and logs stay in
`tests/results/`, which is excluded from Git.

Maya integration references: [module description files](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-DEVHELP/files/Distributing-Maya-Plug-ins/DistributingUsingModules/Maya_DEVHELP_Distributing_Maya_Plug_ins_DistributingUsingModules_ModuleDescriptionFiles_html.html),
[file import/export](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/file.html).

## License and support

Existing repository permission: feel free to use these scripts as you like.
Preserve third-party author notices. Report issues in
[the GitHub repository](https://github.com/Xaia/maya-scripts/issues).
