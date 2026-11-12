"""Run only in a disposable Maya GUI process, with this repo on MAYA_MODULE_PATH."""
import json
import sys
import traceback
from pathlib import Path
import maya.cmds as cmds
import maya.utils
import maya.OpenMayaUI as omui
from PySide6 import QtCore, QtWidgets
from shiboken6 import wrapInstance

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "tests/results/gui.json"


def run():
    report = {"passed": False, "tools": {}}
    try:
        assert cmds.menu("xaiaToolsMenu", exists=True), "Module startup did not create menu"
        from xaia_tools import menu, session_clipboard
        assert Path(cmds.moduleInfo(moduleName="XaiaTools", path=True)).resolve() == ROOT.resolve()
        cmds.loadPlugin("mtoa", quiet=True)
        before = set(cmds.ls())
        menu.install()
        menu.install()
        for category, label, name, entry in menu.TOOLS:
            if name in ("mat_to_group", "remove_name_spaces"):
                report["tools"][name] = "registered scene action; not executed"
                continue
            # Call directly so errors cannot be swallowed by the menu handler.
            import importlib
            try:
                tool = importlib.import_module("xaia_tools.tools." + name)
                window = getattr(tool, entry)()
                if window is not None:
                    menu._windows[name] = window
                report["tools"][name] = "window opened"
            except Exception:
                report["tools"][name] = traceback.format_exc()
        session_clipboard.show()
        assert all(not value.startswith("Traceback") for value in report["tools"].values()), "Tool launch errors"
        assert set(cmds.ls()) == before, "Opening windows modified scene nodes"
        # Installing into a fixture verifies the descriptor without modifying
        # the artist's Maya configuration during this check.
        import runpy
        installer = runpy.run_path(str(ROOT / "install.py"))
        descriptor = installer["install"](ROOT / "tests/results/modules")
        assert descriptor.is_file()
        assert cmds.menu("xaiaToolsMenu", exists=True)
        widget = wrapInstance(int(omui.MQtUtil.findWindow(session_clipboard.WINDOW)), QtWidgets.QWidget)
        widget.grab().save(str(ROOT / "tests/results/clipboard.png"))
        report["passed"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        RESULT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        cmds.quit(force=True)


maya.utils.executeDeferred(lambda: QtCore.QTimer.singleShot(1500, run))
