#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
SAFETY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java")
START_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/StructureStart.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/NeverOverworldVillageReclamation.java")

SAFETY_SIG = "    static boolean allowsGenerated("
QA_RING = '    private static final int MAX_CANDIDATE_RINGS = Integer.getInteger("neverfolia.villageLocateRings", 64);'
FINAL_RING = '    private static final int MAX_CANDIDATE_RINGS = 128; // NeverFolia R9 V17 production'
V12_MARKER = "// NeverFolia R9-v12 QA: strict 12/12 village dry contract with runtime locate-ring budget."
PROD_MARKER = "// NeverFolia R9-v17 production: strict 12/12 probes + rings128 + actual-bbox reclamation."
V17_CALL = "NeverOverworldVillageReclamation.apply(level, this, chunkPos);"
V17_HELPER_MARKER = "NeverFolia R9 V17 actual-bbox village reclamation"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village V17 finalizer] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method not found: {signature.strip()}")
    if text.find(signature, start + 1) >= 0:
        fail(f"method occurs more than once: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail("method opening brace missing")
    depth = 0
    in_s = in_c = in_line = in_block = escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line:
            if ch == "\n":
                in_line = False
            i += 1
            continue
        if in_block:
            if ch == "*" and nxt == "/":
                in_block = False
                i += 2
            else:
                i += 1
            continue
        if in_s:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_s = False
            i += 1
            continue
        if in_c:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_c = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block = True
            i += 2
            continue
        if ch == '"':
            in_s = True
            i += 1
            continue
        if ch == "'":
            in_c = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return start, end
        i += 1
    fail("unterminated method")


def method_text(text: str, signature: str) -> str:
    start, end = find_method_end(text, signature)
    return text[start:end]


def patch_fast(text: str) -> str:
    if FINAL_RING in text:
        if "neverfolia.villageLocateRings" in text:
            fail("production ring constant exists but QA selector still survives")
    else:
        if text.count(QA_RING) != 1:
            fail(f"expected one V12 QA ring selector, got {text.count(QA_RING)}")
        text = text.replace(QA_RING, FINAL_RING, 1)
    if V12_MARKER in text:
        text = text.replace(V12_MARKER, PROD_MARKER)
    if PROD_MARKER not in text:
        fail("production V17 marker missing from fast locate")
    if "neverfolia.villageLocateRings" in text:
        fail("QA ring selector leaked after finalization")
    return text


def patch_policy(text: str) -> str:
    if V12_MARKER in text:
        text = text.replace(V12_MARKER, PROD_MARKER)
    if PROD_MARKER not in text:
        fail("production V17 marker missing from generation policy")
    return text


def validate(fast: str, policy: str, safety: str, start: str, helper: str) -> None:
    if FINAL_RING not in fast:
        fail("hardcoded rings128 constant missing")
    if "neverfolia.villageLocateRings" in fast or "neverfolia.villageLocateRings" in policy:
        fail("runtime ring property remains in production village policy")
    if PROD_MARKER not in fast or PROD_MARKER not in policy:
        fail("shared production strict12 marker missing")
    if V12_MARKER in fast or V12_MARKER in policy:
        fail("QA V12 marker survived finalization")
    if start.count(V17_CALL) != 1:
        fail("V17 StructureStart reclamation hook missing/drifted")
    if V17_HELPER_MARKER not in helper:
        fail("V17 reclamation helper marker missing")

    safety_method = method_text(safety, SAFETY_SIG)
    if "return start.isValid();" not in safety_method:
        fail("R9-v4 generated safety no-op contract missing")
    for forbidden in ("inspectBoundingBox(", ".dry()", "getBaseHeight("):
        if forbidden in safety_method:
            fail(f"generated-bbox rejection primitive leaked into allowsGenerated: {forbidden}")

    for forbidden in (
        "Structure.generate(",
        "NeverOverworldGeneratedVillageSafety.preview",
        "getBaseHeight(",
    ):
        if forbidden in fast:
            fail(f"watchdog-risk primitive leaked into final fast locate: {forbidden}")


def self_test() -> None:
    fast = "class F {\n" + QA_RING + "\n" + V12_MARKER + "\n}\n"
    policy = "class P {\n" + V12_MARKER + "\n}\n"
    safety = '''class S {\n    static boolean allowsGenerated(\n        int x\n    ) {\n        return start.isValid();\n    }\n}\n'''
    start = "class T { void x(){ " + V17_CALL + " } }\n"
    helper = "class H { /* " + V17_HELPER_MARKER + " */ }\n"
    fast = patch_fast(fast)
    policy = patch_policy(policy)
    validate(fast, policy, safety, start, helper)
    if patch_fast(fast) != fast or patch_policy(policy) != policy:
        fail("SELF-TEST: finalizer is not idempotent")
    print("[NeverFolia][R9 village V17 finalizer] SELF-TEST OK")
    print("  locate rings: hardcoded 128; QA selector removed")
    print("  shared village probes: strict 12/12")
    print("  generated safety: start.isValid() only")
    print("  actual-bbox safety: V17 reclamation helper + StructureStart hook required")


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze the proven V17 village policy for production")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree is required unless --self-test is used")

    self_test()
    root = args.folia.resolve()
    paths = {
        "fast": root / FAST_REL,
        "policy": root / POLICY_REL,
        "safety": root / SAFETY_REL,
        "start": root / START_REL,
        "helper": root / HELPER_REL,
    }
    for path in paths.values():
        if not path.is_file():
            fail(f"required source missing: {path}")

    fast = patch_fast(paths["fast"].read_text(encoding="utf-8"))
    policy = patch_policy(paths["policy"].read_text(encoding="utf-8"))
    safety = paths["safety"].read_text(encoding="utf-8")
    start = paths["start"].read_text(encoding="utf-8")
    helper = paths["helper"].read_text(encoding="utf-8")
    validate(fast, policy, safety, start, helper)

    paths["fast"].write_text(fast, encoding="utf-8")
    paths["policy"].write_text(policy, encoding="utf-8")
    print("[NeverFolia][R9 village V17 finalizer] production policy frozen: strict12 + rings128 + actual-bbox reclamation")


if __name__ == "__main__":
    main()
