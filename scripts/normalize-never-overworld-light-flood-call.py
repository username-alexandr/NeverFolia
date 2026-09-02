#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

TASKS_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/status/ChunkStatusTasks.java")
COMMENT_1 = "// NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency. Every"
COMMENT_2 = "// neighboring chunk that can write FEATURES into this chunk has therefore"
COMMENT_3 = "// finished decoration before the chunk-owned flood mutates final blocks."
CALL_FRAGMENT = "net.minecraft.world.level.chunk.NeverOverworldFlood.apply("


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld flood normalize] {message}")


def normalize(source: str) -> str:
    # Remove the transformer-owned block first. This makes normalization independent
    # of whether the current Folia formatting caused it to land between ')' and '{'
    # or at the beginning of the method body.
    block_pattern = re.compile(
        r"^[ \t]*// NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency\. Every\s*\n"
        r"^[ \t]*// neighboring chunk that can write FEATURES into this chunk has therefore\s*\n"
        r"^[ \t]*// finished decoration before the chunk-owned flood mutates final blocks\.\s*\n"
        r"^[ \t]*net\.minecraft\.world\.level\.chunk\.NeverOverworldFlood\.apply\([^\n;]+\);\s*\n?",
        re.MULTILINE,
    )
    blocks = list(block_pattern.finditer(source))
    if len(blocks) != 1:
        fail(f"expected exactly one transformer-owned flood block, got {len(blocks)}")

    call_match = re.search(
        r"NeverOverworldFlood\.apply\(\s*(\w+)\.level\(\)\s*,\s*(\w+)\s*\)",
        blocks[0].group(0),
    )
    if call_match is None:
        fail("could not recover WorldGenContext/ChunkAccess names from flood call")
    context_name, chunk_name = call_match.groups()

    stripped = source[: blocks[0].start()] + source[blocks[0].end() :]

    method_pattern = re.compile(
        r"(?:public\s+|private\s+|protected\s+)?static\s+CompletableFuture\s*<\s*ChunkAccess\s*>\s+light\s*\(",
        re.MULTILINE,
    )
    method_matches = list(method_pattern.finditer(stripped))
    if len(method_matches) != 1:
        fail(f"expected exactly one ChunkStatusTasks.light(...) method, got {len(method_matches)}")
    method_start = method_matches[0].start()

    next_method = re.search(
        r"^[ \t]*(?:(?:public|private|protected)\s+)?static\s+CompletableFuture\s*<\s*ChunkAccess\s*>",
        stripped[method_matches[0].end() :],
        re.MULTILINE,
    )
    method_end = len(stripped)
    if next_method is not None:
        method_end = method_matches[0].end() + next_method.start()

    method_region = stripped[method_start:method_end]
    statement_pattern = re.compile(
        rf"^(?P<indent>[ \t]*)boolean\s+lighted\s*=\s*isLighted\(\s*{re.escape(chunk_name)}\s*\)\s*;\s*$",
        re.MULTILINE,
    )
    statements = list(statement_pattern.finditer(method_region))
    if len(statements) != 1:
        fail(
            "expected exactly one isLighted(chunk) statement inside LIGHT method "
            f"for chunk parameter {chunk_name!r}, got {len(statements)}"
        )

    statement = statements[0]
    insert_at = method_start + statement.start()
    indent = statement.group("indent")
    call = f"net.minecraft.world.level.chunk.NeverOverworldFlood.apply({context_name}.level(), {chunk_name});"
    block = (
        f"{indent}{COMMENT_1}\n"
        f"{indent}{COMMENT_2}\n"
        f"{indent}{COMMENT_3}\n"
        f"{indent}{call}\n"
    )
    normalized = stripped[:insert_at] + block + stripped[insert_at:]

    # Hard fail if the known malformed shape remains: injected comments must never
    # appear between the parameter-list ')' and the opening method-body brace.
    malformed = re.search(
        r"\)\s*// NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency",
        normalized,
    )
    if malformed is not None:
        fail("flood block still appears between ')' and '{' after normalization")
    if normalized.count(CALL_FRAGMENT) != 1:
        fail("normalized source does not contain exactly one flood call")
    return normalized


def self_test() -> None:
    malformed = '''class ChunkStatusTasks {
   static CompletableFuture<ChunkAccess> light(
      final WorldGenContext context,
      final ChunkStep step,
      final StaticCache2D<GenerationChunkHolder> chunks,
      final ChunkAccess chunk
   )    // NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency. Every
      // neighboring chunk that can write FEATURES into this chunk has therefore
      // finished decoration before the chunk-owned flood mutates final blocks.
      net.minecraft.world.level.chunk.NeverOverworldFlood.apply(context.level(), chunk);
   {
      boolean lighted = isLighted(chunk);
      return context.lightEngine().lightChunk(chunk, lighted);
   }

   static CompletableFuture<ChunkAccess> generateSpawn(
      final WorldGenContext context, final ChunkStep step, final StaticCache2D<GenerationChunkHolder> chunks, final ChunkAccess chunk
   ) {
      return null;
   }
}
'''
    patched = normalize(malformed)
    expected = '''   {
      // NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency. Every
      // neighboring chunk that can write FEATURES into this chunk has therefore
      // finished decoration before the chunk-owned flood mutates final blocks.
      net.minecraft.world.level.chunk.NeverOverworldFlood.apply(context.level(), chunk);
      boolean lighted = isLighted(chunk);'''
    if expected not in patched:
        fail("SELF-TEST: malformed Folia placement was not normalized before isLighted")

    already_inside = '''class ChunkStatusTasks {
   public static CompletableFuture < ChunkAccess > light(
      final WorldGenContext worldContext,
      final ChunkStep step,
      final StaticCache2D<GenerationChunkHolder> chunks,
      final ChunkAccess centerChunk
   ) {
      // NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency. Every
      // neighboring chunk that can write FEATURES into this chunk has therefore
      // finished decoration before the chunk-owned flood mutates final blocks.
      net.minecraft.world.level.chunk.NeverOverworldFlood.apply(worldContext.level(), centerChunk);
      boolean lighted = isLighted(centerChunk);
      return worldContext.lightEngine().lightChunk(centerChunk, lighted);
   }
}
'''
    repatched = normalize(already_inside)
    if repatched.count("NeverOverworldFlood.apply(worldContext.level(), centerChunk);") != 1:
        fail("SELF-TEST: already-correct Folia placement was not preserved canonically")
    if repatched.index("NeverOverworldFlood.apply") > repatched.index("boolean lighted"):
        fail("SELF-TEST: flood call must execute before isLighted")

    print("[NeverFolia][NeverOverworld flood normalize] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize NeverOverworld LIGHT flood call placement")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    tasks = args.folia.resolve() / TASKS_REL
    if not tasks.is_file():
        fail(f"ChunkStatusTasks source not found: {tasks}")
    normalized = normalize(tasks.read_text(encoding="utf-8"))
    tasks.write_text(normalized, encoding="utf-8")
    print("[NeverFolia][NeverOverworld flood normalize] LIGHT call normalized before isLighted")
    print(f"  tasks: {tasks}")


if __name__ == "__main__":
    main()
