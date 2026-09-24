#!/usr/bin/env python3
"""NeverOverworld FIELD-R19 unified fixpack built on the accepted FIELD-R18 baseline."""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R18 = ROOT / 'scripts/apply-never-overworld-fixpack-r18.py'
R19 = ROOT / 'scripts/apply-never-overworld-field-r19.py'
PROFILE = 'NO-FIELD-R19-FIXPACK-1'

def run(script: Path, folia: Path, *extra: str) -> None:
    subprocess.run([sys.executable, str(script), str(folia), *extra], cwd=ROOT, check=True)

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia',type=Path)
    p.add_argument('--check-only',action='store_true')
    a=p.parse_args(); folia=a.folia.resolve()
    if a.check_only:
        run(R19, folia, '--check-only')
        print(f'[NeverOverworld R19] {PROFILE} final preflight OK')
        return
    run(R18, folia)
    run(R19, folia)
    print(f'[NeverOverworld R19] {PROFILE} installed')

if __name__=='__main__':main()
