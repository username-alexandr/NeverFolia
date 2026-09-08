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
FIELD_R2 = ROOT / "refine-never-overworld-field-r2-pack.py"
HIGHLAND_VILLAGES = ROOT / "adapt-never-overworld-highland-villages.py"
VILLAGE_SPLIT_SETS = ROOT / "split-never-overworld-village-structure-sets.py"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld native core] {message}")


def path_arg(argv: list[str], name: str) -> Path | None:
    prefix = name + "="
    for index, value in enumerate(argv):
        if value == name:
            if index + 1 >= len(argv): fail(f"{name} requires a path")
            return Path(argv[index + 1])
        if value.startswith(prefix): return Path(value.split("=", 1)[1])
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
    run(str(FIELD_R2), "--self-test")
    run(str(HIGHLAND_VILLAGES), "--self-test")
    run(str(VILLAGE_SPLIT_SETS), "--self-test")
    if output_arg(["--output", "a.zip"]) != Path("a.zip"): fail("SELF-TEST: spaced --output parsing failed")
    if output_arg(["--output=b.zip"]) != Path("b.zip"): fail("SELF-TEST: equals --output parsing failed")
    if path_arg(["--server-jar", "server.jar"], "--server-jar") != Path("server.jar"): fail("SELF-TEST: spaced --server-jar parsing failed")
    print("[NeverFolia][NeverOverworld native core] R6 SPLIT-SET WRAPPER SELF-TEST OK")


def main() -> None:
    argv = sys.argv[1:]
    if "--self-test" in argv:
        self_test(); return
    output = output_arg(argv)
    server_jar = path_arg(argv, "--server-jar")
    if output is None: fail("--output is required for native Core promotion")
    if server_jar is None: fail("--server-jar is required for vanilla ore anchor normalization")
    run(str(LEGACY), *argv)
    if not output.is_file(): fail(f"legacy Core builder did not create output: {output}")
    run(str(ORE_ANCHORS), "--input", str(output), "--server-jar", str(server_jar))
    run(str(PROMOTER), "--input", str(output))
    run(str(FIELD_R1), "--input", str(output), "--server-jar", str(server_jar))
    run(str(FIELD_R2), "--input", str(output))
    run(str(HIGHLAND_VILLAGES), "--input", str(output))
    run(str(VILLAGE_SPLIT_SETS), "--input", str(output))
    print("[NeverFolia][NeverOverworld native core] NATIVE-ONLY CORE READY")
    print("  field profile: field-r2 / R6 continuous deep caves")
    print(f"  output: {output}")
    print("  flooded ore sterile band: Y=65..135")
    print("  trial chambers: Y=-320..-96")
    print("  stronghold/end portal dungeon: disabled")
    print("  village policy: strict 9/9 dry highlands, radius=8, independent sets, spacing=34")
    print("  village fallbacks: plains->savanna highlands; taiga->cold snowy highlands")
    print("  native ores: coal, iron, copper, gold, redstone, lapis, diamond, emerald")


if __name__ == "__main__":
    main()
