#!/usr/bin/env python3
"""Synthetic source-graph regressions; never substitutes for a Folia runtime test."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import PurePosixPath, Path
import sys
import unittest

from nevernether_source_inputs import (
    Archive, apply_resource_aliases, inspect_dependencies, json_resource, resource_path,
)

SPEC = importlib.util.spec_from_file_location("source_r3_fixtures", Path(__file__).with_name("test-never-nether-source-inputs.py"))
FIX = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = FIX
SPEC.loader.exec_module(FIX)


class SourceR3Tests(unittest.TestCase):
    setUp = FIX.InputsTests.setUp
    tearDown = FIX.InputsTests.tearDown
    archive = FIX.InputsTests.archive
    inspect = FIX.InputsTests.inspect

    def test_empty_item_modifier_array_is_retained(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(blocks=[{"nbt": {"LootTable": "test:chest"}}])
        f["data/test/loot_table/chest.json"] = {"functions": [{"function": "minecraft:reference", "name": "test:empty"}]}
        f["data/test/item_modifier/empty.json"] = []
        a = self.archive(f)
        r = inspect_dependencies(a, ["test:tower"])
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(r["selected_counts"]["item_modifier"], 1)
        self.assertEqual(a.decode(PurePosixPath("data/test/item_modifier/empty.json")), [])

    def test_predicate_array_reference_is_followed(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(blocks=[{"nbt": {"LootTable": "test:chest"}}])
        f["data/test/loot_table/chest.json"] = {"conditions": [{"condition": "minecraft:reference", "name": "test:many"}]}
        f["data/test/predicate/many.json"] = [{"condition": "minecraft:reference", "name": "test:missing"}]
        r = self.inspect(f)
        self.assertIn(["predicate", "test:missing", "data/test/predicate/many.json"], r["missing_required_references"])

    def test_array_roots_remain_forbidden_in_other_registries(self):
        for path in ("data/test/loot_table/bad.json", "data/test/worldgen/structure/bad.json", "data/test/trial_spawner/bad.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                json_resource(b"[]", PurePosixPath(path))

    def test_array_members_must_be_objects(self):
        for raw in (b"[1]", b"[null]", b"[[]]", b"[true]", b'["name"]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                json_resource(raw, PurePosixPath("data/test/item_modifier/bad.json"))

    def test_trial_spawners_and_ejected_loot_are_included(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(blocks=[{"nbt": {"id": "minecraft:trial_spawner", "normal_config": "test:normal", "ominous_config": "test:ominous"}}])
        for key in ("normal", "ominous"):
            f[f"data/test/trial_spawner/{key}.json"] = {"loot_tables_to_eject": [{"data": "test:reward", "weight": 1}], "items_to_drop_when_ominous": "test:projectiles"}
        for key in ("reward", "projectiles"):
            f[f"data/test/loot_table/{key}.json"] = {"pools": []}
        r = self.inspect(f)
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(r["selected_counts"]["trial_spawner"], 2)
        self.assertEqual(r["selected_counts"]["loot_table"], 2)

    def test_inline_trial_spawner_config_also_follows_rewards(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(blocks=[{"nbt": {"normal_config": {"loot_tables_to_eject": [{"data": "test:missing", "weight": 1}]}}}])
        self.assertFalse(self.inspect(f)["source_dependency_preflight_passed"])

    def test_missing_trial_config_is_not_reported_as_working(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(blocks=[{"nbt": {"ominous_config": "test:absent"}}])
        self.assertIn(["trial_spawner", "test:absent", "data/test/structure/start.nbt"], self.inspect(f)["missing_required_references"])

    def test_nbt_enchantment_formats_and_stored_enchantments(self):
        for key, component in (("minecraft:enchantments", {"levels": {"test:effect": 1}}), ("minecraft:enchantments", {"test:effect": 1}), ("minecraft:stored_enchantments", {"test:effect": 1})):
            f = FIX.base_files()
            f["data/test/structure/start.nbt"] = FIX.template(entities=[{"nbt": {"equipment": {"mainhand": {"components": {key: component}}}}}])
            f["data/test/enchantment/effect.json"] = {"supported_items": "#test:tools", "effects": {}}
            f["data/test/tags/item/tools.json"] = {"values": ["minecraft:stick"]}
            with self.subTest(key=key, component=component):
                r = self.inspect(f)
                self.assertTrue(r["source_dependency_preflight_passed"])
                self.assertEqual(r["selected_counts"]["enchantment"], 1)
                self.assertEqual(r["selected_counts"]["tags/item"], 1)

    def test_enchantment_function_dependencies_and_review_flag(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(entities=[{"nbt": {"components": {"minecraft:enchantments": {"test:boss": 1}}}}])
        f["data/test/enchantment/boss.json"] = {"effects": {"minecraft:tick": [{"effect": {"type": "minecraft:run_function", "function": "test:boss_tick"}}]}}
        f["data/test/function/boss_tick.mcfunction"] = b"function test:child\nscoreboard players add @s counter 1\n"
        f["data/test/function/child.mcfunction"] = b"execute if predicate test:condition run say ok\n"
        f["data/test/predicate/condition.json"] = []
        r = self.inspect(f)
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(r["selected_counts"]["function"], 2)
        self.assertFalse(r["runtime_validated"])
        self.assertTrue(any(x[0] == "scoreboard_initialization_required" for x in r["runtime_review_required"]))

    def test_function_reference_cycles_are_bounded(self):
        f = FIX.base_files()
        f["data/test/loot_table/reward.json"] = {"functions": [{"function": "minecraft:set_components", "components": {"minecraft:enchantments": {"test:boss": 1}}}]}
        f["data/test/structure/start.nbt"] = FIX.template(blocks=[{"nbt": {"LootTable": "test:reward"}}])
        f["data/test/enchantment/boss.json"] = {"effect": {"type": "minecraft:run_function", "function": "#test:tick"}}
        f["data/test/tags/function/tick.json"] = {"values": ["test:cycle"]}
        f["data/test/function/cycle.mcfunction"] = b"function #test:tick\n"
        self.assertTrue(self.inspect(f)["source_dependency_preflight_passed"])

    def test_macro_function_blocks_not_silently_accepted(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(entities=[{"nbt": {"components": {"minecraft:enchantments": {"test:boss": 1}}}}])
        f["data/test/enchantment/boss.json"] = {"effect": {"type": "minecraft:run_function", "function": "test:macro"}}
        f["data/test/function/macro.mcfunction"] = b"$function $(dynamic_target)\n"
        r = self.inspect(f)
        self.assertFalse(r["source_dependency_preflight_passed"])
        self.assertTrue(any(x[0] == "dynamic_function_requires_review" for x in r["unsupported_or_review_required"]))

    def test_quoted_command_like_text_is_not_a_function_call(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(entities=[{"nbt": {"components": {"minecraft:enchantments": {"test:boss": 1}}}}])
        f["data/test/enchantment/boss.json"] = {"effect": {"type": "minecraft:run_function", "function": "test:message"}}
        f["data/test/function/message.mcfunction"] = b'tellraw @a {"text":"function missing:not_a_command"}\n'
        self.assertTrue(self.inspect(f)["source_dependency_preflight_passed"])

    def test_death_loot_and_processor_injected_loot_are_followed(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(entities=[{"nbt": {"DeathLootTable": "test:mob"}}])
        f["data/test/worldgen/template_pool/start.json"]["elements"][0]["element"]["processors"] = "test:rules"
        f["data/test/worldgen/processor_list/rules.json"] = {"processors": [{"processor_type": "minecraft:rule", "rules": [{"block_entity_modifier": {"type": "minecraft:append_loot", "loot_table": "test:loot"}}]}]}
        r = self.inspect(f)
        self.assertEqual({x[1] for x in r["missing_required_references"]}, {"test:mob", "test:loot"})

    def test_configured_feature_block_tag_and_enchantment_loot_options(self):
        f = FIX.base_files()
        f["data/test/worldgen/template_pool/start.json"]["elements"].append({"weight": 1, "element": {"element_type": "minecraft:feature_pool_element", "feature": "test:column"}})
        f["data/test/worldgen/placed_feature/column.json"] = {"feature": "test:column", "placement": []}
        f["data/test/worldgen/configured_feature/column.json"] = {"type": "minecraft:block_column", "config": {"allowed_placement": {"type": "minecraft:matching_block_tag", "tag": "test:replaceable"}}}
        f["data/test/tags/block/replaceable.json"] = {"values": ["minecraft:air"]}
        f["data/test/structure/start.nbt"] = FIX.template(blocks=[{"nbt": {"LootTable": "test:loot"}}])
        f["data/test/loot_table/loot.json"] = {"functions": [{"function": "minecraft:enchant_randomly", "options": "#test:books"}]}
        f["data/test/tags/enchantment/books.json"] = {"values": ["test:book"]}
        f["data/test/enchantment/book.json"] = {"effects": {}}
        r = self.inspect(f)
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(r["selected_counts"]["tags/block"], 1)
        self.assertEqual(r["selected_counts"]["enchantment"], 1)

    def pool_alias_fixture(self):
        f = FIX.base_files()
        f["data/test/structure/start.nbt"] = FIX.template(blocks=[{"nbt": {"pool": "test:virtual"}}])
        f["data/test/worldgen/structure/tower.json"]["pool_aliases"] = [{"type": "minecraft:random", "alias": "test:virtual", "targets": [{"data": "test:left", "weight": 1}, {"data": "test:right", "weight": 2}]}]
        for name in ("left", "right"):
            f[f"data/test/worldgen/template_pool/{name}.json"] = {"fallback": "minecraft:empty", "elements": []}
        return f

    def test_random_pool_alias_has_no_physical_placeholder(self):
        a = self.archive(self.pool_alias_fixture()); before = dict(a.entries)
        r = inspect_dependencies(a, ["test:tower"])
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(r["virtual_pool_aliases"]["test:virtual"], ["test:left", "test:right"])
        self.assertNotIn("data/test/worldgen/template_pool/virtual.json", r["selected_files"])
        self.assertEqual(a.entries, before)

    def test_cached_alias_facts_are_root_scoped(self):
        f = self.pool_alias_fixture()
        f["data/test/worldgen/structure/other.json"] = {"type": "minecraft:jigsaw", "start_pool": "test:start"}
        a = self.archive(f)
        inspect_dependencies(a, ["test:tower", "test:other"])
        r = inspect_dependencies(a, ["test:other"])
        self.assertFalse(r["source_dependency_preflight_passed"])
        self.assertTrue(any(x[1] == "test:virtual" for x in r["missing_required_references"]))

    def test_all_alias_targets_are_audited_even_unused(self):
        f = self.pool_alias_fixture()
        f["data/test/structure/start.nbt"] = FIX.template()
        del f["data/test/worldgen/template_pool/right.json"]
        self.assertFalse(self.inspect(f)["source_dependency_preflight_passed"])

    def test_direct_and_random_group_aliases(self):
        f = self.pool_alias_fixture()
        f["data/test/worldgen/structure/tower.json"]["pool_aliases"] = [{"type": "minecraft:random_group", "groups": [{"weight": 1, "data": [{"type": "minecraft:direct", "alias": "test:virtual", "target": "test:left"}]}]}]
        r = self.inspect(f)
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(r["virtual_pool_aliases"]["test:virtual"], ["test:left"])

    def test_alias_cycles_are_rejected(self):
        f = self.pool_alias_fixture()
        f["data/test/worldgen/structure/tower.json"]["pool_aliases"] = [
            {"type": "minecraft:direct", "alias": "test:virtual", "target": "test:second"},
            {"type": "minecraft:direct", "alias": "test:second", "target": "test:virtual"}]
        with self.assertRaises(ValueError): self.inspect(f)

    def test_invalid_alias_weight_rejected(self):
        f = self.pool_alias_fixture()
        f["data/test/worldgen/structure/tower.json"]["pool_aliases"][0]["targets"][0]["weight"] = 0
        with self.assertRaises(ValueError): self.inspect(f)

    def profile(self, a):
        return {"source_sha256": a.sha256, "aliases": [{"registry": "structure", "missing": "test:fixed", "existing": "test:start", "reason": "synthetic test", "target_sha256": hashlib.sha256(a.entries[PurePosixPath("data/test/structure/start.nbt")]).hexdigest()}]}

    def test_alias_repair_is_exact_copy_and_source_zip_unchanged(self):
        a = self.archive(); before = a.path.read_bytes()
        apply_resource_aliases(a, self.profile(a))
        self.assertEqual(a.entries[PurePosixPath("data/test/structure/fixed.nbt")], a.entries[PurePosixPath("data/test/structure/start.nbt")])
        self.assertEqual(a.path.read_bytes(), before)
        self.assertEqual(len(a.compatibility_changes), 1)

    def test_alias_repair_rejects_wrong_source_hash(self):
        a = self.archive(); p = self.profile(a); p["source_sha256"] = "0" * 64
        before = dict(a.entries)
        with self.assertRaises(ValueError): apply_resource_aliases(a, p)
        self.assertEqual(a.entries, before)

    def test_alias_repair_is_atomic_when_later_target_hash_fails(self):
        a = self.archive(); p = self.profile(a)
        p["aliases"].append({**p["aliases"][0], "missing": "test:second", "target_sha256": "0" * 64})
        before = dict(a.entries)
        with self.assertRaises(ValueError): apply_resource_aliases(a, p)
        self.assertEqual(a.entries, before)
        self.assertEqual(a.compatibility_changes, [])

    def test_alias_repair_does_not_overwrite_existing_resource(self):
        a = self.archive(); p = self.profile(a); p["aliases"][0]["missing"] = "test:start"
        with self.assertRaises(ValueError): apply_resource_aliases(a, p)

    def test_alias_repair_rejects_missing_target_and_duplicate_destinations(self):
        a = self.archive(); p = self.profile(a); p["aliases"][0]["existing"] = "test:absent"
        with self.assertRaises(ValueError): apply_resource_aliases(a, p)
        p = self.profile(a); p["aliases"].append(dict(p["aliases"][0]))
        with self.assertRaises(ValueError): apply_resource_aliases(a, p)

    def test_resource_path_uses_function_extension(self):
        self.assertEqual(str(resource_path("function", "test:path/run")), "data/test/function/path/run.mcfunction")


if __name__ == "__main__":
    unittest.main(verbosity=2)
