#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path

BLOCKED = frozenset(
    {
        "minecraft:lake_lava_underground",
        "minecraft:lake_lava_surface",
        "minecraft:spring_water",
        "minecraft:spring_lava",
        "minecraft:spring_lava_frozen",
    }
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld native fluid pack] {message}")


def inspect(pack: Path) -> tuple[int, set[str]]:
    if not pack.is_file():
        fail(f"pack not found: {pack}")
    total = 0
    found: set[str] = set()
    biome_files = 0
    with zipfile.ZipFile(pack) as zf:
        for name in zf.namelist():
            if not name.startswith("data/minecraft/worldgen/biome/") or not name.endswith(".json"):
                continue
            biome_files += 1
            try:
                biome = json.loads(zf.read(name))
            except Exception as exc:
                fail(f"cannot parse {name}: {exc}")
            features = biome.get("features", [])
            if not isinstance(features, list):
                continue
            for stage in features:
                if not isinstance(stage, list):
                    continue
                for entry in stage:
                    if isinstance(entry, str) and entry in BLOCKED:
                        total += 1
                        found.add(entry)
    if biome_files == 0:
        fail("pack contains no vanilla Overworld biome JSON")
    if total == 0:
        fail("no vanilla generated-fluid feature references remain; datapack stripping is still authoritative")
    return total, found


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="nr-native-fluid-pack-") as raw:
        root = Path(raw)
        good = root / "good.zip"
        with zipfile.ZipFile(good, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "data/minecraft/worldgen/biome/plains.json",
                json.dumps({"features": [[], ["minecraft:spring_water"], ["minecraft:other"]]}),
            )
        count, found = inspect(good)
        if count != 1 or found != {"minecraft:spring_water"}:
            fail(f"SELF-TEST: expected one preserved spring_water reference, got count={count} found={found}")

        stripped = root / "stripped.zip"
        with zipfile.ZipFile(stripped, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "data/minecraft/worldgen/biome/plains.json",
                json.dumps({"features": [[], ["minecraft:other"]]}),
            )
        try:
            inspect(stripped)
        except SystemExit:
            pass
        else:
            fail("SELF-TEST: fully stripped pack was incorrectly accepted")

    print("[NeverFolia][NeverOverworld native fluid pack] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify that NR Core preserves vanilla generated-fluid feature references")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None:
        parser.error("--input is required unless --self-test is used")
    count, found = inspect(args.input.resolve())
    print("[NeverFolia][NeverOverworld native fluid pack] PRESERVED VANILLA FLUID FEATURES OK")
    print(f"  references: {count}")
    print(f"  ids: {', '.join(sorted(found))}")


if __name__ == "__main__":
    main()
