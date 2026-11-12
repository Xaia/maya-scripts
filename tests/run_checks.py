"""Reproducible native Maya checks. Optional --maya-gui enables UI validation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "tests/results"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mayapy", required=True)
    parser.add_argument("--maya-gui")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, MAYA_SKIP_USERSETUP_PY="1",
               XAIA_CLIPBOARD_DIR=str(RESULTS / "clipboard"))
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "scripts"),
                                        str(ROOT / "maya_studio_renamer"), env.get("PYTHONPATH", "")])
    checks = [("renamer", ["-m", "unittest", "discover", "-s", "maya_studio_renamer/tests", "-v"]),
              ("renamer_arnold", ["tests/renamer_arnold_native.py"]),
              ("bulk", ["tests/test_arnold_bulk_edit.py"]),
              ("standins", ["tests/check_ass_modes.py"])]
    checks.extend((stage, ["tests/module_native.py", stage])
                  for stage in ("copy", "paste", "paste_mixed", "imports"))
    for label, command in checks:
        with (RESULTS / (label + ".log")).open("w", encoding="utf-8") as log:
            result = subprocess.run([args.mayapy] + command, cwd=str(ROOT), env=env,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=180)
        if result.returncode:
            raise RuntimeError("{} failed: {}".format(label, RESULTS / (label + ".log")))
        print("PASS: " + label, flush=True)
    if args.maya_gui:
        env.pop("MAYA_SKIP_USERSETUP_PY", None)
        env["MAYA_APP_DIR"] = str(RESULTS / "maya_profile")
        env["MAYA_MODULE_PATH"] = str(ROOT) + os.pathsep + env.get("MAYA_MODULE_PATH", "")
        outcome = RESULTS / "gui.json"
        if outcome.exists():
            outcome.unlink()
        script = RESULTS / "gui_start.mel"
        python = "import runpy; runpy.run_path({!r}, run_name='__main__')".format((ROOT / "tests/gui_module.py").as_posix())
        script.write_text("python(" + json.dumps(python) + ");\n", encoding="utf-8")
        options = {}
        if sys.platform == "win32":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            options["startupinfo"] = startup
        process = subprocess.Popen([args.maya_gui, "-noAutoloadPlugins", "-log", str(RESULTS / "gui.log"),
                                    "-script", str(script)], env=env, cwd=str(ROOT), **options)
        try:
            process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            process.terminate()
            raise RuntimeError("GUI check timed out. Inspect tests/results/gui.log")
        if not outcome.is_file() or not json.loads(outcome.read_text())["passed"]:
            raise RuntimeError("GUI check failed. Inspect tests/results/gui.json and gui.log")
        print("PASS: GUI startup, all tool windows, menu rebuild, installer", flush=True)


if __name__ == "__main__":
    main()
