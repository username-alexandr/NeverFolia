#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
V16_MARKER = "// NeverFolia R9-v16 QA: variant-specific preliminary score plus exact solid mask."
FINAL_MARKER = "// NeverFolia R9-final: fixed variant-specific preliminary score plus exact solid mask."
RING_SELECTOR = '    private static final int MAX_CANDIDATE_RINGS = Integer.getInteger("neverfolia.villageLocateRings", 128);'
PROFILE_SELECTOR = 'final String maskProfile = System.getProperty("neverfolia.villageVariantMaskProfile", "fit");'
PROFILES = {"fit", "margin8"}
RINGS = {128, 192, 256}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village finalizer v16] {message}")


def method_bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method not found: {signature.strip()}")
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
            if ch == "\n": in_line = False
            i += 1; continue
        if in_block:
            if ch == "*" and nxt == "/": in_block = False; i += 2
            else: i += 1
            continue
        if in_s:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': in_s = False
            i += 1; continue
        if in_c:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == "'": in_c = False
            i += 1; continue
        if ch == "/" and nxt == "/": in_line = True; i += 2; continue
        if ch == "/" and nxt == "*": in_block = True; i += 2; continue
        if ch == '"': in_s = True; i += 1; continue
        if ch == "'": in_c = True; i += 1; continue
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == "\n": end += 1
                return start, end
        i += 1
    fail("unterminated method")


def patch(fast: str, policy: str, profile: str, rings: int) -> tuple[str, str]:
    if profile not in PROFILES:
        fail(f"unsupported profile: {profile}")
    if rings not in RINGS:
        fail(f"unsupported rings: {rings}")
    fixed_ring = f"    private static final int MAX_CANDIDATE_RINGS = {rings};"
    if fixed_ring not in fast:
        if fast.count(RING_SELECTOR) != 1:
            fail(f"ring selector count mismatch: {fast.count(RING_SELECTOR)}")
        fast = fast.replace(RING_SELECTOR, fixed_ring, 1)
    fixed_profile = f'final String maskProfile = "{profile}";'
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = method_bounds(text, sig)
        method = text[start:end]
        if FINAL_MARKER in method:
            continue
        if V16_MARKER not in method:
            fail(f"{label}: V16 marker missing")
        if PROFILE_SELECTOR not in method:
            fail(f"{label}: V16 profile selector missing")
        method = method.replace(V16_MARKER, FINAL_MARKER, 1)
        method = method.replace(PROFILE_SELECTOR, fixed_profile, 1)
        if label == "fast":
            fast = text[:start] + method + text[end:]
        else:
            policy = text[:start] + method + text[end:]
    validate(fast, policy, profile, rings)
    return fast, policy


def validate(fast: str, policy: str, profile: str, rings: int) -> None:
    if f"private static final int MAX_CANDIDATE_RINGS = {rings};" not in fast:
        fail("fixed ring constant missing")
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = method_bounds(text, sig)
        method = text[start:end]
        if FINAL_MARKER not in method:
            fail(f"{label}: final marker missing")
        if f'final String maskProfile = "{profile}";' not in method:
            fail(f"{label}: fixed profile missing")
        if "System.getProperty(" in method:
            fail(f"{label}: runtime profile selector survived")
        if "Heightmap.Types.OCEAN_FLOOR_WG" not in method:
            fail(f"{label}: OCEAN_FLOOR_WG missing")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method:
                fail(f"{label}: forbidden generated preview leaked: {forbidden}")
    for selector in ("neverfolia.villageLocateRings", "neverfolia.villageVariantMaskProfile"):
        if selector in fast or selector in policy:
            fail(f"QA selector leaked after finalization: {selector}")


def self_test() -> None:
    fast = '''class F {\n    private static final int MAX_CANDIDATE_RINGS = Integer.getInteger("neverfolia.villageLocateRings", 128);\n    private static boolean passesNeverOverworldPolicy(int x) {\n        // NeverFolia R9-v16 QA: variant-specific preliminary score plus exact solid mask.\n        final String maskProfile = System.getProperty("neverfolia.villageVariantMaskProfile", "fit");\n        int x1 = Heightmap.Types.OCEAN_FLOOR_WG.ordinal();\n        return true;\n    }\n}\n'''
    policy = '''class P {\n    static boolean allows(int x) {\n        // NeverFolia R9-v16 QA: variant-specific preliminary score plus exact solid mask.\n        final String maskProfile = System.getProperty("neverfolia.villageVariantMaskProfile", "fit");\n        int x1 = Heightmap.Types.OCEAN_FLOOR_WG.ordinal();\n        return true;\n    }\n}\n'''
    for profile in sorted(PROFILES):
        for rings in sorted(RINGS):
            f, p = patch(fast, policy, profile, rings)
            validate(f, p, profile, rings)
    print("[NeverFolia][R9 village finalizer v16] SELF-TEST OK")
    print("  profile and ring budget fixed at build time")
    print("  no QA JVM selectors survive")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folia", nargs="?", type=Path)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="fit")
    ap.add_argument("--rings", type=int, choices=sorted(RINGS), default=128)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None:
        ap.error("folia worktree is required")
    self_test()
    root = args.folia.resolve(); fp = root / FAST_REL; pp = root / POLICY_REL
    for path in (fp, pp):
        if not path.is_file(): fail(f"helper missing: {path}")
    fast, policy = patch(fp.read_text(encoding="utf-8"), pp.read_text(encoding="utf-8"), args.profile, args.rings)
    fp.write_text(fast, encoding="utf-8"); pp.write_text(policy, encoding="utf-8")
    print(f"[NeverFolia][R9 village finalizer v16] fixed profile={args.profile} rings={args.rings}")


if __name__ == "__main__":
    main()
