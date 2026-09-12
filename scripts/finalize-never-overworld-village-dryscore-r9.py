#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
MARKER_PREFIX = "// NeverFolia R9-final: hardcoded shared village dry-score profile="
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"

PROBES = [
    (-64, 0), (64, 0), (0, -64), (0, 64),
    (-32, -32), (-32, 0), (-32, 32),
    (0, -32), (0, 32),
    (32, -32), (32, 0), (32, 32),
]
PROFILES = {"score10": 10, "score9": 9, "score8": 8}

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
    raise SystemExit(f"[NeverFolia][R9 final village dry-score] {message}")


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


def fast_code(profile: str) -> str:
    threshold = PROFILES[profile]
    return f'''            {MARKER_PREFIX}{profile}
            final int minDryProbes = {threshold};
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
            if (dryProbes < minDryProbes) {{
                debugVillage(id, "R9FINAL_SCORE_REJECT", chunkPos, centerSurfaceY,
                    "profile={profile},dry=" + dryProbes + "/" + villageProbes.length + ",wet=" + wetProbes);
                return false;
            }}
            debugVillage(id, "R9FINAL_ACCEPT", chunkPos, centerSurfaceY,
                "profile={profile},dry=" + dryProbes + "/" + villageProbes.length + ",wet=" + wetProbes);
            return true;
'''


def generation_code(profile: str) -> str:
    threshold = PROFILES[profile]
    return f'''            {MARKER_PREFIX}{profile}
            final int minDryProbes = {threshold};
            final int[][] villageProbes = new int[][] {java_points()};
            int dryProbes = 0;
            for (final int[] probeOffset : villageProbes) {{
                if (preliminarySurfaceY(randomState, centerX + probeOffset[0], centerZ + probeOffset[1]) >= MIN_DRY_BASE_HEIGHT) {{
                    ++dryProbes;
                }}
            }}
            return dryProbes >= minDryProbes;
'''


def replace(text: str, sig: str, old: str, new: str, label: str) -> str:
    start, end = find_method_end(text, sig)
    method = text[start:end]
    if MARKER_PREFIX in method:
        if new.strip() in method:
            return text
        fail(f"{label}: a different final dry-score profile is already installed")
    if "neverfolia.villageDryScoreProfile" in method:
        fail(f"{label}: QA runtime selector must be removed before finalization")
    if old not in method:
        fail(f"{label}: corrected V5 reach64 anchor missing")
    method = method.replace(old, new, 1)
    return text[:start] + method + text[end:]


def validate(fast: str, policy: str, profile: str) -> None:
    marker = MARKER_PREFIX + profile
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = find_method_end(text, sig)
        method = text[start:end]
        if marker not in method:
            fail(f"{label}: final profile marker missing")
        if "neverfolia.villageDryScoreProfile" in method:
            fail(f"{label}: QA runtime selector leaked into production finalizer")
        if f"final int minDryProbes = {PROFILES[profile]};" not in method:
            fail(f"{label}: hardcoded threshold missing")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method:
                fail(f"{label}: watchdog-risk primitive leaked: {forbidden}")
        if label == "fast" and "getBaseHeight(" in method:
            fail("fast: getBaseHeight leaked")
        if label == "generation":
            a = method.find(marker)
            b = method.find(NON_VILLAGE_ANCHOR, a)
            if b < 0:
                fail("generation: non-village boundary missing")
            if "getBaseHeight(" in method[a:b]:
                fail("generation: getBaseHeight leaked into village dry-score block")
    if "R9FINAL_SCORE_REJECT" not in fast or "R9FINAL_ACCEPT" not in fast:
        fail("fast: final diagnostics missing")


def self_test() -> None:
    if len(PROBES) != 12 or len(set(PROBES)) != 12 or (0, 0) in PROBES:
        fail("SELF-TEST: invalid probe set")
    if PROFILES != {"score10": 10, "score9": 9, "score8": 8}:
        fail("SELF-TEST: profile thresholds drifted")
    fast_fixture = '''class F {\n    private static boolean passesNeverOverworldPolicy(int x) {\n''' + OLD_FAST + '''    }\n}\n'''
    policy_fixture = '''class P {\n    static boolean allows(int x) {\n''' + OLD_GENERATION + '''        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return generator.getBaseHeight(0,0,type,heightAccessor,randomState)>0;\n    }\n}\n'''
    for profile in PROFILES:
        f = replace(fast_fixture, FAST_SIG, OLD_FAST, fast_code(profile), "fast")
        p = replace(policy_fixture, POLICY_SIG, OLD_GENERATION, generation_code(profile), "generation")
        validate(f, p, profile)
        if "System.getProperty" in f or "System.getProperty" in p:
            fail(f"SELF-TEST: runtime selector survived for {profile}")
    print("[NeverFolia][R9 final village dry-score] SELF-TEST OK")
    print("  12 shared probes; hardcoded threshold; no QA selector")
    print("  generation watchdog validation scoped to village block only")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folia", nargs="?", type=Path)
    ap.add_argument("--profile", choices=sorted(PROFILES))
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None or args.profile is None:
        ap.error("folia worktree and --profile are required")
    self_test()
    root = args.folia.resolve()
    fp = root / FAST_REL
    pp = root / POLICY_REL
    for path in (fp, pp):
        if not path.is_file(): fail(f"helper missing: {path}")
    f = replace(fp.read_text(encoding="utf-8"), FAST_SIG, OLD_FAST, fast_code(args.profile), "fast")
    p = replace(pp.read_text(encoding="utf-8"), POLICY_SIG, OLD_GENERATION, generation_code(args.profile), "generation")
    validate(f, p, args.profile)
    fp.write_text(f, encoding="utf-8")
    pp.write_text(p, encoding="utf-8")
    print(f"[NeverFolia][R9 final village dry-score] hardcoded profile applied: {args.profile}")


if __name__ == "__main__":
    main()
