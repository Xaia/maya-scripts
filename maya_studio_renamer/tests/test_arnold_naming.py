import copy
import unittest
from unittest import mock
import studio_renamer as sr


class ArnoldNamingTests(unittest.TestCase):
    def node(self, typ):
        return sr.Node("uid", "oak", typ, "", "oak", False)

    def test_full_names_replace_legacy_abbreviations(self):
        registry = sr.Registry(copy.deepcopy(sr.DEFAULT_REGISTRY))
        for typ in ("aiColorCorrect", "aiStandardSurface", "aiImage", "aiRange", "aiStandIn"):
            suffix = registry.suffix_for(self.node(typ))
            self.assertEqual(suffix, typ)
            self.assertEqual(sr.replace_suffix("oak_shd_cc", suffix, registry.known), "oak_" + typ)
            self.assertEqual(sr.replace_suffix("oak_" + typ, suffix, registry.known), "oak_" + typ)

    def test_future_types_and_numbering(self):
        registry = sr.Registry(copy.deepcopy(sr.DEFAULT_REGISTRY))
        suffix = registry.suffix_for(self.node("aiFutureArnoldUtility"))
        self.assertEqual(suffix, "aiFutureArnoldUtility")
        self.assertEqual(sr.numbered_name("oak_" + suffix, 2, 3, registry.known), "oak_002_" + suffix)

    def test_aim_constraint_is_not_arnold(self):
        registry = sr.Registry(copy.deepcopy(sr.DEFAULT_REGISTRY))
        self.assertFalse(registry.is_arnold_type("aimConstraint"))
        self.assertFalse(registry.is_arnold_type("airField"))
        self.assertEqual(registry.suffix_for(self.node("aimConstraint")), "cns")
        self.assertFalse(sr.suffix_filter(self.node("aimConstraint"), registry, "Arnold"))

    def test_installed_plugin_types_including_non_ai_names(self):
        maya = mock.Mock()
        maya.pluginInfo.side_effect = lambda *a, **kw: ["aiNewUtility", "alSurface"] if kw.get("dependNode") else True
        with mock.patch.object(sr, "cmds", maya):
            registry = sr.Registry(copy.deepcopy(sr.DEFAULT_REGISTRY))
            self.assertEqual(registry.suffix_for(self.node("alSurface")), "alSurface")
            self.assertIn("aiNewUtility", registry.known)

    def test_existing_user_mapping_does_not_reintroduce_abbreviations(self):
        data = copy.deepcopy(sr.DEFAULT_REGISTRY)
        data["type_suffixes"]["aiColorCorrect"] = "oldCorrection"
        data["type_suffixes"]["aiStandardSurface"] = "aiStandardSurface"
        registry = sr.Registry(data)
        suffix = registry.suffix_for(self.node("aiColorCorrect"))
        self.assertEqual(sr.replace_suffix("oak_oldCorrection", suffix, registry.known), "oak_aiColorCorrect")
        self.assertEqual(registry.role_for(self.node("aiStandardSurface")), "shd")


if __name__ == "__main__":
    unittest.main()
