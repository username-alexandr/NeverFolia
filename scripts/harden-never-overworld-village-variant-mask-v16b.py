#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
V16_MARKER = "// NeverFolia R9-v16 QA: variant-specific preliminary score plus exact solid mask."
V16B_MARKER = "// NeverFolia R9-v16b: exact recheck of every preliminary probe for relaxed variants."
INSERT_ANCHOR = "            int[] exactXs;\n"
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village variant mask v16b] {message}")


def method_bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method not found: {signature.strip()}")
    if text.find(signature, start + 1) >= 0:
        fail(f"method occurs more than once: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail("opening brace missing")
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


def recheck_block(kind: str) -> str:
    if kind == "fast":
        tail = "level, state.randomState()"
        reject = '''
                        debugVillage(id, "R9V16B_RELAXED_EXACT_REJECT", chunkPos, centerSurfaceY,
                            "sample=" + probe[0] + "," + probe[1] + ",solidBase=" + solidBase
                                + ",rings=" + MAX_CANDIDATE_RINGS);'''
    else:
        tail = "heightAccessor, randomState"
        reject = ""
    return f'''            {V16B_MARKER}
            if ("minecraft:village_snowy".equals(id) || "minecraft:village_taiga".equals(id)) {{
                for (final int[] probe : preliminaryProbes) {{
                    final int solidBase = generator.getBaseHeight(
                        centerX + probe[0],
                        centerZ + probe[1],
                        Heightmap.Types.OCEAN_FLOOR_WG,
                        {tail}
                    );
                    if (solidBase < MIN_DRY_BASE_HEIGHT) {{{reject}
                        return false;
                    }}
                }}
            }}

'''


def patch_method(text: str, signature: str, kind: str) -> str:
    start, end = method_bounds(text, signature)
    method = text[start:end]
    if V16B_MARKER in method:
        return text
    if V16_MARKER not in method:
        fail(f"{kind}: V16 marker missing")
    if method.count(INSERT_ANCHOR) != 1:
        fail(f"{kind}: expected one exact-mask insertion anchor, got {method.count(INSERT_ANCHOR)}")
    method = method.replace(INSERT_ANCHOR, recheck_block(kind) + INSERT_ANCHOR, 1)
    return text[:start] + method + text[end:]


def validate(fast: str, policy: str) -> None:
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = method_bounds(text, sig)
        method = text[start:end]
        if V16_MARKER not in method or V16B_MARKER not in method:
            fail(f"{label}: V16/V16b markers missing")
        if method.count("for (final int[] probe : preliminaryProbes)") < 2:
            fail(f"{label}: relaxed exact recheck loop missing")
        if '"minecraft:village_snowy".equals(id) || "minecraft:village_taiga".equals(id)' not in method:
            fail(f"{label}: relaxed-variant guard missing")
        if "Heightmap.Types.OCEAN_FLOOR_WG" not in method:
            fail(f"{label}: solid heightmap missing")
        if "Structure.generate(" in method or "NeverOverworldGeneratedVillageSafety.preview" in method:
            fail(f"{label}: generated preview leaked")
        if label == "fast":
            if "R9V16B_RELAXED_EXACT_REJECT" not in method:
                fail("fast: V16b rejection diagnostic missing")
        else:
            a = method.find(V16B_MARKER)
            b = method.find(NON_VILLAGE_ANCHOR, a)
            if b < 0:
                fail("generation: non-village boundary missing")
            if "WORLD_SURFACE_WG" in method[a:b]:
                fail("generation: fluid-aware WORLD_SURFACE_WG leaked into relaxed recheck")


def self_test() -> None:
    fast_fixture = '''class F {\n    private static boolean passesNeverOverworldPolicy(int x) {\n        // NeverFolia R9-v16 QA: variant-specific preliminary score plus exact solid mask.\n        final int[][] preliminaryProbes = new int[][] {{-64,0},{64,0}};\n        for (final int[] probe : preliminaryProbes) { int y = probe[0]; }\n            int[] exactXs;\n        return true;\n    }\n}\n'''
    policy_fixture = '''class P {\n    static boolean allows(int x) {\n        // NeverFolia R9-v16 QA: variant-specific preliminary score plus exact solid mask.\n        final int[][] preliminaryProbes = new int[][] {{-64,0},{64,0}};\n        for (final int[] probe : preliminaryProbes) { int y = probe[0]; }\n            int[] exactXs;\n        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return true;\n    }\n}\n'''
    fast = patch_method(fast_fixture, FAST_SIG, "fast")
    policy = patch_method(policy_fixture, POLICY_SIG, "generation")
    validate(fast, policy)
    if patch_method(fast, FAST_SIG, "fast") != fast:
        fail("SELF-TEST: fast transformer not idempotent")
    if patch_method(policy, POLICY_SIG, "generation") != policy:
        fail("SELF-TEST: generation transformer not idempotent")
    print("[NeverFolia][R9 village variant mask v16b] SELF-TEST OK")
    print("  snowy/taiga: every relaxed preliminary probe is exact-rechecked with OCEAN_FLOOR_WG")
    print("  locate remains zero Structure.generate / zero Jigsaw preview")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folia", nargs="?", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None:
        ap.error("folia worktree is required")
    self_test()
    root = args.folia.resolve()
    fp = root / FAST_REL
    pp = root / POLICY_REL
    for path in (fp, pp):
        if not path.is_file(): fail(f"helper missing: {path}")
    fast = patch_method(fp.read_text(encoding="utf-8"), FAST_SIG, "fast")
    policy = patch_method(pp.read_text(encoding="utf-8"), POLICY_SIG, "generation")
    validate(fast, policy)
    fp.write_text(fast, encoding="utf-8")
    pp.write_text(policy, encoding="utf-8")
    print("[NeverFolia][R9 village variant mask v16b] relaxed-probe exact recheck applied")


if __name__ == "__main__":
    main()
