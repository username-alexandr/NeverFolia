#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_SIG = "    private static boolean passesNeverOverworldPolicy("
INSERT_ANCHOR = "    private static int sampleRadius(final String id) {"
MARKER = "// NeverFolia R9-v6 diagnostics: expose predicted-surface biome key on biome reject."

OLD = '''        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {
            debugVillage(id, "R9V5_BIOME_REJECT", chunkPos, centerSurfaceY, "shared-preliminary-envelope");
            return false;
        }
'''
NEW = '''        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {
            debugVillage(
                id,
                "R9V6_BIOME_REJECT",
                chunkPos,
                centerSurfaceY,
                "biome=" + biomeIdAtY(generator, state, chunkPos, centerSurfaceY)
            );
            return false;
        }
'''

HELPER = '''    // NeverFolia R9-v6 diagnostics: expose predicted-surface biome key on biome reject.
    private static String biomeIdAtY(
        final ChunkGenerator generator,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final int biomeY
    ) {
        final Holder<Biome> biome = generator.getBiomeSource().getNoiseBiome(
            QuartPos.fromBlock(chunkPos.getMiddleBlockX()),
            QuartPos.fromBlock(biomeY),
            QuartPos.fromBlock(chunkPos.getMiddleBlockZ()),
            state.randomState().sampler()
        );
        return biome.unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse("<direct>");
    }

'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village biome v6] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        fail(f"method signature not found: {signature.strip()}")
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
                return start, i + 1
        i += 1
    fail("unterminated policy method")


def patch(text: str) -> str:
    if MARKER in text:
        validate(text)
        return text
    start, end = find_method_end(text, POLICY_SIG)
    method = text[start:end]
    if OLD not in method:
        fail("R9-v5 BIOME_REJECT anchor missing")
    method = method.replace(OLD, NEW, 1)
    text = text[:start] + method + text[end:]
    if INSERT_ANCHOR not in text:
        fail("sampleRadius insertion anchor missing")
    text = text.replace(INSERT_ANCHOR, HELPER + INSERT_ANCHOR, 1)
    validate(text)
    return text


def validate(text: str) -> None:
    required = (
        MARKER,
        '"R9V6_BIOME_REJECT"',
        '"biome=" + biomeIdAtY(',
        "biome.unwrapKey()",
        ".map(key -> key.identifier().toString())",
        'final int villageReach = 64;',
        'final int[] villageOffsets = {-64, -32, 0, 32, 64};',
    )
    missing = [needle for needle in required if needle not in text]
    if missing:
        fail(f"missing markers: {missing}")
    if '"R9V5_BIOME_REJECT"' in text:
        fail("stale R9V5 biome reject diagnostic survived")


def self_test() -> None:
    fixture = '''final class X {
    private static boolean passesNeverOverworldPolicy(
        final ChunkGenerator generator, final ServerLevel level, final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos, final Holder<Structure> structureHolder, final String id
    ) {
        final int centerSurfaceY = 140;
        if (!passesBiomeAtY(generator, state, chunkPos, structureHolder, centerSurfaceY)) {
            debugVillage(id, "R9V5_BIOME_REJECT", chunkPos, centerSurfaceY, "shared-preliminary-envelope");
            return false;
        }
        final int villageReach = 64;
        final int[] villageOffsets = {-64, -32, 0, 32, 64};
        return true;
    }
    private static int sampleRadius(final String id) { return 1; }
}
'''
    patched = patch(fixture)
    if patch(patched) != patched:
        fail("SELF-TEST: transformer is not idempotent")
    print("[NeverFolia][R9 village biome v6] SELF-TEST OK")


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
    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"helper not found: {helper}")
    helper.write_text(patch(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][R9 village biome v6] biome-key diagnostics applied")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
