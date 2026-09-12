#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
OLD_RING = "    private static final int MAX_CANDIDATE_RINGS = 64;"
MARKER = "// NeverFolia R9-final: fixed conservative village footprint grid."
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"

PROFILES = {
    "grid5": [-96, -48, 0, 48, 96],
    "grid7": [-96, -64, -32, 0, 32, 64, 96],
    "grid13": [-96, -80, -64, -48, -32, -16, 0, 16, 32, 48, 64, 80, 96],
}
ALLOWED_RINGS = {128, 192, 256}

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
    raise SystemExit(f"[NeverFolia][R9 village finalizer v13] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method not found: {signature.strip()}")
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


def offsets_java(profile: str) -> str:
    return ", ".join(map(str, PROFILES[profile]))


def fast_code(profile: str, rings: int) -> str:
    offsets = offsets_java(profile)
    return f'''            {MARKER}
            final int[] villageOffsets = new int[] {{{offsets}}};
            for (final int dx : villageOffsets) {{
                for (final int dz : villageOffsets) {{
                    if (dx == 0 && dz == 0) continue;
                    final int surfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                    if (surfaceY < MIN_DRY_BASE_HEIGHT) {{
                        debugVillage(id, "R9FINAL_GRID_REJECT", chunkPos, centerSurfaceY,
                            "profile={profile},rings={rings},sample=" + dx + "," + dz + ",surface=" + surfaceY);
                        return false;
                    }}
                }}
            }}
            debugVillage(id, "R9FINAL_GRID_ACCEPT", chunkPos, centerSurfaceY, "profile={profile},rings={rings}");
            return true;
'''


def generation_code(profile: str) -> str:
    offsets = offsets_java(profile)
    return f'''            {MARKER}
            final int[] villageOffsets = new int[] {{{offsets}}};
            for (final int dx : villageOffsets) {{
                for (final int dz : villageOffsets) {{
                    if (dx == 0 && dz == 0) continue;
                    if (preliminarySurfaceY(randomState, centerX + dx, centerZ + dz) < MIN_DRY_BASE_HEIGHT) {{
                        return false;
                    }}
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


def apply_fixed(fast: str, policy: str, profile: str, rings: int) -> tuple[str, str]:
    if profile not in PROFILES:
        fail(f"unknown profile: {profile}")
    if rings not in ALLOWED_RINGS:
        fail(f"unsupported rings: {rings}")
    fixed_ring = f"    private static final int MAX_CANDIDATE_RINGS = {rings};"
    if fixed_ring not in fast:
        if fast.count(OLD_RING) != 1:
            fail(f"expected one 64-ring anchor, got {fast.count(OLD_RING)}")
        fast = fast.replace(OLD_RING, fixed_ring, 1)
    fast = patch_method(fast, FAST_SIG, OLD_FAST, fast_code(profile, rings), "fast")
    policy = patch_method(policy, POLICY_SIG, OLD_GENERATION, generation_code(profile), "generation")
    validate(fast, policy, profile, rings)
    return fast, policy


def validate(fast: str, policy: str, profile: str, rings: int) -> None:
    if f"private static final int MAX_CANDIDATE_RINGS = {rings};" not in fast:
        fail("fixed ring constant missing")
    expected_offsets = f"new int[] {{{offsets_java(profile)}}}"
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = find_method_end(text, sig)
        method = text[start:end]
        if MARKER not in method or expected_offsets not in method:
            fail(f"{label}: fixed profile markers missing")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method:
                fail(f"{label}: watchdog-risk primitive leaked: {forbidden}")
        if label == "fast" and "getBaseHeight(" in method:
            fail("fast: getBaseHeight leaked")
        if label == "generation":
            a = method.find(MARKER); b = method.find(NON_VILLAGE_ANCHOR, a)
            if b < 0:
                fail("generation: non-village boundary missing")
            if "getBaseHeight(" in method[a:b]:
                fail("generation: getBaseHeight leaked into village block")
    for selector in ("neverfolia.villageFootprintProfile", "neverfolia.villageLocateRings", "neverfolia.villageDryScoreProfile"):
        if selector in fast or selector in policy:
            fail(f"QA selector leaked into production finalizer: {selector}")


def self_test() -> None:
    fast_fixture = '''class F {\n    private static final int MAX_CANDIDATE_RINGS = 64;\n    private static boolean passesNeverOverworldPolicy(int x) {\n''' + OLD_FAST + '''    }\n}\n'''
    policy_fixture = '''class P {\n    static boolean allows(int x) {\n''' + OLD_GENERATION + '''        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return generator.getBaseHeight(0,0,type,heightAccessor,randomState)>0;\n    }\n}\n'''
    for profile in PROFILES:
        for rings in sorted(ALLOWED_RINGS):
            f, p = apply_fixed(fast_fixture, policy_fixture, profile, rings)
            validate(f, p, profile, rings)
    print("[NeverFolia][R9 village finalizer v13] SELF-TEST OK")
    print("  fixed profiles: grid5/grid7/grid13; fixed rings: 128/192/256")
    print("  no QA JVM selectors survive")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folia", nargs="?", type=Path)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="grid5")
    ap.add_argument("--rings", type=int, choices=sorted(ALLOWED_RINGS), default=128)
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
    fast, policy = apply_fixed(fp.read_text(encoding="utf-8"), pp.read_text(encoding="utf-8"), args.profile, args.rings)
    fp.write_text(fast, encoding="utf-8"); pp.write_text(policy, encoding="utf-8")
    print(f"[NeverFolia][R9 village finalizer v13] fixed profile={args.profile} rings={args.rings}")


if __name__ == "__main__":
    main()
