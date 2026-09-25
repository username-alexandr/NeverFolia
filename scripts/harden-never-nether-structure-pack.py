#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_SPEC = ROOT / "worldgen-spec" / "never-nether-structures.json"
WORLD_SPEC = ROOT / "worldgen-spec" / "never-nether.json"

MONUMENT_ID = "repurposed_structures:monument_nether"
MONUMENT_BIOME_TAG = "#neverfolia:never_nether/monument_biomes"
MONUMENT_BIOME_TAG_PATH = PurePosixPath(
    "data/neverfolia/tags/worldgen/biome/never_nether/monument_biomes.json"
)
MONUMENT_BIOMES = (
    "minecraft:nether_wastes",
    "minecraft:soul_sand_valley",
    "minecraft:crimson_forest",
    "minecraft:warped_forest",
    "minecraft:basalt_deltas",
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverNether structure hardener] {message}")


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_json(payload: bytes, label: str) -> dict:
    try:
        value = json.loads(payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        fail(f"invalid JSON in {label}: {exc}")
    if not isinstance(value, dict):
        fail(f"expected JSON object in {label}")
    return value


def structure_path(structure_id: str) -> PurePosixPath:
    namespace, resource = structure_id.split(":", 1)
    return PurePosixPath("data") / namespace / "worldgen/structure" / f"{resource}.json"


def approved_structure_ids(spec: dict) -> tuple[str, ...]:
    result: list[str] = []
    for group in spec["placement_groups"].values():
        for entry in group["structures"]:
            result.append(entry["id"])
    if len(result) != 20 or len(set(result)) != 20:
        fail(f"expected exactly 20 unique custom structures, got {len(result)}")
    return tuple(sorted(result))


def load_zip(path: Path) -> dict[PurePosixPath, bytes]:
    if not path.is_file():
        fail(f"input pack not found: {path}")
    result: dict[PurePosixPath, bytes] = {}
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            p = PurePosixPath(info.filename)
            if p.is_absolute() or ".." in p.parts:
                fail(f"unsafe ZIP path: {p}")
            result[p] = zf.read(info)
    return result


def write_zip(path: Path, files: dict[PurePosixPath, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(files, key=str):
            zf.writestr(str(name), files[name])


def calculate_padding(structure_spec: dict, world_spec: dict) -> dict[str, int]:
    rules = structure_spec["candidate_rejection"]
    dimension = world_spec["dimension"]
    dimension_min_y = int(dimension["min_y"])
    dimension_max_y = dimension_min_y + int(dimension["height"]) - 1
    allowed_min_y = int(rules["reject_if_bounding_box_min_y_below"])
    allowed_max_y = int(rules["reject_if_bounding_box_max_y_above"])

    bottom = allowed_min_y - dimension_min_y
    top = dimension_max_y - allowed_max_y
    if bottom != 5 or top != 517:
        fail(
            "approved geometry must resolve to dimension_padding bottom=5/top=517; "
            f"got bottom={bottom}, top={top}"
        )
    return {"bottom": bottom, "top": top}


def harden(input_pack: Path, output_pack: Path) -> None:
    structure_spec = json.loads(STRUCTURE_SPEC.read_text(encoding="utf-8"))
    world_spec = json.loads(WORLD_SPEC.read_text(encoding="utf-8"))
    ids = approved_structure_ids(structure_spec)
    padding = calculate_padding(structure_spec, world_spec)
    files = load_zip(input_pack)

    for structure_id in ids:
        path = structure_path(structure_id)
        payload = files.get(path)
        if payload is None:
            fail(f"approved structure missing from integration pack: {structure_id}")
        value = read_json(payload, str(path))
        if value.get("type") != "minecraft:jigsaw":
            fail(f"{structure_id}: expected native minecraft:jigsaw before hardening")

        # JigsawStructure dimension_padding constrains the complete generated
        # structure bounding box, not merely its start position. With NeverNether's
        # technical Y=-128..895 this produces an allowed BB of Y=-123..378.
        value["dimension_padding"] = dict(padding)

        if structure_id == MONUMENT_ID:
            # The supplied Better Monuments compatibility archive references a
            # Repurposed Structures biome tag which is not present in that archive.
            # NeverFolia owns biome eligibility; lava-basin validation remains the
            # authoritative terrain predicate in the native placement hook.
            value["biomes"] = MONUMENT_BIOME_TAG

        files[path] = json_bytes(value)

    files[MONUMENT_BIOME_TAG_PATH] = json_bytes(
        {"replace": False, "values": list(MONUMENT_BIOMES)}
    )

    manifest_path = PurePosixPath("nevernether-structure-integration-manifest.json")
    manifest_payload = files.get(manifest_path)
    if manifest_payload is not None:
        manifest = read_json(manifest_payload, str(manifest_path))
        manifest["neverfolia_hardening"] = {
            "dimension_padding": padding,
            "effective_bounding_box_y": [-123, 378],
            "monument_biome_tag": MONUMENT_BIOME_TAG,
            "monument_biomes": list(MONUMENT_BIOMES),
            "monument_terrain_authority": "native_large_lava_basin_validator",
        }
        files[manifest_path] = json_bytes(manifest)

    validate(files, ids, padding)
    write_zip(output_pack, files)
    print(f"Hardened {output_pack}")
    print(f"  custom structures: {len(ids)}")
    print(f"  dimension padding: bottom={padding['bottom']} top={padding['top']}")
    print(f"  effective structure BB Y: -123..378")
    print(f"  monument biome tag: {MONUMENT_BIOME_TAG}")


def validate(
    files: dict[PurePosixPath, bytes],
    ids: tuple[str, ...],
    padding: dict[str, int],
) -> None:
    for structure_id in ids:
        path = structure_path(structure_id)
        value = read_json(files[path], str(path))
        if value.get("dimension_padding") != padding:
            fail(f"{structure_id}: dimension_padding mismatch")
        if structure_id == MONUMENT_ID and value.get("biomes") != MONUMENT_BIOME_TAG:
            fail("Nether Monument does not use the NeverFolia-owned biome tag")

    tag = read_json(files[MONUMENT_BIOME_TAG_PATH], str(MONUMENT_BIOME_TAG_PATH))
    if tuple(tag.get("values", ())) != MONUMENT_BIOMES:
        fail("Nether Monument biome tag values changed unexpectedly")


def self_test() -> None:
    structure_spec = json.loads(STRUCTURE_SPEC.read_text(encoding="utf-8"))
    ids = approved_structure_ids(structure_spec)
    with tempfile.TemporaryDirectory(prefix="nevernether-hardener-selftest-") as tmp_raw:
        tmp = Path(tmp_raw)
        source = tmp / "integration.zip"
        output = tmp / "hardened.zip"
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("pack.mcmeta", json.dumps({"pack": {"description": "test", "pack_format": 107}}))
            zf.writestr(
                "nevernether-structure-integration-manifest.json",
                json.dumps({"id": "NN-DEV-1-structures-test1"}),
            )
            for structure_id in ids:
                biomes = (
                    "#repurposed_structures:has_structure/monuments/nether"
                    if structure_id == MONUMENT_ID
                    else "#minecraft:is_nether"
                )
                zf.writestr(
                    str(structure_path(structure_id)),
                    json.dumps(
                        {
                            "type": "minecraft:jigsaw",
                            "biomes": biomes,
                            "step": "surface_structures",
                            "spawn_overrides": {},
                            "terrain_adaptation": "none",
                            "start_pool": "neverfolia:test",
                            "size": 1,
                            "start_height": {"absolute": 32},
                            "max_distance_from_center": 32,
                            "use_expansion_hack": False,
                        }
                    ),
                )

        harden(source, output)
        files = load_zip(output)
        padding = {"bottom": 5, "top": 517}
        validate(files, ids, padding)
        monument = read_json(files[structure_path(MONUMENT_ID)], MONUMENT_ID)
        if monument["biomes"] != MONUMENT_BIOME_TAG:
            fail("SELF-TEST: source monument biome dependency survived")
        manifest = read_json(
            files[PurePosixPath("nevernether-structure-integration-manifest.json")],
            "integration manifest",
        )
        if manifest.get("neverfolia_hardening", {}).get("effective_bounding_box_y") != [-123, 378]:
            fail("SELF-TEST: hardening metadata missing from integration manifest")

    print("[NeverFolia][NeverNether structure hardener] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply NeverFolia-owned bounds and biome policy to a NeverNether structure integration pack"
    )
    parser.add_argument("--input", type=Path, help="Structure integration ZIP")
    parser.add_argument("--output", type=Path, help="Hardened output ZIP")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.input is None or args.output is None:
        parser.error("--input and --output are required unless --self-test is used")
    harden(args.input, args.output)


if __name__ == "__main__":
    main()
