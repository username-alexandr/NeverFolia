#!/usr/bin/env python3
"""Read-only voxel audit of STOPPED-server Nether region files.

Findings are observations, not proof of a worldgen bug. In particular, legitimate
lava falls can have air underneath and intentionally sealed caves can be small.
No blocks, region files, locks or player-built roof areas are ever modified.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "nevernether_integrity_decoder", ROOT / "scripts/diff-never-nether-chunks.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load the existing NeverNether NBT decoder")
DECODER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DECODER)

AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
ROCK = {
    "minecraft:netherrack", "minecraft:basalt", "minecraft:smooth_basalt",
    "minecraft:blackstone", "minecraft:magma_block", "minecraft:soul_sand",
    "minecraft:soul_soil", "minecraft:crimson_nylium", "minecraft:warped_nylium",
    "minecraft:nether_quartz_ore", "minecraft:nether_gold_ore",
    "minecraft:ancient_debris", "minecraft:gravel", "minecraft:bedrock",
}
DIRECTIONS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
Position = tuple[int, int, int]
Chunk = tuple[int, int]
Box = tuple[int, int, int, int, int, int]


def block_name(state: str) -> str:
    return state.split("[", 1)[0]


def source_lava(state: str) -> bool:
    if block_name(state) != "minecraft:lava":
        return False
    if "[" not in state:
        return True  # Default lava BlockState is level=0.
    properties = dict(part.split("=", 1) for part in state.split("[", 1)[1][:-1].split(","))
    return properties.get("level", "0") == "0"


def structure_boxes(root: dict[str, Any]) -> list[Box]:
    """Use saved start/piece boxes, never infer a structure's presence from air."""
    boxes: list[Box] = []
    structures = root.get("structures", root.get("Structures", {}))
    starts = structures.get("starts", structures.get("Starts", {}))

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            bb = value.get("BB")
            if isinstance(bb, dict):
                bb = bb.get("$int_array")
            if isinstance(bb, list) and len(bb) == 6 and all(isinstance(n, int) for n in bb):
                if all(bb[i] <= bb[i + 3] for i in range(3)):
                    boxes.append(tuple(bb))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(starts)
    return boxes


class Volume:
    def __init__(self, roots: dict[Chunk, dict[str, Any]], min_y: int, max_y: int) -> None:
        if not -128 <= min_y <= max_y <= 511:
            raise ValueError("Audit range must be inside the current generated body below roof512: Y=-128..511")
        if not roots:
            raise ValueError("No FULL chunks supplied; an empty sample is not a passing audit")
        self.min_y, self.max_y = min_y, max_y
        self.size = (max_y - min_y + 1) * 256
        self.chunks: dict[Chunk, list[str]] = {}
        self.section_tags: dict[tuple[int, int, int], dict[str, Any]] = {}
        self.boxes: list[Box] = []
        self.roof_non_air = 0
        for (cx, cz), original in sorted(roots.items()):
            root = original.get("Level", original)
            if root.get("Status") not in ("minecraft:full", "full"):
                raise ValueError(f"Chunk {cx},{cz} is not FULL: {root.get('Status')!r}")
            if (root.get("xPos"), root.get("zPos")) != (cx, cz):
                raise ValueError(f"Chunk coordinate mismatch at {cx},{cz}")
            blocks = ["minecraft:air"] * self.size
            seen_sections: set[int] = set()
            sections = root.get("sections", root.get("Sections"))
            if not isinstance(sections, list) or any(not isinstance(s, dict) for s in sections):
                raise ValueError(f"Invalid or missing sections list in chunk {cx},{cz}")
            for section in sections:
                sy = section.get("Y")
                if not isinstance(sy, int) or sy in seen_sections:
                    raise ValueError(f"Invalid or duplicate section Y in chunk {cx},{cz}")
                seen_sections.add(sy)
                self.section_tags[(cx, cz, sy)] = section
                low, high = sy * 16, sy * 16 + 15
                # Historical profiles treated Y>=384 as a separate roof zone.
                # R14 extends generated terrain through Y511 and protects bedrock
                # at Y512. Only sections outside the requested audit range are
                # counted as auxiliary roof/padding observations.
                is_roof = 24 <= sy <= 55 and (high < min_y or low > max_y)
                if (high < min_y or low > max_y) and not is_roof:
                    continue
                container = section.get("block_states", section.get("BlockStates"))
                if ("block_states" in section or "BlockStates" in section) and not isinstance(container, dict):
                    raise ValueError(f"Invalid block-state container in chunk {cx},{cz}, section {sy}")
                # FULL chunks may omit an all-air section/container. Malformed
                # palettes/data in a present container must instead fail closed.
                decoded = (["minecraft:air"] * 4096 if container is None else
                           DECODER.decode_paletted_container(container, entry_count=4096, min_bits=4)[0])
                if is_roof:
                    self.roof_non_air += sum(block_name(state) not in AIR for state in decoded)
                for y in range(max(min_y, low), min(max_y, high) + 1):
                    offset = (y - min_y) * 256
                    source = (y - low) * 256
                    blocks[offset:offset + 256] = decoded[source:source + 256]
            self.chunks[(cx, cz)] = blocks
            self.boxes.extend(structure_boxes(root))

    def at(self, position: Position) -> str | None:
        x, y, z = position
        if not self.min_y <= y <= self.max_y:
            return None
        chunk = self.chunks.get((x // 16, z // 16))
        if chunk is None:
            return None  # Missing coverage is UNKNOWN, never air or rock.
        return chunk[(y - self.min_y) * 256 + (z & 15) * 16 + (x & 15)]

    def in_structure(self, position: Position) -> bool:
        x, y, z = position
        return any(a <= x <= d and b <= y <= e and c <= z <= f
                   for a, b, c, d, e, f in self.boxes)

    def provenance_at(self, position: Position) -> dict[str, Any]:
        x, y, z = position
        current = self.at(position)
        section = self.section_tags.get((x // 16, z // 16, y // 16))
        if current is None or not isinstance(section, dict):
            return {"available": False, "current": current, "classification": "unknown"}

        meta = section.get("neverfolia:substrate_r11")
        if not isinstance(meta, dict):
            return {"available": False, "current": current, "classification": "unknown"}

        palette = meta.get("Palette")
        bits = meta.get("Bits")
        original_wrapper = meta.get("Original")
        external_wrapper = meta.get("External")
        proposal_indices_wrapper = meta.get("ProposalIndices")
        proposal_states_wrapper = meta.get("ProposalStates")
        if (
            not isinstance(palette, list) or not palette
            or not isinstance(bits, int) or bits < 0 or bits > 12
            or not isinstance(original_wrapper, dict)
            or "$long_array" not in original_wrapper
            or not isinstance(external_wrapper, dict)
            or "$long_array" not in external_wrapper
            or not isinstance(proposal_indices_wrapper, dict)
            or "$int_array" not in proposal_indices_wrapper
            or not isinstance(proposal_states_wrapper, dict)
            or "$int_array" not in proposal_states_wrapper
        ):
            raise ValueError(f"Malformed neverfolia:substrate_r11 metadata at {position}")

        original_longs = original_wrapper["$long_array"]
        external_longs = external_wrapper["$long_array"]
        proposal_indices = proposal_indices_wrapper["$int_array"]
        proposal_states = proposal_states_wrapper["$int_array"]
        if len(proposal_indices) != len(proposal_states):
            raise ValueError(f"Proposal provenance length mismatch at {position}")

        index = ((y & 15) << 8) | ((z & 15) << 4) | (x & 15)
        if bits == 0:
            original_index = 0
        else:
            per = 64 // bits
            long_index = index // per
            if long_index >= len(original_longs):
                raise ValueError(f"Original provenance packed data too short at {position}")
            packed = original_longs[long_index] & 0xFFFFFFFFFFFFFFFF
            original_index = (packed >> ((index % per) * bits)) & ((1 << bits) - 1)
        if original_index >= len(palette):
            raise ValueError(f"Original provenance palette index out of range at {position}")
        original = palette[original_index]

        external = False
        ext_long = index // 64
        if ext_long < len(external_longs):
            external = bool(((external_longs[ext_long] & 0xFFFFFFFFFFFFFFFF) >> (index % 64)) & 1)

        proposal_state = None
        for raw_index, raw_state in zip(proposal_indices, proposal_states):
            if raw_index == index:
                if raw_state < 0 or raw_state >= len(palette):
                    raise ValueError(f"Proposal palette index out of range at {position}")
                proposal_state = palette[raw_state]
                break

        if external:
            classification = "external"
        elif proposal_state is not None:
            classification = "proposal"
        elif current == original:
            classification = "original"
        else:
            classification = "unrecorded"

        return {
            "available": True,
            "profile": meta.get("Profile"),
            "original": original,
            "current": current,
            "external": external,
            "proposal_state": proposal_state,
            "classification": classification,
        }


def audit(volume: Volume, pocket_limit: int = 64, max_findings: int = 200) -> dict[str, Any]:
    if pocket_limit < 1 or max_findings < 0:
        raise ValueError("pocket_limit must be positive and max_findings nonnegative")
    visited = {chunk: bytearray(volume.size) for chunk in volume.chunks}
    counts: Counter[str] = Counter()
    pocket_samples: list[dict[str, Any]] = []
    lava_samples: list[dict[str, Any]] = []
    shelf_samples: list[dict[str, Any]] = []

    def mark(position: Position) -> bool:
        x, y, z = position
        flags = visited[(x // 16, z // 16)]
        index = (y - volume.min_y) * 256 + (z & 15) * 16 + (x & 15)
        if flags[index]:
            return False
        flags[index] = 1
        return True

    for (cx, cz), blocks in sorted(volume.chunks.items()):
        for index, state in enumerate(blocks):
            y = volume.min_y + index // 256
            position = (cx * 16 + (index & 15), y, cz * 16 + ((index // 16) & 15))
            if source_lava(state):
                counts["source_lava_blocks"] += 1
                below = volume.at((position[0], y - 1, position[2]))
                if below is None:
                    counts["source_lava_support_unknown"] += 1
                elif block_name(below) in AIR:
                    counts["source_lava_with_air_below"] += 1
                    horizontal = [
                        volume.at((position[0] + dx, y, position[2] + dz))
                        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    ]
                    horizontal_source = sum(
                        1 for neighbor in horizontal
                        if neighbor is not None and source_lava(neighbor)
                    )
                    above = volume.at((position[0], y + 1, position[2]))
                    inside_structure = volume.in_structure(position)
                    shelf_candidate = horizontal_source >= 2 and not inside_structure
                    if shelf_candidate:
                        counts["hanging_source_lava_shelf_candidates"] += 1
                        if len(shelf_samples) < max_findings:
                            shelf_samples.append({
                                "position": list(position),
                                "horizontal_source_lava_neighbors": horizontal_source,
                                "above": above,
                                "below": below,
                                "provenance": volume.provenance_at(position),
                                "below_provenance": volume.provenance_at((position[0], y - 1, position[2])),
                            })
                    else:
                        counts["source_lava_fall_or_edge_candidates"] += 1
                    if len(lava_samples) < max_findings:
                        lava_samples.append({
                            "position": list(position),
                            "inside_saved_structure_bbox": inside_structure,
                            "horizontal_source_lava_neighbors": horizontal_source,
                            "above": above,
                            "shelf_candidate": shelf_candidate,
                            "provenance": volume.provenance_at(position),
                        })
            elif block_name(state) == "minecraft:lava":
                counts["flowing_lava_blocks"] += 1
            if block_name(state) not in AIR or not mark(position):
                continue
            queue = deque([position])
            component_positions: list[Position] = []
            size = 0
            unknown = False
            rock_boundary = True
            inside_structure = False
            minimum = list(position)
            maximum = list(position)
            while queue:
                current = queue.popleft()
                size += 1
                if size <= pocket_limit:
                    component_positions.append(current)
                # Once a component exceeds the reporting limit, no more costly
                # structure-box checks are needed; it cannot become a small pocket.
                if size <= pocket_limit and not inside_structure:
                    inside_structure = volume.in_structure(current)
                for axis in range(3):
                    minimum[axis] = min(minimum[axis], current[axis])
                    maximum[axis] = max(maximum[axis], current[axis])
                for dx, dy, dz in DIRECTIONS:
                    neighbor = (current[0] + dx, current[1] + dy, current[2] + dz)
                    adjacent = volume.at(neighbor)
                    if adjacent is None:
                        unknown = True
                    elif block_name(adjacent) in AIR:
                        if mark(neighbor):
                            queue.append(neighbor)
                    elif block_name(adjacent) not in ROCK:
                        rock_boundary = False
            counts["air_components"] += 1
            counts["air_blocks"] += size
            if unknown:
                counts["air_components_touching_unknown_boundary"] += 1
            if size > pocket_limit:
                counts["air_components_above_pocket_limit"] += 1
            elif not unknown and rock_boundary:
                if inside_structure:
                    counts["small_air_components_in_saved_structure_bbox"] += 1
                else:
                    counts["enclosed_small_air_components"] += 1
                    counts["enclosed_small_air_blocks"] += size
                    if size == 1:
                        counts["enclosed_air_components_size_1"] += 1
                    elif size <= 4:
                        counts["enclosed_air_components_size_2_4"] += 1
                    elif size <= 16:
                        counts["enclosed_air_components_size_5_16"] += 1
                    else:
                        counts["enclosed_air_components_size_17_64"] += 1
                    if len(pocket_samples) < max_findings:
                        provenance_counts = Counter(
                            volume.provenance_at(cell)["classification"]
                            for cell in component_positions
                        )
                        pocket_samples.append({
                            "size": size,
                            "bbox": minimum + maximum,
                            "sample": list(position),
                            "sample_provenance": volume.provenance_at(position),
                            "provenance_counts": dict(sorted(provenance_counts.items())),
                        })
    keys = (
        "source_lava_blocks", "source_lava_support_unknown", "source_lava_with_air_below",
        "hanging_source_lava_shelf_candidates", "source_lava_fall_or_edge_candidates",
        "flowing_lava_blocks", "air_components", "air_blocks",
        "air_components_touching_unknown_boundary", "air_components_above_pocket_limit",
        "small_air_components_in_saved_structure_bbox", "enclosed_small_air_components",
        "enclosed_small_air_blocks", "enclosed_air_components_size_1",
        "enclosed_air_components_size_2_4", "enclosed_air_components_size_5_16",
        "enclosed_air_components_size_17_64",
    )
    return {
        "schema": 1, "audit": "nevernether-field-integrity-r1", "read_only": True,
        "range_y": [volume.min_y, volume.max_y], "chunk_count": len(volume.chunks),
        "chunks": [list(chunk) for chunk in sorted(volume.chunks)],
        "pocket_limit": pocket_limit, "counts": {key: counts[key] for key in keys},
        "enclosed_air_samples": pocket_samples,
        "source_lava_air_below_samples": lava_samples,
        "hanging_lava_shelf_samples": shelf_samples,
        "samples_truncated": {
            "enclosed_air": counts["enclosed_small_air_components"] > len(pocket_samples),
            "lava_air_below": counts["source_lava_with_air_below"] > len(lava_samples),
            "hanging_lava_shelf": counts["hanging_source_lava_shelf_candidates"] > len(shelf_samples),
        },
        "roof_non_air_blocks_observed": volume.roof_non_air,
        "interpretation": [
            "Findings are candidates for inspection, not confirmed generation bugs.",
            "Air under source lava is also expected for legitimate waterfalls.",
            "Outside the selected FULL chunks/Y range is unknown, not empty.",
            "Only saved structure boxes in the selected chunks are known; this is not a complete structure-provenance map.",
            "Roof blocks may be player builds; no roof violation is inferred.",
        ],
    }


def chunk_argument(value: str) -> Chunk:
    try:
        x, z = value.split(",")
        return int(x), int(z)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("Expected chunk coordinates X,Z, for example --chunk=-1,0") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region-dir", required=True, type=Path, help="Exact Nether region directory from a stopped-server copy")
    parser.add_argument("--chunk", required=True, type=chunk_argument, action="append")
    parser.add_argument("--min-y", type=int, default=-128)
    parser.add_argument("--max-y", type=int, default=383)
    parser.add_argument("--pocket-limit", type=int, default=64)
    parser.add_argument("--max-findings", type=int, default=200)
    parser.add_argument("--output", type=Path, help="JSON report outside the audited region directory")
    args = parser.parse_args()
    region = args.region_dir.resolve()
    if not region.is_dir():
        parser.error(f"Region directory not found: {region}")
    if args.output is not None:
        output = args.output.resolve()
        if output.is_relative_to(region) or output.suffix.lower() != ".json":
            parser.error("The JSON report must be outside the audited region directory")
    try:
        roots = {chunk: DECODER.HASHER.read_chunk_nbt(region, *chunk) for chunk in sorted(set(args.chunk))}
        result = audit(Volume(roots, args.min_y, args.max_y), args.pocket_limit, args.max_findings)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"NeverNether audit failed; no passing report produced: {exc}\n")
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
