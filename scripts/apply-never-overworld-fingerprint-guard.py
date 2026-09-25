#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

SERVER_REL = Path("folia-server/src/minecraft/java/net/minecraft/server/MinecraftServer.java")
SOURCE_HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/server/NeverNetherFingerprintGuard.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/server/NeverOverworldFingerprintGuard.java")


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld fingerprint guard] {message}")


def transform_helper(source: str) -> str:
    required = (
        "final class NeverNetherFingerprintGuard",
        'private static final String WORLDGEN_ID = "NN-DEV-1";',
        'private static final String ROOT_FINGERPRINT = "nevernether-worldgen-fingerprint.json";',
        'private static final String LOCK_FILE = ".neverfolia-nevernether-worldgen.lock";',
    )
    for needle in required:
        if needle not in source:
            fail(f"source NeverNether helper missing expected marker: {needle}")

    transformed = source
    transformed = transformed.replace("NeverNetherFingerprintGuard", "NeverOverworldFingerprintGuard")
    transformed = transformed.replace("NeverNether", "NeverOverworld")
    transformed = transformed.replace("nevernether", "neveroverworld")
    transformed = transformed.replace("NN-DEV-1", "NR-DEV-1")

    for required_output in (
        "final class NeverOverworldFingerprintGuard",
        'private static final String WORLDGEN_ID = "NR-DEV-1";',
        'private static final String ROOT_FINGERPRINT = "neveroverworld-worldgen-fingerprint.json";',
        'private static final String RESOURCE_FINGERPRINT = "data/neverfolia/neveroverworld/worldgen_fingerprint.json";',
        'private static final String LOCK_FILE = ".neverfolia-neveroverworld-worldgen.lock";',
        "NeverOverworld worldgen fingerprint mismatch",
    ):
        if required_output not in transformed:
            fail(f"transformed helper missing {required_output!r}")
    return transformed


def patch_server(source: str) -> str:
    if "NeverOverworldFingerprintGuard.verify" in source:
        fail("MinecraftServer is already patched for NeverOverworld")
    pattern = re.compile(
        r"(?P<indent>^[ \t]*)NeverNetherFingerprintGuard\.verify\((?P<args>.*?)\);",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        fail(f"expected exactly one NeverNether guard call, got {len(matches)}")
    match = matches[0]
    indent = match.group("indent")
    args = match.group("args")
    addition = f"\n{indent}NeverOverworldFingerprintGuard.verify({args});"
    return source[: match.end()] + addition + source[match.end() :]


def self_test() -> None:
    helper = r'''package net.minecraft.server;
final class NeverNetherFingerprintGuard {
    private static final String WORLDGEN_ID = "NN-DEV-1";
    private static final String ROOT_FINGERPRINT = "nevernether-worldgen-fingerprint.json";
    private static final String RESOURCE_FINGERPRINT = "data/neverfolia/nevernether/worldgen_fingerprint.json";
    private static final String LOCK_FILE = ".neverfolia-nevernether-worldgen.lock";
    // NeverNether worldgen fingerprint mismatch
}
'''
    transformed = transform_helper(helper)
    if "NeverOverworldFingerprintGuard" not in transformed or "NR-DEV-1" not in transformed:
        fail("SELF-TEST: helper transformation failed")

    server = '''class MinecraftServer {
    void x(Object storage) {
        NeverNetherFingerprintGuard.verify(
            storage.getLevelPath(LevelResource.ROOT),
            storage.getLevelPath(LevelResource.DATAPACK_DIR));
    }
}
'''
    patched = patch_server(server)
    if patched.count("NeverOverworldFingerprintGuard.verify") != 1:
        fail("SELF-TEST: NeverOverworld guard call was not injected exactly once")
    print("[NeverFolia][NeverOverworld fingerprint guard] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply independent NeverOverworld startup fingerprint guard")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    folia = args.folia.resolve()
    server = folia / SERVER_REL
    source_helper = folia / SOURCE_HELPER_REL
    helper = folia / HELPER_REL
    if not server.is_file():
        fail(f"MinecraftServer source not found: {server}")
    if not source_helper.is_file():
        fail(f"NeverNether fingerprint helper must be applied first: {source_helper}")

    helper.write_text(transform_helper(source_helper.read_text(encoding="utf-8")), encoding="utf-8")
    server.write_text(patch_server(server.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld fingerprint guard] applied")
    print(f"  server: {server}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
