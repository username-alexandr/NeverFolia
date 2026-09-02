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
                fail("unterminated Java block comment")
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


def normalize(source: str) -> str:
    method_pattern = re.compile(
        r"(?:public\s+|private\s+|protected\s+)?static\s+CompletableFuture\s*<\s*ChunkAccess\s*>\s+light\s*\(",
        re.MULTILINE,
    )
    methods = list(method_pattern.finditer(source))
    if len(methods) != 1:
        fail(f"expected exactly one ChunkStatusTasks.light(...) method, got {len(methods)}")

    method = methods[0]
    method_start = method.start()
    params_open = source.find("(", method.start(), method.end())
    params_close = matching_delimiter(source, params_open, "(", ")")
    params = source[params_open + 1 : params_close]

    context_match = re.search(r"\bWorldGenContext\s+(\w+)\b", params)
    chunk_match = re.search(r"\bChunkAccess\s+(\w+)\b", params)
    if context_match is None or chunk_match is None:
        fail("could not resolve WorldGenContext/ChunkAccess parameter names")
    context_name = context_match.group(1)
    chunk_name = chunk_match.group(1)

    lighted_pattern = re.compile(
        rf"(?P<indent>^[ \t]*)boolean\s+lighted\s*=\s*isLighted\(\s*{re.escape(chunk_name)}\s*\)\s*;",
        re.MULTILINE,
    )
    lighted_matches = list(lighted_pattern.finditer(source, params_close + 1))
    if not lighted_matches:
        fail(f"isLighted({chunk_name}) statement not found after LIGHT parameters")
    lighted = lighted_matches[0]

    # The authoritative method brace is the final opening brace before the known
    # first LIGHT statement. This survives both normal Mojmap formatting and the
    # malformed historical transformer output that left comments/calls/extra ')'
    # between the parameter list and the real body brace.
    body_open = source.rfind("{", params_close + 1, lighted.start())
    if body_open < 0:
        fail("LIGHT body opening brace not found before isLighted")
    body_close = matching_delimiter(source, body_open, "{", "}")
    if not (body_open < lighted.start() < body_close):
        fail("isLighted statement is not inside resolved LIGHT body")

    body = source[body_open + 1 : body_close]
    cleaned_lines: list[str] = []
    for line in body.splitlines(keepends=True):
        if COMMENT_1 in line or COMMENT_2 in line or COMMENT_3 in line or CALL_FRAGMENT in line:
            continue
        cleaned_lines.append(line)
    cleaned_body = "".join(cleaned_lines)

    body_lighted = list(lighted_pattern.finditer(cleaned_body))
    if len(body_lighted) != 1:
        fail(f"expected exactly one isLighted({chunk_name}) statement in cleaned LIGHT body, got {len(body_lighted)}")
    statement = body_lighted[0]
    indent = statement.group("indent")
    call = f"net.minecraft.world.level.chunk.NeverOverworldFlood.apply({context_name}.level(), {chunk_name});"
    block = (
        f"{indent}{COMMENT_1}\n"
        f"{indent}{COMMENT_2}\n"
        f"{indent}{COMMENT_3}\n"
        f"{indent}{call}\n"
    )
    rebuilt_body = cleaned_body[: statement.start()] + block + cleaned_body[statement.start() :]

    # Canonicalize everything between the parameter-list close and body open.
    # In particular this removes the dangling second ')' that caused heavy #95 to
    # fail compilation at ChunkStatusTasks.java:167.
    method_header = source[method_start : params_close + 1]
    rebuilt_method = method_header + " {" + rebuilt_body + "}"
    normalized = source[:method_start] + rebuilt_method + source[body_close + 1 :]

    if normalized.count(CALL_FRAGMENT) != 1:
        fail("normalized source does not contain exactly one flood call")

    # Structural validation of the rebuilt method.
    methods_after = list(method_pattern.finditer(normalized))
    if len(methods_after) != 1:
        fail("normalized source lost the unique LIGHT method")
    m = methods_after[0]
    p_open = normalized.find("(", m.start(), m.end())
    p_close = matching_delimiter(normalized, p_open, "(", ")")
    cursor = p_close + 1
    while cursor < len(normalized) and normalized[cursor].isspace():
        cursor += 1
    if cursor >= len(normalized) or normalized[cursor] != "{":
        fail("canonical LIGHT header is not followed by a body brace")
    b_close = matching_delimiter(normalized, cursor, "{", "}")
    call_pos = normalized.find(CALL_FRAGMENT, cursor, b_close)
    lighted_pos = normalized.find(f"boolean lighted = isLighted({chunk_name})", cursor, b_close)
    if call_pos < 0 or lighted_pos < 0 or call_pos > lighted_pos:
        fail("flood call is not inside LIGHT body before isLighted")
    return normalized


def self_test() -> None:
    fixtures = (
        '''class ChunkStatusTasks {
   static CompletableFuture<ChunkAccess> light(
      final WorldGenContext context, final ChunkStep step, final StaticCache2D<GenerationChunkHolder> chunks, final ChunkAccess chunk
   ) {
      // NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency. Every
      // neighboring chunk that can write FEATURES into this chunk has therefore
      // finished decoration before the chunk-owned flood mutates final blocks.
      net.minecraft.world.level.chunk.NeverOverworldFlood.apply(context.level(), chunk);
      boolean lighted = isLighted(chunk);
      return context.lightEngine().lightChunk(chunk, lighted);
   }
}
''',
        '''class ChunkStatusTasks {
   static CompletableFuture<ChunkAccess> light(
      final WorldGenContext context,
      final ChunkStep step,
      final StaticCache2D<GenerationChunkHolder> chunks,
      final ChunkAccess chunk
   ) // NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency. Every
     // neighboring chunk that can write FEATURES into this chunk has therefore
     // finished decoration before the chunk-owned flood mutates final blocks.
     net.minecraft.world.level.chunk.NeverOverworldFlood.apply(context.level(), chunk);
   ) {
      boolean lighted = isLighted(chunk);
      return context.lightEngine().lightChunk(chunk, lighted);
   }
}
''',
        '''class ChunkStatusTasks {
   public static CompletableFuture < ChunkAccess > light(
      final WorldGenContext worldContext,
      final ChunkStep step,
      final StaticCache2D<GenerationChunkHolder> chunks,
      final ChunkAccess centerChunk
   )
   {
      boolean lighted = isLighted(centerChunk);
      return worldContext.lightEngine().lightChunk(centerChunk, lighted);
   }
}
''',
    )
    expected_calls = (
        "NeverOverworldFlood.apply(context.level(), chunk);",
        "NeverOverworldFlood.apply(context.level(), chunk);",
        "NeverOverworldFlood.apply(worldContext.level(), centerChunk);",
    )
    for fixture, expected in zip(fixtures, expected_calls):
        patched = normalize(fixture)
        if patched.count(expected) != 1:
            fail(f"SELF-TEST: expected canonical call missing: {expected}")
        # normalize() already performs structural Java validation: the parameter
        # list must be followed by the authoritative body brace and the flood call
        # must be inside that body before isLighted. Do not use a text heuristic
        # such as '\n   ) {' here; that is a valid multiline method header.

    print("[NeverFolia][NeverOverworld flood normalize] CANONICAL LIGHT HEADER SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonicalize NeverOverworld LIGHT flood hook")
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
    tasks.write_text(normalize(tasks.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld flood normalize] LIGHT method header/body canonicalized")
    print(f"  tasks: {tasks}")


if __name__ == "__main__":
    main()
