#!/usr/bin/env python3
"""Install NeverOverworld field-R10 fixes after final R9 V17 Overworld policy.

The transformer is exact-source, atomic and idempotent. It replaces only the
known final village reclamation helper, inserts two calls into the known final
flood helper, and installs two new helpers. Existing worlds are not migrated.
A FULL-status gate prevents the LIGHT runtime hook from re-running worldgen
mutation when an already saved chunk is merely relit after restart.
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
SCOPE_ANCHOR = '''        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) {
            return;
        }

'''
FULL_GUARD = SCOPE_ANCHOR + '''        // LIGHT may also execute while an already persisted FULL chunk is relit.
        // Never run generation-only flood/cleanup/ore mutation in that path.
        if (chunk.getPersistedStatus().isOrAfter(net.minecraft.world.level.chunk.status.ChunkStatus.FULL)) {
            return;
        }

'''

PRIMARY_GATE_CONSTANTS = '''    private static final int DEEP_FLOW_MAX_Y = 96;
    private static final int MIN_DEEP_APERTURE = 6;
'''
PRIMARY_GATE_CALL = '''            if (y <= DEEP_FLOW_MAX_Y
                && !hydraulicOpenAir(chunk, localX, y, localZ, minX, minZ)) {
                continue;
            }
'''
PRIMARY_GATE_HELPER = '''    private static boolean hydraulicOpenAir(
        final ChunkAccess chunk,
        final int localX,
        final int y,
        final int localZ,
        final int minX,
        final int minZ
    ) {
        if (y > DEEP_FLOW_MAX_Y) {
            return true;
        }
        final BlockPos.MutableBlockPos probe = new BlockPos.MutableBlockPos();
        int open = 0;
        for (int dz = -1; dz <= 1; ++dz) {
            for (int dx = -1; dx <= 1; ++dx) {
                final int x = localX + dx;
                final int z = localZ + dz;
                if (x < 0 || x > 15 || z < 0 || z > 15) {
                    continue;
                }
                probe.set(minX + x, y, minZ + z);
                if (chunk.getBlockState(probe).isAir() && ++open >= MIN_DEEP_APERTURE) {
                    return true;
                }
            }
        }
        return false;
    }

'''

def normalize_primary_gate(text: str) -> str:
    markers = (
        PRIMARY_GATE_CONSTANTS in text,
        PRIMARY_GATE_CALL in text,
        PRIMARY_GATE_HELPER in text,
    )
    if any(markers) and not all(markers):
        raise ValueError('Partial R24 primary deep-flow gate found in NeverOverworldFlood')
    if all(markers):
        text = text.replace(PRIMARY_GATE_CONSTANTS, '', 1)
        text = text.replace(PRIMARY_GATE_CALL, '', 1)
        text = text.replace(PRIMARY_GATE_HELPER, '', 1)
    return text


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def canonical(rel: Path) -> str:
    path = SOURCE_ROOT/rel
    if not path.is_file(): raise ValueError('Canonical field-R10 source missing: '+str(path))
    value = path.read_text()
    if not value.strip(): raise ValueError('Canonical field-R10 source empty: '+str(path))
    return value


def patch_flood(text: str) -> str:
    installed = FULL_GUARD in text or ORE_CALL in text or CLEAN_CALL in text
    if installed:
        if text.count(FULL_GUARD) != 1 or text.count(ORE_CALL) != 1 or text.count(CLEAN_CALL) != 1:
            raise ValueError('Partial/duplicate field-R10 Flood installation')
        inverted = text.replace(ORE_CALL, ORE_ANCHOR, 1).replace(CLEAN_CALL, CLEAN_ANCHOR, 1).replace(FULL_GUARD, SCOPE_ANCHOR, 1)
        if sha(normalize_primary_gate(inverted)) != OLD_FLOOD_SHA:
            raise ValueError('Installed Flood does not invert to inspected R9 source + allowed R24 primary gate')
        return text
    if sha(normalize_primary_gate(text)) != OLD_FLOOD_SHA:
        raise ValueError('NeverOverworldFlood differs from inspected R9 final source + allowed R24 primary gate')
    if text.count(ORE_ANCHOR) != 1 or text.count(CLEAN_ANCHOR) != 1 or text.count(SCOPE_ANCHOR) != 1:
        raise ValueError('Field-R10 Flood anchors drifted')
    text = text.replace(SCOPE_ANCHOR, FULL_GUARD, 1).replace(ORE_ANCHOR, ORE_CALL, 1).replace(CLEAN_ANCHOR, CLEAN_CALL, 1)
    if text.count('NeverOverworldOreScarcityFieldR10.apply(level, chunk);') != 1:
        raise ValueError('Ore call installation failed')
    if text.count('NeverOverworldSubmergedRemnants.apply(level, chunk);') != 1:
        raise ValueError('Cleanup call installation failed')
    if text.count('chunk.getPersistedStatus().isOrAfter(net.minecraft.world.level.chunk.status.ChunkStatus.FULL)') != 1:
        raise ValueError('FULL relight guard installation failed')
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
    print('[NeverFolia][NeverOverworld FIELD-R10] local village foundations + submerged remnants + 50% final ore thinning + FULL relight guard installed')


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
