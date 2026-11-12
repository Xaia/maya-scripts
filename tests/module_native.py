"""Separate-process Maya integration checks. Run with mayapy and a stage."""
import os
import sys
from pathlib import Path
os.environ["MAYA_SKIP_USERSETUP_PY"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as c
from xaia_tools import session_clipboard as clip


def check_copy():
    c.undoInfo(state=True, infinity=True)
    cube = c.polyCube(name="sharedName")[0]
    sphere = c.polySphere(name="sphere")[0]
    group = c.group(cube, sphere, name="asset")
    shader = c.shadingNode("lambert", asShader=True, name="copy_material")
    sg = c.sets(renderable=True, noSurfaceShader=True, empty=True)
    c.connectAttr(shader + ".outColor", sg + ".surfaceShader")
    c.sets(cube, edit=True, forceElement=sg)
    c.setAttr(shader + ".color", 0.2, 0.4, 0.6, type="double3")
    c.setKeyframe(cube, attribute="translateX", time=1, value=3)
    c.setKeyframe(cube, attribute="translateX", time=10, value=8)
    c.select(group)
    c.file(rename=str(ROOT / "tests/results/source.ma"))
    c.file(modified=False)
    before = c.ls(selection=True, long=True)
    name = c.file(query=True, sceneName=True)
    data = clip.copy_selection()
    assert len(data["selection"]) == 1
    assert c.ls(selection=True, long=True) == before
    assert c.file(query=True, sceneName=True) == name
    assert not c.file(query=True, modified=True)
    old = clip.read_clipboard()["file"]
    c.select(clear=True)
    try:
        clip.copy_selection()
    except RuntimeError:
        pass
    else:
        raise AssertionError("empty selection accepted")
    assert clip.read_clipboard()["file"] == old
    c.select(cube + ".vtx[0]")
    try:
        clip.copy_selection()
    except RuntimeError:
        pass
    else:
        raise AssertionError("component selection accepted")


def check_paste(frame_rate="film"):
    c.undoInfo(state=True, infinity=True)
    original = c.polyCube(name="sharedName")[0]
    c.currentUnit(time=frame_rate)
    c.playbackOptions(minTime=101, maxTime=150)
    c.select(original)
    nodes = clip.paste()
    assert nodes
    assert c.objExists("sharedName")
    assert c.objExists("xaiaPaste_001:asset")
    assert c.objExists("xaiaPaste_001:sharedName")
    assert c.ls(selection=True, long=True) == ["|xaiaPaste_001:asset"]
    assert c.keyframe("xaiaPaste_001:sharedName", attribute="translateX", query=True, keyframeCount=True) == 2
    assert c.objExists("xaiaPaste_001:copy_material")
    assert c.currentUnit(query=True, time=True) == frame_rate
    assert c.playbackOptions(query=True, minTime=True) == 101
    clip.paste()
    assert c.objExists("xaiaPaste_002:asset")
    c.undo()
    assert not c.objExists("xaiaPaste_002:asset")
    assert not c.objExists("xaiaPaste_002:copy_material")
    assert c.objExists("xaiaPaste_001:asset")
    c.redo()
    assert c.objExists("xaiaPaste_002:asset"), (c.ls("*asset*", recursive=True), c.namespaceInfo(listOnlyNamespaces=True))
    assert c.objExists("xaiaPaste_002:copy_material")
    c.undo()
    # Maya scene import flushes earlier history; only the latest paste has an
    # undo command. Earlier pasted objects are intentionally still present.
    assert c.objExists("xaiaPaste_001:asset")
    assert c.objExists("sharedName")


def check_imports():
    from xaia_tools.menu import TOOLS
    import importlib
    before = set(c.ls())
    for _, _, module, entry in TOOLS:
        tool = importlib.import_module("xaia_tools.tools." + module)
        assert callable(getattr(tool, entry)), module
    assert set(c.ls()) == before, "Importing tools modified scene"
    import arnold_bulk_edit
    assert arnold_bulk_edit is importlib.import_module("xaia_tools.tools.arnold_bulk_edit")


try:
    {"copy": check_copy, "paste": check_paste, "paste_mixed": lambda: check_paste("pal"),
     "imports": check_imports}[sys.argv[1]]()
    print("XAIA NATIVE PASS: " + sys.argv[1])
finally:
    maya.standalone.uninitialize()
