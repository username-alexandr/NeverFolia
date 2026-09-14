#!/usr/bin/env python3
"""Opt-in R13 after exact REMOTE R12, never on a world or normal production build.

Remote R12 proposal buffering/randomness and priority policy are preserved. The
local R12 natural-only boundary and plant substrate checks are reconciled here.
All source hashes and helper identities validate before writes; no profile migration.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path('folia-server/src/minecraft/java')
PROFILE = ROOT / 'worldgen-spec/never-nether-r13-hooks.json'
HELPERS = ('net/minecraft/world/level/levelgen/placement/NeverNetherNaturalPolicyR13.java',)
SPEC = importlib.util.spec_from_file_location('nn_r13_exact_transform', ROOT / 'scripts/apply-never-nether-experiment-r12.py')
if SPEC is None or SPEC.loader is None: raise RuntimeError('Missing exact source transformer')
BASE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(BASE)
transform = BASE.transform


def prepare(folia: Path) -> dict[Path, str]:
    profile = json.loads(PROFILE.read_text())
    if profile.get('schema') != 1: raise ValueError('Unsupported R13 hook schema')
    target = folia / JAVA
    staged = {target/name: transform((target/name).read_text(), rule) for name, rule in profile['files'].items()}
    source = ROOT / 'qa/nevernether-r13/candidate'
    if {p.relative_to(source).as_posix() for p in source.rglob('*.java')} != set(HELPERS):
        raise ValueError('Unexpected R13 helper inventory')
    for name in HELPERS:
        text = (source/name).read_text()
        if not text.strip(): raise ValueError('Empty R13 helper')
        dest = target/name
        if dest.exists() and dest.read_text() != text: raise ValueError('Conflicting R13 helper; use a fresh generated build')
        staged[dest] = text
    return staged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folia', type=Path)
    parser.add_argument('--acknowledge-experimental-worldgen', action='store_true')
    args = parser.parse_args()
    if not args.acknowledge_experimental_worldgen: parser.error('Explicit opt-in required; existing worlds must not be upgraded')
    staged = prepare(args.folia)
    for path, text in staged.items():
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8')
    print(f'R13 reconciled candidate installed: {len(staged)} files; no world acceptance asserted')

if __name__ == '__main__': main()
