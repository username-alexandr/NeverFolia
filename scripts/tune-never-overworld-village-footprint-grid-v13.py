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
MARKER = "// NeverFolia R9-v13 QA: conservative dense village footprint grid."
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"

PROFILES = {
    "grid5": [-96, -48, 0, 48, 96],
    "grid7": [-96, -64, -32, 0, 32, 64, 96],
    "grid13": [-96, -80, -64, -48, -32, -16, 0, 16, 32, 48, 64, 80, 96],
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
    raise SystemExit(f"[NeverFolia][R9 village footprint grid v13] {message}")


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


def java_switch() -> str:
    rows = []
    for name, offsets in PROFILES.items():
        values = ", ".join(map(str, offsets))
        rows.append(f'                case "{name}" -> new int[] {{{values}}};')
    return "\n".join(rows)


def fast_code() -> str:
    return f'''            {MARKER}
            final String footprintProfile = System.getProperty("neverfolia.villageFootprintProfile", "grid5");
            final int[] villageOffsets = switch (footprintProfile) {{
{java_switch()}
                default -> throw new IllegalArgumentException("Unknown NeverFolia village footprint profile: " + footprintProfile);
            }};
            int probes = 0;
            for (final int dx : villageOffsets) {{
                for (final int dz : villageOffsets) {{
                    if (dx == 0 && dz == 0) {{
                        continue;
                    }}
                    ++probes;
                    final int surfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                    if (surfaceY < MIN_DRY_BASE_HEIGHT) {{
                        debugVillage(id, "R9V13_GRID_REJECT", chunkPos, centerSurfaceY,
                            "profile=" + footprintProfile + ",rings=" + MAX_CANDIDATE_RINGS
                                + ",sample=" + dx + "," + dz + ",surface=" + surfaceY + ",probesBeforeReject=" + probes);
                        return false;
                    }}
                }}
            }}
            debugVillage(id, "R9V13_GRID_ACCEPT", chunkPos, centerSurfaceY,
                "profile=" + footprintProfile + ",rings=" + MAX_CANDIDATE_RINGS + ",probes=" + probes);
            return true;
'''


def generation_code() -> str:
    return f'''            {MARKER}
            final String footprintProfile = System.getProperty("neverfolia.villageFootprintProfile", "grid5");
            final int[] villageOffsets = switch (footprintProfile) {{
{java_switch()}
                default -> throw new IllegalArgumentException("Unknown NeverFolia village footprint profile: " + footprintProfile);
            }};
            for (final int dx : villageOffsets) {{
                for (final int dz : villageOffsets) {{
                    if (dx == 0 && dz == 0) {{
                        continue;
                    }}
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


def patch_fast(text: str) -> str:
    if NEW_RING not in text:
        if text.count(OLD_RING) != 1:
            fail(f"expected one 64-ring anchor, got {text.count(OLD_RING)}")
        text = text.replace(OLD_RING, NEW_RING, 1)
    return patch_method(text, FAST_SIG, OLD_FAST, fast_code(), "fast")


def validate(fast: str, policy: str) -> None:
    if NEW_RING not in fast:
        fail("runtime ring selector missing")
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = find_method_end(text, sig)
        method = text[start:end]
        if MARKER not in method:
            fail(f"{label}: V13 marker missing")
        if 'System.getProperty("neverfolia.villageFootprintProfile", "grid5")' not in method:
            fail(f"{label}: footprint selector missing")
        for profile in PROFILES:
            if f'case "{profile}"' not in method:
                fail(f"{label}: profile missing: {profile}")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method:
                fail(f"{label}: watchdog-risk primitive leaked: {forbidden}")
        if label == "fast":
            if "getBaseHeight(" in method:
                fail("fast: getBaseHeight leaked")
            if "R9V13_GRID_REJECT" not in method or "R9V13_GRID_ACCEPT" not in method:
                fail("fast: V13 diagnostics missing")
        else:
            a = method.find(MARKER)
            b = method.find(NON_VILLAGE_ANCHOR, a)
            if b < 0:
                fail("generation: non-village boundary missing")
            if "getBaseHeight(" in method[a:b]:
                fail("generation: getBaseHeight leaked into village grid block")
    for stale in ("neverfolia.villageDryScoreProfile", "R9V11_", "R9V12_"):
        if stale in fast or stale in policy:
            fail(f"stale QA policy leaked into V13: {stale}")


def self_test() -> None:
    expected = {"grid5": 5, "grid7": 7, "grid13": 13}
    for name, size in expected.items():
        offsets = PROFILES[name]
        if len(offsets) != size or len(set(offsets)) != size or 0 not in offsets:
            fail(f"SELF-TEST: invalid {name} offsets")
        if min(offsets) != -96 or max(offsets) != 96:
            fail(f"SELF-TEST: {name} must cover reach96")
    fast_fixture = '''class F {\n    private static final int MAX_CANDIDATE_RINGS = 64;\n    private static boolean passesNeverOverworldPolicy(int x) {\n''' + OLD_FAST + '''    }\n}\n'''
    policy_fixture = '''class P {\n    static boolean allows(int x) {\n''' + OLD_GENERATION + '''        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return generator.getBaseHeight(0,0,type,heightAccessor,randomState)>0;\n    }\n}\n'''
    fast = patch_fast(fast_fixture)
    policy = patch_method(policy_fixture, POLICY_SIG, OLD_GENERATION, generation_code(), "generation")
    validate(fast, policy)
    if patch_fast(fast) != fast:
        fail("SELF-TEST: fast transformer not idempotent")
    if patch_method(policy, POLICY_SIG, OLD_GENERATION, generation_code(), "generation") != policy:
        fail("SELF-TEST: generation transformer not idempotent")
    print("[NeverFolia][R9 village footprint grid v13] SELF-TEST OK")
    print("  profiles: grid5/grid7/grid13, all reach96 and strict all-dry")
    print("  locate/generation share the same selected grid")
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
        if not path.is_file():
            fail(f"helper missing: {path}")
    fast = patch_fast(fp.read_text(encoding="utf-8"))
    policy = patch_method(pp.read_text(encoding="utf-8"), POLICY_SIG, OLD_GENERATION, generation_code(), "generation")
    validate(fast, policy)
    fp.write_text(fast, encoding="utf-8")
    pp.write_text(policy, encoding="utf-8")
    print("[NeverFolia][R9 village footprint grid v13] dense reach96 grid matrix applied")


if __name__ == "__main__":
    main()
