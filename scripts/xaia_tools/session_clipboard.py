"""File-backed object clipboard shared by Maya sessions belonging to one user."""
import json
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path

from maya import cmds

WINDOW = "xaiaSessionClipboard"


def clipboard_dir():
    custom = os.environ.get("XAIA_CLIPBOARD_DIR")
    return Path(custom) if custom else Path(cmds.internalVar(userAppDir=True)) / "xaia_tools" / "clipboard"


def read_clipboard():
    manifest = clipboard_dir() / "clipboard.json"
    if not manifest.is_file():
        raise RuntimeError("Clipboard is empty. Copy a selection in the source Maya session first.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    filename = data.get("file", "")
    if data.get("schema") != 1 or Path(filename).name != filename or not filename.endswith(".ma"):
        raise RuntimeError("Clipboard metadata is invalid.")
    if not (clipboard_dir() / filename).is_file():
        raise RuntimeError("The clipboard scene file is missing. Copy again.")
    return data


def copy_selection(*_):
    selection = cmds.ls(selection=True, long=True) or []
    if not selection:
        raise RuntimeError("Select objects, groups, or dependency nodes to copy.")
    if any("." in node for node in selection):
        raise RuntimeError("Select whole objects rather than components or attributes.")
    folder = clipboard_dir()
    folder.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    payload = folder / ("selection_" + token + ".ma")
    scene_name = cmds.file(query=True, sceneName=True)
    modified = cmds.file(query=True, modified=True)
    try:
        cmds.file(str(payload), force=True, type="mayaAscii", exportSelected=True,
                  options="v=0;", preserveReferences=False, constructionHistory=True,
                  channels=True, constraints=True, shader=True, expressions=True)
    finally:
        # Export must not rename the working scene or alter its selection.
        if cmds.file(query=True, sceneName=True) != scene_name:
            cmds.file(rename=scene_name)
        cmds.select(selection, replace=True)
        cmds.file(modified=modified)
    data = {"schema": 1, "file": payload.name, "selection": selection,
            "copied_at": datetime.now(timezone.utc).isoformat(),
            "maya": cmds.about(version=True), "host": socket.gethostname(),
            "scene": scene_name, "workspace": cmds.workspace(query=True, rootDirectory=True),
            "units": {flag: cmds.currentUnit(query=True, **{flag: True})
                      for flag in ("linear", "angle", "time")}}
    temporary = folder / ("manifest_" + token + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Publish only after export succeeds. Concurrent copies cannot expose a
    # partially written scene: every payload has an immutable unique filename.
    os.replace(str(temporary), str(folder / "clipboard.json"))
    print("[Xaia Clipboard] Copied {} selection item(s).".format(len(selection)))
    return data


def paste(*_):
    data = read_clipboard()
    index = 1
    while cmds.namespace(exists="xaiaPaste_{:03d}".format(index)):
        index += 1
    namespace = "xaiaPaste_{:03d}".format(index)
    plugin = str(Path(__file__).with_name("clipboard_command.py"))
    if not cmds.pluginInfo(plugin, query=True, loaded=True):
        cmds.loadPlugin(plugin, quiet=True)
    nodes = cmds.xaiaPasteClipboard(str(clipboard_dir() / data["file"]), namespace) or []
    print("[Xaia Clipboard] Pasted {} node(s) into {}.".format(len(nodes), namespace))
    return nodes


def _run(function, *_):
    try:
        function()
        refresh()
    except Exception as exc:
        cmds.warning(str(exc))
        cmds.scrollField(WINDOW + "Info", edit=True, text=str(exc))


def refresh(*_):
    try:
        data = read_clipboard()
        text = "Copied: {}\nSource: {} (Maya {})\n{} item(s)\n{}".format(
            data["copied_at"], data["scene"] or "Untitled", data["maya"],
            len(data["selection"]), "\n".join(data["selection"]))
    except Exception as exc:
        text = str(exc)
    cmds.scrollField(WINDOW + "Info", edit=True, text=text)


def show():
    from functools import partial
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    cmds.window(WINDOW, title="Xaia | Session Clipboard", widthHeight=(470, 380))
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=("both", 8))
    cmds.text(label="Copy in one Maya session. Paste in another.", height=30)
    cmds.button(label="Copy Selection", height=36, command=partial(_run, copy_selection))
    cmds.button(label="Paste into This Session", height=36, command=partial(_run, paste))
    cmds.text(label="External textures / caches stay on disk. Paste uses a unique namespace.")
    cmds.text(label="Maya import clears earlier undo history. The latest paste can be undone.")
    cmds.scrollField(WINDOW + "Info", editable=False, wordWrap=True, height=110)
    cmds.button(label="Refresh Clipboard Info", command=refresh)
    refresh()
    cmds.showWindow(WINDOW)
