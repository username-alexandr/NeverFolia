#!/usr/bin/env python3
"""Install R15 CARVERS-substrate field cleanup after the exact R14 chain.

New chunks only. The helper runs immediately before R10 captures its immutable
CARVERS substrate, so corrected states become the persisted original substrate.
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
OLD='''        if (!scope(level)) return;
        // This method is called before publishing the CARVERS barrier; neighbor
'''
NEW='''        if (!scope(level)) return;
        NeverNetherFieldCleanupR15.clean(chunk);
        // This method is called before publishing the CARVERS barrier; neighbor
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
    return out

def helper()->str:
    if not SOURCE.is_file(): fail('helper source missing: '+str(SOURCE))
    value=SOURCE.read_text()
    for marker in ('MAX_MICRO_POCKET = 4','solidifyHangingLava','isNaturalRock','owner-chunk'):
        if marker not in value: fail('helper contract marker missing: '+marker)
    return value

def self_test()->None:
    fixture='''class X {
    static boolean scope(Object level){return true;}
    // NeverNetherHeightR14.HEIGHT NeverNetherHeightR14.MAX_Y
    public static void capture(ServerLevel level, ChunkAccess chunk) {
        if (!scope(level)) return;
        // This method is called before publishing the CARVERS barrier; neighbor
    }
}
'''
    out=patch(fixture)
    if patch(out)!=out: fail('transformer not idempotent')
    helper()
    print('[NeverFolia][NN-R15 field cleanup] SELF-TEST OK')

def prepare(folia:Path)->dict[Path,str]:
    self_test()
    target=folia/JAVA/TARGET
    if not target.is_file(): fail('materialized R14 substrate helper missing: '+str(target))
    dest=folia/JAVA/HELPER
    payload=helper()
    if dest.exists() and dest.read_text()!=payload: fail('conflicting R15 helper')
    return {target:patch(target.read_text()),dest:payload}

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
    print('[NeverFolia][NN-R15 field cleanup] installed: '+str(len(staged))+' files')

if __name__=='__main__':main()
