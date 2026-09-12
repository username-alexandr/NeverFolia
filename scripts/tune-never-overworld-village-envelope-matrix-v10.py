#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
MARKER = "// NeverFolia R9-v10 QA: runtime-selectable shared preliminary village envelope."

# Production default remains V5 reach64. QA can select a candidate geometry with
# -Dneverfolia.villageEnvelopeProfile=<name>. The exact same switch is injected
# into locate and generation so prediction/persistence cannot diverge.
PROFILES = {
    "reach64": [
        (dx, dz)
        for dx in (-64, -32, 0, 32, 64)
        for dz in (-64, -32, 0, 32, 64)
        if (dx, dz) != (0, 0)
    ],
    "reach48": [
        (dx, dz)
        for dx in (-48, -24, 0, 24, 48)
        for dz in (-48, -24, 0, 24, 48)
        if (dx, dz) != (0, 0)
    ],
    "cardinal64diag32": [
        (-64, 0), (64, 0), (0, -64), (0, 64),
        (-32, -32), (-32, 32), (32, -32), (32, 32),
    ],
    "cardinal64inner3": [
        (-64, 0), (64, 0), (0, -64), (0, 64),
        (-32, -32), (-32, 0), (-32, 32),
        (0, -32), (0, 32),
        (32, -32), (32, 0), (32, 32),
    ],
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village envelope matrix v10] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method signature not found: {signature.strip()}")
    if text.find(signature, start + 1) >= 0:
        fail(f"method signature occurs more than once: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail("opening brace missing")
    depth = 0
    in_string = in_char = in_line_comment = in_block_comment = escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n": in_line_comment = False
            i += 1; continue
        if in_block_comment:
            if ch == "*" and nxt == "/": in_block_comment = False; i += 2
            else: i += 1
            continue
        if in_string:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': in_string = False
            i += 1; continue
        if in_char:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == "'": in_char = False
            i += 1; continue
        if ch == "/" and nxt == "/": in_line_comment = True; i += 2; continue
        if ch == "/" and nxt == "*": in_block_comment = True; i += 2; continue
        if ch == '"': in_string = True; i += 1; continue
        if ch == "'": in_char = True; i += 1; continue
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == "\n": end += 1
                return start, end
        i += 1
    fail("unterminated method")


def java_points(points: list[tuple[int, int]]) -> str:
    return "{" + ", ".join("{" + f"{x}, {z}" + "}" for x, z in points) + "}"


def switch_java() -> str:
    rows = []
    for name, points in PROFILES.items():
        rows.append(f'                case "{name}" -> new int[][] {java_points(points)};')
    return "\n".join(rows)


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


def fast_replacement() -> str:
    return f'''            {MARKER}
            final String villageProfile = System.getProperty("neverfolia.villageEnvelopeProfile", "reach64");
            final int[][] villageProbes = switch (villageProfile) {{
{switch_java()}
                default -> throw new IllegalArgumentException("Unknown NeverFolia village envelope profile: " + villageProfile);
            }};
            for (final int[] probeOffset : villageProbes) {{
                final int dx = probeOffset[0];
                final int dz = probeOffset[1];
                final int surfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                if (surfaceY < MIN_DRY_BASE_HEIGHT) {{
                    debugVillage(
                        id,
                        "R9V10_ENVELOPE_REJECT",
                        chunkPos,
                        centerSurfaceY,
                        "profile=" + villageProfile + ",sample=" + dx + "," + dz + ",surface=" + surfaceY
                    );
                    return false;
                }}
            }}
            debugVillage(id, "R9V10_ACCEPT", chunkPos, centerSurfaceY, "profile=" + villageProfile + ",probes=" + villageProbes.length);
            return true;
'''


def generation_replacement() -> str:
    return f'''            {MARKER}
            final String villageProfile = System.getProperty("neverfolia.villageEnvelopeProfile", "reach64");
            final int[][] villageProbes = switch (villageProfile) {{
{switch_java()}
                default -> throw new IllegalArgumentException("Unknown NeverFolia village envelope profile: " + villageProfile);
            }};
            for (final int[] probeOffset : villageProbes) {{
                if (preliminarySurfaceY(randomState, centerX + probeOffset[0], centerZ + probeOffset[1]) < MIN_DRY_BASE_HEIGHT) {{
                    return false;
                }}
            }}
            return true;
'''


def patch_method(text: str, signature: str, old: str, replacement: str, label: str) -> str:
    start, end = find_method_end(text, signature)
    method = text[start:end]
    if MARKER in method:
        return text
    if old not in method:
        fail(f"{label}: V5 reach64 loop anchor missing")
    method = method.replace(old, replacement, 1)
    return text[:start] + method + text[end:]


def validate(fast: str, policy: str) -> None:
    for label, text, sig in (("fast", fast, FAST_SIG), ("generation", policy, POLICY_SIG)):
        start, end = find_method_end(text, sig)
        method = text[start:end]
        if MARKER not in method:
            fail(f"{label}: V10 marker missing")
        for profile in PROFILES:
            if f'case "{profile}"' not in method:
                fail(f"{label}: profile missing: {profile}")
        if 'System.getProperty("neverfolia.villageEnvelopeProfile", "reach64")' not in method:
            fail(f"{label}: runtime profile selector missing")
        for forbidden in ("Structure.generate(", "NeverOverworldGeneratedVillageSafety.preview", "getBaseHeight("):
            if forbidden in method:
                fail(f"{label}: watchdog-risk primitive leaked: {forbidden}")
    if "R9V10_ENVELOPE_REJECT" not in fast or "R9V10_ACCEPT" not in fast:
        fail("fast: V10 diagnostics missing")


def self_test() -> None:
    if len(PROFILES["reach48"]) != 24:
        fail("SELF-TEST: reach48 must contain 24 probes")
    if len(PROFILES["cardinal64diag32"]) != 8:
        fail("SELF-TEST: cardinal64diag32 must contain 8 probes")
    if len(PROFILES["cardinal64inner3"]) != 12:
        fail("SELF-TEST: cardinal64inner3 must contain 12 probes")
    if len(PROFILES["reach64"]) != 24:
        fail("SELF-TEST: reach64 baseline must contain 24 probes")
    if (0, 0) in {p for points in PROFILES.values() for p in points}:
        fail("SELF-TEST: centre must not be duplicated in profile probes")

    fast_fixture = '''final class F {\n    private static boolean passesNeverOverworldPolicy(int x) {\n''' + OLD_FAST + '''    }\n}\n'''
    generation_fixture = '''final class P {\n    static boolean allows(int x) {\n''' + OLD_GENERATION + '''    }\n}\n'''
    fast = patch_method(fast_fixture, FAST_SIG, OLD_FAST, fast_replacement(), "fast")
    policy = patch_method(generation_fixture, POLICY_SIG, OLD_GENERATION, generation_replacement(), "generation")
    validate(fast, policy)
    if patch_method(fast, FAST_SIG, OLD_FAST, fast_replacement(), "fast") != fast:
        fail("SELF-TEST: fast transformer not idempotent")
    if patch_method(policy, POLICY_SIG, OLD_GENERATION, generation_replacement(), "generation") != policy:
        fail("SELF-TEST: generation transformer not idempotent")
    print("[NeverFolia][R9 village envelope matrix v10] SELF-TEST OK")
    for name, points in PROFILES.items():
        print(f"  {name}: {len(points)} shared preliminary probes")
    print("  default remains reach64; QA profile selected by JVM property")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None:
        parser.error("folia worktree path is required")

    self_test()
    root = args.folia.resolve()
    fast_path = root / FAST_REL
    policy_path = root / POLICY_REL
    for path in (fast_path, policy_path):
        if not path.is_file():
            fail(f"materialized helper missing: {path}")
    fast = patch_method(fast_path.read_text(encoding="utf-8"), FAST_SIG, OLD_FAST, fast_replacement(), "fast")
    policy = patch_method(policy_path.read_text(encoding="utf-8"), POLICY_SIG, OLD_GENERATION, generation_replacement(), "generation")
    validate(fast, policy)
    fast_path.write_text(fast, encoding="utf-8")
    policy_path.write_text(policy, encoding="utf-8")
    print("[NeverFolia][R9 village envelope matrix v10] shared runtime profile matrix applied")
    print(f"  fast locate: {fast_path}")
    print(f"  generation policy: {policy_path}")


if __name__ == "__main__":
    main()
