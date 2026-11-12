"""Native Maya check; run with mayapy in its own process."""
import os
import sys
from pathlib import Path
os.environ["MAYA_SKIP_USERSETUP_PY"] = "1"
import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as c
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ass_viewport_modes as tool

try:
    c.loadPlugin("mtoa", quiet=True)
    c.undoInfo(state=True)
    shapes = [c.createNode("aiStandIn", name="standin{}Shape".format(i)) for i in range(3)]
    transforms = [c.listRelatives(s, parent=True)[0] for s in shapes]
    group_a = c.group(transforms[0], name="groupA")
    group_b = c.group(transforms[1], name="groupB")
    c.select(group_a, group_b)
    selected = c.ls(selection=True, long=True)
    r = tool.set_mode("Shaded")
    assert len(r["changed"]) == 2, r
    assert [c.getAttr(s + ".mode") for s in shapes] == [6, 6, 0]
    assert c.ls(selection=True, long=True) == selected
    c.undo()
    assert [c.getAttr(s + ".mode") for s in shapes] == [0, 0, 0]
    c.select(shapes[0])
    assert len(tool.set_mode("Shaded")["changed"]) == 1
    assert len(tool.set_mode("Bounding Box")["changed"]) == 1
    for s in shapes:
        c.setAttr(s + ".mode", 6)
    c.select(clear=True)
    assert len(tool.set_mode("Bounding Box", all_scene=True)["changed"]) == 3
    c.undo()
    assert [c.getAttr(s + ".mode") for s in shapes] == [6, 6, 6]
    c.setAttr(shapes[0] + ".mode", lock=True)
    r = tool.set_mode("Bounding Box", all_scene=True)
    assert len(r["changed"]) == 2 and len(r["skipped"]) == 1, r
    c.select(clear=True)
    assert not tool.set_mode("Shaded")["changed"]
    print("ASS MODES: PASS (groups, multiple selection, shapes, scene-wide, locks, undo)")
finally:
    maya.standalone.uninitialize()
