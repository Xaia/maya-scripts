# Studio Renamer for Autodesk Maya

A Maya-native, artist-focused naming tool. Python 3, Maya `cmds`, Qt via PySide6 or PySide2. No pip installation needed.

## Install

1. Unzip the package anywhere Maya can read it, for example `C:\\MayaTools\\StudioRenamer\\`.
2. Open Maya > Windows > General Editors > Script Editor > **Python**.
3. Run the following, changing the folder to the path containing `studio_renamer.py`:

```python
import sys
sys.path.insert(0, r"C:\MayaTools\StudioRenamer")
import studio_renamer
studio_renamer.show()
```

If you modify the source while Maya is open, restart Maya or use:

```python
import importlib
importlib.reload(studio_renamer)
studio_renamer.show()
```

Optional shelf button: make a Python shelf button using the same launch snippet.

## The workflow

### Arnold naming

Arnold nodes use `customname_fullMayaNodeType`, preserving exact spelling and
capitalization: `oak_aiStandardSurface`, `oak_aiColorCorrect`, `oak_aiRange`,
or `oak_aiTriplanar`. Types are discovered from the installed MtoA plugin,
including types missing from the saved suffix registry. The registry is
refreshed on each scan, so loading Arnold after opening the UI is supported.
Old abbreviated Arnold mappings in existing JSON files no longer control
Arnold naming. Other Maya naming rules remain configurable as before.

For a new custom base, enter it and use **Batch Rename** with **Auto by node
type**. **Auto Suffix** preserves each node's existing custom base while
replacing its old suffix. **Shader Network** uses the material base followed
by the exact type for Arnold nodes, without inserting channel labels. Duplicate
types get a number before the type: `oak_001_aiColorCorrect`. Reapplying Auto
Suffix does not append the type a second time. Non-Arnold utilities in a shader
network retain their channel-based names.

The Arnold category includes Arnold shapes automatically. Ordinary transform
nodes retain their transform conventions (`_lgt`, `_ass`, etc.); synchronized
Arnold shapes use their full type, for example `key_lgt` with
`key_aiAreaLight`. Referenced, locked, and default nodes remain protected.

1. Select nodes and choose **Selected**, **Hierarchy**, or **Scene** scope.
2. Optionally filter by geometry, groups, shaders, Arnold, lights, etc.
3. Choose an action, for example **Auto Suffix**, **Quick Fix**, **Fix Duplicates**, or **Preview Batch Rename**.
4. Review and, if needed, double-click a **Proposed Name** to edit it.
5. Click **Apply Rename**. Each batch is a single Maya Undo step.

`Fix Duplicates` scans for global conflicts but only changes eligible nodes within your requested scope. If only some of the conflicting nodes are editable, run a full scene audit to inspect unresolved names.

## Features

- Type-aware `_geo`, `_grp`, `_crv`, `_srf`, `_jnt`, `_loc`, `_cam`, `_lgt`, `_ass`, `_vol`, `_shd`, `_sg`, `_tex`, and many more mappings.
- Arnold shaders, utility nodes, texture nodes, AOV nodes, drivers, filters, light types and stand-ins.
- Configurable, automatic global short-name collision detection, including across namespaces.
- Rename selected nodes, hierarchies, or filtered scene-wide collections.
- Batch naming, custom prefix/suffix, deterministic numbers, adjustable padding and starting index.
- Regular-expression and case-insensitive find/replace.
- Auto-suffix, name cleanup, sequential renumbering, name-from-parent, duplicate correction.
- Optional predictable shape synchronization, including `OrigShape` names and multi-shape numbering.
- Shader-network rename with channel-aware utility naming and conservative handling of shared nodes.
- Naming audit, select preview rows in Maya, export JSON report.
- Preserves namespaces and skips referenced/locked/default nodes.
- UUID-backed planning, two-stage collision-safe rename, scene-staleness check, one-step Undo.
- Minimal compact Maya-dark Qt interface with searchable/sortable editable preview.

## Edit the suffix registry

On first launch, Studio Renamer writes a JSON registry to:

- Windows: inside your Maya user application directory, under `studio_renamer/suffix_registry.json`
- Linux: inside your Maya user application directory, under `studio_renamer/suffix_registry.json`

You can locate it using **Registry / Settings** in the tool. The included `suffix_registry.example.json` is an editable reference copy; the tool creates its own live user copy on first launch.

Example edits in your user registry:

```json
{
  "type_suffixes": {
    "aiStandardSurface": "shd",
    "file": "tex",
    "myStudioCustomNode": "custom"
  },
  "transform_shape_overrides": {
    "myStudioScatterShape": "scatter"
  }
}
```

User-defined mappings override the defaults. Any omitted mapping inherits its built-in default. Edit the live file, then click **Registry / Settings > Reload Registry**.

## Pipeline use, without the UI

```python
import studio_renamer
studio_renamer.rename_selection_auto(sync_shapes=True)
issues = studio_renamer.validate_scene()
for issue in issues:
    print(issue["old_path"], issue["note"])
```

The engine and preview are usable independently of the UI:

```python
engine = studio_renamer.Engine()
plan = engine.preview("Auto Suffix", scope="Hierarchy", sync_shapes=True)
for row in plan.rows:
    print(row.old_path, "->", row.new_name, row.status)
engine.apply(plan)
```

## Design and safety notes

- **Strict uniqueness** means identical short names are treated as conflicts even when Maya permits them under different DAG parents or namespaces. Already duplicated nodes outside the chosen scope remain unchanged. The validator will still report them.
- Referenced, locked, protected, or undeletable nodes are never silently unlocked or renamed. They reserve their short names. Some scene-wide duplicate names may therefore be unresolvable until the originating reference or lock is changed.
- Maya normally auto-renames shapes when their transform is renamed. This tool passes `ignoreShape=True` and explicitly synchronizes shapes when requested.
- Instanced shapes with multiple parents are skipped by automatic shape-sync to avoid guessing which parent should own the name.
- Auto Suffix only renames node types present in the mapping or identifiable from Maya type classification. Unsupported and UFE/USD prim nodes are not automatically renamed through `maya.cmds`.
- Shading-network capture is deliberately conservative. Shared upstream nodes, uncertain connections, and multiple materials on a mesh can require manual review. Displacement networks not connected upstream to the selected surface shader are not automatically traversed.
- A saved preview is invalidated if scene node names/paths change before applying. Click Preview again.
- The execution engine attempts to undo the entire batch if an unexpected Maya command fails. Check the undo stack and scene after any exceptional Maya/plugin failure.
- Auditing very large scenes scans all dependency/DAG nodes. The Qt table uses a model/view rather than creating individual UI widgets per row.

## Tests

Pure-Python tests for the allocator and a mocked Maya rename transaction can be run outside Maya:

```bash
python -m unittest discover -s tests -v
```

The suite covers short-name collisions, namespaces, protected nodes, swaps, invalid names, stale previews, collision numbering and rollback. Maya API, Qt, Arnold graph and scene-integration behavior still require an interactive Maya test scene. This release has **not** been executed inside Maya here.
