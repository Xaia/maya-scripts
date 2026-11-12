"""Run with mayapy; uses real Maya meshes, MtoA shaders, and undo."""

import os
import sys
import unittest
from pathlib import Path

os.environ["MAYA_SKIP_USERSETUP_PY"] = "1"
import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import arnold_bulk_edit as bulk


class BulkEditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bulk.ensure_arnold()

    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.a, self.sg_a = self.material("mat_a")
        self.b, self.sg_b = self.material("mat_b")
        self.cube = cmds.polyCube(name="cube")[0]
        cmds.sets(self.cube, edit=True, forceElement=self.sg_a)

    @staticmethod
    def material(name):
        shader = cmds.shadingNode("aiStandardSurface", asShader=True, name=name)
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
        cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader")
        return shader, sg

    def test_shared_material_deduplicated_and_selection_preserved(self):
        other = cmds.polyCube(name="other")[0]
        cmds.sets(other, edit=True, forceElement=self.sg_a)
        cmds.select([self.cube, other])
        before = cmds.ls(selection=True, long=True)
        result = bulk.apply_settings({"specularRoughness": 0.45, "coat": 0.2})
        self.assertEqual(len(result["changed"]), 2)
        self.assertEqual(before, cmds.ls(selection=True, long=True))
        self.assertAlmostEqual(cmds.getAttr(self.a + ".specularRoughness"), 0.45)
        self.assertAlmostEqual(cmds.getAttr(self.a + ".coat"), 0.2)
        self.assertAlmostEqual(cmds.getAttr(self.b + ".coat"), 0.0)

    def test_faces_and_mixed_object_component_selection(self):
        cmds.sets(self.cube + ".f[0:2]", edit=True, forceElement=self.sg_b)
        self.assertEqual(bulk.discover_materials([self.cube + ".f[0:1]"])["materials"], [self.b])
        self.assertEqual(bulk.discover_materials([self.cube + ".f[3:5]"])["materials"], [self.a])
        self.assertEqual(bulk.discover_materials([self.cube + ".f[0]", self.cube + ".f[4]"])["materials"], [self.a, self.b])
        for items in ([self.cube, self.cube + ".f[0]"], [self.cube + ".f[0]", self.cube]):
            self.assertEqual(bulk.discover_materials(items)["materials"], [self.a, self.b])

    def test_edges_vertices_and_uv_conversion(self):
        cmds.sets(self.cube + ".f[0:2]", edit=True, forceElement=self.sg_b)
        for component in (".vtx[0:7]", ".e[0:11]", ".map[*]"):
            with self.subTest(component=component):
                self.assertEqual(bulk.discover_materials([self.cube + component])["materials"], [self.a, self.b])

    def test_group_hierarchy_and_intermediate_shape(self):
        group = cmds.group(self.cube, name="meshes")
        cmds.polyCube(name="ignored")
        shape = cmds.createNode("mesh", name="intermediate", parent=group)
        cmds.setAttr(shape + ".intermediateObject", True)
        found = bulk.discover_materials([group])
        self.assertEqual(found["materials"], [self.a])
        self.assertEqual(len(found["meshes"]), 1)

    def test_per_instance_assignments(self):
        instance = cmds.instance(self.cube, name="cube_instance")[0]
        cmds.sets(instance, edit=True, forceElement=self.sg_b)
        self.assertEqual(bulk.discover_materials([self.cube])["materials"], [self.a])
        self.assertEqual(bulk.discover_materials([instance])["materials"], [self.b])

    def test_connection_preservation_and_explicit_disconnect_undo(self):
        texture = cmds.shadingNode("file", asTexture=True)
        cmds.connectAttr(texture + ".outColor", self.a + ".baseColor")
        cmds.connectAttr(texture + ".outAlpha", self.a + ".specularRoughness")
        settings = {"baseColor": (0.1, 0.2, 0.3), "specularRoughness": 0.6}
        first = bulk.apply_settings(settings, [self.cube])
        self.assertEqual(len(first["skipped"]), 2)
        self.assertFalse(first["changed"])
        self.assertTrue(cmds.isConnected(texture + ".outColor", self.a + ".baseColor"))
        result = bulk.apply_settings(settings, [self.cube], disconnect_inputs=True)
        self.assertEqual(len(result["changed"]), 2, result)
        self.assertFalse(cmds.isConnected(texture + ".outColor", self.a + ".baseColor"))
        self.assertAlmostEqual(cmds.getAttr(self.a + ".baseColorG"), 0.2)
        cmds.undo()
        self.assertTrue(cmds.isConnected(texture + ".outColor", self.a + ".baseColor"))
        self.assertTrue(cmds.isConnected(texture + ".outAlpha", self.a + ".specularRoughness"))

    def test_child_channel_connections_and_locks(self):
        texture = cmds.shadingNode("file", asTexture=True)
        cmds.connectAttr(texture + ".outAlpha", self.a + ".baseColorR")
        cmds.setAttr(self.a + ".specularColorG", lock=True)
        result = bulk.apply_settings({"baseColor": (0.2, 0.3, 0.4), "specularColor": (0.1, 0.2, 0.3)}, [self.cube])
        self.assertEqual(len(result["skipped"]), 2)
        self.assertFalse(result["changed"])
        result = bulk.apply_settings({"baseColor": (0.2, 0.3, 0.4)}, [self.cube], disconnect_inputs=True)
        self.assertEqual(len(result["changed"]), 1, result)
        cmds.undo()
        self.assertTrue(cmds.isConnected(texture + ".outAlpha", self.a + ".baseColorR"))

    def test_scalar_locks_and_locked_node(self):
        cmds.setAttr(self.a + ".coat", lock=True)
        result = bulk.apply_settings({"coat": 0.8, "specularRoughness": 0.7}, [self.cube])
        self.assertEqual(result["changed"], [self.a + ".specularRoughness"])
        self.assertEqual(len(result["skipped"]), 1)
        cmds.lockNode(self.a, lock=True)
        result = bulk.apply_settings({"specularRoughness": 0.2}, [self.cube])
        self.assertFalse(result["changed"])
        cmds.lockNode(self.a, lock=False)

    def test_all_value_types_and_single_undo(self):
        settings = {"coat": 0.75, "baseColor": (0.2, 0.3, 0.4),
                    "subsurfaceRadius": (1.0, 0.5, 0.2), "thinWalled": True,
                    "subsurfaceType": "randomwalk", "dielectricPriority": 2}
        before = {a: cmds.getAttr(self.a + "." + a) for a in settings}
        result = bulk.apply_settings(settings, [self.cube])
        self.assertEqual(len(result["changed"]), len(settings), result)
        self.assertFalse(result["skipped"])
        self.assertEqual(cmds.getAttr(self.a + ".dielectricPriority"), 2)
        cmds.undo()
        self.assertEqual({a: cmds.getAttr(self.a + "." + a) for a in settings}, before)

    def test_invalid_request_does_not_partially_apply(self):
        for invalid in ({"coat": 0.2, "typo": 0.5}, {"coat": 0.2, "metalness": -1},
                        {"coat": 0.2, "base": float("nan")}, {"baseColor": (1, 2)},
                        {"thinWalled": 4}, {"subsurfaceType": 999}, {"dielectricPriority": 0.5}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    bulk.apply_settings(invalid, [self.cube])
                self.assertEqual(cmds.getAttr(self.a + ".coat"), 0)

    def test_empty_unsupported_and_non_mesh_selection(self):
        self.assertEqual(bulk.apply_settings({"coat": 1}, [])["changed"], [])
        light = cmds.directionalLight()
        found = bulk.discover_materials([light, self.a])
        self.assertFalse(found["materials"])
        self.assertEqual(len(found["ignored"]), 2)
        lambert = cmds.shadingNode("lambert", asShader=True, name="test_lambert")
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
        cmds.connectAttr(lambert + ".outColor", sg + ".surfaceShader")
        cmds.sets(self.cube, edit=True, forceElement=sg)
        result = bulk.apply_settings({"coat": 1}, [self.cube])
        self.assertFalse(result["changed"])
        self.assertEqual(result["unsupported"], [lambert])

    def test_all_exposed_attributes_accept_plugin_defaults(self):
        settings = {a: s["default"] for a, s in bulk.attribute_specs().items()}
        result = bulk.apply_settings(settings, [self.cube])
        self.assertEqual(len(result["changed"]), len(settings), result)
        self.assertFalse(result["skipped"])

    def test_failed_write_restores_disconnected_inputs(self):
        from unittest.mock import patch
        texture = cmds.shadingNode("file", asTexture=True)
        cmds.connectAttr(texture + ".outColor", self.a + ".baseColor")
        old = cmds.getAttr(self.a + ".baseColor")
        original_set = bulk._set_value
        new = (0.1, 0.2, 0.3)

        def fail_new_value(plug, value, spec):
            if value == new:
                raise RuntimeError("Simulated write failure")
            original_set(plug, value, spec)

        with patch.object(bulk, "_set_value", side_effect=fail_new_value):
            result = bulk.apply_settings({"baseColor": new}, [self.cube], disconnect_inputs=True)
        self.assertFalse(result["changed"])
        self.assertEqual(len(result["skipped"]), 1)
        self.assertFalse(result["rollback_errors"])
        self.assertTrue(cmds.isConnected(texture + ".outColor", self.a + ".baseColor"))
        self.assertEqual(cmds.getAttr(self.a + ".baseColor"), old)

    def test_referenced_material_skipped(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "referenced.ma")
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(new=True, force=True)
            cmds.file(path, reference=True, namespace="ref")
            result = bulk.apply_settings({"coat": 0.8}, ["ref:cube"])
            self.assertFalse(result["changed"])
            self.assertEqual(result["skipped"][0]["reason"], "referenced material")
            cmds.file(new=True, force=True)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BulkEditTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    maya.standalone.uninitialize()
    sys.exit(0 if result.wasSuccessful() else 1)
