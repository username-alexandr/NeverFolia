#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HASHER_PATH = ROOT / "scripts/hash-never-overworld-generation-chunks.py"
MAX_EXACT_SAMPLES = 128


def load_hasher():
    spec = importlib.util.spec_from_file_location("never_overworld_hasher", HASHER_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load hasher: {HASHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load_hasher()
BASE = H.BASE


def sha(value) -> str:
    return hashlib.sha256(H.canonical_bytes(value)).hexdigest()


def sections_by_y(root: dict) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for section in BASE.section_list(root):
        y = section.get("Y")
        if isinstance(y, int) and H.BODY_SECTION_MIN <= y <= H.BODY_SECTION_MAX:
            result[y] = section
    return result


def exact_block_diff(a: dict, b: dict, cx: int, cz: int, section_ys: list[int]) -> dict:
    pair_counts: Counter[tuple[str, str]] = Counter()
    samples: list[dict] = []
    base_x = cx * 16
    base_z = cz * 16
    total = 0
    for sy in sorted(set(section_ys)):
        min_y = sy * 16
        for y in range(min_y, min_y + 16):
            for lz in range(16):
                for lx in range(16):
                    x = base_x + lx
                    z = base_z + lz
                    block_a = BASE.block_at(a, x, y, z)
                    block_b = BASE.block_at(b, x, y, z)
                    if block_a == block_b:
                        continue
                    total += 1
                    pair_counts[(block_a, block_b)] += 1
                    if len(samples) < MAX_EXACT_SAMPLES:
                        samples.append({"x": x, "y": y, "z": z, "a": block_a, "b": block_b})
    pairs = [
        {"a": pair[0], "b": pair[1], "count": count}
        for pair, count in sorted(pair_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {"total_changed_blocks": total, "pair_counts": pairs, "samples": samples}


def component_diff(a: dict, b: dict, cx: int, cz: int) -> dict:
    out: dict = {
        "status": {},
        "sections": [],
        "heightmaps": [],
        "structures": {},
        "exact_blocks": {},
    }

    for key in ("yPos", "Status"):
        av = a.get(key, a.get(key.lower()))
        bv = b.get(key, b.get(key.lower()))
        if av != bv:
            out["status"][key] = {"a": av, "b": bv}

    sa = sections_by_y(a)
    sb = sections_by_y(b)
    changed_block_sections: list[int] = []
    for y in sorted(set(sa) | set(sb)):
        aa = sa.get(y)
        bb = sb.get(y)
        if aa is None or bb is None:
            out["sections"].append({"Y": y, "present_a": aa is not None, "present_b": bb is not None})
            changed_block_sections.append(y)
            continue
        blocks_a = H.section_semantic_digest(aa)
        blocks_b = H.section_semantic_digest(bb)
        biomes_a = sha(aa.get("biomes"))
        biomes_b = sha(bb.get("biomes"))
        if blocks_a != blocks_b or biomes_a != biomes_b:
            out["sections"].append({
                "Y": y,
                "blocks_a": blocks_a,
                "blocks_b": blocks_b,
                "blocks_equal": blocks_a == blocks_b,
                "biomes_a": biomes_a,
                "biomes_b": biomes_b,
                "biomes_equal": biomes_a == biomes_b,
            })
            if blocks_a != blocks_b:
                changed_block_sections.append(y)

    if changed_block_sections:
        out["exact_blocks"] = exact_block_diff(a, b, cx, cz, changed_block_sections)

    ha = a.get("Heightmaps", a.get("heightmaps", {}))
    hb = b.get("Heightmaps", b.get("heightmaps", {}))
    if not isinstance(ha, dict):
        ha = {}
    if not isinstance(hb, dict):
        hb = {}
    for key in sorted(set(ha) | set(hb)):
        if H.canonical_bytes(ha.get(key)) != H.canonical_bytes(hb.get(key)):
            out["heightmaps"].append({
                "name": key,
                "a_sha256": sha(ha.get(key)),
                "b_sha256": sha(hb.get(key)),
            })

    sta = a.get("structures", a.get("Structures", {}))
    stb = b.get("structures", b.get("Structures", {}))
    if H.canonical_bytes(sta) != H.canonical_bytes(stb):
        out["structures"] = {
            "equal": False,
            "a_sha256": sha(sta),
            "b_sha256": sha(stb),
        }
    else:
        out["structures"] = {"equal": True}
    return out


def parse_chunk(value: str) -> tuple[int, int]:
    try:
        x, z = value.split(",", 1)
        return int(x), int(z)
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"chunk must be x,z: {value!r}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff NeverOverworld generation components between two worlds")
    parser.add_argument("--world-a", type=Path, required=True)
    parser.add_argument("--world-b", type=Path, required=True)
    parser.add_argument("--chunk", action="append", type=parse_chunk, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    region_a = H.find_region_dir(args.world_a)
    region_b = H.find_region_dir(args.world_b)
    report = {"schema": 2, "chunks": []}

    for cx, cz in sorted(set(args.chunk)):
        a = BASE.read_chunk_nbt(region_a, cx, cz)
        b = BASE.read_chunk_nbt(region_b, cx, cz)
        digest_a = H.chunk_digest(a)
        digest_b = H.chunk_digest(b)
        if digest_a == digest_b:
            continue
        diff = component_diff(a, b, cx, cz)
        entry = {"x": cx, "z": cz, "chunk_a": digest_a, "chunk_b": digest_b, "diff": diff}
        report["chunks"].append(entry)
        print(f"[NeverFolia][NeverOverworld diagnostic] chunk {cx},{cz}")
        changed_sections = diff["sections"]
        if changed_sections:
            block_sections = [x["Y"] for x in changed_sections if x.get("blocks_equal") is False or "blocks_equal" not in x]
            biome_sections = [x["Y"] for x in changed_sections if x.get("biomes_equal") is False]
            print("  block sections:", block_sections or "none")
            print("  biome sections:", biome_sections or "none")
        else:
            print("  sections: equal")
        print("  heightmaps:", [x["name"] for x in diff["heightmaps"]] or "none")
        print("  structures:", "different" if not diff["structures"].get("equal", False) else "equal")
        exact = diff.get("exact_blocks", {})
        if exact:
            print("  exact changed blocks:", exact.get("total_changed_blocks", 0))
            for pair in exact.get("pair_counts", [])[:16]:
                print(f"    {pair['a']} -> {pair['b']}: {pair['count']}")
            for sample in exact.get("samples", [])[:24]:
                print(f"    at {sample['x']},{sample['y']},{sample['z']}: {sample['a']} -> {sample['b']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[NeverFolia][NeverOverworld diagnostic] mismatching chunks: {len(report['chunks'])}")
    print(f"[NeverFolia][NeverOverworld diagnostic] report: {args.output}")


if __name__ == "__main__":
    main()
