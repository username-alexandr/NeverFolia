#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "build-never-overworld-native-structures.py"
HARDENER = ROOT / "harden-never-overworld-rock-mass-structures-r8.py"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld structures R8] {message}")


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def self_test() -> None:
    if not BASE.is_file() or not HARDENER.is_file():
        fail("base builder or R8 hardener missing")
    run(str(BASE), "--self-test")
    run(str(HARDENER), "--self-test")
    print("[NeverFolia][NeverOverworld structures R8] COMBINED SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build NeverOverworld native structures with R8 rock-mass envelopes")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None:
        parser.error("--input is required unless --self-test is used")
    if not args.input.is_file():
        fail(f"input pack not found: {args.input}")

    self_test()
    target = args.output or args.input
    command = [str(BASE), "--input", str(args.input)]
    if args.output is not None:
        command += ["--output", str(args.output)]
    run(*command)
    if not target.is_file():
        fail(f"base builder did not produce target: {target}")
    run(str(HARDENER), "--input", str(target))
    print("[NeverFolia][NeverOverworld structures R8] PRODUCTION PACK HARDENED")
    print(f"  output: {target}")


if __name__ == "__main__":
    main()
