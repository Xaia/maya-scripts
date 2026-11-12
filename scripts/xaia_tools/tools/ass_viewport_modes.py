"""Small Maya window for Arnold stand-in viewport modes. Run or call show()."""
from functools import partial
import maya.cmds as cmds

WINDOW = "assViewportModesWindow"


def standins(all_scene=False):
    """Find stand-in shapes under any number of selected shapes/groups."""
    if all_scene:
        nodes = cmds.ls(type="aiStandIn", long=True) or []
    else:
        nodes = []
        for item in cmds.ls(selection=True, objectsOnly=True, long=True) or []:
            if cmds.nodeType(item) == "aiStandIn":
                nodes.append(item)
            elif cmds.objectType(item, isAType="transform"):
                nodes.extend(cmds.listRelatives(item, allDescendents=True,
                                                fullPath=True, type="aiStandIn") or [])
    # An instanced shape can have multiple paths; its mode is shared.
    unique = {}
    for node in nodes:
        unique.setdefault(cmds.ls(node, uuid=True)[0], node)
    return list(unique.values())


def set_mode(label, all_scene=False):
    """Set Bounding Box or Shaded on targets; preserve selection and allow undo."""
    nodes = standins(all_scene)
    result = {"changed": [], "skipped": [], "unchanged": []}
    if not nodes:
        cmds.warning("No Arnold stand-ins found." if all_scene else
                     "Select Arnold stand-ins or groups containing them.")
        return result
    # Read enum values from MtoA instead of assuming their numeric indices.
    enum = cmds.attributeQuery("mode", node=nodes[0], listEnum=True)[0]
    modes, index = {}, 0
    for entry in enum.split(":"):
        if "=" in entry:
            entry, number = entry.rsplit("=", 1)
            index = int(number)
        modes[entry] = index
        index += 1
    if label not in modes:
        raise ValueError("Unsupported stand-in viewport mode: " + label)
    cmds.undoInfo(openChunk=True, chunkName="ASS Viewport Mode")
    try:
        for node in nodes:
            plug = node + ".mode"
            try:
                if (cmds.getAttr(plug, lock=True)
                        or any(cmds.lockNode(node, query=True, lock=True))
                        or cmds.listConnections(plug, source=True, destination=False)):
                    result["skipped"].append(node)
                    continue
                if cmds.getAttr(plug) == modes[label]:
                    result["unchanged"].append(node)
                    continue
                cmds.setAttr(plug, modes[label])
                result["changed"].append(node)
            except RuntimeError as exc:
                result["skipped"].append(node)
                cmds.warning("{}: {}".format(node, exc))
    finally:
        cmds.undoInfo(closeChunk=True)
    message = "{}: {} changed, {} already set, {} skipped.".format(
        label, len(result["changed"]), len(result["unchanged"]), len(result["skipped"]))
    print("[ASS Viewport] " + message)
    if result["skipped"]:
        cmds.warning("Skipped locked/connected/uneditable stand-ins: " +
                     ", ".join(result["skipped"]))
    return result


def _click(label, all_scene, *_):
    result = set_mode(label, all_scene)
    cmds.text(WINDOW + "Status", edit=True, label="{} changed | {} already set | {} skipped".format(
        len(result["changed"]), len(result["unchanged"]), len(result["skipped"])))


def show():
    if not cmds.pluginInfo("mtoa", query=True, loaded=True):
        cmds.loadPlugin("mtoa", quiet=True)
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    cmds.window(WINDOW, title="ASS Viewport Modes", widthHeight=(340, 180), sizeable=False)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=7,
                      columnAttach=("both", 8))
    cmds.text(label="Select stand-ins or groups (multiple supported).", height=24)
    cmds.button(label="Selected  →  Shaded", height=30,
                command=partial(_click, "Shaded", False))
    cmds.button(label="Selected  →  Bounding Box", height=30,
                command=partial(_click, "Bounding Box", False))
    cmds.separator(height=6, style="in")
    cmds.button(label="ALL in scene  →  Bounding Box", height=34,
                backgroundColor=(0.40, 0.30, 0.20),
                command=partial(_click, "Bounding Box", True))
    cmds.text(WINDOW + "Status", label="Each action is one undo step.", height=24)
    cmds.showWindow(WINDOW)


if __name__ == "__main__":
    show()
