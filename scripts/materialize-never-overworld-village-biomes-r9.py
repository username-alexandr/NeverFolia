#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

MANIFEST = "neveroverworld-test1-manifest.json"
STRUCTURE_PREFIX = "data/minecraft/worldgen/structure/"
EXPECTED_TAG_PREFIX = "#minecraft:has_structure/"

BIOMES = {
    "village_plains": [
        "minecraft:plains",
        "minecraft:meadow",
        "minecraft:cherry_grove",
        "minecraft:savanna_plateau",
        "minecraft:windswept_savanna",
        "minecraft:stony_peaks",
    ],
    "village_desert": [
        "minecraft:desert",
        "minecraft:badlands",
        "minecraft:wooded_badlands",
        "minecraft:eroded_badlands",
        "minecraft:stony_peaks",
        "minecraft:savanna_plateau",
    ],
    "village_savanna": [
        "minecraft:savanna",
        "minecraft:savanna_plateau",
        "minecraft:windswept_savanna",
        "minecraft:stony_peaks",
    ],
    "village_snowy": [
        "minecraft:snowy_plains",
        "minecraft:grove",
        "minecraft:snowy_slopes",
        "minecraft:jagged_peaks",
        "minecraft:frozen_peaks",
    ],
    "village_taiga": [
        "minecraft:taiga",
        "minecraft:old_growth_pine_taiga",
        "minecraft:old_growth_spruce_taiga",
        "minecraft:grove",
        "minecraft:snowy_slopes",
        "minecraft:jagged_peaks",
        "minecraft:frozen_peaks",
        "minecraft:stony_peaks",
    ],
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village direct biomes] {message}")


def dump(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def embedded_folia_payload(server_jar: Path) -> bytes:
    with zipfile.ZipFile(server_jar) as outer:
        candidates = [
            name
            for name in outer.namelist()
            if name.startswith("META-INF/versions/") and name.endswith("/folia-26.2.jar")
        ]
        if len(candidates) != 1:
            fail(f"expected one embedded Folia 26.2 JAR, got {candidates}")
        return outer.read(candidates[0])


def vanilla_structures(server_jar: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    payload = embedded_folia_payload(server_jar)
    with zipfile.ZipFile(io.BytesIO(payload)) as inner:
        for variant in BIOMES:
            path = f"{STRUCTURE_PREFIX}{variant}.json"
            try:
                value = json.loads(inner.read(path))
            except KeyError as exc:
                fail(f"exact server JAR is missing {path}")
            expected_tag = EXPECTED_TAG_PREFIX + variant
            if value.get("biomes") != expected_tag:
                fail(f"{variant}: unexpected vanilla biome HolderSet {value.get('biomes')!r}; expected {expected_tag!r}")
            if value.get("type") != "minecraft:jigsaw":
                fail(f"{variant}: expected vanilla jigsaw structure, got {value.get('type')!r}")
            if value.get("max_distance_from_center") != 80:
                fail(f"{variant}: vanilla max_distance_from_center drifted: {value.get('max_distance_from_center')!r}")
            result[variant] = value
    return result


def transform(pack: bytes, server_jar: Path) -> bytes:
    with zipfile.ZipFile(io.BytesIO(pack), "r") as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}
    if MANIFEST not in entries:
        fail("NeverOverworld manifest missing")

    source_structures = vanilla_structures(server_jar)
    for variant, biomes in BIOMES.items():
        value = json.loads(json.dumps(source_structures[variant]))
        value["biomes"] = list(biomes)
        entries[f"{STRUCTURE_PREFIX}{variant}.json"] = dump(value)

    manifest = json.loads(entries[MANIFEST])
    manifest["village_biome_holder_policy"] = "direct-list-materialized-from-exact-folia-26.2-structure"
    manifest["village_biome_holder_sets"] = BIOMES
    manifest["village_biome_tag_merge_authoritative"] = False
    entries[MANIFEST] = dump(manifest)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name in sorted(entries):
            target.writestr(name, entries[name])
    return out.getvalue()


def validate(payload: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        manifest = json.loads(source.read(MANIFEST))
        if manifest.get("village_biome_holder_policy") != "direct-list-materialized-from-exact-folia-26.2-structure":
            fail("direct-list manifest policy missing")
        if manifest.get("village_biome_holder_sets") != BIOMES:
            fail("direct-list manifest HolderSets mismatch")
        if manifest.get("village_biome_tag_merge_authoritative") is not False:
            fail("tag-merge authority marker mismatch")
        for variant, expected in BIOMES.items():
            path = f"{STRUCTURE_PREFIX}{variant}.json"
            value = json.loads(source.read(path))
            if value.get("biomes") != expected:
                fail(f"{variant}: materialized direct HolderSet mismatch: {value.get('biomes')!r}")
            if value.get("type") != "minecraft:jigsaw" or value.get("max_distance_from_center") != 80:
                fail(f"{variant}: vanilla structure geometry fields changed unexpectedly")


def apply_pack(pack_path: Path, server_jar: Path) -> None:
    result = transform(pack_path.read_bytes(), server_jar)
    validate(result)
    with tempfile.NamedTemporaryFile(prefix="nr-r9-village-direct-biomes-", suffix=".zip", delete=False) as tmp:
        temp = Path(tmp.name)
        temp.write_bytes(result)
    try:
        temp.replace(pack_path)
    finally:
        temp.unlink(missing_ok=True)
    print("[NeverFolia][R9 village direct biomes] EXACT-SERVER STRUCTURES MATERIALIZED")
    print("  biome policy: direct HolderSet lists; no vanilla-tag merge dependency")
    for variant, biomes in BIOMES.items():
        print(f"  {variant}: {', '.join(biomes)}")


def synthetic_server_jar() -> bytes:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as z:
        for variant in BIOMES:
            z.writestr(
                f"{STRUCTURE_PREFIX}{variant}.json",
                dump({
                    "type": "minecraft:jigsaw",
                    "biomes": EXPECTED_TAG_PREFIX + variant,
                    "max_distance_from_center": 80,
                    "size": 6,
                    "start_pool": f"minecraft:village/{variant.removeprefix('village_')}/town_centers",
                }),
            )
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("META-INF/versions/26.2/folia-26.2.jar", inner.getvalue())
    return outer.getvalue()


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="nr-r9-village-direct-biomes-") as tmp_raw:
        root = Path(tmp_raw)
        server = root / "server.jar"
        server.write_bytes(synthetic_server_jar())
        pack_buf = io.BytesIO()
        with zipfile.ZipFile(pack_buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFEST, dump({"schema": 1}))
        first = transform(pack_buf.getvalue(), server)
        validate(first)
        second = transform(first, server)
        validate(second)
        if second != first:
            fail("SELF-TEST: materializer is not idempotent")
    if len(BIOMES) != 5:
        fail("SELF-TEST: expected exactly five village variants")
    print("[NeverFolia][R9 village direct biomes] SELF-TEST OK")
    print("  exact server structure JSON preserved except biomes")
    print("  HolderSet representation: direct registry list")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--server-jar", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None or args.server_jar is None:
        parser.error("--input and --server-jar are required")
    self_test()
    pack = args.input.resolve()
    server = args.server_jar.resolve()
    if not pack.is_file():
        fail(f"pack not found: {pack}")
    if not server.is_file():
        fail(f"server JAR not found: {server}")
    apply_pack(pack, server)


if __name__ == "__main__":
    main()
