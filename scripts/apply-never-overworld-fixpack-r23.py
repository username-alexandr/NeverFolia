#!/usr/bin/env python3
"""NeverOverworld FIELD-R23 unified fixpack.

Extends FIELD-R22 with strict verified-ocean cave flooding. R22 prospective
surface seeds remain, while proximity-only admission is disabled.
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROFILE="NO-FIELD-R23-FIXPACK-1"

def run(stage: str, folia: Path, check_only: bool=False) -> None:
    cmd=[sys.executable,str(ROOT/stage),str(folia)]
    if check_only: cmd.append("--check-only")
    subprocess.run(cmd,cwd=ROOT,check=True)

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",type=Path)
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args();folia=a.folia.resolve()
    if a.check_only:
        # R23 intentionally changes the final R22 proximity markers, so the
        # final state is verified by R21 + R23 instead of replaying R22 verify.
        run("scripts/apply-never-overworld-fixpack-r21.py",folia,True)
        run("scripts/apply-never-overworld-field-r23.py",folia,True)
        print(f"[NeverOverworld R23] {PROFILE} final invariants OK")
        return
    run("scripts/apply-never-overworld-fixpack-r22.py",folia)
    run("scripts/apply-never-overworld-field-r23.py",folia)
    run("scripts/apply-never-overworld-fixpack-r21.py",folia,True)
    run("scripts/apply-never-overworld-field-r23.py",folia,True)
    print(f"[NeverOverworld R23] {PROFILE} installed")

if __name__=="__main__":
    main()
