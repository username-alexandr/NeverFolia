#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
START_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/StructureStart.java")
QA_RING = '    private static final int MAX_CANDIDATE_RINGS = Integer.getInteger("neverfolia.villageLocateRings", 64);'
FINAL_RING = '    private static final int MAX_CANDIDATE_RINGS = 128; // NeverFolia R9 V17 production'
V12_MARKER = "// NeverFolia R9-v12 QA: strict 12/12 village dry contract with runtime locate-ring budget."
V17_CALL = "NeverOverworldVillageReclamation.apply(level, this, chunkPos);"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village V17 finalizer] {message}")


def patch_fast(text: str) -> str:
    if FINAL_RING in text:
        if "neverfolia.villageLocateRings" in text:
            fail("production ring constant exists but QA selector still survives")
        return text
    if text.count(QA_RING) != 1:
        fail(f"expected one V12 QA ring selector, got {text.count(QA_RING)}")
    if V12_MARKER not in text:
        fail("V12 strict 12/12 marker missing")
    text = text.replace(QA_RING, FINAL_RING, 1)
    if "neverfolia.villageLocateRings" in text:
        fail("QA ring selector leaked after finalization")
    return text


def validate(fast: str, policy: str, start: str) -> None:
    if FINAL_RING not in fast:
        fail("hardcoded rings128 constant missing")
    if "neverfolia.villageLocateRings" in fast:
        fail("runtime ring property remains in production fast locate")
    if V12_MARKER not in fast or V12_MARKER not in policy:
        fail("shared V12 strict 12/12 policy missing")
    if start.count(V17_CALL) != 1:
        fail("V17 StructureStart reclamation hook missing/drifted")
    for forbidden in (
        "Structure.generate(",
        "NeverOverworldGeneratedVillageSafety.preview",
    ):
        if forbidden in fast:
            fail(f"watchdog-risk primitive leaked into final fast locate: {forbidden}")


def self_test() -> None:
    fast = "class F {\n" + QA_RING + "\n" + V12_MARKER + "\n}\n"
    policy = "class P {\n" + V12_MARKER + "\n}\n"
    start = "class S { void x(){ " + V17_CALL + " } }\n"
    out = patch_fast(fast)
    validate(out, policy, start)
    if patch_fast(out) != out:
        fail("SELF-TEST: finalizer is not idempotent")
    print("[NeverFolia][R9 village V17 finalizer] SELF-TEST OK")
    print("  locate rings: hardcoded 128")
    print("  shared strict probes: V12 12/12")
    print("  actual-bbox safety: V17 reclamation hook required")


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze the proven V17 village policy for production")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None:
        parser.error("folia worktree is required unless --self-test is used")

    self_test()
    root = args.folia.resolve()
    fast_path = root / FAST_REL
    policy_path = root / POLICY_REL
    start_path = root / START_REL
    for path in (fast_path, policy_path, start_path):
        if not path.is_file():
            fail(f"required source missing: {path}")
    fast = patch_fast(fast_path.read_text(encoding="utf-8"))
    policy = policy_path.read_text(encoding="utf-8")
    start = start_path.read_text(encoding="utf-8")
    validate(fast, policy, start)
    fast_path.write_text(fast, encoding="utf-8")
    print("[NeverFolia][R9 village V17 finalizer] production policy frozen: strict12 + rings128 + actual-bbox reclamation")


if __name__ == "__main__":
    main()
