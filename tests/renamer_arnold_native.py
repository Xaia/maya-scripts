"""Validate Arnold naming against every registered MtoA node type and real graphs."""
import copy
import os
import sys
from pathlib import Path
os.environ["MAYA_SKIP_USERSETUP_PY"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as c
from xaia_tools.tools import studio_renamer as sr

try:
    c.loadPlugin("mtoa", quiet=True)
    c.undoInfo(state=True, infinity=True)
    registry = sr.Registry(copy.deepcopy(sr.DEFAULT_REGISTRY))
    types = c.pluginInfo("mtoa", query=True, dependNode=True)
    for typ in types:
        node = sr.Node(typ, "oak", typ, "", "oak", False)
        assert registry.suffix_for(node) == typ, typ
        assert sr.suffix_filter(node, registry, "Arnold"), typ
    shader = c.shadingNode("aiStandardSurface", asShader=True, name="old_shd")
    a = c.shadingNode("aiColorCorrect", asUtility=True, name="old_cc")
    b = c.shadingNode("aiColorCorrect", asUtility=True, name="another_cc")
    c.connectAttr(a + ".outColor", b + ".input")
    c.connectAttr(b + ".outColor", shader + ".baseColor")
    c.select(shader)
    engine = sr.Engine(registry)
    plan = engine.preview("Shader Network", base="oak")
    names = {row.new_name for row in plan.rows}
    assert {"oak_aiStandardSurface", "oak_aiColorCorrect", "oak_001_aiColorCorrect"} <= names, names
    engine.apply(plan)
    assert c.isConnected("oak_aiColorCorrect.outColor", "oak_001_aiColorCorrect.input") or c.isConnected("oak_001_aiColorCorrect.outColor", "oak_aiColorCorrect.input")
    c.undo()
    assert c.objExists(shader) and c.objExists(a) and c.objExists(b)
    c.select(shader, a, b)
    plan = engine.preview("Batch Rename", base="wood", category="Arnold")
    assert all(row.new_name.endswith("_" + row.node_type) for row in plan.rows)
    engine.apply(plan)
    plan = engine.preview("Auto Suffix", category="Arnold")
    assert not plan.changes(), [(r.old_name, r.new_name) for r in plan.rows]
    c.undo()
    # Arnold shape synchronization keeps the full type suffix rather than Shape.
    standin = c.createNode("aiStandIn", name="standinShape")
    parent = c.listRelatives(standin, parent=True, fullPath=True)[0]
    c.select(parent)
    plan = engine.preview("Batch Rename", base="rock", category="Arnold", sync_shapes=True)
    assert any(r.new_name == "rock_aiStandIn" for r in plan.rows), [(r.old_name, r.new_name) for r in plan.rows]
    engine.apply(plan)
    assert c.nodeType("rock_aiStandIn") == "aiStandIn"
    assert c.objExists("rock_ass")
    c.undo()
    assert c.objExists(standin)
    print("ARNOLD RENAMER PASS: {} registered node types, real network, batch, repeat, shapes, undo".format(len(types)))
finally:
    maya.standalone.uninitialize()
