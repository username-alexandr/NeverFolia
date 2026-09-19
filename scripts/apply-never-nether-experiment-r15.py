#!/usr/bin/env python3
"""Install R15 pre-capture and post-FEATURES field cleanup after exact R14+BUG01.

New chunks only. The pre-capture pass runs immediately before R10 snapshots the
immutable CARVERS substrate. A second conservative pass runs in Moonrise LIGHT,
after FEATURES have finished and before Starlight reads section emptiness.
No datapack/profile migration and no existing-world rewrite is performed.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
TARGET=Path('net/minecraft/world/level/levelgen/placement/NeverNetherSubstrateR10.java')
HELPER=Path('net/minecraft/world/level/levelgen/placement/NeverNetherFieldCleanupR15.java')
SOURCE=ROOT/'qa/nevernether-r15/candidate'/HELPER
MOONRISE=Path('ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java')
OVERWORLD_LIGHT_CALL='net.minecraft.world.level.chunk.NeverOverworldFlood.apply(task.world, task.fromChunk);'
POST_MARKER='// NEVERFOLIA: NeverNether R15 post-FEATURES cleanup'
POST_CALL='net.minecraft.world.level.levelgen.placement.NeverNetherFieldCleanupR15.afterFeatures(task.world, task.fromChunk);'
STARLIGHT='StarLightEngine.getEmptySectionsForChunk(task.fromChunk)'
OLD='''        if (chunk.getPersistedStatus().isOrAfter(net.minecraft.world.level.chunk.status.ChunkStatus.FEATURES))
            throw new IllegalStateException("R10 cannot capture an already decorated chunk");
        LevelChunkSection[] sections = chunk.getSections();
'''
NEW='''        if (chunk.getPersistedStatus().isOrAfter(net.minecraft.world.level.chunk.status.ChunkStatus.FEATURES))
            throw new IllegalStateException("R10 cannot capture an already decorated chunk");
        NeverNetherFieldCleanupR15.clean(chunk);
        LevelChunkSection[] sections = chunk.getSections();
'''
MARKER='NeverNetherFieldCleanupR15.clean(chunk);'

def fail(msg:str)->None: raise SystemExit('[NeverFolia][NN-R15 field cleanup] '+msg)

def patch(text:str)->str:
    required=(
        'NeverNetherHeightR14.HEIGHT',
        'NeverNetherHeightR14.MAX_Y',
        'public static void capture(ServerLevel level, ChunkAccess chunk)',
    )
    for marker in required:
        if marker not in text: fail('R14 substrate marker missing: '+marker)
    if MARKER in text:
        if text.count(MARKER)!=1 or OLD in text: fail('partial/duplicate R15 installation')
        return text
    if text.count(OLD)!=1: fail('expected one R10 capture anchor, got '+str(text.count(OLD)))
    out=text.replace(OLD,NEW,1)
    if out.count(MARKER)!=1: fail('cleanup hook installation failed')
    guard=out.index('chunk.getPersistedStatus().isOrAfter')
    hook=out.index(MARKER)
    sections=out.index('LevelChunkSection[] sections')
    if not guard < hook < sections: fail('cleanup must run after persisted-status guard and before snapshot')
    return out

def patch_light(text:str)->str:
    if POST_CALL in text or POST_MARKER in text:
        if text.count(POST_CALL)!=1 or text.count(POST_MARKER)!=1:
            fail('partial/duplicate R15 LIGHT installation')
        if text.index(POST_CALL)>text.index(STARLIGHT):
            fail('R15 LIGHT cleanup must run before Starlight')
        return text
    if text.count(OVERWORLD_LIGHT_CALL)!=1:
        fail('expected exactly one installed NeverOverworld Moonrise LIGHT call')
    if text.count(STARLIGHT)!=1:
        fail('expected exactly one Starlight empty-section anchor')
    replacement=(
        OVERWORLD_LIGHT_CALL+'\n'
        '                '+POST_MARKER+'\n'
        '                '+POST_CALL
    )
    out=text.replace(OVERWORLD_LIGHT_CALL,replacement,1)
    if not out.index(OVERWORLD_LIGHT_CALL)<out.index(POST_CALL)<out.index(STARLIGHT):
        fail('R15 LIGHT ordering invalid')
    return out

def helper()->str:
    if not SOURCE.is_file(): fail('helper source missing: '+str(SOURCE))
    value=SOURCE.read_text()
    for marker in ('MAX_MICRO_POCKET = 4','solidifyHangingLava','afterFeatures','hasAnyStructureReferences','isNaturalRock','owner-chunk'):
        if marker not in value: fail('helper contract marker missing: '+marker)
    return value

def self_test()->None:
    fixture='''class X {
    static boolean scope(Object level){return true;}
    // NeverNetherHeightR14.HEIGHT NeverNetherHeightR14.MAX_Y
    public static void capture(ServerLevel level, ChunkAccess chunk) {
        if (!scope(level)) return;
        if (chunk.getPersistedStatus().isOrAfter(net.minecraft.world.level.chunk.status.ChunkStatus.FEATURES))
            throw new IllegalStateException("R10 cannot capture an already decorated chunk");
        LevelChunkSection[] sections = chunk.getSections();
    }
}
'''
    out=patch(fixture)
    if patch(out)!=out: fail('transformer not idempotent')
    light_fixture='''class ChunkLightTask {
        boolean run() {
            net.minecraft.world.level.chunk.NeverOverworldFlood.apply(task.world, task.fromChunk);
            final Boolean[] emptySections = StarLightEngine.getEmptySectionsForChunk(task.fromChunk);
            return true;
        }
    }
'''
    light=patch_light(light_fixture)
    if patch_light(light)!=light: fail('LIGHT transformer not idempotent')
    if not light.index(OVERWORLD_LIGHT_CALL)<light.index(POST_CALL)<light.index(STARLIGHT):
        fail('SELF-TEST: LIGHT ordering invalid')
    helper()
    print('[NeverFolia][NN-R15 field cleanup] SELF-TEST OK')

def prepare(folia:Path)->dict[Path,str]:
    self_test()
    target=folia/JAVA/TARGET
    if not target.is_file(): fail('materialized R14 substrate helper missing: '+str(target))
    dest=folia/JAVA/HELPER
    light=folia/JAVA/MOONRISE
    payload=helper()
    if dest.exists() and dest.read_text()!=payload: fail('conflicting R15 helper')
    if not light.is_file(): fail('materialized Moonrise ChunkLightTask missing: '+str(light))
    return {target:patch(target.read_text()),dest:payload,light:patch_light(light.read_text())}

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia',nargs='?',type=Path)
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--acknowledge-experimental-worldgen',action='store_true')
    a=p.parse_args()
    if a.self_test:
        self_test();return
    if a.folia is None:p.error('folia worktree required')
    if not a.acknowledge_experimental_worldgen:p.error('explicit opt-in required; new worlds/chunks only')
    staged=prepare(a.folia.resolve())
    for path,value in staged.items():
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value,encoding='utf-8')
    print('[NeverFolia][NN-R15 field cleanup] installed: '+str(len(staged))+' files (pre-capture + LIGHT post-FEATURES)')

if __name__=='__main__':main()
