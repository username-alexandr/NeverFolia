#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FLOOD = ROOT / "harden-never-overworld-flood-r9.py"
ORE = ROOT / "tune-never-overworld-ore-field-r9.py"
UPPER_FINALIZER = ROOT / "finalize-never-overworld-upper-ores-r9.py"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 field overrides] {message}")


def run(script: Path, *args: str) -> None:
    if not script.is_file():
        fail(f"transformer missing: {script}")
    subprocess.run([sys.executable, str(script), *args], check=True)


def self_test() -> None:
    run(FLOOD, "--self-test")
    run(ORE, "--self-test")
    run(UPPER_FINALIZER, "--self-test")
    print("[NeverFolia][R9 field overrides] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required")
    self_test()
    folia = str(args.folia.resolve())
    run(FLOOD, folia)
    run(ORE, folia)
    # This wrapper is invoked at the end of flood-debug instrumentation. Apply
    # the authoritative LIGHT cleanup only after the final R9 flood/ore
    # overrides, so no later field transformer can erase it.
    run(UPPER_FINALIZER, folia)
    print("[NeverFolia][R9 field overrides] final R9 stabilization + upper ore LIGHT cleanup applied")


if __name__ == "__main__":
    main()
