#!/usr/bin/env python3
"""Synthetic regressions for source preflight, never a runtime worldgen gate."""
from __future__ import annotations

import copy
import gzip
import importlib.util
import json
from pathlib import Path, PurePosixPath
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile

from nevernether_source_inputs import (Archive, apply_server_compatibility,
    format_bounds, inspect_dependencies, resource_path, selected_files)

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


IMPORTER = load("source_test_importer", "build-never-nether-structure-pack.py")


def nbt_payload(value):
    def text(s):
        raw = s.encode(); return struct.pack(">H", len(raw)) + raw
    if isinstance(value, str):
        return 8, text(value)
    if type(value) is int:
        return 3, struct.pack(">i", value)
    if isinstance(value, list):
        children = [nbt_payload(x) for x in value]
        tag = children[0][0] if children else 0
        assert all(t == tag for t, _ in children)
        return 9, bytes([tag]) + struct.pack(">i", len(children)) + b"".join(v for _, v in children)
    assert isinstance(value, dict)
    parts = []
    for name, child in value.items():
        tag, payload = nbt_payload(child)
        parts.append(bytes([tag]) + text(name) + payload)
    return 10, b"".join(parts) + b"\0"


def template(**extra):
    value = {"size": [3, 3, 3], "palette": [{"Name": "minecraft:netherrack"}],
             "blocks": [], "entities": [], **extra}
    _, payload = nbt_payload(value)
    return gzip.compress(b"\x0a\x00\x00" + payload, mtime=0)


def base_files():
    return {
        "pack.mcmeta": {"pack": {"pack_format": 107, "description": "fixture"}},
        "data/test/worldgen/structure/tower.json": {"type": "minecraft:jigsaw", "start_pool": "test:start", "biomes": "#minecraft:is_nether"},
        "data/test/worldgen/template_pool/start.json": {"fallback": "minecraft:empty", "elements": [
            {"weight": 1, "element": {"element_type": "minecraft:single_pool_element", "location": "test:start", "processors": "minecraft:empty"}}]},
        "data/test/structure/start.nbt": template(),
    }


class InputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def archive(self, files=None, name="input.zip", prefix=""):
        files = base_files() if files is None else files
        path = self.root / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, value in files.items():
                zf.writestr(prefix + name, value if isinstance(value, bytes) else json.dumps(value))
        return Archive(path)

    def inspect(self, files=None):
        a = self.archive(files)
        return inspect_dependencies(a, ["test:tower"])

    def test_reachable_resources_only_not_entire_namespace(self):
        f = base_files()
        f["data/test/worldgen/configured_feature/unrelated.json"] = {"type": "mod:unsupported"}
        f["data/test/function/tick.mcfunction"] = b"say not an imported tick function"
        r = self.inspect(f)
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(r["selected_counts"], {"structure": 1, "worldgen/structure": 1, "worldgen/template_pool": 1})
        self.assertFalse(any("unrelated" in p or "function/" in p for p in r["selected_files"]))

    def test_missing_approved_root_is_blocked(self):
        f = base_files(); del f["data/test/worldgen/structure/tower.json"]
        self.assertFalse(self.inspect(f)["source_dependency_preflight_passed"])

    def test_missing_template_is_blocked(self):
        f = base_files(); del f["data/test/structure/start.nbt"]
        r = self.inspect(f)
        self.assertEqual(r["missing_required_references"][0][:2], ["structure", "test:start"])

    def test_nbt_jigsaw_reference_is_followed(self):
        f = base_files()
        f["data/test/structure/start.nbt"] = template(blocks=[{"nbt": {"id": "minecraft:jigsaw", "pool": "test:missing"}}])
        self.assertEqual(self.inspect(f)["missing_required_references"][0][:2], ["worldgen/template_pool", "test:missing"])

    def test_nbt_loot_table_is_not_invented(self):
        f = base_files()
        f["data/test/structure/start.nbt"] = template(blocks=[{"nbt": {"id": "minecraft:chest", "LootTable": "test:missing"}}])
        self.assertEqual(self.inspect(f)["missing_required_references"][0][:2], ["loot_table", "test:missing"])

    def test_recursive_loot_dependency(self):
        f = base_files()
        f["data/test/structure/start.nbt"] = template(blocks=[{"nbt": {"id": "minecraft:chest", "LootTable": "test:chest"}}])
        f["data/test/loot_table/chest.json"] = {"pools": [{"entries": [{"type": "minecraft:loot_table", "value": "test:second"}]}]}
        self.assertEqual(self.inspect(f)["missing_required_references"][0][:2], ["loot_table", "test:second"])

    def test_self_referencing_pools_terminate(self):
        f = base_files(); f["data/test/worldgen/template_pool/start.json"]["fallback"] = "test:start"
        self.assertTrue(self.inspect(f)["source_dependency_preflight_passed"])

    def test_unknown_vanilla_reference_is_delegated_not_claimed_verified(self):
        f = base_files(); f["data/test/worldgen/template_pool/start.json"]["fallback"] = "minecraft:example_not_verified"
        r = self.inspect(f)
        self.assertIn(["worldgen/template_pool", "minecraft:example_not_verified"], r["external_vanilla_references_unverified"])
        self.assertFalse(r["runtime_validated"])

    def test_custom_pool_element_blocks_instead_of_losing_max_count(self):
        f = base_files()
        e = f["data/test/worldgen/template_pool/start.json"]["elements"][0]["element"]
        e.update(element_type="yungsapi:max_count_single_element", max_count=1)
        r = self.inspect(f)
        self.assertFalse(r["source_dependency_preflight_passed"])
        self.assertEqual(r["unsupported_or_review_required"][0][1], "yungsapi:max_count_single_element")

    def test_custom_processor_blocks_instead_of_being_removed(self):
        f = base_files()
        f["data/test/worldgen/template_pool/start.json"]["elements"][0]["element"]["processors"] = "test:custom"
        f["data/test/worldgen/processor_list/custom.json"] = {"processors": [{"processor_type": "mod:pillar"}]}
        a = self.archive(f); before = dict(a.entries)
        r = inspect_dependencies(a, ["test:tower"])
        with self.assertRaises(ValueError): selected_files(a, r)
        self.assertEqual(a.entries, before)

    def test_mod_block_and_entity_are_reported(self):
        f = base_files()
        f["data/test/structure/start.nbt"] = template(palette=[{"Name": "mod:block"}], entities=[{"nbt": {"id": "mod:entity"}}])
        r = self.inspect(f)
        self.assertEqual({x[1] for x in r["unsupported_or_review_required"]}, {"mod:block", "mod:entity"})

    def test_feature_pool_follows_placed_then_configured(self):
        f = base_files()
        f["data/test/worldgen/template_pool/start.json"]["elements"] = [{"weight": 1, "element": {"element_type": "minecraft:feature_pool_element", "feature": "test:fire"}}]
        f["data/test/worldgen/placed_feature/fire.json"] = {"feature": "test:fire", "placement": []}
        f["data/test/worldgen/configured_feature/fire.json"] = {"type": "minecraft:simple_block", "config": {}}
        r = self.inspect(f)
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(r["selected_counts"]["worldgen/configured_feature"], 1)
        self.assertNotIn("structure", r["selected_counts"])

    def test_overlay_selection_and_later_priority(self):
        f = base_files()
        f["pack.mcmeta"]["overlays"] = {"entries": [
            {"directory": "old", "min_format": 1, "max_format": [107, 0]},
            {"directory": "first", "formats": [107, 107]},
            {"directory": "last", "min_format": [107, 1], "max_format": [107, 1]}]}
        for directory, val in (("old", 1), ("first", 2), ("last", 3)):
            f[directory + "/data/test/value.json"] = {"value": val}
        a = self.archive(f)
        self.assertEqual(a.active_overlays, ["first", "last"])
        self.assertEqual(json.loads(a.entries[PurePosixPath("data/test/value.json")]), {"value": 3})
        self.assertFalse(any(p.parts[0] in ("old", "first", "last") for p in a.entries))

    def test_integer_max_format_includes_minor_versions(self):
        self.assertGreaterEqual(format_bounds({"min_format": 107, "max_format": 107})[1], (107, 1))

    def test_reversed_format_rejected(self):
        with self.assertRaises(ValueError): format_bounds({"min_format": 108, "max_format": 107})

    def test_wrong_target_format_rejected(self):
        f = base_files(); f["pack.mcmeta"]["pack"]["pack_format"] = 48
        with self.assertRaises(ValueError): self.archive(f)

    def test_modern_template_wins_without_converting_legacy(self):
        f = base_files(); f["data/test/structures/start.nbt"] = template(palette=[{"Name": "mod:legacy"}])
        r = self.inspect(f)
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertNotIn("data/test/structures/start.nbt", r["selected_files"])

    def test_legacy_only_template_is_not_silently_accepted(self):
        f = base_files(); f["data/test/structures/start.nbt"] = f.pop("data/test/structure/start.nbt")
        self.assertFalse(self.inspect(f)["source_dependency_preflight_passed"])

    def test_corrupt_nbt_is_not_accepted(self):
        f = base_files(); f["data/test/structure/start.nbt"] = b"invalid nbt"
        with self.assertRaises(ValueError): self.inspect(f)

    def test_duplicate_zip_paths_rejected(self):
        p = self.root / "dup.zip"
        with warnings.catch_warnings(), zipfile.ZipFile(p, "w") as z:
            warnings.simplefilter("ignore")
            z.writestr("pack.mcmeta", '{}'); z.writestr("pack.mcmeta", '{}')
        with self.assertRaises(ValueError): Archive(p)

    def test_unsafe_paths_rejected(self):
        for path in ("../evil", "/evil", "C:/evil", "dir\\evil"):
            with self.subTest(path=path):
                f = base_files(); f[path] = b"bad"
                with self.assertRaises(ValueError): self.archive(f)

    def test_wrapped_archive_supported(self):
        a = self.archive(prefix="wrapped/")
        self.assertTrue(inspect_dependencies(a, ["test:tower"])["source_dependency_preflight_passed"])

    def test_multiple_pack_roots_rejected(self):
        f = base_files(); f["other/pack.mcmeta"] = f["pack.mcmeta"]
        with self.assertRaises(ValueError): self.archive(f)

    def test_symlink_zip_entry_rejected(self):
        p = self.root / "sym.zip"
        with zipfile.ZipFile(p, "w") as z:
            info = zipfile.ZipInfo("link"); info.create_system = 3; info.external_attr = 0o120777 << 16
            z.writestr(info, "../target")
        with self.assertRaises(ValueError): Archive(p)

    def test_only_specific_monument_tag_has_known_provider(self):
        f = base_files()
        sid = "repurposed_structures:monument_nether"
        f[str(resource_path("worldgen/structure", sid))] = f.pop("data/test/worldgen/structure/tower.json")
        f[str(resource_path("worldgen/structure", sid))]["biomes"] = "#repurposed_structures:has_structure/monuments/nether"
        a = self.archive(f); r = inspect_dependencies(a, [sid])
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(len(r["provided_by_neverfolia_hardener"]), 1)

    def test_missing_optional_tag_not_mandatory(self):
        f = base_files(); f["data/test/worldgen/structure/tower.json"]["biomes"] = "#test:tag"
        f["data/test/tags/worldgen/biome/tag.json"] = {"values": [{"id": "mod:optional_biome", "required": False}]}
        self.assertTrue(self.inspect(f)["source_dependency_preflight_passed"])

    def test_explicit_optional_mod_pool_override_leaves_template_unchanged(self):
        f = base_files()
        original = template(blocks=[{"nbt": {"id": "minecraft:jigsaw", "pool": "structory_towers:waystones/waystone"}}])
        f["data/test/structure/start.nbt"] = original
        for ident in ("structory_towers:waystones/waystone", "structory_towers:waystones/fwaystone"):
            f[str(resource_path("worldgen/template_pool", ident))] = {"fallback": "minecraft:empty", "elements": [
                {"weight": 1, "element": {"element_type": "minecraft:single_pool_element", "location": "test:mod", "processors": "minecraft:empty"}}]}
        f["data/test/structure/mod.nbt"] = template(palette=[{"Name": "waystones:waystone"}])
        a = self.archive(f); before = a.path.read_bytes()
        self.assertFalse(inspect_dependencies(a, ["test:tower"])["source_dependency_preflight_passed"])
        apply_server_compatibility(a, "structory_towers")
        r = inspect_dependencies(a, ["test:tower"])
        self.assertTrue(r["source_dependency_preflight_passed"])
        self.assertEqual(len(r["compatibility_changes"]), 2)
        self.assertEqual(a.entries[PurePosixPath("data/test/structure/start.nbt")], original)
        self.assertEqual(a.path.read_bytes(), before)
        self.assertNotIn("data/test/structure/mod.nbt", r["selected_files"])

    def test_legacy_processor_entry_point_never_drops_unsupported(self):
        p = IMPORTER.PackFiles()
        path = "data/test/worldgen/processor_list/main.json"
        p.put(path, json.dumps({"processors": [{"processor_type": "mod:pillar"}]}).encode())
        before = dict(p.files)
        with self.assertRaises(SystemExit): IMPORTER.sanitize_processor_lists(p)
        self.assertEqual(p.files, before)

    def test_full_build_still_requires_all_five_sources(self):
        output = self.root / "do-not-replace.zip"; output.write_bytes(b"old-output")
        with self.assertRaises(SystemExit): IMPORTER.build(self.root / "absent.zip", {}, output)
        self.assertEqual(output.read_bytes(), b"old-output")


if __name__ == "__main__":
    unittest.main(verbosity=2)
