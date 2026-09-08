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

# Keep vanilla spacing/separation but split the five weighted variants into
# independent candidate grids. Runtime QA selected these salts because each
# corresponding variant has at least one strict dry highland candidate on the
# deterministic TEST1 seed. Savanna keeps the vanilla village salt/grid.
SETS = {
    "village_savanna": {
        "path": VANILLA_SET,
        "structure": "minecraft:village_savanna",
        "salt": 10387312,
    },
    "village_desert": {
        "path": "data/neverfolia/worldgen/structure_set/village_desert.json",
        "structure": "minecraft:village_desert",
        "salt": 10387413,
    },
    "village_snowy": {
        "path": "data/neverfolia/worldgen/structure_set/village_snowy.json",
        "structure": "minecraft:village_snowy",
        "salt": 10387615,
    },
    "village_plains": {
        "path": "data/neverfolia/worldgen/structure_set/village_plains.json",
        "structure": "minecraft:village_plains",
        "salt": 10400103,
    },
    "village_taiga": {
        "path": "data/neverfolia/worldgen/structure_set/village_taiga.json",
        "structure": "minecraft:village_taiga",
        "salt": 10388001,
    },
}
SPACING = 34
SEPARATION = 8


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


def transform(payload: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}
    if MANIFEST not in entries:
        fail("NeverOverworld manifest missing")

    for config in SETS.values():
        entries[str(config["path"])] = dump(
            structure_set(str(config["structure"]), int(config["salt"]))
        )

    manifest = json.loads(entries[MANIFEST])
    manifest["village_structure_set_policy"] = "independent-dry-highland-r6"
    manifest["village_structure_set_spacing"] = SPACING
    manifest["village_structure_set_separation"] = SEPARATION
    manifest["village_structure_set_salts"] = {
        name: int(config["salt"]) for name, config in SETS.items()
    }
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
        manifest = json.loads(source.read(MANIFEST))
        salts: list[int] = []
        for variant, config in SETS.items():
            path = str(config["path"])
            if path not in names:
                fail(f"validation: missing structure set {path}")
            value = json.loads(source.read(path))
            expected = structure_set(str(config["structure"]), int(config["salt"]))
            if value != expected:
                fail(f"validation: wrong payload for {variant}: {value}")
            salts.append(int(config["salt"]))

    if len(salts) != len(set(salts)):
        fail(f"validation: village salts are not unique: {salts}")
    if manifest.get("village_structure_set_policy") != "independent-dry-highland-r6":
        fail("validation: split-set manifest policy missing")
    if manifest.get("village_structure_set_spacing") != SPACING:
        fail("validation: split-set spacing mismatch")
    if manifest.get("village_structure_set_separation") != SEPARATION:
        fail("validation: split-set separation mismatch")
    expected_salts = {name: int(config["salt"]) for name, config in SETS.items()}
    if manifest.get("village_structure_set_salts") != expected_salts:
        fail(f"validation: split-set salt manifest mismatch: {manifest.get('village_structure_set_salts')}")


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
    print("[NeverFolia][NeverOverworld village split sets] INDEPENDENT R6 VILLAGE GRIDS APPLIED")
    print(f"  spacing={SPACING}, separation={SEPARATION}")
    for variant, config in SETS.items():
        print(f"  {variant}: salt={config['salt']} -> {config['path']}")


def self_test() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as target:
        target.writestr(MANIFEST, dump({"schema": 1}))
        # Simulate vanilla's shared weighted set. The transformer must replace it.
        target.writestr(VANILLA_SET, dump({"placement": {}, "structures": []}))
    first = transform(buf.getvalue())
    validate(first)
    second = transform(first)
    validate(second)
    with zipfile.ZipFile(io.BytesIO(second), "r") as source:
        if len([name for name in source.namelist() if name.endswith("worldgen/structure_set/villages.json")]) != 1:
            fail("SELF-TEST: duplicate vanilla villages set path")
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
