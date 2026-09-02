#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

TASKS_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/status/ChunkStatusTasks.java")
CALL_PREFIX = "net.minecraft.world.level.chunk.NeverOverworldOreGeology.apply("


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld geology stage] {message}")


def matching(source: str, start: int, opening: str, closing: str) -> int:
    if start < 0 or start >= len(source) or source[start] != opening:
        fail(f"expected {opening!r} at index {start}")
    depth = 0
    in_string = False
    in_char = False
    escaped = False
    i = start
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
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
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            in_char = True
            i += 1
            continue
        if ch == "/" and nxt == "/":
            newline = source.find("\n", i + 2)
            i = len(source) if newline < 0 else newline + 1
            continue
        if ch == "/" and nxt == "*":
            end = source.find("*/", i + 2)
            if end < 0:
                fail("unterminated Java block comment")
            i = end + 2
            continue
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    fail(f"unterminated delimiter {opening}{closing}")


def method_bounds(source: str, method_name: str) -> tuple[int, int, int, str, str]:
    method = re.search(
        rf"(?:public\s+|private\s+|protected\s+)?static\s+CompletableFuture\s*<\s*ChunkAccess\s*>\s+{re.escape(method_name)}\s*\(",
        source,
        re.MULTILINE,
    )
    if method is None:
        fail(f"ChunkStatusTasks.{method_name}(...) not found")
    params_open = source.find("(", method.start(), method.end())
    params_close = matching(source, params_open, "(", ")")
    params = source[params_open + 1 : params_close]
    context_match = re.search(r"\bWorldGenContext\s+(\w+)\b", params)
    chunk_match = re.search(r"\bChunkAccess\s+(\w+)\b", params)
    if context_match is None or chunk_match is None:
        fail(f"could not resolve context/chunk parameters in {method_name}")
    cursor = params_close + 1
    while cursor < len(source) and source[cursor].isspace():
        cursor += 1
    if cursor >= len(source) or source[cursor] != "{":
        fail(f"{method_name} body opening brace not found")
    body_close = matching(source, cursor, "{", "}")
    return cursor, body_close, method.start(), context_match.group(1), chunk_match.group(1)


def remove_carver_call(source: str) -> str:
    body_open, body_close, _method_start, _context, _chunk = method_bounds(source, "generateCarvers")
    body = source[body_open + 1 : body_close]
    positions = [m.start() for m in re.finditer(re.escape(CALL_PREFIX), body)]
    if len(positions) != 1:
        fail(f"expected exactly one geology call in generateCarvers, got {len(positions)}")
    call_abs = body_open + 1 + positions[0]
    call_open = source.find("(", call_abs, body_close)
    call_close = matching(source, call_open, "(", ")")
    semi = call_close + 1
    while semi < body_close and source[semi].isspace() and source[semi] != "\n":
        semi += 1
    if semi >= body_close or source[semi] != ";":
        fail("geology call in generateCarvers has no terminating semicolon")
    line_start = source.rfind("\n", 0, call_abs) + 1
    line_end = source.find("\n", semi + 1)
    if line_end < 0:
        line_end = semi + 1
    else:
        line_end += 1
    return source[:line_start] + source[line_end:]


def inject_surface_call(source: str) -> str:
    body_open, body_close, _method_start, context, chunk = method_bounds(source, "generateSurface")
    body = source[body_open + 1 : body_close]
    calls = list(re.finditer(r"\bbuildSurface\s*\(", body))
    if len(calls) != 1:
        fail(f"expected exactly one buildSurface(...) call in generateSurface, got {len(calls)}")
    call_abs = body_open + 1 + calls[0].start()
    call_open = source.find("(", call_abs, body_close)
    call_close = matching(source, call_open, "(", ")")
    semi = call_close + 1
    while semi < body_close and source[semi].isspace():
        semi += 1
    if semi >= body_close or source[semi] != ";":
        fail("buildSurface(...) is not followed by a semicolon")
    line_start = source.rfind("\n", 0, call_abs) + 1
    indent = re.match(r"[ \t]*", source[line_start:call_abs]).group(0)
    injection = (
        "\n"
        f"{indent}// NeverFolia NR-DEV-1: geology must complete at SURFACE, before CARVERS.\n"
        f"{indent}// FEATURES only require neighboring CARVERS, so writing geology inside CARVERS\n"
        f"{indent}// races with cross-chunk vanilla features such as Deep Dark sculk propagation.\n"
        f"{indent}{CALL_PREFIX}{context}.level(), {chunk});"
    )
    return source[:semi + 1] + injection + source[semi + 1:]


def relocate(source: str) -> str:
    if source.count(CALL_PREFIX) != 1:
        fail(f"expected one existing geology call before relocation, got {source.count(CALL_PREFIX)}")
    without = remove_carver_call(source)
    if CALL_PREFIX in without:
        fail("geology call remained after removing CARVERS hook")
    patched = inject_surface_call(without)
    if patched.count(CALL_PREFIX) != 1:
        fail("relocated geology call must exist exactly once")
    surface_open, surface_close, *_ = method_bounds(patched, "generateSurface")
    carver_open, carver_close, *_ = method_bounds(patched, "generateCarvers")
    if CALL_PREFIX not in patched[surface_open:surface_close]:
        fail("geology call is not inside generateSurface")
    if CALL_PREFIX in patched[carver_open:carver_close]:
        fail("geology call still exists inside generateCarvers")
    return patched


def self_test() -> None:
    fixture = '''class ChunkStatusTasks {
   static CompletableFuture<ChunkAccess> generateSurface(WorldGenContext worldContext, ChunkStep step, StaticCache2D<GenerationChunkHolder> chunks, ChunkAccess centerChunk) {
      WorldGenRegion region = new WorldGenRegion(worldContext.level(), chunks, step, centerChunk);
      worldContext.generator().buildSurface(region, worldContext.level().structureManager(), worldContext.level().getChunkSource().randomState(), centerChunk);
      return CompletableFuture.completedFuture(centerChunk);
   }
   static CompletableFuture<ChunkAccess> generateCarvers(WorldGenContext worldContext, ChunkStep step, StaticCache2D<GenerationChunkHolder> chunks, ChunkAccess centerChunk) {
      WorldGenRegion region = new WorldGenRegion(worldContext.level(), chunks, step, centerChunk);
      worldContext.generator().applyCarvers(region, worldContext.level().getSeed(), worldContext.level().getChunkSource().randomState(), worldContext.level().getBiomeManager(), worldContext.level().structureManager().forWorldGenRegion(region), centerChunk);
      // NeverFolia: deterministic NR-DEV-1 geology runs after caves are cut.
      // It writes only the owning chunk and never observes mutable neighbors.
      net.minecraft.world.level.chunk.NeverOverworldOreGeology.apply(worldContext.level(), centerChunk);
      return CompletableFuture.completedFuture(centerChunk);
   }
}
'''
    patched = relocate(fixture)
    surface_open, surface_close, *_ = method_bounds(patched, "generateSurface")
    carver_open, carver_close, *_ = method_bounds(patched, "generateCarvers")
    if patched[surface_open:surface_close].index("buildSurface") > patched[surface_open:surface_close].index(CALL_PREFIX):
        fail("SELF-TEST: geology must run after buildSurface")
    if CALL_PREFIX in patched[carver_open:carver_close]:
        fail("SELF-TEST: CARVERS call survived")
    print("[NeverFolia][NeverOverworld geology stage] SURFACE-BEFORE-CARVERS SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Relocate native NR-DEV-1 ore geology from CARVERS to SURFACE")
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
    tasks.write_text(relocate(tasks.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld geology stage] relocated native geology to SURFACE")
    print(f"  tasks: {tasks}")


if __name__ == "__main__":
    main()
