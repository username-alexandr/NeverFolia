#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path(
    "folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java"
)
POLICY_SIG = "    private static boolean passesNeverOverworldPolicy("
MARKER = "// NeverFolia R9-v2: village locate matches generation prefilter; exact bbox remains generation-only."
CENTER_PROBE = "final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);"
ENVELOPE_PROBE = "preliminarySurfaceY(state, centerX + dx, centerZ + dz)"

NEW_POLICY = r'''    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder,
        final String id
    ) {
        if (SWAMP_HUT.equals(id)) {
            return passesBiomeAtY(generator, state, chunkPos, structureHolder, FLOOD_LEVEL + 1);
        }
        if (!DRY_LAND_ONLY.contains(id)) {
            return false;
        }

        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);
        if (centerSurfaceY < MIN_DRY_BASE_HEIGHT) {
            debugVillage(id, "R9V2_CENTER_DRY_REJECT", chunkPos, centerSurfaceY, "min=" + MIN_DRY_BASE_HEIGHT);
            return false;
        }
        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {
            debugVillage(id, "R9V2_BIOME_REJECT", chunkPos, centerSurfaceY, "generation-prefilter");
            return false;
        }

        if (id.startsWith("minecraft:village_")) {
            // NeverFolia R9-v2: village locate matches generation prefilter; exact bbox remains generation-only.
            // Real village generation uses the same dry-centre + biome eligibility before
            // Structure#generate. The generated StructureStart bbox is then checked exactly
            // before persistence. /locate must not add an older 7/9 radius-48 envelope,
            // because that rejects candidates which real generation is allowed to evaluate.
            // A dedicated runtime gate verifies every predicted direct village by generating
            // its predicted chunk and requiring the corresponding persisted StructureStart.
            debugVillage(id, "R9V2_ACCEPT_PREFILTER", chunkPos, centerSurfaceY, "center+biome;exact-bbox-on-generation");
            return true;
        }

        // Non-village dry-land structures retain the established bounded 3x3 policy.
        final int radius = sampleRadius(id);
        int drySamples = 1;
        final int[] offsets = {-radius, 0, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                if (dx == 0 && dz == 0) {
                    continue;
                }
                if (preliminarySurfaceY(state, centerX + dx, centerZ + dz) >= MIN_DRY_BASE_HEIGHT) {
                    ++drySamples;
                }
            }
        }
        return drySamples >= minDrySamples(id);
    }
'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village locate v2] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method signature not found: {signature.strip()}")
    if text.find(signature, start + 1) >= 0:
        fail(f"method signature occurs more than once: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail("policy opening brace not found")
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
    fail("unterminated policy method")


def patch(text: str) -> str:
    if MARKER in text:
        validate(text)
        return text
    start, end = find_method_end(text, POLICY_SIG)
    out = text[:start] + NEW_POLICY + text[end:]
    validate(out)
    return out


def validate(text: str) -> None:
    start, end = find_method_end(text, POLICY_SIG)
    policy = text[start:end]
    required = (
        MARKER,
        'id.startsWith("minecraft:village_")',
        'debugVillage(id, "R9V2_ACCEPT_PREFILTER"',
        "final int[] offsets = {-radius, 0, radius};",
        "drySamples >= minDrySamples(id)",
    )
    missing = [needle for needle in required if needle not in policy]
    if missing:
        fail(f"patched policy missing markers: {missing}")
    forbidden = (
        "NeverOverworldGeneratedVillageSafety.preview",
        ".preview(",
        "Structure.generate(",
        ".generate(",
        "getBaseHeight(",
        "inspectBoundingBox(",
        "R9_ENVELOPE_REJECT",
    )
    leaked = [needle for needle in forbidden if needle in policy]
    if leaked:
        fail(f"unbounded/legacy village locate path survived: {leaked}")
    if policy.count(CENTER_PROBE) != 1:
        fail(f"expected exactly one center preliminary-surface probe, got {policy.count(CENTER_PROBE)}")
    if policy.count(ENVELOPE_PROBE) != 1:
        fail(f"expected only non-village bounded envelope probe, got {policy.count(ENVELOPE_PROBE)}")
    village_start = policy.find('if (id.startsWith("minecraft:village_"))')
    non_village_envelope = policy.find("final int radius = sampleRadius(id);", village_start)
    village_block = policy[village_start:non_village_envelope]
    if "drySamples" in village_block or ENVELOPE_PROBE in village_block:
        fail("village branch still contains legacy dry-envelope rejection")
    if "return true;" not in village_block:
        fail("village generation-prefilter acceptance missing")


def self_test() -> None:
    fixture = r'''final class NeverOverworldVanillaFastLocate {
    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator,
        final ServerLevel level,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> structureHolder,
        final String id
    ) {
        if (id.startsWith("minecraft:village_")) {
            final NeverOverworldGeneratedVillageSafety.Preview preview =
                NeverOverworldGeneratedVillageSafety.preview(generator, level, state, chunkPos, structureHolder);
            return preview.dry();
        }
        return true;
    }
}
'''
    out = patch(fixture)
    start, end = find_method_end(out, POLICY_SIG)
    policy = out[start:end]
    if "NeverOverworldGeneratedVillageSafety.preview" in policy:
        fail("SELF-TEST: Jigsaw preview call survived")
    if out.count(MARKER) != 1:
        fail("SELF-TEST: R9-v2 marker count mismatch")
    if policy.count(CENTER_PROBE) != 1 or policy.count(ENVELOPE_PROBE) != 1:
        fail("SELF-TEST: probe topology drifted")
    if "R9V2_ACCEPT_PREFILTER" not in policy:
        fail("SELF-TEST: village generation-prefilter acceptance missing")
    again = patch(out)
    if again != out:
        fail("SELF-TEST: transformer is not idempotent")
    print("[NeverFolia][R9 village locate v2] SELF-TEST OK")
    print("  village locate: dry-center + biome only, matching generation prefilter")
    print("  village locate: no Jigsaw preview / no bbox scan / no legacy 7-of-9 envelope")
    print("  real generation: exact generated bbox safety remains authoritative")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None: parser.error("folia worktree path is required")
    self_test()
    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file(): fail(f"NeverOverworldVanillaFastLocate helper missing: {helper}")
    helper.write_text(patch(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][R9 village locate v2] generation-aligned village locate applied")
    print(f"  helper: {helper}")

if __name__ == "__main__": main()
