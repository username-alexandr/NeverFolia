#!/usr/bin/env python3
"""Install the R8 CANDIDATE only into generated disposable Folia build sources.

Not called by the production transformer chain. This changes generation semantics
and does not fix the complete determinism gate. An explicit acknowledgement is
required. No Minecraft source or third-party templates are embedded here.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/placement')
EXPECTED = 'ef408e581dbe6612752e2a44d532ff9d5e7833afb796ecfbd48be48fdbe6031d'
OLD_CALL = 'return this.placeWithContext(new PlacementContext(level, generator, Optional.empty()), random, origin);'
NEW_CALL = '''return this.placeWithContext(new PlacementContext(NeverNetherDecorationR8.supportView(this, level), generator, Optional.empty()),
            NeverNetherDecorationR8.supportRandom(this, level, origin, random), origin);'''
OLD_START = '        Stream<BlockPos> placements = Stream.of(origin);'
NEW_START = '''        // NeverFolia NN-R8 CANDIDATE: deterministic proposals, not release acceptance.
        if (NeverNetherFloraCandidateR8.handles(this, context)) return NeverNetherFloraCandidateR8.place(this, context, random, origin);
''' + OLD_START
HELPERS = ('NeverNetherDecorationR8.java', 'NeverNetherFloraCandidateR8.java')


def transform(text: str) -> str:
    if NEW_CALL in text and NEW_START in text:
        original = text.replace(NEW_CALL, OLD_CALL, 1).replace(NEW_START, OLD_START, 1)
        if hashlib.sha256(original.encode()).hexdigest() != EXPECTED:
            raise ValueError('Patched source does not invert to the exact inspected API')
        return text
    if hashlib.sha256(text.encode()).hexdigest() != EXPECTED or text.count(OLD_CALL) != 1 or text.count(OLD_START) != 1:
        raise ValueError('PlacedFeature differs from inspected Folia 26.2 source')
    return text.replace(OLD_CALL, NEW_CALL, 1).replace(OLD_START, NEW_START, 1)


def prepare(folia: Path) -> dict[Path, str]:
    target = folia / REL
    path = target / 'PlacedFeature.java'
    staged = {path: transform(path.read_text())}
    source = ROOT / 'qa/nevernether-r8/candidate/net/minecraft/world/level/levelgen/placement'
    for name in HELPERS:
        payload = (source / name).read_text()
        if not payload.strip():
            raise ValueError('Empty candidate helper')
        dest = target / name
        if dest.exists() and dest.read_text() != payload:
            raise ValueError('Different candidate helper already present; use a fresh build tree')
        staged[dest] = payload
    return staged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folia', type=Path)
    parser.add_argument('--acknowledge-experimental-worldgen', action='store_true')
    args = parser.parse_args()
    if not args.acknowledge_experimental_worldgen:
        parser.error('This is an experimental generator, not a production fix')
    staged = prepare(args.folia)
    for path, content in staged.items():
        path.write_text(content, encoding='utf-8')
    print('NN-R8 EXPERIMENT installed. Normal production chain is unchanged; no world acceptance asserted.')


if __name__ == '__main__':
    main()
