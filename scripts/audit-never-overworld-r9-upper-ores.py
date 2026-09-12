#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_AUDITOR = ROOT / "scripts/audit-never-overworld-native-geology.py"

spec = importlib.util.spec_from_file_location("native_audit", BASE_AUDITOR)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot import native geology auditor: {BASE_AUDITOR}")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

UPPER_MIN_SECTION = -4   # Y=-64
UPPER_MAX_SECTION = 19   # Y=319
FULL_STATUSES = {"full", "minecraft:full"}
FORBIDDEN = ("lapis", "diamond")


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 upper ore integrity] {message}")


def sample_key(coord: tuple[int, int]) -> bytes:
    cx, cz = coord
    return hashlib.sha256(f"NR-R9-UPPER-ORE:{cx},{cz}".encode("ascii")).digest()


def chunk_status(root: dict) -> str:
    value = root.get("Status", root.get("status", ""))
    return value if isinstance(value, str) else ""


def full_coords(region: Path) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for cx, cz in A.generated_chunks(region):
        try:
            root = A.BASE.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        if chunk_status(root) in FULL_STATUSES:
            result.add((cx, cz))
    return result


def count_upper(root: dict) -> tuple[Counter[str], Counter[str], int]:
    counts: Counter[str] = Counter()
    blocks: Counter[str] = Counter()
    sections = 0
    for section in A.BASE.section_list(root):
        sy = section.get("Y")
        if not isinstance(sy, int) or sy < UPPER_MIN_SECTION or sy > UPPER_MAX_SECTION:
            continue
        sections += 1
        A.count_section(section, counts, blocks)
    return counts, blocks, sections


def contract(candidate: Counter[str], vanilla: Counter[str] | None) -> dict:
    candidate_forbidden = {kind: int(candidate.get(kind, 0)) for kind in FORBIDDEN}
    candidate_zero = all(value == 0 for value in candidate_forbidden.values())
    vanilla_coverage = None
    vanilla_counts = None
    if vanilla is not None:
        vanilla_counts = {kind: int(vanilla.get(kind, 0)) for kind in FORBIDDEN}
        vanilla_coverage = all(value > 0 for value in vanilla_counts.values())
    return {
        "candidate_forbidden_ore_blocks": candidate_forbidden,
        "candidate_zero_upper_lapis_diamond": candidate_zero,
        "vanilla_reference_forbidden_ore_blocks": vanilla_counts,
        "vanilla_reference_has_both_for_coverage": vanilla_coverage,
    }


def audit(world: Path, vanilla_world: Path | None, max_chunks: int) -> dict:
    """Collect metrics only. Contract enforcement is deliberately separate.

    The production density gate imports this function. Returning the report even
    when the contract is violated lets the caller persist exact offending counts
    before it raises, instead of losing the diagnostics in an early SystemExit.
    """
    candidate_region = A.NR.find_region_dir(world)
    candidate_full = full_coords(candidate_region)
    if not candidate_full:
        fail("candidate world contains no readable FULL chunks")

    vanilla_region = None
    vanilla_full: set[tuple[int, int]] | None = None
    if vanilla_world is not None:
        vanilla_region = A.NR.find_region_dir(vanilla_world)
        vanilla_full = full_coords(vanilla_region)
        coords = sorted(candidate_full & vanilla_full, key=sample_key)[:max_chunks]
        if not coords:
            fail("no common FULL chunks between R9 candidate and vanilla reference")
    else:
        coords = sorted(candidate_full, key=sample_key)[:max_chunks]

    candidate_counts: Counter[str] = Counter()
    candidate_blocks: Counter[str] = Counter()
    vanilla_counts: Counter[str] | None = Counter() if vanilla_region is not None else None
    vanilla_blocks: Counter[str] | None = Counter() if vanilla_region is not None else None
    candidate_sections = 0
    vanilla_sections = 0
    scanned = 0

    for cx, cz in coords:
        try:
            candidate_root = A.BASE.read_chunk_nbt(candidate_region, cx, cz)
            if chunk_status(candidate_root) not in FULL_STATUSES:
                continue
            c_counts, c_blocks, c_sections = count_upper(candidate_root)
            if c_sections == 0:
                continue
            if vanilla_region is not None:
                vanilla_root = A.BASE.read_chunk_nbt(vanilla_region, cx, cz)
                if chunk_status(vanilla_root) not in FULL_STATUSES:
                    continue
                v_counts, v_blocks, v_sections = count_upper(vanilla_root)
                if v_sections == 0:
                    continue
                assert vanilla_counts is not None and vanilla_blocks is not None
                vanilla_counts.update(v_counts)
                vanilla_blocks.update(v_blocks)
                vanilla_sections += v_sections
            candidate_counts.update(c_counts)
            candidate_blocks.update(c_blocks)
            candidate_sections += c_sections
            scanned += 1
        except Exception:
            continue

    if scanned == 0 or candidate_sections == 0:
        fail("no readable upper-range sections were scanned")

    status = contract(candidate_counts, vanilla_counts)
    return {
        "schema": 2,
        "contract": "R9 upper-world lapis/diamond suppression",
        "upper_y": [-64, 319],
        "full_chunks_requested": max_chunks,
        "candidate_full_chunks_available": len(candidate_full),
        "vanilla_full_chunks_available": len(vanilla_full) if vanilla_full is not None else None,
        "common_full_chunks_available": len(candidate_full & vanilla_full) if vanilla_full is not None else None,
        "full_chunks_scanned": scanned,
        "candidate_upper_sections_scanned": candidate_sections,
        "vanilla_upper_sections_scanned": vanilla_sections if vanilla_region is not None else None,
        "candidate_upper_ore_blocks": {kind: int(candidate_counts.get(kind, 0)) for kind in A.ORE_KINDS},
        "candidate_upper_ore_block_variants": {
            block: int(candidate_blocks.get(block, 0)) for block in sorted(A.ORE_NAMES)
        },
        "vanilla_reference_upper_ore_blocks": (
            {kind: int(vanilla_counts.get(kind, 0)) for kind in A.ORE_KINDS}
            if vanilla_counts is not None else None
        ),
        "vanilla_reference_upper_ore_block_variants": (
            {block: int(vanilla_blocks.get(block, 0)) for block in sorted(A.ORE_NAMES)}
            if vanilla_blocks is not None else None
        ),
        **status,
    }


def enforce(result: dict, require_vanilla_coverage: bool) -> None:
    if not result.get("candidate_zero_upper_lapis_diamond", False):
        fail(
            "R9 candidate retained forbidden upper-world lapis/diamond in persisted FULL chunks: "
            f"{result.get('candidate_forbidden_ore_blocks')}"
        )
    if require_vanilla_coverage and not result.get("vanilla_reference_has_both_for_coverage", False):
        fail(
            "vanilla reference did not contain both lapis and diamond in the common sample; "
            "coverage is insufficient to prove the R9 suppression contract"
        )


def self_test() -> None:
    good = contract(Counter({"iron": 12, "lapis": 0, "diamond": 0}), Counter({"lapis": 7, "diamond": 4}))
    if not good["candidate_zero_upper_lapis_diamond"]:
        fail("SELF-TEST: zero candidate lapis/diamond was rejected")
    if not good["vanilla_reference_has_both_for_coverage"]:
        fail("SELF-TEST: valid vanilla coverage was rejected")

    bad_candidate = contract(Counter({"lapis": 1, "diamond": 0}), Counter({"lapis": 7, "diamond": 4}))
    if bad_candidate["candidate_zero_upper_lapis_diamond"]:
        fail("SELF-TEST: upper lapis regression was accepted")

    bad_coverage = contract(Counter(), Counter({"lapis": 7, "diamond": 0}))
    if bad_coverage["vanilla_reference_has_both_for_coverage"]:
        fail("SELF-TEST: empty vanilla diamond coverage was accepted")

    print("[NeverFolia][R9 upper ore integrity] SELF-TEST OK")
    print("  audit(): metrics-only so callers can persist diagnostics before enforcement")
    print("  candidate Y=-64..319: lapis=0, diamond=0")
    print("  vanilla common-chunk coverage: lapis>0 and diamond>0 required")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enforce R9 persisted upper-world lapis/diamond suppression against a vanilla coverage reference"
    )
    parser.add_argument("--world", type=Path)
    parser.add_argument("--vanilla-world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=1024)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.world is None:
        parser.error("--world is required unless --self-test is used")
    if args.max_chunks <= 0:
        parser.error("--max-chunks must be positive")

    result = audit(
        args.world.resolve(),
        args.vanilla_world.resolve() if args.vanilla_world is not None else None,
        args.max_chunks,
    )
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    print(rendered, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    enforce(result, args.vanilla_world is not None)


if __name__ == "__main__":
    main()
