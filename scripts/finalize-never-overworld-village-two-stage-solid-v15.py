#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
OLD_RING = "    private static final int MAX_CANDIDATE_RINGS = 64;"
MARKER = "// NeverFolia R9-final: fixed two-stage solid-terrain village predictor."
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"
HEIGHTMAP_IMPORT = "import net.minecraft.world.level.levelgen.Heightmap;\n"
DENSITY_IMPORT = "import net.minecraft.world.level.levelgen.DensityFunction;\n"

PREFILTER = [
    (-64, 0), (64, 0), (0, -64), (0, 64),
    (-32, -32), (-32, 0), (-32, 32),
    (0, -32), (0, 32),
    (32, -32), (32, 0), (32, 32),
]
PROFILES = {
    "solid5": [-96, -48, 0, 48, 96],
    "solid7": [-96, -64, -32, 0, 32, 64, 96],
    "solid13": [-96, -80, -64, -48, -32, -16, 0, 16, 32, 48, 64, 80, 96],
}
RINGS = {128, 192, 256}

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
    raise SystemExit(f"[NeverFolia][R9 village finalizer v15] {message}")


def bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0: fail(f"method not found: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0: fail("opening brace missing")
    depth = 0; in_s = in_c = in_line = in_block = escaped = False; i = opening
    while i < len(text):
        ch = text[i]; nxt = text[i + 1] if i + 1 < len(text) else ""
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


def points_java() -> str:
    return "{" + ", ".join("{" + f"{x}, {z}" + "}" for x, z in PREFILTER) + "}"


def fast_code(profile: str, rings: int) -> str:
    offsets = ", ".join(map(str, PROFILES[profile]))
    return f'''            {MARKER}
            final int[][] preliminaryProbes = new int[][] {points_java()};
            for (final int[] probe : preliminaryProbes) {{
                final int surfaceY = preliminarySurfaceY(state, centerX + probe[0], centerZ + probe[1]);
                if (surfaceY < MIN_DRY_BASE_HEIGHT) {{
                    debugVillage(id, "R9FINAL_PRELIM_REJECT", chunkPos, centerSurfaceY,
                        "profile={profile},rings={rings},sample=" + probe[0] + "," + probe[1] + ",surface=" + surfaceY);
                    return false;
                }}
            }}
            final int[] solidOffsets = new int[] {{{offsets}}};
            for (final int dx : solidOffsets) {{
                for (final int dz : solidOffsets) {{
                    final int solidBase = generator.getBaseHeight(
                        centerX + dx, centerZ + dz, Heightmap.Types.OCEAN_FLOOR_WG, level, state.randomState());
                    if (solidBase < MIN_DRY_BASE_HEIGHT) {{
                        debugVillage(id, "R9FINAL_SOLID_REJECT", chunkPos, centerSurfaceY,
                            "profile={profile},rings={rings},sample=" + dx + "," + dz + ",solidBase=" + solidBase);
                        return false;
                    }}
                }}
            }}
            debugVillage(id, "R9FINAL_ACCEPT", chunkPos, centerSurfaceY, "profile={profile},rings={rings}");
            return true;
'''


def generation_code(profile: str) -> str:
    offsets = ", ".join(map(str, PROFILES[profile]))
    return f'''            {MARKER}
            final int[][] preliminaryProbes = new int[][] {points_java()};
            for (final int[] probe : preliminaryProbes) {{
                if (preliminarySurfaceY(randomState, centerX + probe[0], centerZ + probe[1]) < MIN_DRY_BASE_HEIGHT) {{
                    return false;
                }}
            }}
            final int[] solidOffsets = new int[] {{{offsets}}};
            for (final int dx : solidOffsets) {{
                for (final int dz : solidOffsets) {{
                    final int solidBase = generator.getBaseHeight(
                        centerX + dx, centerZ + dz, Heightmap.Types.OCEAN_FLOOR_WG, heightAccessor, randomState);
                    if (solidBase < MIN_DRY_BASE_HEIGHT) return false;
                }}
            }}
            return true;
'''


def replace(text: str, signature: str, old: str, new: str, label: str) -> str:
    start, end = bounds(text, signature); method = text[start:end]
    if MARKER in method: return text
    if old not in method: fail(f"{label}: corrected V5 anchor missing")
    return text[:start] + method.replace(old, new, 1) + text[end:]


def apply_fixed(fast: str, policy: str, profile: str, rings: int) -> tuple[str, str]:
    if profile not in PROFILES: fail(f"unknown profile: {profile}")
    if rings not in RINGS: fail(f"unsupported rings: {rings}")
    fixed_ring = f"    private static final int MAX_CANDIDATE_RINGS = {rings};"
    if fixed_ring not in fast:
        if fast.count(OLD_RING) != 1: fail(f"expected one 64-ring anchor, got {fast.count(OLD_RING)}")
        fast = fast.replace(OLD_RING, fixed_ring, 1)
    if HEIGHTMAP_IMPORT not in fast:
        if DENSITY_IMPORT not in fast: fail("DensityFunction import anchor missing")
        fast = fast.replace(DENSITY_IMPORT, DENSITY_IMPORT + HEIGHTMAP_IMPORT, 1)
    fast = replace(fast, FAST_SIG, OLD_FAST, fast_code(profile, rings), "fast")
    policy = replace(policy, POLICY_SIG, OLD_GENERATION, generation_code(profile), "generation")
    validate(fast, policy, profile, rings)
    return fast, policy


def validate(fast: str, policy: str, profile: str, rings: int) -> None:
    if f"private static final int MAX_CANDIDATE_RINGS = {rings};" not in fast: fail("fixed rings missing")
    expected = "new int[] {" + ", ".join(map(str, PROFILES[profile])) + "}"
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = bounds(text, sig); method = text[start:end]
        if MARKER not in method or expected not in method: fail(f"{label}: fixed policy missing")
        if "Heightmap.Types.OCEAN_FLOOR_WG" not in method: fail(f"{label}: OCEAN_FLOOR_WG missing")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method: fail(f"{label}: forbidden preview leaked")
        if label == "generation":
            a = method.find(MARKER); b = method.find(NON_VILLAGE_ANCHOR, a)
            if b < 0: fail("generation boundary missing")
            if "Heightmap.Types.WORLD_SURFACE_WG" in method[a:b]: fail("fluid-aware heightmap in village block")
    for selector in ("neverfolia.villageSolidProfile", "neverfolia.villageLocateRings", "neverfolia.villageFootprintProfile", "neverfolia.villageDryScoreProfile"):
        if selector in fast or selector in policy: fail(f"QA selector leaked: {selector}")


def self_test() -> None:
    ff = '''import net.minecraft.world.level.levelgen.DensityFunction;\nclass F {\n    private static final int MAX_CANDIDATE_RINGS = 64;\n    private static boolean passesNeverOverworldPolicy(int x) {\n''' + OLD_FAST + '''    }\n}\n'''
    pf = '''class P {\n    static boolean allows(int x) {\n''' + OLD_GENERATION + '''        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return generator.getBaseHeight(0,0,Heightmap.Types.WORLD_SURFACE_WG,heightAccessor,randomState)>0;\n    }\n}\n'''
    for profile in PROFILES:
        for rings in sorted(RINGS):
            f, p = apply_fixed(ff, pf, profile, rings); validate(f, p, profile, rings)
    print("[NeverFolia][R9 village finalizer v15] SELF-TEST OK")
    print("  fixed two-stage profiles: solid5/solid7/solid13; rings: 128/192/256")
    print("  no QA runtime selectors survive")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folia", nargs="?", type=Path)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="solid7")
    ap.add_argument("--rings", choices=sorted(RINGS), type=int, default=128)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test: self_test(); return
    if args.folia is None: ap.error("folia worktree required")
    self_test(); root = args.folia.resolve(); fp = root / FAST_REL; pp = root / POLICY_REL
    for path in (fp, pp):
        if not path.is_file(): fail(f"helper missing: {path}")
    fast, policy = apply_fixed(fp.read_text(encoding="utf-8"), pp.read_text(encoding="utf-8"), args.profile, args.rings)
    fp.write_text(fast, encoding="utf-8"); pp.write_text(policy, encoding="utf-8")
    print(f"[NeverFolia][R9 village finalizer v15] fixed profile={args.profile} rings={args.rings}")


if __name__ == "__main__":
    main()
