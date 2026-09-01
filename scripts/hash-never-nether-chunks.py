#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

BODY_SECTION_MIN = -8   # Y=-128
BODY_SECTION_MAX = 23   # Y=383
ALGORITHM = "nevernether-canonical-chunk-v1"


class NbtReader:
    def __init__(self, data: bytes) -> None:
        self.data = memoryview(data)
        self.pos = 0

    def read(self, n: int) -> bytes:
        end = self.pos + n
        if end > len(self.data):
            raise ValueError("truncated NBT payload")
        out = self.data[self.pos:end].tobytes()
        self.pos = end
        return out

    def u8(self) -> int:
        return self.read(1)[0]

    def i8(self) -> int:
        return struct.unpack(">b", self.read(1))[0]

    def i16(self) -> int:
        return struct.unpack(">h", self.read(2))[0]

    def u16(self) -> int:
        return struct.unpack(">H", self.read(2))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self.read(4))[0]

    def i64(self) -> int:
        return struct.unpack(">q", self.read(8))[0]

    def f32(self) -> float:
        return struct.unpack(">f", self.read(4))[0]

    def f64(self) -> float:
        return struct.unpack(">d", self.read(8))[0]

    def string(self) -> str:
        length = self.u16()
        return self.read(length).decode("utf-8")

    def payload(self, tag: int):
        if tag == 1:
            return self.i8()
        if tag == 2:
            return self.i16()
        if tag == 3:
            return self.i32()
        if tag == 4:
            return self.i64()
        if tag == 5:
            return self.f32()
        if tag == 6:
            return self.f64()
        if tag == 7:
            length = self.i32()
            if length < 0:
                raise ValueError("negative TAG_Byte_Array length")
            return {"$byte_array": self.read(length).hex()}
        if tag == 8:
            return self.string()
        if tag == 9:
            child_type = self.u8()
            length = self.i32()
            if length < 0:
                raise ValueError("negative TAG_List length")
            return [self.payload(child_type) for _ in range(length)]
        if tag == 10:
            out = {}
            while True:
                child_type = self.u8()
                if child_type == 0:
                    return out
                name = self.string()
                out[name] = self.payload(child_type)
        if tag == 11:
            length = self.i32()
            if length < 0:
                raise ValueError("negative TAG_Int_Array length")
            return {"$int_array": [self.i32() for _ in range(length)]}
        if tag == 12:
            length = self.i32()
            if length < 0:
                raise ValueError("negative TAG_Long_Array length")
            return {"$long_array": [self.i64() for _ in range(length)]}
        raise ValueError(f"unsupported NBT tag id {tag}")

    def root(self):
        tag = self.u8()
        if tag == 0:
            raise ValueError("NBT root cannot be TAG_End")
        _name = self.string()
        value = self.payload(tag)
        if self.pos != len(self.data):
            trailing = len(self.data) - self.pos
            raise ValueError(f"unexpected trailing NBT data: {trailing} byte(s)")
        return value


def parse_nbt(data: bytes):
    return NbtReader(data).root()


def find_region_dir(world: Path) -> Path:
    candidates = (
        world / "dimensions/minecraft/the_nether/region",
        world.parent / "world_nether/region",
        world.parent / "world_nether/DIM-1/region",
        world / "DIM-1/region",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "Nether region directory not found; checked: "
        + ", ".join(str(path) for path in candidates)
    )


def decompress_chunk(compression: int, payload: bytes) -> bytes:
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"unsupported Anvil compression type {compression}")


def read_chunk_nbt(region_dir: Path, cx: int, cz: int):
    rx = cx // 32
    rz = cz // 32
    region_path = region_dir / f"r.{rx}.{rz}.mca"
    if not region_path.is_file():
        raise FileNotFoundError(f"region file missing for chunk {cx},{cz}: {region_path}")

    index = (cx & 31) + ((cz & 31) * 32)
    with region_path.open("rb") as fh:
        fh.seek(index * 4)
        location = fh.read(4)
        if len(location) != 4:
            raise ValueError(f"short Anvil location table in {region_path}")
        packed = int.from_bytes(location, "big")
        sector_offset = packed >> 8
        sector_count = packed & 0xFF
        if sector_offset == 0 or sector_count == 0:
            raise FileNotFoundError(f"chunk {cx},{cz} is not present in {region_path}")

        fh.seek(sector_offset * 4096)
        raw_length = fh.read(4)
        if len(raw_length) != 4:
            raise ValueError(f"truncated chunk length for {cx},{cz}")
        length = struct.unpack(">I", raw_length)[0]
        if length < 1:
            raise ValueError(f"invalid chunk length {length} for {cx},{cz}")
        compression_raw = fh.read(1)
        if len(compression_raw) != 1:
            raise ValueError(f"missing compression byte for {cx},{cz}")
        compression = compression_raw[0]
        external = bool(compression & 0x80)
        compression &= 0x7F
        payload = fh.read(length - 1)

    if external:
        external_path = region_dir / f"c.{cx}.{cz}.mcc"
        if not external_path.is_file():
            raise FileNotFoundError(
                f"external chunk payload missing for {cx},{cz}: {external_path}"
            )
        payload = external_path.read_bytes()

    return parse_nbt(decompress_chunk(compression, payload))


def section_list(root: dict) -> list[dict]:
    sections = root.get("sections", root.get("Sections", []))
    return [section for section in sections if isinstance(section, dict)]


def palette_name(entry) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        name = entry.get("Name", entry.get("name"))
        if isinstance(name, str):
            return name
    raise ValueError(f"unsupported block-state palette entry: {entry!r}")


def block_at(root: dict, x: int, y: int, z: int) -> str:
    section_y = y // 16
    section = next((item for item in section_list(root) if item.get("Y") == section_y), None)
    if section is None:
        return "minecraft:air"

    states = section.get("block_states", section.get("BlockStates"))
    if not isinstance(states, dict):
        return "minecraft:air"
    palette = states.get("palette")
    if not isinstance(palette, list) or not palette:
        return "minecraft:air"
    if len(palette) == 1:
        return palette_name(palette[0])

    data_wrapper = states.get("data")
    if not isinstance(data_wrapper, dict) or "$long_array" not in data_wrapper:
        raise ValueError(
            f"section Y={section_y} has {len(palette)} block states but no packed data"
        )
    longs = data_wrapper["$long_array"]
    bits = max(4, (len(palette) - 1).bit_length())
    values_per_long = 64 // bits
    local_x = x & 15
    local_y = y & 15
    local_z = z & 15
    index = (local_y << 8) | (local_z << 4) | local_x
    long_index = index // values_per_long
    bit_offset = (index % values_per_long) * bits
    if long_index >= len(longs):
        raise ValueError(
            f"packed block-state data too short in section Y={section_y}: "
            f"need long {long_index}, have {len(longs)}"
        )
    packed = longs[long_index] & 0xFFFFFFFFFFFFFFFF
    palette_index = (packed >> bit_offset) & ((1 << bits) - 1)
    if palette_index >= len(palette):
        raise ValueError(
            f"palette index {palette_index} out of range {len(palette)} in section Y={section_y}"
        )
    return palette_name(palette[palette_index])


def canonical_chunk(root: dict) -> dict:
    body_sections = []
    for section in section_list(root):
        y = section.get("Y")
        if not isinstance(y, int) or y < BODY_SECTION_MIN or y > BODY_SECTION_MAX:
            continue
        body_sections.append(
            {
                "Y": y,
                "block_states": section.get("block_states", section.get("BlockStates")),
                "biomes": section.get("biomes"),
            }
        )
    body_sections.sort(key=lambda section: section["Y"])

    return {
        "xPos": root.get("xPos"),
        "zPos": root.get("zPos"),
        "yPos": root.get("yPos"),
        "Status": root.get("Status", root.get("status")),
        "sections": body_sections,
        "Heightmaps": root.get("Heightmaps", root.get("heightmaps", {})),
        "structures": root.get("structures", root.get("Structures", {})),
    }


def canonical_bytes(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def chunk_digest(root: dict) -> str:
    return hashlib.sha256(canonical_bytes(canonical_chunk(root))).hexdigest()


def parse_chunk_arg(value: str) -> tuple[int, int]:
    try:
        x_text, z_text = value.split(",", 1)
        return int(x_text), int(z_text)
    except Exception as exc:
        raise argparse.ArgumentTypeError(
            f"chunk must be formatted as x,z; got {value!r}"
        ) from exc


def parse_block_assertion(value: str) -> tuple[int, int, int, str]:
    try:
        coords, expected = value.split("=", 1)
        x_text, y_text, z_text = coords.split(",", 2)
        if ":" not in expected:
            raise ValueError("expected block must be namespaced")
        return int(x_text), int(y_text), int(z_text), expected
    except Exception as exc:
        raise argparse.ArgumentTypeError(
            f"block assertion must be x,y,z=minecraft:block; got {value!r}"
        ) from exc


def build_manifest(world: Path, chunks: list[tuple[int, int]]) -> dict:
    region_dir = find_region_dir(world)
    entries = []
    for cx, cz in sorted(set(chunks)):
        root = read_chunk_nbt(region_dir, cx, cz)
        if root.get("xPos") != cx or root.get("zPos") != cz:
            raise ValueError(
                f"chunk coordinate mismatch: requested {cx},{cz}, "
                f"NBT has {root.get('xPos')},{root.get('zPos')}"
            )
        entries.append({"x": cx, "z": cz, "sha256": chunk_digest(root)})

    digest = hashlib.sha256()
    for entry in entries:
        digest.update(
            f"{entry['x']},{entry['z']}:{entry['sha256']}\n".encode("ascii")
        )

    return {
        "schema": 1,
        "algorithm": ALGORITHM,
        "body_section_min": BODY_SECTION_MIN,
        "body_section_max": BODY_SECTION_MAX,
        "chunk_count": len(entries),
        "chunks": entries,
        "overall_sha256": digest.hexdigest(),
    }


def verify_blocks(world: Path, assertions: list[tuple[int, int, int, str]]) -> None:
    region_dir = find_region_dir(world)
    cache: dict[tuple[int, int], dict] = {}
    for x, y, z, expected in assertions:
        chunk_key = (x // 16, z // 16)
        root = cache.get(chunk_key)
        if root is None:
            root = read_chunk_nbt(region_dir, *chunk_key)
            cache[chunk_key] = root
        actual = block_at(root, x, y, z)
        if actual != expected:
            raise SystemExit(
                f"NeverNether block assertion failed at {x},{y},{z}: "
                f"expected {expected}, got {actual}"
            )
        print(f"[NeverFolia][NeverNether NBT] {x},{y},{z} = {actual} OK")


def self_test() -> None:
    raw = (
        b"\x0a\x00\x00"
        b"\x03\x00\x04xPos\x00\x00\x00\x07"
        b"\x00"
    )
    parsed = parse_nbt(raw)
    if parsed != {"xPos": 7}:
        raise SystemExit(f"NBT parser self-test failed: {parsed!r}")

    base = {
        "xPos": 1,
        "zPos": -2,
        "yPos": -8,
        "Status": "minecraft:full",
        "sections": [
            {
                "Y": -8,
                "block_states": {"palette": [{"Name": "minecraft:netherrack"}]},
                "biomes": {"palette": ["minecraft:nether_wastes"]},
                "BlockLight": {"$byte_array": "ff"},
            },
            {
                "Y": 24,
                "block_states": {"palette": [{"Name": "minecraft:stone"}]},
                "biomes": {"palette": ["minecraft:nether_wastes"]},
            },
        ],
        "Heightmaps": {"WORLD_SURFACE": {"$long_array": [1, 2, 3]}},
        "structures": {},
        "LastUpdate": 123,
    }
    same_terrain = dict(base)
    same_terrain["LastUpdate"] = 999
    if chunk_digest(base) != chunk_digest(same_terrain):
        raise SystemExit("canonical digest incorrectly depends on LastUpdate")

    changed = json.loads(json.dumps(base))
    changed["sections"][0]["block_states"]["palette"][0]["Name"] = "minecraft:blackstone"
    if chunk_digest(base) == chunk_digest(changed):
        raise SystemExit("canonical digest failed to detect terrain mutation")

    if block_at(base, 16, -128, -32) != "minecraft:netherrack":
        raise SystemExit("single-palette block decoder self-test failed")
    if block_at(base, 16, 384, -32) != "minecraft:stone":
        raise SystemExit("roof-zone block decoder self-test failed")
    if block_at(base, 16, 400, -32) != "minecraft:air":
        raise SystemExit("missing-section air decoder self-test failed")

    packed = {
        "sections": [
            {
                "Y": 0,
                "block_states": {
                    "palette": [
                        {"Name": "minecraft:air"},
                        {"Name": "minecraft:stone"},
                    ],
                    "data": {"$long_array": [1 << (4 * 3)] + [0] * 255},
                },
            }
        ]
    }
    if block_at(packed, 3, 0, 0) != "minecraft:stone":
        raise SystemExit("packed block-state decoder self-test failed")

    print("[NeverFolia][NeverNether determinism] HASHER SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hash/inspect canonical NeverNether chunk content from Anvil region files"
    )
    parser.add_argument("--world", type=Path)
    parser.add_argument("--chunk", action="append", type=parse_chunk_arg, default=[])
    parser.add_argument(
        "--assert-block",
        action="append",
        type=parse_block_assertion,
        default=[],
        help="Assert saved Nether block state: x,y,z=minecraft:block",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.world is None:
        parser.error("--world is required")
    if not args.chunk and not args.assert_block:
        parser.error("at least one --chunk or --assert-block is required")

    if args.assert_block:
        verify_blocks(args.world, args.assert_block)

    if args.chunk:
        manifest = build_manifest(args.world, args.chunk)
        payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
