"""Maya Python plugin: give file import a real object-level undo/redo operation."""
import maya.api.OpenMaya as om
import maya.cmds as cmds


def maya_useNewAPI():
    pass


class PasteCommand(om.MPxCommand):
    def isUndoable(self):
        return True

    def doIt(self, args):
        self.previous = om.MGlobal.getActiveSelectionList()
        self.namespace = args.asString(1)
        self.filepath = args.asString(0)
        self._import()

    def _import(self):
        before = set(cmds.ls(uuid=True))
        try:
            self.nodes = cmds.file(self.filepath, i=True, type="mayaAscii",
                                   namespace=self.namespace, mergeNamespacesOnClash=False,
                                   returnNewNodes=True, preserveReferences=False,
                                   executeScriptNodes=False, importFrameRate=False,
                                   importTimeRange="keep") or []
        except Exception:
            # A failed file import can still have created nodes.
            created = [n for n in cmds.ls(long=True)
                       if cmds.ls(n, uuid=True)[0] not in before]
            if created:
                cmds.delete(created)
            if cmds.namespace(exists=self.namespace):
                cmds.namespace(removeNamespace=self.namespace)
            om.MGlobal.setActiveSelectionList(self.previous)
            raise
        objects, roots = [], []
        imported = set()
        for name in self.nodes:
            if not cmds.objExists(name):
                continue
            selection = om.MSelectionList()
            selection.add(name)
            node = selection.getDependNode(0)
            imported.add(om.MFnDependencyNode(node).uuid().asString())
            objects.append(node)
        self.deletion = None
        self.delete_objects = []
        for node in objects:
            if node.hasFn(om.MFn.kDagNode):
                fn = om.MFnDagNode(node)
                if any(om.MFnDependencyNode(fn.parent(i)).uuid().asString() in imported
                       for i in range(fn.parentCount())):
                    continue
                if node.hasFn(om.MFn.kTransform):
                    roots.append(fn.fullPathName())
            self.delete_objects.append(node)
        self.pasted = om.MSelectionList()
        for name in roots or [n for n in self.nodes if cmds.objExists(n)]:
            self.pasted.add(name)
        om.MGlobal.setActiveSelectionList(self.pasted)
        self.setResult(self.nodes)

    def undoIt(self):
        if self.deletion is None:
            self.deletion = om.MDagModifier()
            for node in self.delete_objects:
                self.deletion.deleteNode(node)
        self.deletion.doIt()
        om.MGlobal.setActiveSelectionList(self.previous)

    def redoIt(self):
        self.deletion.undoIt()
        om.MGlobal.setActiveSelectionList(self.pasted)


def initializePlugin(plugin):
    om.MFnPlugin(plugin, "Xaia", "1.0.0", "Any").registerCommand("xaiaPasteClipboard", PasteCommand)


def uninitializePlugin(plugin):
    om.MFnPlugin(plugin).deregisterCommand("xaiaPasteClipboard")
