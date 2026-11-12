"""Compatibility launcher; implementation lives in xaia_tools.tools."""
import importlib
import sys
from pathlib import Path
_scripts = str(Path(__file__).resolve().parents[0] / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
_tool = importlib.import_module("xaia_tools.tools.render_curves")
if __name__ == "__main__":
    _tool.show_arnold_curves_tool()
else:
    sys.modules[__name__] = _tool
