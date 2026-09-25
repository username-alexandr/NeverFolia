#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
OLD_RING = "    private static final int MAX_CANDIDATE_RINGS = 64;"
NEW_RING = '    private static final int MAX_CANDIDATE_RINGS = Integer.getInteger("neverfolia.villageLocateRings", 64);'
MARKER = "// NeverFolia R9-v12 QA: strict 12/12 village dry contract with runtime locate-ring budget."
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"

PROBES = [
    (-64, 0), (64, 0), (0, -64), (0, 64),
    (-32, -32), (-32, 0), (-32, 32),
    (0, -32), (0, 32),
    (32, -32), (32, 0), (32, 32),
]

OLD_FAST = '''            final int villageReach = 64;
            final int[] villageOffsets = {-64, -32, 0, 32, 64};
            for (final int dx : villageOffsets) {
                for (final int dz : villageOffsets) {
                    if (dx == 0 && dz == 0) {
                        continue;
                    }
                    final int surfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                    if (surfaceY < MIN_DRY_BASE_HEIGHT) {
                        debugVillage(
                            id,
                            "R9V5_ENVELOPE_REJECT",
                            chunkPos,
                            centerSurfaceY,
                            "sample=" + dx + "," + dz + ",surface=" + surfaceY + ",reach=" + villageReach
                        );
                        return false;
                    }
                }
            }
            debugVillage(id, "R9V5_ACCEPT", chunkPos, centerSurfaceY, "5x5-calibrated-reach=" + villageReach);
            return true;
'''

OLD_GENERATION = '''            final int villageReach = 64;
            final int[] villageOffsets = {-64, -32, 0, 32, 64};
            for (final int dx : villageOffsets) {
                for (final int dz : villageOffsets) {
                    if (dx == 0 && dz == 0) {
                        continue;
                    }
                    if (preliminarySurfaceY(randomState, centerX + dx, centerZ + dz) < MIN_DRY_BASE_HEIGHT) {
                        return false;
                    }
                }
            }
            return villageReach == 64;
'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village strict search v12] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
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


def java_points() -> str:
    return "{" + ", ".join("{" + f"{x}, {z}" + "}" for x, z in PROBES) + "}"


def fast_code() -> str:
    return f'''            {MARKER}
            final int[][] villageProbes = new int[][] {java_points()};
            int dryProbes = 0;
            final StringBuilder wetProbes = new StringBuilder();
            for (final int[] probeOffset : villageProbes) {{
                final int dx = probeOffset[0];
                final int dz = probeOffset[1];
                final int surfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                if (surfaceY >= MIN_DRY_BASE_HEIGHT) {{
                    ++dryProbes;
                }} else {{
                    if (!wetProbes.isEmpty()) wetProbes.append(';');
                    wetProbes.append(dx).append(',').append(dz).append('=').append(surfaceY);
                }}
            }}
            if (dryProbes != villageProbes.length) {{
                debugVillage(id, "R9V12_STRICT_REJECT", chunkPos, centerSurfaceY,
                    "rings=" + MAX_CANDIDATE_RINGS + ",dry=" + dryProbes + "/" + villageProbes.length + ",wet=" + wetProbes);
                return false;
            }}
            debugVillage(id, "R9V12_ACCEPT", chunkPos, centerSurfaceY,
                "rings=" + MAX_CANDIDATE_RINGS + ",dry=" + dryProbes + "/" + villageProbes.length);
            return true;
'''


def generation_code() -> str:
    return f'''            {MARKER}
            final int[][] villageProbes = new int[][] {java_points()};
            for (final int[] probeOffset : villageProbes) {{
                if (preliminarySurfaceY(randomState, centerX + probeOffset[0], centerZ + probeOffset[1]) < MIN_DRY_BASE_HEIGHT) {{
                    return false;
                }}
            }}
            return true;
'''


def patch_method(text: str, sig: str, old: str, new: str, label: str) -> str:
    start, end = find_method_end(text, sig)
    method = text[start:end]
    if MARKER in method:
        return text
    if old not in method:
        fail(f"{label}: corrected V5 anchor missing")
    method = method.replace(old, new, 1)
    return text[:start] + method + text[end:]


def patch(text: str) -> str:
    if NEW_RING not in text:
        if text.count(OLD_RING) != 1:
            fail(f"expected one 64-ring anchor, got {text.count(OLD_RING)}")
        text = text.replace(OLD_RING, NEW_RING, 1)
    text = patch_method(text, FAST_SIG, OLD_FAST, fast_code(), "fast")
    return text


def validate(fast: str, policy: str) -> None:
    if NEW_RING not in fast:
        fail("runtime ring selector missing")
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = find_method_end(text, sig)
        method = text[start:end]
        if MARKER not in method:
            fail(f"{label}: V12 marker missing")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method:
                fail(f"{label}: watchdog-risk primitive leaked: {forbidden}")
        if label == "fast":
            if "getBaseHeight(" in method:
                fail("fast: getBaseHeight leaked")
            if "R9V12_STRICT_REJECT" not in method or "R9V12_ACCEPT" not in method:
                fail("fast: strict diagnostics missing")
            if "dryProbes != villageProbes.length" not in method:
                fail("fast: 12/12 contract missing")
        else:
            a = method.find(MARKER)
            b = method.find(NON_VILLAGE_ANCHOR, a)
            if b < 0:
                fail("generation: non-village boundary missing")
            if "getBaseHeight(" in method[a:b]:
                fail("generation: getBaseHeight leaked into village strict block")
            if "return true;" not in method[a:b]:
                fail("generation: strict block return missing")
    if "neverfolia.villageDryScoreProfile" in fast or "neverfolia.villageDryScoreProfile" in policy:
        fail("V11 dry-score selector leaked into V12")


def self_test() -> None:
    if len(PROBES) != 12 or len(set(PROBES)) != 12 or (0, 0) in PROBES:
        fail("SELF-TEST: invalid strict probe set")
    fast_fixture = '''class F {\n    private static final int MAX_CANDIDATE_RINGS = 64;\n    private static boolean passesNeverOverworldPolicy(int x) {\n''' + OLD_FAST + '''    }\n}\n'''
    policy_fixture = '''class P {\n    static boolean allows(int x) {\n''' + OLD_GENERATION + '''        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return generator.getBaseHeight(0,0,type,heightAccessor,randomState)>0;\n    }\n}\n'''
    fast = patch(fast_fixture)
    policy = patch_method(policy_fixture, POLICY_SIG, OLD_GENERATION, generation_code(), "generation")
    validate(fast, policy)
    if patch(fast) != fast:
        fail("SELF-TEST: fast transformer not idempotent")
    if patch_method(policy, POLICY_SIG, OLD_GENERATION, generation_code(), "generation") != policy:
        fail("SELF-TEST: generation transformer not idempotent")
    print("[NeverFolia][R9 village strict search v12] SELF-TEST OK")
    print("  safety: strict 12/12 shared preliminary probes")
    print("  availability: runtime-selectable locate ring budget")
    print("  locate remains zero-generation / zero getBaseHeight")


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
    fast = patch(fp.read_text(encoding="utf-8"))
    policy = patch_method(pp.read_text(encoding="utf-8"), POLICY_SIG, OLD_GENERATION, generation_code(), "generation")
    validate(fast, policy)
    fp.write_text(fast, encoding="utf-8")
    pp.write_text(policy, encoding="utf-8")
    print("[NeverFolia][R9 village strict search v12] strict 12/12 + runtime ring budget applied")


if __name__ == "__main__":
    main()
