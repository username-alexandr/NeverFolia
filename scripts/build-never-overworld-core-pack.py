#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEGACY = ROOT / "build-never-overworld-core-pack-legacy.py"
PROMOTER = ROOT / "promote-never-overworld-native-geology-pack.py"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld native core] {message}")


def output_arg(argv: list[str]) -> Path | None:
    for index, value in enumerate(argv):
        if value == "--output":
            if index + 1 >= len(argv):
                fail("--output requires a path")
            return Path(argv[index + 1])
        if value.startswith("--output="):
            return Path(value.split("=", 1)[1])
    return None


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def self_test() -> None:
    run(str(LEGACY), "--self-test")
    run(str(PROMOTER), "--self-test")
    if output_arg(["--output", "a.zip"]) != Path("a.zip"):
        fail("SELF-TEST: spaced --output parsing failed")
    if output_arg(["--output=b.zip"]) != Path("b.zip"):
        fail("SELF-TEST: equals --output parsing failed")
    print("[NeverFolia][NeverOverworld native core] WRAPPER SELF-TEST OK")


def main() -> None:
    argv = sys.argv[1:]
    if "--self-test" in argv:
        self_test()
        return

    output = output_arg(argv)
    if output is None:
        fail("--output is required for native Core promotion")

    # Build the exact established NR-DEV-1 pack first. Keeping this implementation
    # byte-identical avoids coupling the native-geology promotion to terrain/noise
    # maintenance. The second step atomically removes the obsolete TEST1 count/
    # height deep ores and marks the manifest as neverfolia-native-geology-v2.
    run(str(LEGACY), *argv)
    if not output.is_file():
        fail(f"legacy Core builder did not create output: {output}")
    run(str(PROMOTER), "--input", str(output))

    print("[NeverFolia][NeverOverworld native core] NATIVE-ONLY CORE READY")
    print(f"  output: {output}")
    print("  deep placed material retained: deep_tuff")
    print("  native ores: coal, iron, copper, gold, redstone, lapis, diamond, emerald")


if __name__ == "__main__":
    main()
