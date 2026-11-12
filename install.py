"""Run in Maya's Python editor or drag this file into a Maya viewport."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def install(modules_dir=None):
    from maya import cmds
    directory = Path(modules_dir) if modules_dir else Path(cmds.internalVar(userAppDir=True)) / "modules"
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = directory / "XaiaTools.mod"
    content = "+ XaiaTools 1.0.0 {}\nPYTHONPATH+:=scripts\n".format(ROOT.as_posix())
    if descriptor.exists() and descriptor.read_text(encoding="utf-8") != content:
        descriptor.with_suffix(".mod.bak").write_bytes(descriptor.read_bytes())
    descriptor.write_text(content, encoding="utf-8")
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import xaia_tools
    xaia_tools.show_menu()
    print("Xaia Tools installed: {}. Startup menu available after restarting Maya.".format(descriptor))
    return descriptor


def onMayaDroppedPythonFile(*_):
    install()


if __name__ == "__main__":
    install()
