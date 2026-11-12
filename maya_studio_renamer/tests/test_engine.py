"""Non-Maya tests for planning logic and transactional rename behavior.
Run: python -m unittest discover -s tests -v
"""
import json
import unittest
from unittest import mock

import studio_renamer as sr


class FakeScene:
    def __init__(self, nodes, reg=None):
        self.registry = reg or sr.Registry(json.loads(json.dumps(sr.DEFAULT_REGISTRY)))
        self.nodes = {n.uid: n for n in nodes}
        self.signature = tuple(sorted((n.uid, n.path) for n in nodes))


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.a = sr.Node("id-a", "|a_grp|wheel_geo", "transform", "", "wheel_geo", True)
        self.b = sr.Node("id-b", "|b_grp|wheel_geo", "transform", "", "wheel_geo", True)
        self.c = sr.Node("id-c", "another_geo", "transform", "", "another_geo", False)

    def test_unique_global_names(self):
        scene = FakeScene([self.a, self.b, self.c])
        plan = sr.Planner(scene).create([
            sr.Intent("id-a", "wheel_geo"), sr.Intent("id-b", "wheel_geo")], "fix")
        self.assertEqual({r.new_name for r in plan.rows}, {"wheel_geo", "wheel_001_geo"})
        self.assertEqual(len(plan.changes()), 1)

    def test_external_node_occupies_name(self):
        scene = FakeScene([self.a, self.c])
        p = sr.Planner(scene).create([sr.Intent("id-c", "wheel_geo")], "rename")
        self.assertEqual(p.rows[0].new_name, "wheel_001_geo")
        self.assertEqual(p.rows[0].status, "Resolved")

    def test_swaps(self):
        scene = FakeScene([self.a, self.c])
        p = sr.Planner(scene).create([
            sr.Intent("id-a", "another_geo"), sr.Intent("id-c", "wheel_geo")], "rename")
        self.assertEqual({r.new_name for r in p.rows}, {"another_geo", "wheel_geo"})
        self.assertEqual(len(p.changes()), 2)

    def test_locked_node_skip_and_reservation(self):
        self.a.editable = False
        self.a.skip_reason = "Locked node"
        scene = FakeScene([self.a, self.c])
        p = sr.Planner(scene).create([
            sr.Intent("id-a", "new_geo"), sr.Intent("id-c", "wheel_geo")], "rename")
        self.assertEqual(p.rows[0].new_name, "wheel_001_geo")
        self.assertEqual(p.rows[1].status, "Skipped")

    def test_conflict_policy_skip(self):
        scene = FakeScene([self.a, self.c])
        p = sr.Planner(scene).create([sr.Intent("id-c", "wheel_geo")], "rename", resolve=False)
        self.assertEqual(p.rows[0].status, "Conflict")
        self.assertEqual(len(p.changes()), 0)

    def test_number_placement_and_repeated_suffix(self):
        known = sr.Registry(sr.DEFAULT_REGISTRY).known
        self.assertEqual(sr.numbered_name("wheel_geo", 5, 3, known), "wheel_005_geo")
        self.assertEqual(sr.numbered_name("wheel_014_geo", 5, 3, known), "wheel_005_geo")
        self.assertEqual(sr.replace_suffix("wheel_grp_geo_geo", "geo", known), "wheel_geo")
        self.assertEqual(sr.replace_suffix("wheel_geo", "geo", known), "wheel_geo")

    def test_namespace_collision(self):
        nsa = sr.Node("ns-a", "nsA:body_geo", "transform", "nsA", "body_geo", False)
        nsb = sr.Node("ns-b", "nsB:box_geo", "transform", "nsB", "box_geo", False)
        scene = FakeScene([nsa, nsb])
        p = sr.Planner(scene).create([sr.Intent("ns-b", "body_geo")], "rename")
        self.assertEqual(p.rows[0].new_name, "body_001_geo")
        self.assertEqual(sr.make_absolute("nsB", p.rows[0].new_name), ":nsB:body_001_geo")

    def test_invalid_name_not_applied(self):
        scene = FakeScene([self.a])
        p = sr.Planner(scene).create([sr.Intent("id-a", "24 invalid")], "rename")
        self.assertEqual(p.rows[0].status, "Invalid")


class FakeMaya:
    def __init__(self):
        self.names = {"a": "|left_grp|body_geo", "b": "|right_grp|wheel_geo"}
        self.original = dict(self.names)
        self.chunks = []
        self.undo_called = False
        self.fail_final = False

    def ls(self, *args, **kwargs):
        if kwargs.get("dependencyNodes") or kwargs.get("dag"):
            return list(self.names.values())
        if kwargs.get("undeletable"):
            return []
        if kwargs.get("uuid"):
            return [k for k, value in self.names.items() if value == args[0]]
        if args and kwargs.get("long"):
            return [self.names[args[0]]] if args[0] in self.names else []
        return []

    def nodeType(self, path):
        return "transform"

    def referenceQuery(self, *args, **kwargs):
        return False

    def lockNode(self, *args, **kwargs):
        return [False]

    def undoInfo(self, **kwargs):
        self.chunks.append(kwargs)

    def rename(self, path, dest, ignoreShape=False):
        if not ignoreShape:
            raise AssertionError("ignoreShape must be True")
        if self.fail_final and "studioTmp" not in dest:
            raise RuntimeError("Simulated Maya failure")
        uid = next(k for k, v in self.names.items() if v == path)
        leaf = dest.rsplit(":", 1)[-1]
        self.names[uid] = path.rsplit("|", 1)[0] + "|" + leaf
        return self.names[uid]

    def undo(self):
        self.undo_called = True
        self.names = dict(self.original)


class ApplyTests(unittest.TestCase):
    def test_transactional_swap(self):
        fake = FakeMaya()
        with mock.patch.object(sr, "cmds", fake):
            engine = sr.Engine(sr.Registry(sr.DEFAULT_REGISTRY))
            scene = engine.scan()
            intents = [sr.Intent("a", "wheel_geo"), sr.Intent("b", "body_geo")]
            plan = sr.Planner(scene).create(intents, "swap")
            self.assertEqual(engine.apply(plan), 2)
            self.assertEqual(sr.short_name(fake.names["a"]), "wheel_geo")
            self.assertEqual(sr.short_name(fake.names["b"]), "body_geo")
            self.assertEqual(len(fake.chunks), 2)

    def test_failure_auto_undo(self):
        fake = FakeMaya()
        fake.fail_final = True
        with mock.patch.object(sr, "cmds", fake):
            engine = sr.Engine(sr.Registry(sr.DEFAULT_REGISTRY))
            scene = engine.scan()
            plan = sr.Planner(scene).create([sr.Intent("a", "renamed_geo")], "test")
            with self.assertRaises(RuntimeError):
                engine.apply(plan)
            self.assertTrue(fake.undo_called)
            self.assertEqual(fake.names, fake.original)

    def test_preview_invalidated_when_scene_changes(self):
        fake = FakeMaya()
        with mock.patch.object(sr, "cmds", fake):
            engine = sr.Engine(sr.Registry(sr.DEFAULT_REGISTRY))
            scene = engine.scan()
            plan = sr.Planner(scene).create([sr.Intent("a", "renamed_geo")], "test")
            fake.names["b"] = "|right_grp|edited_geo"
            with self.assertRaisesRegex(RuntimeError, "Scene changed"):
                engine.apply(plan)
            self.assertEqual(fake.chunks, [])


if __name__ == "__main__":
    unittest.main()
