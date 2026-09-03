#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import struct
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT_NAMESPACE = "neverfolia"
DATA_VERSION = 4903  # informational; runtime DFU can update structure templates as needed

STRUCTURES = {
    "buried_sanctum": {"size": (17, 9, 17), "step": "underground_structures", "terrain": None},
    "abyssal_archive": {"size": (15, 10, 19), "step": "underground_structures", "terrain": None},
    "ancient_cistern": {"size": (17, 9, 17), "step": "underground_structures", "terrain": None},
    "collapsed_mine": {"size": (19, 8, 13), "step": "underground_structures", "terrain": None},
    "geode_vault": {"size": (15, 15, 15), "step": "underground_structures", "terrain": None},
    "flooded_ruins": {"size": (21, 9, 15), "step": "underground_structures", "terrain": None},
    "prospector_camp": {"size": (15, 8, 15), "step": "underground_structures", "terrain": None},
    "sealed_cache": {"size": (9, 8, 9), "step": "underground_structures", "terrain": None},
}

GROUPS = {
    "deep_major": {
        "spacing": 96,
        "separation": 36,
        "salt": 147302113,
        "structures": [("buried_sanctum", 4), ("abyssal_archive", 2), ("ancient_cistern", 3)],
    },
    "deep_medium": {
        "spacing": 48,
        "separation": 18,
        "salt": 913440721,
        "structures": [("collapsed_mine", 5), ("geode_vault", 3), ("flooded_ruins", 3)],
    },
    "deep_ambient": {
        "spacing": 22,
        "separation": 8,
        "salt": 1880479151,
        "structures": [("prospector_camp", 5), ("sealed_cache", 3)],
    },
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld structures] {message}")


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


# ---- Minimal vanilla structure-template NBT writer ----------------------------
# We intentionally emit only the tags needed by StructureTemplate:
# size, entities, blocks, palette, DataVersion.


def _utf(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack(">H", len(raw)) + raw


def _tag_header(tag_type: int, name: str) -> bytes:
    return bytes([tag_type]) + _utf(name)


def _tag_int(name: str, value: int) -> bytes:
    return _tag_header(3, name) + struct.pack(">i", value)


def _tag_string(name: str, value: str) -> bytes:
    return _tag_header(8, name) + _utf(value)


def _tag_int_list(name: str, values: tuple[int, ...] | list[int]) -> bytes:
    return _tag_header(9, name) + bytes([3]) + struct.pack(">i", len(values)) + b"".join(struct.pack(">i", v) for v in values)


def _tag_compound_payload(tags: list[bytes]) -> bytes:
    return b"".join(tags) + b"\x00"


def _tag_list_of_compounds(name: str, compounds: list[bytes]) -> bytes:
    return _tag_header(9, name) + bytes([10]) + struct.pack(">i", len(compounds)) + b"".join(compounds)


def _palette_entry(name: str, properties: dict[str, str] | None = None) -> bytes:
    tags = [_tag_string("Name", name)]
    if properties:
        prop_tags = [_tag_string(k, v) for k, v in sorted(properties.items())]
        tags.append(_tag_header(10, "Properties") + _tag_compound_payload(prop_tags))
    return _tag_compound_payload(tags)


def structure_nbt(size: tuple[int, int, int], blocks: dict[tuple[int, int, int], tuple[str, dict[str, str] | None]]) -> bytes:
    palette_keys: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    palette_index: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
    block_compounds: list[bytes] = []

    for pos in sorted(blocks, key=lambda p: (p[1], p[2], p[0])):
        name, props = blocks[pos]
        key = (name, tuple(sorted((props or {}).items())))
        if key not in palette_index:
            palette_index[key] = len(palette_keys)
            palette_keys.append(key)
        state = palette_index[key]
        block_compounds.append(
            _tag_compound_payload([
                _tag_int_list("pos", list(pos)),
                _tag_int("state", state),
            ])
        )

    palette = [_palette_entry(name, dict(props) if props else None) for name, props in palette_keys]
    root_payload = _tag_compound_payload([
        _tag_int_list("size", list(size)),
        _tag_list_of_compounds("entities", []),
        _tag_list_of_compounds("blocks", block_compounds),
        _tag_list_of_compounds("palette", palette),
        _tag_int("DataVersion", DATA_VERSION),
    ])
    raw = bytes([10]) + _utf("") + root_payload
    return gzip.compress(raw, compresslevel=9, mtime=0)


# ---- Voxel helpers ----------------------------------------------------------


@dataclass
class Voxel:
    size: tuple[int, int, int]

    def __post_init__(self) -> None:
        self.blocks: dict[tuple[int, int, int], tuple[str, dict[str, str] | None]] = {}

    def set(self, x: int, y: int, z: int, block: str, props: dict[str, str] | None = None) -> None:
        sx, sy, sz = self.size
        if 0 <= x < sx and 0 <= y < sy and 0 <= z < sz:
            self.blocks[(x, y, z)] = (block, props)

    def box(self, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int, block: str) -> None:
        for y in range(y1, y2 + 1):
            for z in range(z1, z2 + 1):
                for x in range(x1, x2 + 1):
                    self.set(x, y, z, block)

    def shell(self, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int, block: str) -> None:
        for y in range(y1, y2 + 1):
            for z in range(z1, z2 + 1):
                for x in range(x1, x2 + 1):
                    if x in (x1, x2) or y in (y1, y2) or z in (z1, z2):
                        self.set(x, y, z, block)

    def floor(self, y: int, block: str, margin: int = 0) -> None:
        sx, _, sz = self.size
        self.box(margin, y, margin, sx - 1 - margin, y, sz - 1 - margin, block)

    def pillar(self, x: int, z: int, y1: int, y2: int, block: str) -> None:
        for y in range(y1, y2 + 1):
            self.set(x, y, z, block)


STONE = "minecraft:stone_bricks"
DEEP = "minecraft:deepslate_bricks"
TILES = "minecraft:deepslate_tiles"
TUFF = "minecraft:tuff_bricks"
PRIS = "minecraft:prismarine_bricks"
DARK_PRIS = "minecraft:dark_prismarine"
OAK = "minecraft:oak_planks"
LOG = "minecraft:oak_log"
AIR = "minecraft:air"
WATER = "minecraft:water"


def buried_sanctum() -> Voxel:
    v = Voxel(STRUCTURES["buried_sanctum"]["size"])
    v.shell(0, 0, 0, 16, 8, 16, STONE)
    v.box(1, 1, 1, 15, 7, 15, AIR)
    v.floor(0, "minecraft:polished_andesite")
    for x, z in ((3, 3), (13, 3), (3, 13), (13, 13)):
        v.pillar(x, z, 1, 6, "minecraft:chiseled_stone_bricks")
    v.box(6, 1, 6, 10, 2, 10, "minecraft:polished_blackstone_bricks")
    v.set(8, 3, 8, "minecraft:lodestone")
    for x in range(2, 15, 3):
        v.set(x, 1, 1, "minecraft:cracked_stone_bricks")
        v.set(x, 1, 15, "minecraft:mossy_stone_bricks")
    # Entry breach toward -Z.
    v.box(7, 1, 0, 9, 4, 1, AIR)
    return v


def abyssal_archive() -> Voxel:
    v = Voxel(STRUCTURES["abyssal_archive"]["size"])
    v.shell(0, 0, 0, 14, 9, 18, DEEP)
    v.box(1, 1, 1, 13, 8, 17, AIR)
    v.floor(0, TILES)
    for z in (3, 7, 11, 15):
        for x in (2, 12):
            v.box(x, 1, z, x, 5, z + 1, "minecraft:bookshelf")
            v.set(x, 6, z, "minecraft:chiseled_deepslate")
    v.box(5, 1, 7, 9, 1, 11, TUFF)
    v.set(7, 2, 9, "minecraft:lapis_block")
    v.box(6, 1, 0, 8, 4, 1, AIR)
    return v


def ancient_cistern() -> Voxel:
    v = Voxel(STRUCTURES["ancient_cistern"]["size"])
    v.shell(0, 0, 0, 16, 8, 16, TUFF)
    v.box(1, 1, 1, 15, 7, 15, AIR)
    v.floor(0, "minecraft:polished_tuff")
    # Basin.
    v.box(3, 1, 3, 13, 1, 13, "minecraft:polished_tuff")
    v.box(4, 2, 4, 12, 4, 12, WATER)
    for x, z in ((2, 2), (14, 2), (2, 14), (14, 14)):
        v.pillar(x, z, 1, 6, "minecraft:chiseled_tuff_bricks")
    v.box(7, 1, 0, 9, 5, 1, AIR)
    return v


def collapsed_mine() -> Voxel:
    v = Voxel(STRUCTURES["collapsed_mine"]["size"])
    v.floor(0, "minecraft:cobblestone")
    # Long tunnel with timber ribs and deliberate rubble.
    for x in range(1, 18):
        for z in range(2, 11):
            v.set(x, 1, z, AIR)
    for x in (2, 6, 10, 14, 17):
        for z in (2, 10):
            v.pillar(x, z, 1, 5, LOG)
        v.box(x, 5, 2, x, 5, 10, LOG)
    for x in range(2, 18):
        v.set(x, 1, 6, "minecraft:rail", {"shape": "east_west"})
    for pos in ((8,1,4),(9,1,4),(9,2,4),(13,1,8),(13,2,8),(14,1,8)):
        v.set(*pos, "minecraft:gravel")
    v.set(4, 1, 4, "minecraft:crafting_table")
    v.set(15, 1, 8, "minecraft:furnace", {"facing": "west", "lit": "false"})
    return v


def geode_vault() -> Voxel:
    v = Voxel(STRUCTURES["geode_vault"]["size"])
    cx = cy = cz = 7
    for y in range(15):
        for z in range(15):
            for x in range(15):
                d = math.sqrt((x-cx)**2 + (y-cy)**2 + (z-cz)**2)
                if 5.7 <= d <= 7.1:
                    v.set(x, y, z, "minecraft:smooth_basalt")
                elif 4.9 <= d < 5.7:
                    v.set(x, y, z, "minecraft:calcite")
                elif 4.1 <= d < 4.9:
                    v.set(x, y, z, "minecraft:amethyst_block")
                elif d < 4.1:
                    v.set(x, y, z, AIR)
    v.floor(1, "minecraft:amethyst_block", margin=5)
    v.set(7, 2, 7, "minecraft:budding_amethyst")
    # Small entry tunnel.
    v.box(6, 5, 0, 8, 8, 4, AIR)
    return v


def flooded_ruins() -> Voxel:
    v = Voxel(STRUCTURES["flooded_ruins"]["size"])
    v.floor(0, PRIS)
    for x in (1, 5, 10, 15, 19):
        v.box(x, 1, 2, x, 5, 12, PRIS)
    for z in (2, 12):
        v.box(1, 1, z, 19, 4, z, PRIS)
    # Break walls into a ruin and fill lower volume with water.
    for x in range(2, 19):
        for z in range(3, 12):
            v.set(x, 1, z, WATER)
            v.set(x, 2, z, WATER)
    for pos in ((5,4,2),(10,3,2),(15,4,12),(1,3,7),(19,2,9)):
        v.set(*pos, AIR)
    v.box(8, 0, 5, 12, 0, 9, DARK_PRIS)
    v.set(10, 1, 7, "minecraft:sea_lantern")
    return v


def prospector_camp() -> Voxel:
    v = Voxel(STRUCTURES["prospector_camp"]["size"])
    v.floor(0, "minecraft:coarse_dirt")
    # Shelter.
    v.box(2, 1, 2, 7, 1, 7, OAK)
    for x, z in ((2,2),(7,2),(2,7),(7,7)):
        v.pillar(x, z, 1, 5, LOG)
    v.box(2, 5, 2, 7, 5,7, "minecraft:oak_slab")
    v.set(4, 1, 4, "minecraft:crafting_table")
    v.set(5, 1, 4, "minecraft:furnace", {"facing":"south","lit":"false"})
    # Campfire/work area.
    v.set(10, 1, 9, "minecraft:campfire", {"lit":"true","signal_fire":"false","waterlogged":"false","facing":"north"})
    for x, z in ((9,8),(11,8),(9,10),(11,10)):
        v.set(x, 1, z, "minecraft:cobblestone")
    v.set(12, 1, 5, "minecraft:iron_ore")
    v.set(13, 1, 5, "minecraft:coal_ore")
    return v


def sealed_cache() -> Voxel:
    v = Voxel(STRUCTURES["sealed_cache"]["size"])
    v.shell(0, 0, 0, 8, 7, 8, TILES)
    v.box(1, 1, 1, 7, 6, 7, AIR)
    v.floor(0, "minecraft:polished_deepslate")
    v.box(3, 1, 3, 5, 2, 5, "minecraft:reinforced_deepslate")
    v.set(4, 3, 4, "minecraft:gold_block")
    for x, z in ((1,1),(7,1),(1,7),(7,7)):
        v.pillar(x,z,1,5,"minecraft:chiseled_deepslate")
    v.box(3, 1, 0, 5, 3, 1, AIR)
    return v


BUILDERS = {
    "buried_sanctum": buried_sanctum,
    "abyssal_archive": abyssal_archive,
    "ancient_cistern": ancient_cistern,
    "collapsed_mine": collapsed_mine,
    "geode_vault": geode_vault,
    "flooded_ruins": flooded_ruins,
    "prospector_camp": prospector_camp,
    "sealed_cache": sealed_cache,
}


def alias_pool(name: str) -> str:
    return f"neverfolia:never_overworld/start/neverfolia__{name}"


def structure_resource(name: str) -> dict:
    cfg = STRUCTURES[name]
    result = {
        "type": "minecraft:jigusaw",
        "biomes": "#minecraft:is_overworld",
        "max_distance_from_center": 32,
        "size": 1,
        "spawn_overrides": {},
        "start_height": {"absolute": 0},
        "start_pool": alias_pool(name),
        "step": cfg["step"],
        "use_expansion_hack": False,
    }
    if name in {"ancient_cistern", "flooded_ruins"}:
        result["liquid_settings"] = "ignore_waterlogging"
    return result


def pool_resource(name: str) -> dict:
    return {
        "elements": [
            {
                "element": {
                    "element_type": "minecraft:single_pool_element",
                    "location": f"neverfolia:never_overworld/structures/{name}",
                    "processors": {"processors": []},
                    "projection": "rigid",
                },
                "weight": 1,
            }
        ],
        "fallback": "minecraft:empty",
    }


def structure_set_resource(group: str) -> dict:
    cfg = GROUPS[group]
    return {
        "placement": {
            "type": "minecraft:random_spread",
            "salt": cfg["salt"],
            "separation": cfg["separation"],
            "spacing": cfg["spacing"],
            "spread_type": "linear",
        },
        "structures": [
            {"structure": f"neverfolia:{name}", "weight": weight}
            for name, weight in cfg["structures"]
        ],
    }


def generated_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for name in STRUCTURES:
        files[f"data/neverfolia/worldgen/structure/{name}.json"] = json_bytes(structure_resource(name))
        files[f"data/neverfolia/worldgen/template_pool/never_overworld/start/neverfolia__{name}.json"] = json_bytes(pool_resource(name))
        voxel = BUILDERS[name]()
        files[f"data/neverfolia/structure/never_overworld/structures/{name}.nbt"] = structure_nbt(voxel.size, voxel.blocks)
    for group in GROUPS:
        files[f"data/neverfolia/worldgen/structure_set/never_overworld_{group}.json"] = json_bytes(structure_set_resource(group))
    files["neveroverworld-native-structures-v1.json"] = json_bytes({
        "profile": "native-structures-v1",
        "structures": list(STRUCTURES),
        "structure_sets": list(GROUPS),
        "template_mode": "custom-single-piece-nbt",
        "runtime_placement": "NeverOverworldStructurePlacement",
        "neighbor_chunk_loads": False,
        "cross_chunk_writes": False,
    })
    return files


def install(input_path: Path, output_path: Path) -> None:
    additions = generated_files()
    with zipfile.ZipFile(input_path, "r") as src:
        existing = {i.filename: src.read(i.filename) for i in src.infolist() if not i.is_dir()}
    collisions = sorted(set(existing) & set(additions))
    if collisions:
        fail(f"pack already contains native structures v1 resources: {collisions[:5]}")
    existing.update(additions)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
        for name in sorted(existing):
            dst.writestr(name, existing[name])
    print("[NeverFolia][NeverOverworld structures] NATIVE STRUCTURES V1 INSTALLED")
    print(f"  structures: {len(STRUCTURES)}")
    print(f"  structure sets: {len(GROUPS)}")
    print(f"  generated resources: {len(additions)}")
    print(f"  output: {output_path}")


def _read_root_names(gz_payload: bytes) -> set[str]:
    # Tiny verifier for our own top-level NBT tags; not a general NBT parser.
    raw = gzip.decompress(gz_payload)
    if not raw or raw[0] != 10:
        fail("SELF-TEST: NBT root is not TAG_Compound")
    # For structural validation, tag names can be found safely in the decompressed
    # payload because every required root key is encoded as a UTF-8 name.
    return {name for name in ("size", "entities", "blocks", "palette", "DataVersion") if name.encode() in raw}


def self_test() -> None:
    files = generated_files()
    expected = len(STRUCTURES) * 3 + len(GROUPS) + 1
    if len(files) != expected:
        fail(f"SELF-TEST: expected {expected} generated resources, got {len(files)}")
    for name in STRUCTURES:
        s = json.loads(files[f"data/neverfolia/worldgen/structure/{name}.json"])
        if s["start_pool"] != alias_pool(name):
            fail(f"SELF-TEST: start pool alias drift for {name}")
        p = json.loads(files[f"data/neverfolia/worldgen/template_pool/never_overworld/start/neverfolia__{name}.json"])
        loc = p["elements"][0]["element"]["location"]
        if loc != f"neverfolia:never_overworld/structures/{name}":
            fail(f"SELF-TEST: template location drift for {name}")
        nbt = files[f"data/neverfolia/structure/never_overworld/structures/{name}.nbt"]
        names = _read_root_names(nbt)
        if names != {"size", "entities", "blocks", "palette", "DataVersion"}:
            fail(f"SELF-TEST: invalid NBT root tags for {name}: {sorted(names)}")
        if len(nbt) < 100:
            fail(f"SELF-TEST: suspiciously tiny structure NBT for {name}")
    for group, cfg in GROUPS.items():
        ss = json.loads(files[f"data/neverfolia/worldgen/structure_set/never_overworld_{group}.json"])
        if ss["placement"]["spacing"] <= ss["placement"]["separation"]:
            fail(f"SELF-TEST: invalid spacing/separation for {group}")
        expected_ids = {f"neverfolia:{n}" for n, _ in cfg["structures"]}
        actual_ids = {x["structure"] for x in ss["structures"]}
        if expected_ids != actual_ids:
            fail(f"SELF-TEST: structure set membership drift for {group}")
    print("[NeverFolia][NeverOverworld structures] NATIVE STRUCTURES V1 SELF-TEST OK")
    print(f"  structures={len(STRUCTURES)} resources={len(files)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install NeverOverworld native structures v1 into an NR Core datapack")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None:
        parser.error("--input is required unless --self-test is used")
    if not args.input.is_file():
        fail(f"input pack not found: {args.input}")
    out = args.output or args.input
    if out.resolve() == args.input.resolve():
        with tempfile.NamedTemporaryFile(prefix="nr-structures-", suffix=".zip", delete=False) as tmp:
            temp = Path(tmp.name)
        try:
            install(args.input, temp)
            temp.replace(args.input)
        finally:
            temp.unlink(missing_ok=True)
    else:
        install(args.input, out)


if __name__ == "__main__":
    main()
