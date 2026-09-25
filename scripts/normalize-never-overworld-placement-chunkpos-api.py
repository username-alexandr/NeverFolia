#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path(
    "folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.java"
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld placement API] {message}")


def normalize(source: str) -> str:
    if "chunkPos.x()" in source or "chunkPos.z()" in source:
        if "chunkPos.x" in source.replace("chunkPos.x()", "") or "chunkPos.z" in source.replace("chunkPos.z()", ""):
            fail("mixed raw/accessor ChunkPos coordinate API")
        return source

    x_count = source.count("chunkPos.x")
    z_count = source.count("chunkPos.z")
    if x_count != 1 or z_count != 1:
        fail(f"expected exactly one raw chunkPos.x and chunkPos.z use, got x={x_count}, z={z_count}")

    patched = source.replace("chunkPos.x", "chunkPos.x()", 1).replace("chunkPos.z", "chunkPos.z()", 1)
    if "chunkPos.x()" not in patched or "chunkPos.z()" not in patched:
        fail("ChunkPos accessor normalization failed")
    if "chunkPos.x *" in patched or "chunkPos.z *" in patched:
        fail("raw ChunkPos field access survived")
    return patched


def self_test() -> None:
    fixture = '''final long hash = mix64(
        seed
            ^ ((long)chunkPos.x * 0x9E3779B97F4A7C15L)
            ^ ((long)chunkPos.z * 0xC2B2AE3D27D4EB4FL)
    );
'''
    patched = normalize(fixture)
    if "chunkPos.x()" not in patched or "chunkPos.z()" not in patched:
        fail("SELF-TEST: accessor form missing")
    if "chunkPos.x *" in patched or "chunkPos.z *" in patched:
        fail("SELF-TEST: raw field access survived")
    if normalize(patched) != patched:
        fail("SELF-TEST: normalizer is not idempotent")
    print("[NeverFolia][NeverOverworld placement API] CHUNKPOS 26.2 SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize NR-DEV-1 placement helper to Minecraft 26.2 ChunkPos accessors")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"placement helper not found: {helper}")
    helper.write_text(normalize(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld placement API] ChunkPos x()/z() accessors normalized")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
