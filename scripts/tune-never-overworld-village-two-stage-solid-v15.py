#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
OLD_RING = "    private static final int MAX_CANDIDATE_RINGS = 64;"
NEW_RING = '    private static final int MAX_CANDIDATE_RINGS = Integer.getInteger("neverfolia.villageLocateRings", 128);'
MARKER = "// NeverFolia R9-v15 QA: cheap preliminary prefilter plus bounded exact solid-terrain grid."
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"
HEIGHTMAP_IMPORT = "import net.minecraft.world.level.levelgen.Heightmap;\n"
DENSITY_IMPORT = "import net.minecraft.world.level.levelgen.DensityFunction;\n"

PREFILTER = [
    (-64, 0), (64, 0), (0, -64), (0, 64),
    (-32, -32), (-32, 0), (-32, 32),
    (0, -32), (0, 32),
    (32, -32), (32, 0), (32, 32),
]
SOLID_PROFILES = {
    "solid5": [-96, -48, 0, 48, 96],
    "solid7": [-96, -64, -32, 0, 32, 64, 96],
    "solid13": [-96, -80, -64, -48, -32, -16, 0, 16, 32, 48, 64, 80, 96],
}

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
    raise SystemExit(f"[NeverFolia][R9 village two-stage solid v15] {message}")


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


def points_java(points: list[tuple[int, int]]) -> str:
    return "{" + ", ".join("{" + f"{x}, {z}" + "}" for x, z in points) + "}"


def profile_switch() -> str:
    rows = []
    for name, offsets in SOLID_PROFILES.items():
        rows.append(f'                case "{name}" -> new int[] {{{", ".join(map(str, offsets))}}};')
    return "\n".join(rows)


def fast_code() -> str:
    return f'''            {MARKER}
            // Stage 1 is the cheap V12-style density-router filter. Most flooded
            // candidates die here without any getBaseHeight call.
            final int[][] preliminaryProbes = new int[][] {points_java(PREFILTER)};
            for (final int[] probe : preliminaryProbes) {{
                final int surfaceY = preliminarySurfaceY(state, centerX + probe[0], centerZ + probe[1]);
                if (surfaceY < MIN_DRY_BASE_HEIGHT) {{
                    debugVillage(id, "R9V15_PRELIM_REJECT", chunkPos, centerSurfaceY,
                        "rings=" + MAX_CANDIDATE_RINGS + ",sample=" + probe[0] + "," + probe[1] + ",surface=" + surfaceY);
                    return false;
                }}
            }}

            // Stage 2 is exact terrain height, but only for preliminary survivors.
            // OCEAN_FLOOR_WG intentionally measures motion-blocking terrain rather
            // than WORLD_SURFACE_WG, whose surface may itself be fluid.
            final String solidProfile = System.getProperty("neverfolia.villageSolidProfile", "solid7");
            final int[] solidOffsets = switch (solidProfile) {{
{profile_switch()}
                default -> throw new IllegalArgumentException("Unknown NeverFolia village solid profile: " + solidProfile);
            }};
            int exactProbes = 0;
            for (final int dx : solidOffsets) {{
                for (final int dz : solidOffsets) {{
                    ++exactProbes;
                    final int solidBase = generator.getBaseHeight(
                        centerX + dx,
                        centerZ + dz,
                        Heightmap.Types.OCEAN_FLOOR_WG,
                        level,
                        state.randomState()
                    );
                    if (solidBase < MIN_DRY_BASE_HEIGHT) {{
                        debugVillage(id, "R9V15_SOLID_REJECT", chunkPos, centerSurfaceY,
                            "profile=" + solidProfile + ",rings=" + MAX_CANDIDATE_RINGS
                                + ",sample=" + dx + "," + dz + ",solidBase=" + solidBase + ",exactProbes=" + exactProbes);
                        return false;
                    }}
                }}
            }}
            debugVillage(id, "R9V15_ACCEPT", chunkPos, centerSurfaceY,
                "profile=" + solidProfile + ",rings=" + MAX_CANDIDATE_RINGS + ",exactProbes=" + exactProbes);
            return true;
'''


def generation_code() -> str:
    return f'''            {MARKER}
            final int[][] preliminaryProbes = new int[][] {points_java(PREFILTER)};
            for (final int[] probe : preliminaryProbes) {{
                if (preliminarySurfaceY(randomState, centerX + probe[0], centerZ + probe[1]) < MIN_DRY_BASE_HEIGHT) {{
                    return false;
                }}
            }}
            final String solidProfile = System.getProperty("neverfolia.villageSolidProfile", "solid7");
            final int[] solidOffsets = switch (solidProfile) {{
{profile_switch()}
                default -> throw new IllegalArgumentException("Unknown NeverFolia village solid profile: " + solidProfile);
            }};
            for (final int dx : solidOffsets) {{
                for (final int dz : solidOffsets) {{
                    final int solidBase = generator.getBaseHeight(
                        centerX + dx,
                        centerZ + dz,
                        Heightmap.Types.OCEAN_FLOOR_WG,
                        heightAccessor,
                        randomState
                    );
                    if (solidBase < MIN_DRY_BASE_HEIGHT) {{
                        return false;
                    }}
                }}
            }}
            return true;
'''


def replace_method(text: str, signature: str, old: str, new: str, label: str) -> str:
    start, end = method_bounds(text, signature)
    method = text[start:end]
    if MARKER in method:
        return text
    if old not in method:
        fail(f"{label}: corrected V5 anchor missing")
    return text[:start] + method.replace(old, new, 1) + text[end:]


def patch_fast(text: str) -> str:
    if NEW_RING not in text:
        if text.count(OLD_RING) != 1:
            fail(f"expected one 64-ring anchor, got {text.count(OLD_RING)}")
        text = text.replace(OLD_RING, NEW_RING, 1)
    if HEIGHTMAP_IMPORT not in text:
        if DENSITY_IMPORT not in text:
            fail("DensityFunction import anchor missing")
        text = text.replace(DENSITY_IMPORT, DENSITY_IMPORT + HEIGHTMAP_IMPORT, 1)
    return replace_method(text, FAST_SIG, OLD_FAST, fast_code(), "fast")


def patch_policy(text: str) -> str:
    return replace_method(text, POLICY_SIG, OLD_GENERATION, generation_code(), "generation")


def validate(fast: str, policy: str) -> None:
    if NEW_RING not in fast:
        fail("runtime ring selector missing")
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = method_bounds(text, sig)
        method = text[start:end]
        if MARKER not in method:
            fail(f"{label}: V15 marker missing")
        if "Heightmap.Types.OCEAN_FLOOR_WG" not in method:
            fail(f"{label}: exact solid heightmap missing")
        if 'System.getProperty("neverfolia.villageSolidProfile", "solid7")' not in method:
            fail(f"{label}: solid profile selector missing")
        for name in SOLID_PROFILES:
            if f'case "{name}"' not in method:
                fail(f"{label}: missing profile {name}")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method:
                fail(f"{label}: forbidden generation preview leaked: {forbidden}")
        if label == "fast":
            if "R9V15_PRELIM_REJECT" not in method or "R9V15_SOLID_REJECT" not in method or "R9V15_ACCEPT" not in method:
                fail("fast: diagnostics missing")
            # getBaseHeight is intentional only after the preliminary stage.
            prelim = method.find("R9V15_PRELIM_REJECT")
            exact = method.find("generator.getBaseHeight(")
            if exact < prelim:
                fail("fast: exact height call occurs before cheap preliminary gate")
        else:
            a = method.find(MARKER)
            b = method.find(NON_VILLAGE_ANCHOR, a)
            if b < 0:
                fail("generation: non-village boundary missing")
            if "Heightmap.Types.WORLD_SURFACE_WG" in method[a:b]:
                fail("generation village block uses fluid-aware WORLD_SURFACE_WG")
    if HEIGHTMAP_IMPORT not in fast:
        fail("fast Heightmap import missing")
    for stale in ("neverfolia.villageFootprintProfile", "neverfolia.villageDryScoreProfile"):
        if stale in fast or stale in policy:
            fail(f"stale selector leaked into V15: {stale}")


def self_test() -> None:
    if len(PREFILTER) != 12 or len(set(PREFILTER)) != 12:
        fail("SELF-TEST: preliminary probe set drifted")
    for name, offsets in SOLID_PROFILES.items():
        if min(offsets) != -96 or max(offsets) != 96 or 0 not in offsets:
            fail(f"SELF-TEST: invalid reach96 profile: {name}")
    fast_fixture = '''import net.minecraft.world.level.levelgen.DensityFunction;\nclass F {\n    private static final int MAX_CANDIDATE_RINGS = 64;\n    private static boolean passesNeverOverworldPolicy(int x) {\n''' + OLD_FAST + '''    }\n}\n'''
    policy_fixture = '''class P {\n    static boolean allows(int x) {\n''' + OLD_GENERATION + '''        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return generator.getBaseHeight(0,0,Heightmap.Types.WORLD_SURFACE_WG,heightAccessor,randomState)>0;\n    }\n}\n'''
    fast = patch_fast(fast_fixture)
    policy = patch_policy(policy_fixture)
    validate(fast, policy)
    if patch_fast(fast) != fast:
        fail("SELF-TEST: fast transformer not idempotent")
    if patch_policy(policy) != policy:
        fail("SELF-TEST: generation transformer not idempotent")
    print("[NeverFolia][R9 village two-stage solid v15] SELF-TEST OK")
    print("  stage1: 12 cheap preliminary probes")
    print("  stage2: bounded OCEAN_FLOOR_WG exact grid only for survivors")
    print("  profiles: solid5/solid7/solid13; no Structure.generate preview")


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
    root = args.folia.resolve(); fp = root / FAST_REL; pp = root / POLICY_REL
    for path in (fp, pp):
        if not path.is_file(): fail(f"helper missing: {path}")
    fast = patch_fast(fp.read_text(encoding="utf-8"))
    policy = patch_policy(pp.read_text(encoding="utf-8"))
    validate(fast, policy)
    fp.write_text(fast, encoding="utf-8"); pp.write_text(policy, encoding="utf-8")
    print("[NeverFolia][R9 village two-stage solid v15] predictor applied")


if __name__ == "__main__":
    main()
