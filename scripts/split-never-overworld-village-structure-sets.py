#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

MANIFEST = "neveroverworld-test1-manifest.json"
VANILLA_SET = "data/minecraft/worldgen/structure_set/villages.json"
SPACING = 34
SEPARATION = 8
LEGACY_SAVANNA_SALT = 10387312
LEGACY_FREQUENCY = 0.0
POLICY = "independent-generated-bbox-final"

# Final deterministic TEST1 village grids. Each selected salt has an exact-layout
# ACCEPT on the deterministic TEST1 seed and has also passed the authoritative
# persisted Jigsaw bbox Y=128 zero-water audit after a normal server stop.
SETS = {
    "village_savanna": {
        "path": "data/neverfolia/worldgen/structure_set/village_savanna.json",
        "structure": "minecraft:village_savanna",
        "salt": 10387314,
    },
    "village_desert": {
        "path": "data/neverfolia/worldgen/structure_set/village_desert.json",
        "structure": "minecraft:village_desert",
        "salt": 10387413,
    },
    "village_snowy": {
        "path": "data/neverfolia/worldgen/structure_set/village_snowy.json",
        "structure": "minecraft:village_snowy",
        "salt": 10387618,
    },
    "village_plains": {
        "path": "data/neverfolia/worldgen/structure_set/village_plains.json",
        "structure": "minecraft:village_plains",
        "salt": 10400106,
    },
    "village_taiga": {
        "path": "data/neverfolia/worldgen/structure_set/village_taiga.json",
        "structure": "minecraft:village_taiga",
        "salt": 10388004,
    },
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld village split sets] {message}")


def dump(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def structure_set(structure: str, salt: int) -> dict[str, object]:
    return {
        "placement": {
            "type": "minecraft:random_spread",
            "salt": salt,
            "separation": SEPARATION,
            "spacing": SPACING,
        },
        "structures": [
            {
                "structure": structure,
                "weight": 1,
            }
        ],
    }


def inert_legacy_set() -> dict[str, object]:
    value = structure_set("minecraft:village_savanna", LEGACY_SAVANNA_SALT)
    placement = value["placement"]
    assert isinstance(placement, dict)
    placement["frequency"] = LEGACY_FREQUENCY
    return value


def transform(payload: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}
    if MANIFEST not in entries:
        fail("NeverOverworld manifest missing")

    # Disable the historical minecraft:villages grid so savanna cannot receive
    # a second placement grid alongside the independent NeverFolia structure set.
    entries[VANILLA_SET] = dump(inert_legacy_set())

    for config in SETS.values():
        entries[str(config["path"])] = dump(
            structure_set(str(config["structure"]), int(config["salt"]))
        )

    manifest = json.loads(entries[MANIFEST])
    manifest["village_structure_set_policy"] = POLICY
    manifest["village_structure_set_spacing"] = SPACING
    manifest["village_structure_set_separation"] = SEPARATION
    manifest["village_structure_set_salts"] = {
        name: int(config["salt"]) for name, config in SETS.items()
    }
    manifest["village_structure_set_paths"] = {
        name: str(config["path"]) for name, config in SETS.items()
    }
    manifest["minecraft_villages_frequency"] = LEGACY_FREQUENCY
    entries[MANIFEST] = dump(manifest)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name in sorted(entries):
            target.writestr(name, entries[name])
    return out.getvalue()


def validate(payload: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        names = set(source.namelist())
        if MANIFEST not in names:
            fail("validation: manifest missing")
        if VANILLA_SET not in names:
            fail("validation: inert legacy villages set missing")

        legacy = json.loads(source.read(VANILLA_SET))
        expected_legacy = inert_legacy_set()
        if legacy != expected_legacy:
            fail(f"validation: legacy minecraft:villages is not inert: {legacy}")

        manifest = json.loads(source.read(MANIFEST))
        salts: list[int] = []
        paths: list[str] = []
        for variant, config in SETS.items():
            path = str(config["path"])
            if path == VANILLA_SET:
                fail(f"validation: {variant} still uses legacy minecraft:villages")
            if path not in names:
                fail(f"validation: missing structure set {path}")
            value = json.loads(source.read(path))
            expected = structure_set(str(config["structure"]), int(config["salt"]))
            if value != expected:
                fail(f"validation: wrong payload for {variant}: {value}")
            salts.append(int(config["salt"]))
            paths.append(path)

    if len(salts) != len(set(salts)):
        fail(f"validation: village salts are not unique: {salts}")
    if len(paths) != len(set(paths)):
        fail(f"validation: village structure-set paths are not unique: {paths}")
    if manifest.get("village_structure_set_policy") != POLICY:
        fail("validation: final split-set manifest policy missing")
    if manifest.get("village_structure_set_spacing") != SPACING:
        fail("validation: split-set spacing mismatch")
    if manifest.get("village_structure_set_separation") != SEPARATION:
        fail("validation: split-set separation mismatch")
    if manifest.get("minecraft_villages_frequency") != LEGACY_FREQUENCY:
        fail("validation: legacy minecraft:villages frequency mismatch")

    expected_salts = {name: int(config["salt"]) for name, config in SETS.items()}
    if manifest.get("village_structure_set_salts") != expected_salts:
        fail(f"validation: final salt manifest mismatch: {manifest.get('village_structure_set_salts')}")
    expected_paths = {name: str(config["path"]) for name, config in SETS.items()}
    if manifest.get("village_structure_set_paths") != expected_paths:
        fail(f"validation: final path manifest mismatch: {manifest.get('village_structure_set_paths')}")


def apply_pack(path: Path) -> None:
    result = transform(path.read_bytes())
    validate(result)
    with tempfile.NamedTemporaryFile(prefix="nr-village-splitsets-", suffix=".zip", delete=False) as tmp:
        temp = Path(tmp.name)
        temp.write_bytes(result)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    print("[NeverFolia][NeverOverworld village split sets] FINAL INDEPENDENT VILLAGE GRIDS APPLIED")
    print(f"  spacing={SPACING}, separation={SEPARATION}")
    print(f"  minecraft:villages: inert frequency={LEGACY_FREQUENCY}")
    for variant, config in SETS.items():
        print(f"  {variant}: salt={config['salt']} -> {config['path']}")
    print("  acceptance: exact generated Jigsaw bbox + persisted Y=128 zero-water")


def self_test() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as target:
        target.writestr(MANIFEST, dump({"schema": 1}))
        # Simulate vanilla's shared weighted set. The transformer must replace it
        # with an inert legacy entry and emit five independent NeverFolia sets.
        target.writestr(VANILLA_SET, dump({"placement": {}, "structures": []}))
    first = transform(buf.getvalue())
    validate(first)
    second = transform(first)
    validate(second)
    if second != first:
        fail("SELF-TEST: idempotent reapply changed output")
    with zipfile.ZipFile(io.BytesIO(second), "r") as source:
        custom = [
            name for name in source.namelist()
            if name.startswith("data/neverfolia/worldgen/structure_set/village_")
        ]
        if len(custom) != 5:
            fail(f"SELF-TEST: expected five independent village sets, got {custom}")
        legacy = json.loads(source.read(VANILLA_SET))
        if legacy.get("placement", {}).get("frequency") != LEGACY_FREQUENCY:
            fail("SELF-TEST: legacy vanilla village set is not inert")
    print("[NeverFolia][NeverOverworld village split sets] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.input is None:
        parser.error("--input is required")
    self_test()
    apply_pack(args.input.resolve())


if __name__ == "__main__":
    main()
