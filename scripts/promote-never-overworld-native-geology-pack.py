#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

LEGACY_NAMES = (
    "deep_ore_iron",
    "deep_ore_gold",
    "deep_ore_redstone",
    "deep_ore_lapis",
    "deep_ore_diamond",
    "deep_ore_copper",
)
LEGACY_IDS = {f"neverfolia:{name}" for name in LEGACY_NAMES}
LEGACY_PATHS = {f"data/neverfolia/worldgen/placed_feature/{name}.json" for name in LEGACY_NAMES}
MANIFEST = "neveroverworld-test1-manifest.json"
NATIVE_ORES = ["coal", "iron", "copper", "gold", "redstone", "lapis", "diamond", "emerald"]


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld geology pack] {message}")


def dump_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def transform_bytes(payload: bytes) -> tuple[bytes, dict[str, int]]:
    source = zipfile.ZipFile(io.BytesIO(payload), "r")
    names = set(source.namelist())
    missing = sorted(LEGACY_PATHS - names)
    if missing:
        fail(f"expected legacy TEST1 deep ore files before native promotion, missing: {missing}")
    if MANIFEST not in names:
        fail("NeverOverworld TEST1 manifest missing")

    removed_refs = 0
    touched_biomes = 0
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for info in source.infolist():
            name = info.filename
            if name in LEGACY_PATHS:
                continue
            raw = source.read(name)
            if name.startswith("data/minecraft/worldgen/biome/") and name.endswith(".json"):
                biome = json.loads(raw)
                features = biome.get("features")
                changed = False
                if isinstance(features, list):
                    for stage in features:
                        if not isinstance(stage, list):
                            continue
                        kept = []
                        for entry in stage:
                            if isinstance(entry, str) and entry in LEGACY_IDS:
                                removed_refs += 1
                                changed = True
                            else:
                                kept.append(entry)
                        stage[:] = kept
                if changed:
                    raw = dump_json(biome)
                    touched_biomes += 1
            elif name == MANIFEST:
                manifest = json.loads(raw)
                deep = manifest.get("deep_placed_features")
                if isinstance(deep, list):
                    manifest["deep_placed_features"] = [x for x in deep if x not in LEGACY_NAMES]
                manifest["ore_generation"] = "neverfolia-native-geology-v2"
                manifest["native_ore_kinds"] = NATIVE_ORES
                manifest["legacy_count_height_deep_ores_removed"] = list(LEGACY_NAMES)
                manifest["native_geology_chunk_ownership"] = "owning-chunk-only"
                manifest["native_geology_seed_model"] = "world-seed+absolute-coarse-cell+ore-salt"
                raw = dump_json(manifest)
            target.writestr(info, raw)
    source.close()

    if removed_refs == 0:
        fail("legacy deep ore files existed but no biome feature references were removed")
    return out.getvalue(), {"removed_refs": removed_refs, "touched_biomes": touched_biomes}


def promote(input_path: Path, output_path: Path) -> None:
    payload, stats = transform_bytes(input_path.read_bytes())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    print("[NeverFolia][NeverOverworld geology pack] NATIVE GEOLOGY PROMOTION OK")
    print(f"  removed legacy deep ore files: {len(LEGACY_PATHS)}")
    print(f"  removed biome references: {stats['removed_refs']}")
    print(f"  touched biomes: {stats['touched_biomes']}")
    print(f"  retained material layer: neverfolia:deep_tuff when present")
    print(f"  native ores: {', '.join(NATIVE_ORES)}")
    print(f"  output: {output_path}")


def self_test() -> None:
    src = io.BytesIO()
    with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(LEGACY_PATHS):
            zf.writestr(path, "{}\n")
        zf.writestr("data/neverfolia/worldgen/placed_feature/deep_tuff.json", "{}\n")
        biome = {"features": [[], [], [], [], [], [], sorted(LEGACY_IDS | {"neverfolia:deep_tuff", "minecraft:ore_dirt"})]}
        zf.writestr("data/minecraft/worldgen/biome/plains.json", dump_json(biome))
        zf.writestr(
            MANIFEST,
            dump_json({"deep_placed_features": list(LEGACY_NAMES) + ["deep_tuff"], "worldgen_id": "NR-DEV-1"}),
        )
    promoted, stats = transform_bytes(src.getvalue())
    if stats["removed_refs"] != len(LEGACY_IDS):
        fail("SELF-TEST: did not remove every legacy biome reference")
    with zipfile.ZipFile(io.BytesIO(promoted)) as zf:
        names = set(zf.namelist())
        if names & LEGACY_PATHS:
            fail("SELF-TEST: legacy placed-feature files survived")
        if "data/neverfolia/worldgen/placed_feature/deep_tuff.json" not in names:
            fail("SELF-TEST: deep_tuff should remain until material geology replaces it")
        biome = json.loads(zf.read("data/minecraft/worldgen/biome/plains.json"))
        flat = [entry for stage in biome["features"] for entry in stage]
        if LEGACY_IDS & set(flat):
            fail("SELF-TEST: legacy biome references survived")
        manifest = json.loads(zf.read(MANIFEST))
        if manifest.get("ore_generation") != "neverfolia-native-geology-v2":
            fail("SELF-TEST: native geology manifest marker missing")
        if manifest.get("native_ore_kinds") != NATIVE_ORES:
            fail("SELF-TEST: native ore list drifted")
        if manifest.get("deep_placed_features") != ["deep_tuff"]:
            fail("SELF-TEST: only deep_tuff should remain in deep_placed_features")
    print("[NeverFolia][NeverOverworld geology pack] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove legacy TEST1 deep placed ores after native geology promotion")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None:
        parser.error("--input is required")
    output = args.output or args.input
    if not args.input.is_file():
        fail(f"input pack not found: {args.input}")
    if output.resolve() == args.input.resolve():
        with tempfile.NamedTemporaryFile(prefix="nr-native-geology-", suffix=".zip", delete=False) as tmp:
            temp_path = Path(tmp.name)
        try:
            promote(args.input, temp_path)
            temp_path.replace(args.input)
        finally:
            temp_path.unlink(missing_ok=True)
    else:
        promote(args.input, output)


if __name__ == "__main__":
    main()
