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


def matching_delimiter(source: str, start: int, opening: str, closing: str) -> int:
    if start < 0 or start >= len(source) or source[start] != opening:
        fail(f"delimiter parser expected {opening!r} at index {start}")
    depth = 0
    in_string = False
    in_char = False
    escaped = False
    index = start
    while index < len(source):
        ch = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            index += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            index += 1
            continue
        if ch == '"':
            in_string = True
            index += 1
            continue
        if ch == "'":
            in_char = True
            index += 1
            continue
        if ch == "/" and nxt == "/":
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline + 1
            continue
        if ch == "/" and nxt == "*":
            end = source.find("*/", index + 2)
            if end < 0:
                fail("unterminated Java block comment while validating LIGHT method")
            index = end + 2
            continue
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    fail(f"unterminated Java delimiter {opening}{closing}")


def method_body_bounds(source: str, method_start: int) -> tuple[int, int]:
    params_open = source.find("(", method_start)
    if params_open < 0:
        fail("LIGHT parameter list opening '(' not found")
    params_close = matching_delimiter(source, params_open, "(", ")")
    cursor = params_close + 1
    while cursor < len(source) and source[cursor].isspace():
        cursor += 1
    if cursor >= len(source) or source[cursor] != "{":
        context = source[max(method_start, params_close - 80) : min(len(source), params_close + 220)].replace("\n", "\\n")
        fail(f"LIGHT body does not begin with '{{' after parameter list; context={context}")
    body_open = cursor
    body_close = matching_delimiter(source, body_open, "{", "}")
    return body_open, body_close


def normalize(source: str) -> str:
    marker_positions = [match.start() for match in re.finditer(re.escape(COMMENT_1), source)]
    if len(marker_positions) != 1:
        fail(f"expected exactly one transformer-owned flood marker, got {len(marker_positions)}")
    marker_start = marker_positions[0]

    call_match = re.search(
        r"net\.minecraft\.world\.level\.chunk\.NeverOverworldFlood\.apply\(\s*(\w+)\.level\(\)\s*,\s*(\w+)\s*\)\s*;",
        source[marker_start:],
    )
    if call_match is None:
        fail("could not locate/recover transformer-owned flood call")
    context_name, chunk_name = call_match.groups()
    call_start = marker_start + call_match.start()
    call_end = marker_start + call_match.end()

    owned_region = source[marker_start:call_start]
    if COMMENT_2 not in owned_region or COMMENT_3 not in owned_region:
        fail("transformer-owned flood comments are incomplete before the call")

    # Remove the transformer-owned block. If COMMENT_1 was emitted inline after
    # the parameter-list ')', preserve that prefix and restore a newline.
    call_line_end = source.find("\n", call_end)
    block_end = len(source) if call_line_end < 0 else call_line_end + 1
    marker_line_start = source.rfind("\n", 0, marker_start) + 1
    prefix = source[marker_line_start:marker_start]
    if prefix.strip():
        removal_start = marker_start
        replacement = "\n"
    else:
        removal_start = marker_line_start
        replacement = ""
    stripped = source[:removal_start] + replacement + source[block_end:]

    method_pattern = re.compile(
        r"(?:public\s+|private\s+|protected\s+)?static\s+CompletableFuture\s*<\s*ChunkAccess\s*>\s+light\s*\(",
        re.MULTILINE,
    )
    method_matches = list(method_pattern.finditer(stripped))
    if len(method_matches) != 1:
        fail(f"expected exactly one ChunkStatusTasks.light(...) method, got {len(method_matches)}")
    method_start = method_matches[0].start()
    body_open, body_close = method_body_bounds(stripped, method_start)
    method_region = stripped[body_open + 1 : body_close]

    statement_pattern = re.compile(
        rf"^(?P<indent>[ \t]*)boolean\s+lighted\s*=\s*isLighted\(\s*{re.escape(chunk_name)}\s*\)\s*;\s*$",
        re.MULTILINE,
    )
    statements = list(statement_pattern.finditer(method_region))
    if len(statements) != 1:
        fail(
            "expected exactly one isLighted(chunk) statement inside LIGHT body "
            f"for chunk parameter {chunk_name!r}, got {len(statements)}"
        )

    statement = statements[0]
    insert_at = body_open + 1 + statement.start()
    indent = statement.group("indent")
    call = f"net.minecraft.world.level.chunk.NeverOverworldFlood.apply({context_name}.level(), {chunk_name});"
    block = (
        f"{indent}{COMMENT_1}\n"
        f"{indent}{COMMENT_2}\n"
        f"{indent}{COMMENT_3}\n"
        f"{indent}{call}\n"
    )
    normalized = stripped[:insert_at] + block + stripped[insert_at:]

    if normalized.count(CALL_FRAGMENT) != 1:
        fail("normalized source does not contain exactly one flood call")

    # Validate semantically against the actual LIGHT method body. This replaces
    # the former `)\\s*//` heuristic, which could span newlines and reject valid
    # Folia formatting even after the call had been moved inside the body.
    normalized_method = list(method_pattern.finditer(normalized))
    if len(normalized_method) != 1:
        fail("normalized source lost the unique LIGHT method")
    normalized_body_open, normalized_body_close = method_body_bounds(normalized, normalized_method[0].start())
    call_pos = normalized.find(CALL_FRAGMENT)
    lighted_match = re.search(
        rf"boolean\s+lighted\s*=\s*isLighted\(\s*{re.escape(chunk_name)}\s*\)",
        normalized[normalized_body_open + 1 : normalized_body_close],
    )
    if lighted_match is None:
        fail("normalized LIGHT body no longer contains isLighted(chunk)")
    lighted_pos = normalized_body_open + 1 + lighted_match.start()
    if not (normalized_body_open < call_pos < lighted_pos < normalized_body_close):
        context = normalized[max(normalized_body_open - 80, 0) : min(normalized_body_close + 80, len(normalized))].replace("\n", "\\n")
        fail(f"flood call is not inside LIGHT body before isLighted; context={context}")
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
    expected = '''   )    
   {
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

    # Reproduce the real Folia style where the opening brace is on the next line;
    # semantic body validation, not a cross-line regex, is authoritative.
    next_line_brace = '''class ChunkStatusTasks {
   static CompletableFuture<ChunkAccess> light(
      final WorldGenContext ctx, final ChunkStep step, final StaticCache2D<GenerationChunkHolder> chunks, final ChunkAccess target
   )
   // NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency. Every
   // neighboring chunk that can write FEATURES into this chunk has therefore
   // finished decoration before the chunk-owned flood mutates final blocks.
   net.minecraft.world.level.chunk.NeverOverworldFlood.apply(ctx.level(), target);
   {
      boolean lighted = isLighted(target);
      return ctx.lightEngine().lightChunk(target, lighted);
   }
}
'''
    next_line_patched = normalize(next_line_brace)
    if "{\n      // NeverFolia: LIGHT" not in next_line_patched:
        fail("SELF-TEST: next-line Folia body brace was not normalized")

    print("[NeverFolia][NeverOverworld flood normalize] SEMANTIC BODY SELF-TEST OK")


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
    print("[NeverFolia][NeverOverworld flood normalize] LIGHT call normalized inside method body before isLighted")
    print(f"  tasks: {tasks}")


if __name__ == "__main__":
    main()
