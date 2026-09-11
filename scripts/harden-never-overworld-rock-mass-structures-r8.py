#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILDER_PATH = ROOT / "build-never-overworld-native-structures.py"
TARGETS = {
    "sealed_cache": "data/neverfolia/structure/never_overworld/structures/sealed_cache.nbt",
    "buried_sanctum": "data/neverfolia/structure/never_overworld/structures/buried_sanctum.nbt",
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld rock-mass R8] {message}")


def load_builder():
    spec = importlib.util.spec_from_file_location("nr_native_structures_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        fail(f"cannot import structure builder: {BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def host_block(x: int, y: int, z: int) -> str:
    value = (x * 31 + y * 17 + z * 13) % 19
    if value in (0, 7):
        return "minecraft:tuff"
    if value == 11:
        return "minecraft:andesite"
    return "minecraft:deepslate"


def fill_ellipsoid(v, cx: float, cy: float, cz: float, rx: float, ry: float, rz: float) -> None:
    sx, sy, sz = v.size
    for y in range(sy):
        for z in range(sz):
            for x in range(sx):
                nx = (x - cx) / rx
                ny = (y - cy) / ry
                nz = (z - cz) / rz
                d = nx * nx + ny * ny + nz * nz
                rough = 1.0 + ((((x * 734287 + y * 912271 + z * 438289) & 15) - 7) / 90.0)
                if d <= rough:
                    v.set(x, y, z, host_block(x, y, z))


def sealed_cache(builder):
    v = builder.Voxel((17, 14, 17))
    fill_ellipsoid(v, 8.0, 6.5, 8.0, 8.0, 6.4, 8.0)

    ox, oy, oz = 4, 3, 4
    v.shell(ox, oy, oz, ox + 8, oy + 7, oz + 8, builder.TILES)
    v.box(ox + 1, oy + 1, oz + 1, ox + 7, oy + 6, oz + 7, builder.AIR)
    v.box(ox, oy, oz, ox + 8, oy, oz + 8, "minecraft:polished_deepslate")
    v.box(ox + 3, oy + 1, oz + 3, ox + 5, oy + 2, oz + 5, "minecraft:reinforced_deepslate")
    v.set(ox + 4, oy + 3, oz + 4, "minecraft:gold_block")
    for x, z in ((ox + 1, oz + 1), (ox + 7, oz + 1), (ox + 1, oz + 7), (ox + 7, oz + 7)):
        v.pillar(x, z, oy + 1, oy + 5, "minecraft:chiseled_deepslate")
    return v


def buried_sanctum(builder):
    v = builder.Voxel((25, 17, 25))
    fill_ellipsoid(v, 12.0, 8.0, 12.0, 12.0, 7.8, 12.0)

    ox, oy, oz = 4, 4, 4
    v.shell(ox, oy, oz, ox + 16, oy + 8, oz + 16, builder.STONE)
    v.box(ox + 1, oy + 1, oz + 1, ox + 15, oy + 7, oz + 15, builder.AIR)
    v.box(ox, oy, oz, ox + 16, oy, oz + 16, "minecraft:polished_andesite")
    for x, z in ((ox + 3, oz + 3), (ox + 13, oz + 3), (ox + 3, oz + 13), (ox + 13, oz + 13)):
        v.pillar(x, z, oy + 1, oy + 6, "minecraft:chiseled_stone_bricks")
    v.box(ox + 6, oy + 1, oz + 6, ox + 10, oy + 2, oz + 10, "minecraft:polished_blackstone_bricks")
    v.set(ox + 8, oy + 3, oz + 8, "minecraft:lodestone")
    for x in range(ox + 2, ox + 15, 3):
        v.set(x, oy + 1, oz + 1, "minecraft:cracked_stone_bricks")
        v.set(x, oy + 1, oz + 15, "minecraft:mossy_stone_bricks")
    return v


def replacements() -> dict[str, bytes]:
    builder = load_builder()
    cache = sealed_cache(builder)
    sanctum = buried_sanctum(builder)
    return {
        TARGETS["sealed_cache"]: builder.structure_nbt(cache.size, cache.blocks),
        TARGETS["buried_sanctum"]: builder.structure_nbt(sanctum.size, sanctum.blocks),
    }


def rewrite_pack(path: Path) -> None:
    repl = replacements()
    with zipfile.ZipFile(path, "r") as src:
        files = {info.filename: src.read(info.filename) for info in src.infolist() if not info.is_dir()}
    missing = sorted(set(repl) - set(files))
    if missing:
        fail(f"native structure templates missing from pack: {missing}")
    files.update(repl)
    with tempfile.NamedTemporaryFile(prefix="nr-r8-rockmass-", suffix=".zip", delete=False) as handle:
        temp = Path(handle.name)
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
            for name in sorted(files):
                dst.writestr(name, files[name])
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    print("[NeverFolia][NeverOverworld rock-mass R8] natural host envelopes installed")
    print("  sealed_cache: 17x14x17 / sealed / irregular deepslate+tuff jacket")
    print("  buried_sanctum: 25x17x25 / irregular deepslate+tuff jacket")


def self_test() -> None:
    builder = load_builder()
    cache = sealed_cache(builder)
    sanctum = buried_sanctum(builder)
    if cache.size != (17, 14, 17) or sanctum.size != (25, 17, 25):
        fail("SELF-TEST: R8 structure sizes drifted")
    cache_names = {name for name, _props in cache.blocks.values()}
    sanctum_names = {name for name, _props in sanctum.blocks.values()}
    for required in ("minecraft:gold_block", "minecraft:reinforced_deepslate", "minecraft:deepslate", "minecraft:tuff"):
        if required not in cache_names:
            fail(f"SELF-TEST: cache missing {required}")
    for required in ("minecraft:lodestone", "minecraft:stone_bricks", "minecraft:deepslate", "minecraft:tuff"):
        if required not in sanctum_names:
            fail(f"SELF-TEST: sanctum missing {required}")
    if len(cache.blocks) < 1100 or len(sanctum.blocks) < 3000:
        fail("SELF-TEST: natural host envelope unexpectedly sparse")
    payloads = replacements()
    if set(payloads) != set(TARGETS.values()) or not all(len(data) > 150 for data in payloads.values()):
        fail("SELF-TEST: replacement NBT generation failed")
    print("[NeverFolia][NeverOverworld rock-mass R8] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None or not args.input.is_file():
        parser.error("--input existing pack is required")
    self_test()
    rewrite_pack(args.input.resolve())


if __name__ == "__main__":
    main()
