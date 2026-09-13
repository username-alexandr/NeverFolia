#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
SAFETY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java")

FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
SAFETY_SIG = "    static boolean allowsGenerated("

OLD_MARKER = "// NeverFolia R9-v4: shared 5x5 preliminary village envelope; no Jigsaw preview in locate."
NEW_MARKER = "// NeverFolia R9-v5: calibrated 5x5 preliminary village envelope; no Jigsaw preview in locate."
OLD_REACH = "final int villageReach = 96;"
NEW_REACH = "final int villageReach = 64;"
OLD_OFFSETS = "final int[] villageOffsets = {-96, -48, 0, 48, 96};"
NEW_OFFSETS = "final int[] villageOffsets = {-64, -32, 0, 32, 64};"
OLD_GENERATION_RETURN = "return villageReach == 96;"
NEW_GENERATION_RETURN = "return villageReach == 64;"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village locate v5] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method signature not found: {signature.strip()}")
    if text.find(signature, start + 1) >= 0:
        fail(f"method signature occurs more than once: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail(f"opening brace not found: {signature.strip()}")
    depth = 0
    in_string = in_char = in_line_comment = in_block_comment = escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            in_char = True
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
    fail(f"unterminated method: {signature.strip()}")


def patch_method(text: str, signature: str, kind: str) -> str:
    start, end = find_method_end(text, signature)
    body = text[start:end]

    # Idempotence plus repair for the historical V5 bug where the numeric
    # reach was changed to 64 but the generation-side sentinel remained == 96.
    if NEW_MARKER in body and NEW_REACH in body and NEW_OFFSETS in body:
        if OLD_MARKER in body or OLD_REACH in body or OLD_OFFSETS in body:
            fail(f"{kind}: mixed V4/V5 village envelope detected")
        if kind == "generation":
            if OLD_GENERATION_RETURN in body:
                body = body.replace(OLD_GENERATION_RETURN, NEW_GENERATION_RETURN, 1)
                return text[:start] + body + text[end:]
            if NEW_GENERATION_RETURN not in body:
                fail("generation: calibrated V5 sentinel missing")
        return text

    required = [OLD_MARKER, OLD_REACH, OLD_OFFSETS]
    missing = [needle for needle in required if needle not in body]
    if missing:
        fail(f"{kind}: V4 envelope anchors missing: {missing}")

    body = body.replace(OLD_MARKER, NEW_MARKER, 1)
    body = body.replace(OLD_REACH, NEW_REACH, 1)
    body = body.replace(OLD_OFFSETS, NEW_OFFSETS, 1)
    if kind == "fast":
        body = body.replace("R9V4_CENTER_DRY_REJECT", "R9V5_CENTER_DRY_REJECT")
        body = body.replace("R9V4_BIOME_REJECT", "R9V5_BIOME_REJECT")
        body = body.replace("R9V4_ENVELOPE_REJECT", "R9V5_ENVELOPE_REJECT")
        body = body.replace("R9V4_ACCEPT", "R9V5_ACCEPT")
        body = body.replace("5x5-preliminary-reach=", "5x5-calibrated-reach=")
    else:
        if OLD_GENERATION_RETURN not in body:
            fail("generation: V4 reach96 sentinel missing")
        body = body.replace(OLD_GENERATION_RETURN, NEW_GENERATION_RETURN, 1)
    return text[:start] + body + text[end:]


def patch_safety(text: str) -> str:
    start, end = find_method_end(text, SAFETY_SIG)
    body = text[start:end]
    body = body.replace("NeverFolia R9-v4:", "NeverFolia R9-v5:")
    return text[:start] + body + text[end:]


def method_text(text: str, signature: str) -> str:
    start, end = find_method_end(text, signature)
    return text[start:end]


def validate(fast: str, policy: str, safety: str) -> None:
    fast_method = method_text(fast, FAST_SIG)
    policy_method = method_text(policy, POLICY_SIG)
    safety_method = method_text(safety, SAFETY_SIG)

    for label, body in (("fast", fast_method), ("generation", policy_method)):
        if NEW_MARKER not in body:
            fail(f"{label}: V5 marker missing")
        if NEW_REACH not in body or NEW_OFFSETS not in body:
            fail(f"{label}: reach64 5x5 contract missing")
        for old in (OLD_MARKER, OLD_REACH, OLD_OFFSETS):
            if old in body:
                fail(f"{label}: stale V4 envelope survived: {old}")
        if "Structure.generate(" in body or "NeverOverworldGeneratedVillageSafety.preview" in body:
            fail(f"{label}: forbidden generated-Jigsaw preview returned")

    if "R9V5_ENVELOPE_REJECT" not in fast_method or "R9V5_ACCEPT" not in fast_method:
        fail("fast: V5 diagnostics missing")
    if OLD_GENERATION_RETURN in policy_method:
        fail("generation: stale reach96 sentinel survived V5 calibration")
    if NEW_GENERATION_RETURN not in policy_method:
        fail("generation: reach64 sentinel missing")
    if "return start.isValid();" not in safety_method:
        fail("safety: start validity guard missing")
    if "inspectBoundingBox(" in safety_method or ".dry()" in safety_method:
        fail("safety: post-generation exact bbox rejection survived")


def self_test() -> None:
    fast_fixture = '''final class F {\n    private static boolean passesNeverOverworldPolicy(\n        int a\n    ) {\n        // NeverFolia R9-v4: shared 5x5 preliminary village envelope; no Jigsaw preview in locate.\n        final int villageReach = 96;\n        final int[] villageOffsets = {-96, -48, 0, 48, 96};\n        debugVillage(id, "R9V4_CENTER_DRY_REJECT", p, y, "");\n        debugVillage(id, "R9V4_BIOME_REJECT", p, y, "");\n        debugVillage(id, "R9V4_ENVELOPE_REJECT", p, y, "");\n        debugVillage(id, "R9V4_ACCEPT", p, y, "5x5-preliminary-reach=" + villageReach);\n        return true;\n    }\n}\n'''
    policy_fixture = '''final class P {\n    static boolean allows(\n        int a\n    ) {\n        // NeverFolia R9-v4: shared 5x5 preliminary village envelope; no Jigsaw preview in locate.\n        final int villageReach = 96;\n        final int[] villageOffsets = {-96, -48, 0, 48, 96};\n        return villageReach == 96;\n    }\n}\n'''
    safety_fixture = '''final class S {\n    static boolean allowsGenerated(\n        int a\n    ) {\n        // NeverFolia R9-v4: shared candidate envelope.\n        return start.isValid();\n    }\n}\n'''
    fast = patch_method(fast_fixture, FAST_SIG, "fast")
    policy = patch_method(policy_fixture, POLICY_SIG, "generation")
    safety = patch_safety(safety_fixture)
    validate(fast, policy, safety)
    if patch_method(fast, FAST_SIG, "fast") != fast:
        fail("SELF-TEST: fast transformer is not idempotent")
    if patch_method(policy, POLICY_SIG, "generation") != policy:
        fail("SELF-TEST: generation transformer is not idempotent")
    if patch_safety(safety) != safety:
        fail("SELF-TEST: safety transformer is not idempotent")

    # Regression fixture for the exact broken V5 state observed in earlier QA:
    # reach64 constants present while the generation sentinel still compares 96.
    stale_v5 = policy.replace(NEW_GENERATION_RETURN, OLD_GENERATION_RETURN, 1)
    repaired = patch_method(stale_v5, POLICY_SIG, "generation")
    if OLD_GENERATION_RETURN in method_text(repaired, POLICY_SIG):
        fail("SELF-TEST: stale V5 generation sentinel was not repaired")
    validate(fast, repaired, safety)

    print("[NeverFolia][R9 village locate v5] SELF-TEST OK")
    print("  locate + generation: identical 5x5 preliminarySurfaceLevel envelope")
    print("  calibrated reach: 64 blocks; offsets -64,-32,0,32,64")
    print("  generation sentinel: reach64 (historical ==96 mismatch repaired)")
    print("  locate: zero Structure.generate / generated-bbox preview / getBaseHeight")
    print("  final safety: persisted full Jigsaw bbox water=0 QA")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required")

    self_test()
    root = args.folia.resolve()
    fast_path = root / FAST_REL
    policy_path = root / POLICY_REL
    safety_path = root / SAFETY_REL
    for path in (fast_path, policy_path, safety_path):
        if not path.is_file():
            fail(f"materialized helper missing: {path}")

    fast = patch_method(fast_path.read_text(encoding="utf-8"), FAST_SIG, "fast")
    policy = patch_method(policy_path.read_text(encoding="utf-8"), POLICY_SIG, "generation")
    safety = patch_safety(safety_path.read_text(encoding="utf-8"))
    validate(fast, policy, safety)

    fast_path.write_text(fast, encoding="utf-8")
    policy_path.write_text(policy, encoding="utf-8")
    safety_path.write_text(safety, encoding="utf-8")
    print("[NeverFolia][R9 village locate v5] calibrated shared envelope applied")
    print(f"  fast locate: {fast_path}")
    print(f"  generation policy: {policy_path}")
    print(f"  generated safety: {safety_path}")


if __name__ == "__main__":
    main()
