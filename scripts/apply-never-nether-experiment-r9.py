#!/usr/bin/env python3
"""Optional R9 after optional R8 in a disposable generated Folia build.

Normal production entry points do not call this. Hashes and exact occurrence
counts are checked for every source before any generated file is changed.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path('folia-server/src/minecraft/java')
PLACEMENT = 'net/minecraft/world/level/levelgen/placement/'
FUNGUS = 'net/minecraft/world/level/levelgen/feature/HugeFungusFeature.java'
CONTRACTS = {
    PLACEMENT+'PlacedFeature.java': ('345069ddd0622c2d035d15098610b6244de8ee8c1035ded80bac53bc4a5ada40', [
        ('NeverNetherDecorationR8.support', 'NeverNetherSupportCandidateR9.support', 2)]),
    PLACEMENT+'NeverNetherFloraCandidateR8.java': ('f666ff040379d1e7fce59026f8889d4cab103498104d3189d86e082df95c51dd', [
        ('new Class<?>[]{WorldGenLevel.class}', 'new Class<?>[]{WorldGenLevel.class, NeverNetherPlanningViewR9.class}', 1)]),
    FUNGUS: ('50d33b1b81ff93a24841ecd6940c2dda945bcb5d3ababfb78ae1610229055b1b', [
        ('if (random.nextFloat() < 0.1F)', 'if (net.minecraft.world.level.levelgen.placement.NeverNetherFungusRandomR9.at(level, surfaceOrigin, blockPos, 0x52395452554e4bL, random).nextFloat() < 0.1F)', 1),
        ('                    blockPos.setWithOffset(surfaceOrigin, dx, dy, dz);\n                    if (isReplaceable(level, blockPos, config, false))',
         '                    blockPos.setWithOffset(surfaceOrigin, dx, dy, dz);\n                    RandomSource cellRandom = net.minecraft.world.level.levelgen.placement.NeverNetherFungusRandomR9.at(level, surfaceOrigin, blockPos, 0x523943414e4f5059L, random);\n                    if (isReplaceable(level, blockPos, config, false))', 1),
        ('this.placeHatDropBlock(level, random, blockPos,', 'this.placeHatDropBlock(level, cellRandom, blockPos,', 1),
        ('this.placeHatBlock(level, random, config, blockPos,', 'this.placeHatBlock(level, cellRandom, config, blockPos,', 3)])
}
HELPERS = ('NeverNetherSupportCandidateR9.java', 'NeverNetherPlanningViewR9.java', 'NeverNetherFungusRandomR9.java')


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def transform(path: str, text: str) -> str:
    expected, replacements = CONTRACTS[path]
    if sha(text) == expected:
        for old, new, count in replacements:
            if text.count(old) != count or new in text:
                raise ValueError(f'Unexpected API anchor count in {path}: {old}')
            text = text.replace(old, new)
        return text
    # Idempotence is accepted only if the exact transformed source can be
    # inverted to the inspected original. Mixed or unrelated edits are rejected.
    original = text
    for old, new, count in reversed(replacements):
        if original.count(new) != count:
            raise ValueError(f'API source identity mismatch: {path}')
        original = original.replace(new, old)
    if sha(original) != expected:
        raise ValueError(f'Installed source does not invert to the inspected API: {path}')
    return text


def prepare(folia: Path) -> dict[Path, str]:
    root = folia / JAVA
    staged = {root/name: transform(name, (root/name).read_text()) for name in CONTRACTS}
    source = ROOT / 'qa/nevernether-r9/candidate' / PLACEMENT
    if {p.name for p in source.glob('*.java')} != set(HELPERS):
        raise ValueError('Unexpected R9 helper source inventory')
    for name in HELPERS:
        text = (source/name).read_text()
        if not text.strip():
            raise ValueError('Empty R9 helper source')
        dest = root / PLACEMENT / name
        if dest.exists() and dest.read_text() != text:
            raise ValueError(f'Conflicting R9 helper; use a fresh build tree: {dest}')
        staged[dest] = text
    return staged


def apply(folia: Path) -> None:
    staged = prepare(folia)
    for path, text in staged.items():
        path.write_text(text, encoding='utf-8')
    print(f'NN-R9 optional support/canopy experiment: {len(staged)} files. No full-world acceptance asserted.')


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia',type=Path)
    p.add_argument('--acknowledge-experimental-worldgen',action='store_true')
    a=p.parse_args()
    if not a.acknowledge_experimental_worldgen:
        p.error('Requires explicit opt-in on a fresh R8 candidate build, not a production world')
    apply(a.folia)

if __name__=='__main__':main()
