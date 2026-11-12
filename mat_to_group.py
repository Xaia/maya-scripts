"""Compatibility launcher; implementation lives in xaia_tools.tools."""
import importlib
import sys
from pathlib import Path
_scripts = str(Path(__file__).resolve().parents[0] / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
_tool = importlib.import_module("xaia_tools.tools.mat_to_group")
if __name__ == "__main__":
    _tool.group_selected_meshes_by_material_in_their_top_group()
else:
    sys.modules[__name__] = _tool
