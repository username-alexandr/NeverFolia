#!/usr/bin/env python3
"""Install NeverOverworld field-R10 fixes after final R9 V17 Overworld policy.

The transformer is exact-source, atomic and idempotent. It replaces only the
known final village reclamation helper, inserts two calls into the known final
flood helper, and installs two new helpers. Existing worlds are not migrated.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path('folia-server/src/minecraft/java')
VILLAGE = Path('net/minecraft/world/level/levelgen/structure/NeverOverworldVillageReclamation.java')
FLOOD = Path('net/minecraft/world/level/chunk/NeverOverworldFlood.java')
SUBMERGED = Path('net/minecraft/world/level/chunk/NeverOverworldSubmergedRemnants.java')
ORE = Path('net/minecraft/world/level/chunk/NeverOverworldOreScarcityFieldR10.java')
SOURCE_ROOT = ROOT/'native/neveroverworld/field-r10/java'
OLD_VILLAGE_SHA = '10a40a1111b59f6ac11aa876293aa17642b97022afbbb1d97417c6af6954d2d1'
OLD_FLOOD_SHA = '3581f1d0e041ec8e603c95f30146b64004f99fdc72f9d994ec8c88457542168d'
ORE_ANCHOR = '        removeUpperLapisDiamondAfterNeighbourFeatures(chunk);\n'
ORE_CALL = ORE_ANCHOR + '        NeverOverworldOreScarcityFieldR10.apply(level, chunk);\n'
CLEAN_ANCHOR = '        weatherSubmergedSurface(chunk, minY, FLOOD_LEVEL);\n'
CLEAN_CALL = CLEAN_ANCHOR + '        NeverOverworldSubmergedRemnants.apply(level, chunk);\n'


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def canonical(rel: Path) -> str:
    path = SOURCE_ROOT/rel
    if not path.is_file(): raise ValueError('Canonical field-R10 source missing: '+str(path))
    value = path.read_text()
    if not value.strip(): raise ValueError('Canonical field-R10 source empty: '+str(path))
    return value


def patch_flood(text: str) -> str:
    if ORE_CALL in text or CLEAN_CALL in text:
        if text.count(ORE_CALL) != 1 or text.count(CLEAN_CALL) != 1:
            raise ValueError('Partial/duplicate field-R10 Flood installation')
        inverted = text.replace(ORE_CALL, ORE_ANCHOR, 1).replace(CLEAN_CALL, CLEAN_ANCHOR, 1)
        if sha(inverted) != OLD_FLOOD_SHA:
            raise ValueError('Installed Flood does not invert to inspected R9 source')
        return text
    if sha(text) != OLD_FLOOD_SHA:
        raise ValueError('NeverOverworldFlood differs from inspected R9 final source')
    if text.count(ORE_ANCHOR) != 1 or text.count(CLEAN_ANCHOR) != 1:
        raise ValueError('Field-R10 Flood anchors drifted')
    text = text.replace(ORE_ANCHOR, ORE_CALL, 1).replace(CLEAN_ANCHOR, CLEAN_CALL, 1)
    if text.count('NeverOverworldOreScarcityFieldR10.apply(level, chunk);') != 1:
        raise ValueError('Ore call installation failed')
    if text.count('NeverOverworldSubmergedRemnants.apply(level, chunk);') != 1:
        raise ValueError('Cleanup call installation failed')
    return text


def prepare(folia: Path) -> dict[Path, str]:
    target = folia/JAVA
    village = target/VILLAGE
    flood = target/FLOOD
    if not village.is_file() or not flood.is_file():
        raise ValueError('Materialized final Overworld sources are missing')
    village_new = canonical(VILLAGE)
    village_old = village.read_text()
    if village_old != village_new and sha(village_old) != OLD_VILLAGE_SHA:
        raise ValueError('Village reclamation differs from inspected V17 or exact field-R10 source')
    staged = {village: village_new, flood: patch_flood(flood.read_text())}
    for rel in (SUBMERGED, ORE):
        value = canonical(rel)
        dest = target/rel
        if dest.exists() and dest.read_text() != value:
            raise ValueError('Conflicting field-R10 helper; use a fresh generated source tree: '+str(dest))
        staged[dest] = value
    return staged


def apply(folia: Path) -> None:
    staged = prepare(folia)
    for path, value in staged.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
    print('[NeverFolia][NeverOverworld FIELD-R10] local village foundations + submerged remnants + 50% final ore thinning installed')


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia',type=Path)
    p.add_argument('--check-only',action='store_true')
    a=p.parse_args()
    staged=prepare(a.folia)
    if a.check_only:
        print(f'[NeverFolia][NeverOverworld FIELD-R10] preflight OK: {len(staged)} files; no writes')
        return
    apply(a.folia)

if __name__=='__main__':main()
