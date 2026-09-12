#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
OLD_RING = "    private static final int MAX_CANDIDATE_RINGS = 64;"
MARKER_PREFIX = "// NeverFolia R9-final: strict 12/12 village dry contract, locate-rings="
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"
ALLOWED_RINGS = (96, 128, 192, 256)
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


def fail(msg: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 final village strict search] {msg}")


def method_bounds(text: str, sig: str) -> tuple[int, int]:
    start = text.find(sig)
    if start < 0 or text.find(sig, start + 1) >= 0:
        fail(f"method signature missing/ambiguous: {sig.strip()}")
    opening = text.find("{", start)
    depth = 0; i = opening; ins = inc = inl = inb = esc = False
    while i < len(text):
        c = text[i]; n = text[i+1] if i+1 < len(text) else ""
        if inl:
            if c == "\n": inl = False
            i += 1; continue
        if inb:
            if c == "*" and n == "/": inb = False; i += 2
            else: i += 1
            continue
        if ins:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': ins = False
            i += 1; continue
        if inc:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == "'": inc = False
            i += 1; continue
        if c == "/" and n == "/": inl = True; i += 2; continue
        if c == "/" and n == "*": inb = True; i += 2; continue
        if c == '"': ins = True; i += 1; continue
        if c == "'": inc = True; i += 1; continue
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == "\n": end += 1
                return start, end
        i += 1
    fail("unterminated method")


def points_java() -> str:
    return "{" + ", ".join(f"{{{x}, {z}}}" for x, z in PROBES) + "}"


def fast_code(rings: int) -> str:
    return f'''            {MARKER_PREFIX}{rings}
            final int[][] villageProbes = new int[][] {points_java()};
            for (final int[] probeOffset : villageProbes) {{
                final int surfaceY = preliminarySurfaceY(state, centerX + probeOffset[0], centerZ + probeOffset[1]);
                if (surfaceY < MIN_DRY_BASE_HEIGHT) {{
                    debugVillage(id, "R9FINAL_STRICT_REJECT", chunkPos, centerSurfaceY,
                        "rings={rings},sample=" + probeOffset[0] + "," + probeOffset[1] + ",surface=" + surfaceY);
                    return false;
                }}
            }}
            debugVillage(id, "R9FINAL_ACCEPT", chunkPos, centerSurfaceY, "rings={rings},dry=12/12");
            return true;
'''


def generation_code(rings: int) -> str:
    return f'''            {MARKER_PREFIX}{rings}
            final int[][] villageProbes = new int[][] {points_java()};
            for (final int[] probeOffset : villageProbes) {{
                if (preliminarySurfaceY(randomState, centerX + probeOffset[0], centerZ + probeOffset[1]) < MIN_DRY_BASE_HEIGHT) {{
                    return false;
                }}
            }}
            return true;
'''


def replace_method(text: str, sig: str, old: str, new: str, label: str) -> str:
    start, end = method_bounds(text, sig); method = text[start:end]
    if MARKER_PREFIX in method:
        if new.strip() in method: return text
        fail(f"{label}: another final strict-search profile already installed")
    if old not in method: fail(f"{label}: corrected V5 anchor missing")
    return text[:start] + method.replace(old, new, 1) + text[end:]


def patch(fast: str, policy: str, rings: int) -> tuple[str, str]:
    if rings not in ALLOWED_RINGS: fail(f"unsupported rings={rings}")
    new_ring = f"    private static final int MAX_CANDIDATE_RINGS = {rings};"
    if new_ring not in fast:
        if fast.count(OLD_RING) != 1: fail("64-ring baseline anchor missing/ambiguous")
        fast = fast.replace(OLD_RING, new_ring, 1)
    fast = replace_method(fast, FAST_SIG, OLD_FAST, fast_code(rings), "fast")
    policy = replace_method(policy, POLICY_SIG, OLD_GENERATION, generation_code(rings), "generation")
    validate(fast, policy, rings)
    return fast, policy


def validate(fast: str, policy: str, rings: int) -> None:
    marker = MARKER_PREFIX + str(rings)
    if f"MAX_CANDIDATE_RINGS = {rings};" not in fast: fail("hardcoded ring budget missing")
    for forbidden_selector in ("neverfolia.villageLocateRings", "neverfolia.villageDryScoreProfile"):
        if forbidden_selector in fast or forbidden_selector in policy:
            fail(f"QA selector leaked: {forbidden_selector}")
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        s, e = method_bounds(text, sig); method = text[s:e]
        if marker not in method: fail(f"{label}: final marker missing")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method: fail(f"{label}: watchdog primitive leaked: {forbidden}")
        if label == "fast" and "getBaseHeight(" in method: fail("fast: getBaseHeight leaked")
        if label == "generation":
            a = method.find(marker); b = method.find(NON_VILLAGE_ANCHOR, a)
            if b < 0: fail("generation: non-village boundary missing")
            if "getBaseHeight(" in method[a:b]: fail("generation: getBaseHeight leaked into village block")
    if "R9FINAL_ACCEPT" not in fast or "R9FINAL_STRICT_REJECT" not in fast: fail("final diagnostics missing")


def self_test() -> None:
    if len(PROBES) != 12 or len(set(PROBES)) != 12 or (0,0) in PROBES: fail("bad probe set")
    ff = '''class F {\n    private static final int MAX_CANDIDATE_RINGS = 64;\n    private static boolean passesNeverOverworldPolicy(int x) {\n''' + OLD_FAST + '''    }\n}\n'''
    pf = '''class P {\n    static boolean allows(int x) {\n''' + OLD_GENERATION + '''        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return generator.getBaseHeight(0,0,type,heightAccessor,randomState)>0;\n    }\n}\n'''
    for rings in ALLOWED_RINGS:
        f, p = patch(ff, pf, rings)
        validate(f, p, rings)
    print("[NeverFolia][R9 final village strict search] SELF-TEST OK")
    print("  hardcoded strict 12/12 probes; hardcoded ring budget; no QA selector")


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("folia", nargs="?", type=Path); ap.add_argument("--rings", type=int, choices=ALLOWED_RINGS); ap.add_argument("--self-test", action="store_true"); a = ap.parse_args()
    if a.self_test: self_test(); return
    if a.folia is None or a.rings is None: ap.error("folia and --rings are required")
    self_test(); root = a.folia.resolve(); fp = root / FAST_REL; pp = root / POLICY_REL
    for path in (fp, pp):
        if not path.is_file(): fail(f"helper missing: {path}")
    f, p = patch(fp.read_text(encoding="utf-8"), pp.read_text(encoding="utf-8"), a.rings)
    fp.write_text(f, encoding="utf-8"); pp.write_text(p, encoding="utf-8")
    print(f"[NeverFolia][R9 final village strict search] applied rings={a.rings}")

if __name__ == "__main__": main()
