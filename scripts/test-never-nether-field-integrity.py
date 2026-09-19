#!/usr/bin/env python3
"""Synthetic regressions. These tests do not claim a live Folia worldgen pass."""
from __future__ import annotations

import copy
import importlib.util
import json
import struct
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDIT = load("integrity_audit", "audit-never-nether-field-integrity.py")
BUILDER = load("integrity_core", "build-never-nether-core-test1-pack.py")
BASE = BUILDER.load_base_builder()


def fixture(cx=0, cz=0, changes=None):
    palette = [{"Name": "minecraft:netherrack"}, {"Name": "minecraft:air"},
               {"Name": "minecraft:cave_air"},
               {"Name": "minecraft:lava", "Properties": {"level": "0"}},
               {"Name": "minecraft:lava", "Properties": {"level": "1"}},
               {"Name": "minecraft:chest"}]
    indices = [0] * 4096
    for (x, y, z), state in (changes or {}).items():
        indices[y * 256 + z * 16 + x] = state
    return {"xPos": cx, "zPos": cz, "Status": "minecraft:full", "sections": [
        {"Y": 0, "block_states": {"palette": palette,
                                  "data": {"$long_array": AUDIT.DECODER.pack_indices(indices, 4)}}}
    ]}


def report(roots, limit=64, max_findings=200):
    return AUDIT.audit(AUDIT.Volume(roots, 0, 15), limit, max_findings)


def attach_original_state(root, position, state_name):
    x,y,z=position
    section=next(s for s in root["sections"] if s["Y"] == y//16)
    palette=["minecraft:netherrack",state_name]
    bits=1
    per=64//bits
    original=[0]*((4096+per-1)//per)
    index=((y&15)<<8)|((z&15)<<4)|(x&15)
    original[index//per] |= 1 << (index%per)
    section["neverfolia:substrate_r11"]={
        "Schema":1,
        "Profile":"NN-R14-SUBSTRATE-1-ROOF512",
        "Seed":7270913,
        "ChunkX":root["xPos"],
        "ChunkZ":root["zPos"],
        "SectionY":y//16,
        "Palette":palette,
        "Bits":bits,
        "Original":{"$long_array":original},
        "External":{"$long_array":[]},
        "ProposalIndices":{"$int_array":[]},
        "ProposalStates":{"$int_array":[]},
    }
    return index


def attach_substrate_provenance(root, position, *, external=False, proposal=False):
    x,y,z=position
    section=next(s for s in root["sections"] if s["Y"] == y//16)
    palette=["minecraft:netherrack","minecraft:lava[level=0]"]
    bits=1
    per=64//bits
    original=[0]*((4096+per-1)//per)
    index=((y&15)<<8)|((z&15)<<4)|(x&15)
    external_longs=[]
    if external:
        external_longs=[0]*(index//64+1)
        external_longs[index//64] |= 1 << (index%64)
    section["neverfolia:substrate_r11"]={
        "Schema":1,
        "Profile":"NN-R11-SUBSTRATE-1-REMOTE-R10-PRIORITY",
        "Seed":7270913,
        "ChunkX":root["xPos"],
        "ChunkZ":root["zPos"],
        "SectionY":y//16,
        "Palette":palette,
        "Bits":bits,
        "Original":{"$long_array":original},
        "External":{"$long_array":external_longs},
        "ProposalIndices":{"$int_array":[index] if proposal else []},
        "ProposalStates":{"$int_array":[1] if proposal else []},
    }
    return index


class FieldAuditTests(unittest.TestCase):
    def test_solid_rock_has_no_pockets(self):
        r = report({(0, 0): fixture()})
        self.assertEqual(r["counts"]["air_components"], 0)

    def test_enclosed_single_voxel(self):
        r = report({(0, 0): fixture(changes={(8, 8, 8): 1})})
        self.assertEqual(r["counts"]["enclosed_small_air_components"], 1)
        self.assertEqual(r["counts"]["enclosed_air_components_size_1"], 1)
        self.assertEqual(r["enclosed_air_samples"][0]["bbox"], [8, 8, 8, 8, 8, 8])

    def test_r15_original_owner_micro_counter(self):
        root=fixture(changes={(8,8,8):1})
        attach_original_state(root,(8,8,8),"minecraft:air")
        r=report({(0,0):root})
        self.assertEqual(r["counts"]["enclosed_micro_components"],1)
        self.assertEqual(r["counts"]["enclosed_micro_owner_components"],1)
        self.assertEqual(r["counts"]["enclosed_micro_edge_components"],0)
        self.assertEqual(r["counts"]["r15_original_owner_micro_components"],1)
        self.assertEqual(r["counts"]["r15_original_owner_micro_blocks"],1)
        sample=r["enclosed_air_samples"][0]
        self.assertTrue(sample["original_only"])
        self.assertFalse(sample["touches_owner_chunk_boundary"])

    def test_r15_original_owner_micro_tracks_structure_references(self):
        root=fixture(changes={(8,8,8):1})
        attach_original_state(root,(8,8,8),"minecraft:air")
        root["structures"]={
            "references":{
                "minecraft:fortress":{"$long_array":[123456789]}
            }
        }
        r=report({(0,0):root})
        self.assertEqual(r["counts"]["r15_original_owner_micro_components"],1)
        self.assertEqual(r["counts"]["r15_original_owner_micro_referenced_components"],1)
        self.assertEqual(r["counts"]["r15_original_owner_micro_unreferenced_components"],0)
        self.assertEqual(
            r["enclosed_air_samples"][0]["chunk_structure_reference_ids"],
            ["minecraft:fortress"],
        )

    def test_r15_chunk_edge_micro_is_diagnostic_not_owner_gate(self):
        roots={
            (-1,0):fixture(-1,0,{(15,8,8):1}),
            (0,0):fixture(0,0,{(0,8,8):1}),
        }
        r=report(roots)
        self.assertEqual(r["counts"]["enclosed_micro_components"],1)
        self.assertEqual(r["counts"]["enclosed_micro_owner_components"],0)
        self.assertEqual(r["counts"]["enclosed_micro_edge_components"],1)
        self.assertEqual(r["counts"]["enclosed_micro_edge_blocks"],2)
        self.assertTrue(r["enclosed_air_samples"][0]["touches_owner_chunk_boundary"])

    def test_face_connected_air_variants_are_one_component(self):
        r = report({(0, 0): fixture(changes={(8, 8, 8): 1, (9, 8, 8): 2})})
        self.assertEqual(r["counts"]["enclosed_small_air_components"], 1)
        self.assertEqual(r["counts"]["enclosed_small_air_blocks"], 2)

    def test_negative_chunk_seam_is_not_a_wall(self):
        roots = {(-1, 0): fixture(-1, 0, {(15, 8, 8): 1}),
                 (0, 0): fixture(changes={(0, 8, 8): 1})}
        r = report(roots)
        self.assertEqual(r["counts"]["enclosed_small_air_components"], 1)
        self.assertEqual(r["enclosed_air_samples"][0]["bbox"], [-1, 8, 8, 0, 8, 8])
        self.assertEqual(r, report(dict(reversed(list(roots.items())))))

    def test_missing_neighbor_is_unknown_not_sealed(self):
        r = report({(0, 0): fixture(changes={(0, 8, 8): 1})})
        self.assertEqual(r["counts"]["enclosed_small_air_components"], 0)
        self.assertEqual(r["counts"]["air_components_touching_unknown_boundary"], 1)

    def test_vertical_boundary_is_unknown(self):
        r = report({(0, 0): fixture(changes={(8, 0, 8): 1})})
        self.assertEqual(r["counts"]["enclosed_small_air_components"], 0)
        self.assertEqual(r["counts"]["air_components_touching_unknown_boundary"], 1)

    def test_large_cavern_not_reported_as_small_hole(self):
        r = report({(0, 0): fixture(changes={(x, 8, 8): 1 for x in range(4, 10)})}, limit=4)
        self.assertEqual(r["counts"]["air_components_above_pocket_limit"], 1)
        self.assertEqual(r["counts"]["enclosed_small_air_components"], 0)

    def test_structure_bbox_is_separate_and_input_is_unchanged(self):
        root = fixture(changes={(8, 8, 8): 1})
        root["structures"] = {"starts": {"test:room": {"Children": [
            {"BB": {"$int_array": [7, 7, 7, 9, 9, 9]}}
        ]}}}
        before = copy.deepcopy(root)
        r = report({(0, 0): root})
        self.assertEqual(r["counts"]["enclosed_small_air_components"], 0)
        self.assertEqual(r["counts"]["small_air_components_in_saved_structure_bbox"], 1)
        self.assertEqual(root, before)

    def test_non_rock_boundary_is_not_geological_pocket(self):
        r = report({(0, 0): fixture(changes={(8, 8, 8): 1, (9, 8, 8): 5})})
        self.assertEqual(r["counts"]["enclosed_small_air_components"], 0)

    def test_source_and_flowing_lava_are_distinct(self):
        root = fixture(changes={(8, 8, 8): 3, (8, 7, 8): 1, (10, 8, 8): 4})
        r = report({(0, 0): root})
        self.assertEqual(r["counts"]["source_lava_blocks"], 1)
        self.assertEqual(r["counts"]["flowing_lava_blocks"], 1)
        self.assertEqual(r["counts"]["source_lava_with_air_below"], 1)
        self.assertEqual(r["counts"]["hanging_source_lava_shelf_candidates"], 0)
        self.assertEqual(r["counts"]["source_lava_fall_or_edge_candidates"], 1)
        self.assertIn("waterfalls", " ".join(r["interpretation"]))

    def test_horizontal_source_lava_cluster_is_shelf_candidate(self):
        changes = {
            (7, 8, 8): 3, (8, 8, 8): 3, (9, 8, 8): 3,
            (7, 7, 8): 1, (8, 7, 8): 1, (9, 7, 8): 1,
        }
        r = report({(0, 0): fixture(changes=changes)})
        self.assertEqual(r["counts"]["source_lava_with_air_below"], 3)
        self.assertEqual(r["counts"]["hanging_source_lava_shelf_candidates"], 1)
        self.assertEqual(r["counts"]["source_lava_fall_or_edge_candidates"], 2)
        self.assertEqual(r["hanging_lava_shelf_samples"][0]["position"], [8, 8, 8])
        self.assertEqual(r["hanging_lava_shelf_samples"][0]["horizontal_source_lava_neighbors"], 2)

    def test_chunk_edge_shelf_reports_cross_chunk_neighbor(self):
        left=fixture(0,0,{
            (8,8,15):3,
            (7,8,15):3,
            (8,7,15):1,
        })
        right=fixture(0,1,{(8,8,0):3})
        attach_original_state(left,(8,8,15),"minecraft:lava[level=0]")
        r=report({(0,0):left,(0,1):right})
        self.assertEqual(r["counts"]["source_lava_with_air_below"],1)
        self.assertEqual(r["counts"]["hanging_source_lava_shelf_candidates"],1)
        self.assertEqual(r["counts"]["hanging_source_lava_shelf_original_candidates"],1)
        sample=r["hanging_lava_shelf_samples"][0]
        self.assertEqual(sample["position"],[8,8,15])
        sources=[n for n in sample["horizontal_neighbors"] if n["source_lava"]]
        self.assertEqual(len(sources),2)
        self.assertEqual(sum(1 for n in sources if n["same_chunk"]),1)
        self.assertEqual(sum(1 for n in sources if not n["same_chunk"]),1)

    def test_saved_provenance_distinguishes_proposal_and_external(self):
        position=(8,8,8)

        proposal_root=fixture(changes={position:3})
        attach_substrate_provenance(proposal_root,position,proposal=True)
        proposal_volume=AUDIT.Volume({(0,0):proposal_root},0,15)
        proposal=proposal_volume.provenance_at(position)
        self.assertTrue(proposal["available"])
        self.assertEqual(proposal["classification"],"proposal")
        self.assertEqual(proposal["original"],"minecraft:netherrack")
        self.assertEqual(proposal["proposal_state"],"minecraft:lava[level=0]")
        self.assertFalse(proposal["external"])

        external_root=fixture(changes={position:3})
        attach_substrate_provenance(external_root,position,external=True)
        external_volume=AUDIT.Volume({(0,0):external_root},0,15)
        external=external_volume.provenance_at(position)
        self.assertTrue(external["available"])
        self.assertEqual(external["classification"],"external")
        self.assertEqual(external["original"],"minecraft:netherrack")
        self.assertIsNone(external["proposal_state"])
        self.assertTrue(external["external"])

        original_root=fixture()
        attach_substrate_provenance(original_root,position)
        original_volume=AUDIT.Volume({(0,0):original_root},0,15)
        original=original_volume.provenance_at(position)
        self.assertEqual(original["classification"],"original")
        self.assertEqual(original["current"],"minecraft:netherrack")

    def test_roof_player_blocks_only_observed(self):
        root = fixture()
        root["sections"].append({"Y": 24, "block_states": {"palette": [{"Name": "minecraft:stone"}]}})
        r = report({(0, 0): root})
        self.assertEqual(r["roof_non_air_blocks_observed"], 4096)
        self.assertTrue(r["read_only"])

    def test_r14_upper_generated_body_range_is_auditable(self):
        root = fixture()
        root["sections"].append({"Y": 31, "block_states": {"palette": [{"Name": "minecraft:netherrack"}]}})
        volume = AUDIT.Volume({(0, 0): root}, 384, 511)
        self.assertEqual(volume.min_y, 384)
        self.assertEqual(volume.max_y, 511)
        self.assertEqual(volume.at((0, 511, 0)), "minecraft:netherrack")
        self.assertEqual(volume.roof_non_air, 0)

    def test_r14_roof_section_remains_auxiliary_outside_body_audit(self):
        root = fixture()
        root["sections"].append({"Y": 32, "block_states": {"palette": [{"Name": "minecraft:bedrock"}]}})
        volume = AUDIT.Volume({(0, 0): root}, 384, 511)
        self.assertEqual(volume.roof_non_air, 4096)

    def test_empty_sample_is_not_success(self):
        with self.assertRaises(ValueError):
            report({})

    def test_non_full_chunk_rejected(self):
        root = fixture()
        root["Status"] = "minecraft:noise"
        with self.assertRaises(ValueError):
            report({(0, 0): root})

    def test_malformed_packed_data_rejected(self):
        root = fixture()
        root["sections"][0]["block_states"]["data"]["$long_array"] = []
        with self.assertRaises(ValueError):
            report({(0, 0): root})

    def test_invalid_sections_list_rejected(self):
        for sections in (None, {}, [None]):
            root = fixture()
            root["sections"] = sections
            with self.subTest(sections=sections), self.assertRaises(ValueError):
                report({(0, 0): root})

    def test_invalid_present_block_container_rejected(self):
        root = fixture()
        root["sections"][0]["block_states"] = None
        with self.assertRaises(ValueError):
            report({(0, 0): root})

    def test_duplicate_section_rejected(self):
        root = fixture()
        root["sections"].append(copy.deepcopy(root["sections"][0]))
        with self.assertRaises(ValueError):
            report({(0, 0): root})

    def test_coordinate_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            report({(1, 0): fixture()})

    def test_sample_limit_does_not_hide_total_counts(self):
        root = fixture(changes={(3, 3, 3): 1, (10, 10, 10): 1})
        r = report({(0, 0): root}, max_findings=1)
        self.assertEqual(r["counts"]["enclosed_small_air_components"], 2)
        self.assertEqual(len(r["enclosed_air_samples"]), 1)
        self.assertTrue(r["samples_truncated"]["enclosed_air"])


class RegionIoTests(unittest.TestCase):
    @staticmethod
    def nbt(value):
        def text(value):
            raw = value.encode("utf-8")
            return struct.pack(">H", len(raw)) + raw
        if isinstance(value, str):
            return 8, text(value)
        if isinstance(value, int):
            return 3, struct.pack(">i", value)
        if isinstance(value, list):
            children = [RegionIoTests.nbt(child) for child in value]
            tag = children[0][0] if children else 0
            assert all(t == tag for t, _ in children)
            return 9, bytes([tag]) + struct.pack(">i", len(children)) + b"".join(raw for _, raw in children)
        if "$long_array" in value:
            values = value["$long_array"]
            return 12, struct.pack(">i", len(values)) + b"".join(
                struct.pack(">q", n if n < (1 << 63) else n - (1 << 64)) for n in values)
        parts = []
        for name, child in value.items():
            tag, raw = RegionIoTests.nbt(child)
            parts.append(bytes([tag]) + text(name) + raw)
        return 10, b"".join(parts) + b"\x00"

    def test_cli_reads_anvil_without_modifying_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            region = root / "region"
            region.mkdir()
            _, payload = self.nbt(fixture(changes={(8, 8, 8): 1}))
            payload = b"\x0a\x00\x00" + payload
            record = struct.pack(">I", len(payload) + 1) + b"\x03" + payload
            sectors = (len(record) + 4095) // 4096
            header = struct.pack(">I", (2 << 8) | sectors) + bytes(8192 - 4)
            saved = header + record + bytes(sectors * 4096 - len(record))
            path = region / "r.0.0.mca"
            path.write_bytes(saved)
            output = root / "report.json"
            command = [sys.executable, str(ROOT / "scripts/audit-never-nether-field-integrity.py"),
                       "--region-dir", str(region), "--chunk=0,0", "--min-y", "0", "--max-y", "15",
                       "--output", str(output)]
            run = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(output.read_text())["counts"]["enclosed_small_air_components"], 1)
            self.assertEqual(path.read_bytes(), saved)
            output.unlink()
            command[command.index("--chunk=0,0")] = "--chunk=1,0"
            failed = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(failed.returncode, 2)
            self.assertFalse(output.exists(), "A missing chunk must not produce a passing report")
            self.assertEqual(path.read_bytes(), saved)


class DeltaPackTests(unittest.TestCase):
    def test_only_surface_lava_changes_not_density_sea_or_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "base"
            BASE.build_pack(root)
            rel = "data/minecraft/worldgen/noise_settings/nether.json"
            before = json.loads((root / rel).read_text())
            terrain_before = {p.relative_to(root).as_posix(): p.read_bytes()
                              for p in root.rglob("*.json")
                              if "/density_function/" in p.as_posix() or "/dimension_type/" in p.as_posix()}
            BUILDER.finalize_pack_tree(root)
            after = json.loads((root / rel).read_text())
            expected = copy.deepcopy(before)
            changed = 0

            def visit(value):
                nonlocal changed
                if isinstance(value, dict):
                    if value.get("type") == "minecraft:block" and value.get("result_state", {}).get("Name") == "minecraft:lava":
                        value["result_state"] = {"Name": "minecraft:magma_block"}
                        changed += 1
                    for child in value.values():
                        visit(child)
                elif isinstance(value, list):
                    for child in value:
                        visit(child)

            visit(expected["surface_rule"])
            self.assertEqual(changed, 1, "Regression fixture must exercise the original unsafe lava rule")
            self.assertEqual(after, expected)
            self.assertEqual(after["sea_level"], 32)
            self.assertEqual(after["default_fluid"]["Name"], "minecraft:lava")
            for rel, original in terrain_before.items():
                self.assertEqual((root / rel).read_bytes(), original, rel)
            manifest = json.loads((root / "nevernether-core-manifest.json").read_text())
            self.assertEqual(manifest["field_integrity_revision"], "NN-FIELD-R1")

    def test_changed_upstream_contract_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            BASE.build_pack(root)
            BUILDER.make_delta_surface_solid(root)
            with self.assertRaises(ValueError):
                BUILDER.make_delta_surface_solid(root)

    def test_built_zip_has_no_surface_lava_and_preserves_fingerprint_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            packs = [Path(tmp) / "a.zip", Path(tmp) / "b.zip"]
            for pack in packs:
                BUILDER.build(pack)
            with zipfile.ZipFile(packs[0]) as a, zipfile.ZipFile(packs[1]) as b:
                self.assertEqual(a.namelist(), b.namelist())
                self.assertEqual(len(a.namelist()), len(set(a.namelist())))
                for name in a.namelist():
                    self.assertEqual(a.read(name), b.read(name), name)
                noise = json.loads(a.read("data/minecraft/worldgen/noise_settings/nether.json"))
                self.assertNotIn('"minecraft:lava"', json.dumps(noise["surface_rule"]))
                self.assertEqual(noise["noise"]["height"], 512)
                self.assertEqual(noise["noise"]["min_y"], -128)
                self.assertFalse(any("spring" in name for name in a.namelist()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
