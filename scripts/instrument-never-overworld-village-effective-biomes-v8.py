#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_SIG = "    private static boolean passesNeverOverworldPolicy("
INSERT_ANCHOR = "    private static int sampleRadius(final String id) {"
MARKER = "// NeverFolia R9-v8 diagnostics: expose effective village biome HolderSet."

BIOME_GATE = '''        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {\n            debugVillage(id, "R9V5_BIOME_REJECT", chunkPos, centerSurfaceY, "shared-preliminary-envelope");\n            return false;\n        }\n'''

BIOME_GATE_V8 = '''        if (id.startsWith("minecraft:village_")) {\n            debugVillage(\n                id,\n                "R9V8_EFFECTIVE_BIOMES",\n                chunkPos,\n                centerSurfaceY,\n                "candidate=" + biomeIdAtYV8(generator, state, chunkPos, centerSurfaceY)\n                    + ",allowed=" + allowedBiomeIdsV8(structureHolder)\n            );\n        }\n        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {\n            debugVillage(\n                id,\n                "R9V8_BIOME_REJECT",\n                chunkPos,\n                centerSurfaceY,\n                "candidate=" + biomeIdAtYV8(generator, state, chunkPos, centerSurfaceY)\n                    + ",allowed=" + allowedBiomeIdsV8(structureHolder)\n            );\n            return false;\n        }\n'''

HELPERS = '''    // NeverFolia R9-v8 diagnostics: expose effective village biome HolderSet.\n    private static String biomeIdAtYV8(\n        final ChunkGenerator generator,\n        final ChunkGeneratorStructureState state,\n        final ChunkPos chunkPos,\n        final int biomeY\n    ) {\n        final Holder<Biome> biome = generator.getBiomeSource().getNoiseBiome(\n            QuartPos.fromBlock(chunkPos.getMiddleBlockX()),\n            QuartPos.fromBlock(biomeY),\n            QuartPos.fromBlock(chunkPos.getMiddleBlockZ()),\n            state.randomState().sampler()\n        );\n        return biome.unwrapKey()\n            .map(key -> key.identifier().toString())\n            .orElse("<direct>");\n    }\n\n    private static String allowedBiomeIdsV8(final Holder<Structure> structureHolder) {\n        final StringBuilder result = new StringBuilder("[");\n        boolean first = true;\n        for (final Holder<Biome> allowed : structureHolder.value().biomes()) {\n            if (!first) {\n                result.append(',');\n            }\n            first = false;\n            result.append(\n                allowed.unwrapKey()\n                    .map(key -> key.identifier().toString())\n                    .orElse("<direct>")\n            );\n        }\n        return result.append(']').toString();\n    }\n\n'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village effective biomes v8] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method signature not found: {signature.strip()}")
    if text.find(signature, start + 1) >= 0:
        fail(f"method signature occurs more than once: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0:
        fail("opening brace not found")
    depth = 0
    in_string = in_char = in_line_comment = in_block_comment = escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            in_char = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    fail("unterminated policy method")


def patch(text: str) -> str:
    if MARKER in text:
        validate(text)
        return text

    start, end = find_method_end(text, POLICY_SIG)
    method = text[start:end]
    if BIOME_GATE not in method:
        fail("R9-v5 biome gate anchor missing")
    if 'final int villageReach = 64;' not in method or 'final int[] villageOffsets = {-64, -32, 0, 32, 64};' not in method:
        fail("R9-v5 reach64 contract missing before V8 instrumentation")
    method = method.replace(BIOME_GATE, BIOME_GATE_V8, 1)
    text = text[:start] + method + text[end:]

    if INSERT_ANCHOR not in text:
        fail("sampleRadius insertion anchor missing")
    text = text.replace(INSERT_ANCHOR, HELPERS + INSERT_ANCHOR, 1)
    validate(text)
    return text


def validate(text: str) -> None:
    required = (
        MARKER,
        '"R9V8_EFFECTIVE_BIOMES"',
        '"R9V8_BIOME_REJECT"',
        'for (final Holder<Biome> allowed : structureHolder.value().biomes())',
        'allowed.unwrapKey()',
        'final int villageReach = 64;',
        'final int[] villageOffsets = {-64, -32, 0, 32, 64};',
    )
    missing = [needle for needle in required if needle not in text]
    if missing:
        fail(f"missing markers: {missing}")
    if '"R9V5_BIOME_REJECT"' in text:
        fail("stale R9V5 biome-reject branch survived V8 instrumentation")
    for forbidden in (
        "NeverOverworldGeneratedVillageSafety.preview",
        "Structure.generate(",
        "getBaseHeight(",
    ):
        start, end = find_method_end(text, POLICY_SIG)
        if forbidden in text[start:end]:
            fail(f"watchdog-risk primitive leaked into V8 village locate: {forbidden}")


def self_test() -> None:
    fixture = '''final class X {\n    private static boolean passesNeverOverworldPolicy(\n        final ChunkGenerator generator, final ServerLevel level, final ChunkGeneratorStructureState state,\n        final ChunkPos chunkPos, final Holder<Structure> structureHolder, final String id\n    ) {\n        final int centerSurfaceY = 140;\n        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {\n            debugVillage(id, "R9V5_BIOME_REJECT", chunkPos, centerSurfaceY, "shared-preliminary-envelope");\n            return false;\n        }\n        if (id.startsWith("minecraft:village_")) {\n            final int villageReach = 64;\n            final int[] villageOffsets = {-64, -32, 0, 32, 64};\n            return villageReach == 64;\n        }\n        return true;\n    }\n    private static int sampleRadius(final String id) { return 1; }\n}\n'''
    patched = patch(fixture)
    if patch(patched) != patched:
        fail("SELF-TEST: transformer is not idempotent")
    print("[NeverFolia][R9 village effective biomes v8] SELF-TEST OK")
    print("  diagnostics: candidate biome + effective structure HolderSet")
    print("  village geometry: unchanged reach64 5x5")
    print("  locate: no Jigsaw preview / getBaseHeight")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required")

    self_test()
    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"helper not found: {helper}")
    helper.write_text(patch(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][R9 village effective biomes v8] runtime HolderSet diagnostics applied")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
