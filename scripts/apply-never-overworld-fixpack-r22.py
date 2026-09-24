#!/usr/bin/env python3
"""NeverOverworld FIELD-R22 unified fixpack.

Extends FIELD-R21 with scheduling-independent prospective ocean seeds for the
Moonrise LIGHT neighbour-cache seam reconciliation.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "NO-FIELD-R22-FIXPACK-1"

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
        run("scripts/apply-never-overworld-field-r22.py", folia, True)
        print(f"[NeverOverworld R22] {PROFILE} final invariants OK")
        return

    run("scripts/apply-never-overworld-fixpack-r21.py", folia)
    run("scripts/apply-never-overworld-field-r22.py", folia)
    run("scripts/apply-never-overworld-fixpack-r21.py", folia, True)
    run("scripts/apply-never-overworld-field-r22.py", folia, True)
    print(f"[NeverOverworld R22] {PROFILE} installed")

if __name__ == "__main__":
    main()
