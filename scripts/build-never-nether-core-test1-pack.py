#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_BUILDER = ROOT / "scripts/build-never-nether-core-pack.py"
BASALT_BLOBS_OVERRIDE = Path("data/minecraft/worldgen/placed_feature/basalt_blobs.json")
DELTA_OVERRIDE = Path("data/minecraft/worldgen/placed_feature/delta.json")
MANIFEST = Path("nevernether-core-manifest.json")
AIR_FILTER = {"type": "minecraft:block_predicate_filter", "predicate": {"type": "minecraft:matching_block_tag", "tag": "minecraft:air"}}
VEGETATION = {
    "crimson_fungi": ("minecraft:crimson_fungus", 8),
    "warped_fungi": ("minecraft:warped_fungus", 8),
    "crimson_forest_vegetation": ("minecraft:crimson_forest_vegetation", 6),
    "warped_forest_vegetation": ("minecraft:warped_forest_vegetation", 5),
    "nether_sprouts": ("minecraft:nether_sprouts", 4),
}


def load_base_builder():
    spec = importlib.util.spec_from_file_location("nevernether_core_builder", BASE_BUILDER)
    if spec is None or spec.loader is None: raise SystemExit(f"Cannot load base NeverNether builder: {BASE_BUILDER}")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def write_json(root: Path, rel: str, value: object) -> None:
    path = root / rel; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def debris_config(size: int) -> dict:
    return {"type":"minecraft:scattered_ore","config":{"discard_chance_on_air_exposure":1.0,"size":size,"targets":[{"state":{"Name":"minecraft:ancient_debris"},"target":{"predicate_type":"minecraft:tag_match","tag":"minecraft:base_stone_nether"}}]}}


def debris_placed(feature: str, minimum: int, maximum: int) -> dict:
    return {"feature":f"minecraft:{feature}","placement":[{"type":"minecraft:in_square"},{"type":"minecraft:height_range","height":{"type":"minecraft:trapezoid","min_inclusive":{"absolute":minimum},"max_inclusive":{"absolute":maximum}}},{"type":"minecraft:biome"}]}


def finalize_pack_tree(root: Path) -> None:
    basalt_override = root / BASALT_BLOBS_OVERRIDE
    if not basalt_override.is_file(): raise SystemExit("Expected diagnostic basalt_blobs override is missing; base builder contract changed")
    basalt_override.unlink()
    delta_override = root / DELTA_OVERRIDE
    if not delta_override.is_file(): raise SystemExit("Deterministic delta override is missing")
    for name, (feature, count) in VEGETATION.items():
        write_json(root, f"data/minecraft/worldgen/placed_feature/{name}.json", {"feature":feature,"placement":[{"type":"minecraft:count_on_every_layer","count":count},AIR_FILTER,{"type":"minecraft:biome"}]})
    write_json(root, "data/minecraft/worldgen/configured_feature/ore_ancient_debris_large.json", debris_config(3))
    write_json(root, "data/minecraft/worldgen/configured_feature/ore_ancient_debris_small.json", debris_config(2))
    write_json(root, "data/minecraft/worldgen/placed_feature/ore_ancient_debris_large.json", debris_placed("ore_ancient_debris_large", -64, 96))
    write_json(root, "data/minecraft/worldgen/placed_feature/ore_debris_small.json", debris_placed("ore_ancient_debris_small", -112, 144))
    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["replaced_vanilla_placed_features"] = ["delta", *VEGETATION.keys(), "ore_ancient_debris_large", "ore_debris_small"]
    manifest.pop("diagnostic_disabled_placed_features", None)
    manifest["netherrack_replace_blobs_mode"] = "vanilla_geometry_chunk_owned_v1"
    manifest["lava_vegetation_policy"] = "air-origin-filter-r6"
    manifest["ancient_debris_profile"] = {"peak_y":16,"large_range":[-64,96],"small_range":[-112,144],"distribution":"trapezoid","discard_chance_on_air_exposure":1.0}
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build(output: Path) -> None:
    base = load_base_builder()
    with tempfile.TemporaryDirectory(prefix="nevernether-core-test1-") as tmp:
        root = Path(tmp) / "pack"; root.mkdir(); base.build_pack(root); finalize_pack_tree(root); base.validate_json(root)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists(): output.unlink()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file(): archive.write(path, path.relative_to(root).as_posix())


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="nevernether-core-test1-selftest-") as tmp:
        output = Path(tmp) / "NeverNether-Core.zip"; build(output)
        with zipfile.ZipFile(output) as zf:
            names=set(zf.namelist()); manifest=json.loads(zf.read(MANIFEST.as_posix())); delta=json.loads(zf.read(DELTA_OVERRIDE.as_posix()))
            large=json.loads(zf.read("data/minecraft/worldgen/placed_feature/ore_ancient_debris_large.json")); small=json.loads(zf.read("data/minecraft/worldgen/placed_feature/ore_debris_small.json")); cfg=json.loads(zf.read("data/minecraft/worldgen/configured_feature/ore_ancient_debris_large.json")); fungi=json.loads(zf.read("data/minecraft/worldgen/placed_feature/crimson_fungi.json"))
        assert BASALT_BLOBS_OVERRIDE.as_posix() not in names
        assert delta["placement"][0] == {"type":"minecraft:count","count":0}
        assert large["placement"][1]["height"]["min_inclusive"] == {"absolute":-64}
        assert large["placement"][1]["height"]["max_inclusive"] == {"absolute":96}
        assert small["placement"][1]["height"]["min_inclusive"] == {"absolute":-112}
        assert small["placement"][1]["height"]["max_inclusive"] == {"absolute":144}
        assert cfg["config"]["discard_chance_on_air_exposure"] == 1.0
        assert AIR_FILTER in fungi["placement"]
        assert manifest["ancient_debris_profile"]["peak_y"] == 16
        assert manifest["lava_vegetation_policy"] == "air-origin-filter-r6"
    print("[NeverFolia][NeverNether core TEST1] R6 SELF-TEST OK")


def main() -> None:
    parser=argparse.ArgumentParser(description="Build the finalized NeverNether 26.2 TEST1 core datapack")
    parser.add_argument("--output",type=Path); parser.add_argument("--self-test",action="store_true"); args=parser.parse_args()
    if args.self_test: self_test(); return
    if args.output is None: parser.error("--output is required unless --self-test is used")
    self_test(); build(args.output); print(f"Built finalized TEST1 R6 core pack: {args.output}")


if __name__ == "__main__":
    main()
