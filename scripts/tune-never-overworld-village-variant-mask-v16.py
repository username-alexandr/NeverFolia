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
MARKER = "// NeverFolia R9-v16 QA: variant-specific preliminary score plus exact solid mask."
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"
HEIGHTMAP_IMPORT = "import net.minecraft.world.level.levelgen.Heightmap;\n"
DENSITY_IMPORT = "import net.minecraft.world.level.levelgen.DensityFunction;\n"

PREFILTER = [
    (-64, 0), (64, 0), (0, -64), (0, 64),
    (-32, -32), (-32, 0), (-32, 32),
    (0, -32), (0, 32),
    (32, -32), (32, 0), (32, 32),
]

# Data-driven conservative masks based on persisted R9 Jigsaw footprints seen in
# the fixed release seed. They are still only predictors: the V14 full generated
# bbox OCEAN_FLOOR gate is authoritative and must remain enabled.
MASKS: dict[str, dict[str, tuple[list[int], list[int]]]] = {
    "fit": {
        "plains": ([-72, -48, -24, 0, 24, 48, 72], [-72, -48, -24, 0, 24, 48, 72]),
        "desert": ([-40, -20, 0, 20, 40], [-56, -28, 0, 28, 56]),
        "savanna": ([-56, -28, 0, 28, 56, 72], [-48, -24, 0, 24, 48, 64]),
        "snowy": ([-72, -48, -24, 0, 24, 48, 72], [-72, -48, -24, 0, 24, 48, 64]),
        "taiga": ([-56, -28, 0, 28, 56, 64], [-32, -16, 0, 16, 32, 48, 56]),
    },
    "margin8": {
        "plains": ([-80, -56, -32, 0, 32, 56, 80], [-80, -56, -32, 0, 32, 56, 80]),
        "desert": ([-48, -24, 0, 24, 48], [-64, -32, 0, 32, 64]),
        "savanna": ([-64, -32, 0, 32, 64, 80], [-56, -28, 0, 28, 56, 72]),
        "snowy": ([-80, -56, -32, 0, 32, 56, 80], [-80, -56, -32, 0, 32, 56, 72]),
        "taiga": ([-64, -32, 0, 32, 64, 72], [-40, -20, 0, 20, 40, 56, 64]),
    },
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
    raise SystemExit(f"[NeverFolia][R9 village variant mask v16] {message}")


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


def arr(values: list[int]) -> str:
    return "new int[] {" + ", ".join(map(str, values)) + "}"


def mask_select_java(profile: str) -> str:
    data = MASKS[profile]
    rows: list[str] = []
    order = ["plains", "desert", "savanna", "snowy", "taiga"]
    for i, variant in enumerate(order):
        xs, zs = data[variant]
        kw = "if" if i == 0 else "else if"
        rows.append(
            f'            {kw} ("minecraft:village_{variant}".equals(id)) {{\n'
            f'                exactXs = {arr(xs)};\n'
            f'                exactZs = {arr(zs)};\n'
            f'            }}'
        )
    rows.append('            else {\n                return false;\n            }')
    return "\n".join(rows)


def profile_switch_block() -> str:
    rows = []
    for profile in MASKS:
        rows.append(
            f'            if ("{profile}".equals(maskProfile)) {{\n'
            f'{mask_select_java(profile)}\n'
            f'            }}'
        )
    # Instead of nested duplicated declarations, generated code below uses one profile branch at a time.
    return "\n".join(rows)


def exact_assignment_java() -> str:
    blocks: list[str] = []
    for pi, profile in enumerate(MASKS):
        prefix = "if" if pi == 0 else "else if"
        body = mask_select_java(profile).replace("            ", "                ")
        blocks.append(
            f'            {prefix} ("{profile}".equals(maskProfile)) {{\n'
            f'{body}\n'
            f'            }}'
        )
    blocks.append('            else {\n                throw new IllegalArgumentException("Unknown NeverFolia village variant mask profile: " + maskProfile);\n            }')
    return "\n".join(blocks)


def common_code(exact_context: str, diagnostics: bool) -> str:
    # exact_context is either fast or generation and controls API arguments.
    prelim_state = "state" if exact_context == "fast" else "randomState"
    getbase_tail = "level, state.randomState()" if exact_context == "fast" else "heightAccessor, randomState"
    diag_prelim = '''
                debugVillage(id, "R9V16_PRELIM_REJECT", chunkPos, centerSurfaceY,
                    "profile=" + maskProfile + ",dry=" + dryPreliminary + "/" + preliminaryProbes.length
                        + ",required=" + minPreliminaryDry + ",rings=" + MAX_CANDIDATE_RINGS);''' if diagnostics else ""
    diag_solid = '''
                    debugVillage(id, "R9V16_SOLID_REJECT", chunkPos, centerSurfaceY,
                        "profile=" + maskProfile + ",sample=" + dx + "," + dz + ",solidBase=" + solidBase
                            + ",rings=" + MAX_CANDIDATE_RINGS + ",exactProbes=" + exactProbes);''' if diagnostics else ""
    diag_accept = '''
            debugVillage(id, "R9V16_ACCEPT", chunkPos, centerSurfaceY,
                "profile=" + maskProfile + ",dry=" + dryPreliminary + "/" + preliminaryProbes.length
                    + ",rings=" + MAX_CANDIDATE_RINGS + ",exactProbes=" + exactProbes);''' if diagnostics else ""
    return f'''            {MARKER}
            final String maskProfile = System.getProperty("neverfolia.villageVariantMaskProfile", "fit");
            final int[][] preliminaryProbes = new int[][] {points_java(PREFILTER)};
            int dryPreliminary = 0;
            for (final int[] probe : preliminaryProbes) {{
                if (preliminarySurfaceY({prelim_state}, centerX + probe[0], centerZ + probe[1]) >= MIN_DRY_BASE_HEIGHT) {{
                    ++dryPreliminary;
                }}
            }}
            final int minPreliminaryDry = ("minecraft:village_snowy".equals(id) || "minecraft:village_taiga".equals(id)) ? 10 : 12;
            if (dryPreliminary < minPreliminaryDry) {{{diag_prelim}
                return false;
            }}

            int[] exactXs;
            int[] exactZs;
{exact_assignment_java()}
            int exactProbes = 0;
            for (final int dx : exactXs) {{
                for (final int dz : exactZs) {{
                    ++exactProbes;
                    final int solidBase = generator.getBaseHeight(
                        centerX + dx,
                        centerZ + dz,
                        Heightmap.Types.OCEAN_FLOOR_WG,
                        {getbase_tail}
                    );
                    if (solidBase < MIN_DRY_BASE_HEIGHT) {{{diag_solid}
                        return false;
                    }}
                }}
            }}{diag_accept}
            return true;
'''


def fast_code() -> str:
    return common_code("fast", True)


def generation_code() -> str:
    return common_code("generation", False)


def replace_method(text: str, sig: str, old: str, new: str, label: str) -> str:
    start, end = method_bounds(text, sig)
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
            fail(f"{label}: V16 marker missing")
        if 'System.getProperty("neverfolia.villageVariantMaskProfile", "fit")' not in method:
            fail(f"{label}: mask selector missing")
        if "minPreliminaryDry" not in method or "? 10 : 12" not in method:
            fail(f"{label}: variant preliminary threshold missing")
        if "Heightmap.Types.OCEAN_FLOOR_WG" not in method:
            fail(f"{label}: exact solid heightmap missing")
        for profile in MASKS:
            if f'"{profile}".equals(maskProfile)' not in method:
                fail(f"{label}: profile branch missing {profile}")
        for variant in ("plains", "desert", "savanna", "snowy", "taiga"):
            if f'"minecraft:village_{variant}".equals(id)' not in method:
                fail(f"{label}: variant branch missing {variant}")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method:
                fail(f"{label}: forbidden generated preview leaked: {forbidden}")
        if label == "fast":
            for diag in ("R9V16_PRELIM_REJECT", "R9V16_SOLID_REJECT", "R9V16_ACCEPT"):
                if diag not in method:
                    fail(f"fast: diagnostic missing {diag}")
        else:
            a = method.find(MARKER)
            b = method.find(NON_VILLAGE_ANCHOR, a)
            if b < 0:
                fail("generation: non-village boundary missing")
            if "Heightmap.Types.WORLD_SURFACE_WG" in method[a:b]:
                fail("generation village block uses fluid-aware WORLD_SURFACE_WG")
    if HEIGHTMAP_IMPORT not in fast:
        fail("fast Heightmap import missing")
    for stale in ("neverfolia.villageSolidProfile", "neverfolia.villageFootprintProfile", "neverfolia.villageDryScoreProfile"):
        if stale in fast or stale in policy:
            fail(f"stale selector leaked into V16: {stale}")


def self_test() -> None:
    if len(PREFILTER) != 12 or len(set(PREFILTER)) != 12:
        fail("SELF-TEST: preliminary probe set drifted")
    for profile, variants in MASKS.items():
        if set(variants) != {"plains", "desert", "savanna", "snowy", "taiga"}:
            fail(f"SELF-TEST: variant coverage drifted: {profile}")
        for variant, (xs, zs) in variants.items():
            if 0 not in xs or 0 not in zs or len(xs) != len(set(xs)) or len(zs) != len(set(zs)):
                fail(f"SELF-TEST: invalid mask {profile}/{variant}")
    fast_fixture = '''import net.minecraft.world.level.levelgen.DensityFunction;\nclass F {\n    private static final int MAX_CANDIDATE_RINGS = 64;\n    private static boolean passesNeverOverworldPolicy(int x) {\n''' + OLD_FAST + '''    }\n}\n'''
    policy_fixture = '''class P {\n    static boolean allows(int x) {\n''' + OLD_GENERATION + '''        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return generator.getBaseHeight(0,0,Heightmap.Types.WORLD_SURFACE_WG,heightAccessor,randomState)>0;\n    }\n}\n'''
    fast = patch_fast(fast_fixture)
    policy = patch_policy(policy_fixture)
    validate(fast, policy)
    if patch_fast(fast) != fast:
        fail("SELF-TEST: fast transformer not idempotent")
    if patch_policy(policy) != policy:
        fail("SELF-TEST: generation transformer not idempotent")
    print("[NeverFolia][R9 village variant mask v16] SELF-TEST OK")
    print("  preliminary thresholds: normal=12/12, snowy+taiga=10/12")
    print("  exact profiles: fit / margin8; five variant-specific OCEAN_FLOOR masks")
    print("  no Structure.generate/Jigsaw preview in fast locate")


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
    print("[NeverFolia][R9 village variant mask v16] predictor applied")


if __name__ == "__main__":
    main()
