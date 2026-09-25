#!/usr/bin/env python3
"""NeverOverworld FIELD-R23 unified fixpack.

Extends FIELD-R22 with strict physical ocean connectivity for cave flooding.
R23 removes the R22 near-ocean proximity fallback while preserving prospective
Y128 ocean seeds, Moonrise neighbour-cache seam reconciliation, R19 external
structures and all prior worldgen hardening.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "NO-FIELD-R23-FIXPACK-1"

def run(stage: str, folia: Path, check_only: bool = False) -> None:
    cmd = [sys.executable, str(ROOT / stage), str(folia)]
    if check_only:
        cmd.append("--check-only")
    subprocess.run(cmd, cwd=ROOT, check=True)

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia", type=Path)
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()
    folia = a.folia.resolve()

    if a.check_only:
        run("scripts/apply-never-overworld-fixpack-r21.py", folia, True)
        run("scripts/apply-never-overworld-field-r23.py", folia, True)
        print(f"[NeverOverworld R23] {PROFILE} final invariants OK")
        return

    run("scripts/apply-never-overworld-fixpack-r22.py", folia)
    run("scripts/apply-never-overworld-field-r23.py", folia)
    run("scripts/apply-never-overworld-fixpack-r21.py", folia, True)
    run("scripts/apply-never-overworld-field-r23.py", folia, True)
    print(f"[NeverOverworld R23] {PROFILE} installed")

if __name__ == "__main__":
    main()
