#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEGACY = ROOT / "build-never-overworld-core-pack-legacy.py"
ORE_ANCHORS = ROOT / "normalize-never-overworld-vanilla-ore-anchors.py"
PROMOTER = ROOT / "promote-never-overworld-native-geology-pack.py"
FIELD_R1 = ROOT / "refine-never-overworld-field-r1-pack.py"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld native core] {message}")


def path_arg(argv: list[str], name: str) -> Path | None:
    prefix = name + "="
    for index, value in enumerate(argv):
        if value == name:
            if index + 1 >= len(argv):
                fail(f"{name} requires a path")
            return Path(argv[index + 1])
        if value.startswith(prefix):
            return Path(value.split("=", 1)[1])
    return None


def output_arg(argv: list[str]) -> Path | None:
    return path_arg(argv, "--output")


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def self_test() -> None:
    run(str(LEGACY), "--self-test")
    run(str(ORE_ANCHORS), "--self-test")
    run(str(PROMOTER), "--self-test")
    run(str(FIELD_R1), "--self-test")
    if output_arg(["--output", "a.zip"]) != Path("a.zip"):
        fail("SELF-TEST: spaced --output parsing failed")
    if output_arg(["--output=b.zip"]) != Path("b.zip"):
        fail("SELF-TEST: equals --output parsing failed")
    if path_arg(["--server-jar", "server.jar"], "--server-jar") != Path("server.jar"):
        fail("SELF-TEST: spaced --server-jar parsing failed")
    print("[NeverFolia][NeverOverworld native core] WRAPPER SELF-TEST OK")


def main() -> None:
    argv = sys.argv[1:]
    if "--self-test" in argv:
        self_test()
        return

    output = output_arg(argv)
    server_jar = path_arg(argv, "--server-jar")
    if output is None:
        fail("--output is required for native Core promotion")
    if server_jar is None:
        fail("--server-jar is required for vanilla ore anchor normalization")

    # Build the established NR-DEV-1 pack first. Then restore vanilla 26.2
    # resource-ore anchors, remove obsolete transitional deep ores and finally
    # apply the field-r1 corrections proven necessary by the first real server QA.
    run(str(LEGACY), *argv)
    if not output.is_file():
        fail(f"legacy Core builder did not create output: {output}")
    run(str(ORE_ANCHORS), "--input", str(output), "--server-jar", str(server_jar))
    run(str(PROMOTER), "--input", str(output))
    run(str(FIELD_R1), "--input", str(output), "--server-jar", str(server_jar))

    print("[NeverFolia][NeverOverworld native core] NATIVE-ONLY FIELD-R1 CORE READY")
    print(f"  output: {output}")
    print("  vanilla resource ore anchors: original 26.2 absolute Y semantics outside flooded sterile band")
    print("  flooded ore sterile band: Y=65..135")
    print("  trial chambers: Y=-320..-96")
    print("  stronghold/end portal dungeon: disabled")
    print("  deep chasm density: field-r1 shortened profile")
    print("  native ores: coal, iron, copper, gold, redstone, lapis, diamond, emerald")


if __name__ == "__main__":
    main()
