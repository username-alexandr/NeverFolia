#!/usr/bin/env python3
"""Install the R40 LIGHT hook into a materialized, already R399-patched source tree.
Default is read-only preflight. --apply writes sources; --check-only verifies installation.
Does not touch saved worlds, binary JARs or the historical transformation chain.
"""
from pathlib import Path
import argparse,hashlib,os,tempfile
ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
CHUNK=Path('net/minecraft/world/level/chunk')
LIGHT=Path('ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java')
LIGHT_SHA='e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283'
GUARDS={'NeverOverworldWaterPolicyR38.java':'f2f75f2ed71228da3d0637c77c7b892466b4b1b195571196a2de35fca2267fdb','NeverOverworldDryMinesR12.java':'edff456b5ce54fae72c733b1ffb2d6809ff6ffccec1edf0055bc8b0f666188c1'}
HELPERS={'OceanConnectivityR395.java':'5bd7187e44b56ce98aceb0ee6f431f5c4fe5e877','NeverOverworldOceanClosureR395.java':'d022c60f5c08a156f00154ddf85ab5882f3aaa39'}
ANCHOR=b'                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);'
CALL=b'                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR395.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R40_ON_R399\n'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def blob(raw):return hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
def need(ok,message):
    if not ok:raise ValueError(message)
def light_transform(raw):
    if raw.count(CALL)==1:
        need(raw.count(CALL+ANCHOR)==1,'R40 call is not at the verified LIGHT site')
        restored=raw.replace(CALL,b'',1)
        need(sha(restored)==LIGHT_SHA,'Changed already-installed LIGHT source')
        return raw
    need(sha(raw)==LIGHT_SHA and raw.count(ANCHOR)==1,'Uninspected LIGHT source')
    return raw.replace(ANCHOR,CALL+ANCHOR,1)
def prepare(folia,repository=ROOT):
    java=folia/JAVA
    for name,expected in GUARDS.items():
        need(sha((java/CHUNK/name).read_bytes())==expected,'Required exact R396/R399 source missing: '+name)
    staged={}
    for name,expected in HELPERS.items():
        raw=(repository/'native/overworld-r395'/name).read_bytes()
        need(blob(raw)==expected,'Uninspected ocean helper: '+name)
        target=java/CHUNK/name
        need(not target.exists() or target.read_bytes()==raw,'Conflicting ocean helper: '+str(target))
        staged[target]=raw
    target=java/LIGHT;staged[target]=light_transform(target.read_bytes())
    return staged

def install(folia,repository=ROOT):
    staged=prepare(folia,repository)
    old={p:p.read_bytes() if p.exists() else None for p in staged}
    changed=[p for p,value in staged.items() if old[p]!=value]
    # Helpers are committed first; the only call-site is installed last.
    for path in changed:
        previous=old[path]
        need((path.read_bytes() if path.exists() else None)==previous,'Source changed during installation')
        path.parent.mkdir(parents=True,exist_ok=True)
        if previous is not None:
            backup=path.with_name(path.name+'.before-r40')
            if backup.exists():need(backup.read_bytes()==previous,'Conflicting R40 backup')
            else:
                with backup.open('xb') as f:f.write(previous)
        temp=None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.r40-',delete=False) as f:
                temp=Path(f.name);f.write(staged[path]);f.flush();os.fsync(f.fileno())
            os.chmod(temp,path.stat().st_mode&0o777 if path.exists() else 0o644)
            need((path.read_bytes() if path.exists() else None)==previous,'Source changed during preparation')
            os.replace(temp,path)
        finally:
            if temp is not None:temp.unlink(missing_ok=True)
    need(all(p.read_bytes()==raw for p,raw in prepare(folia,repository).items()),'Post-install verification failed')
    return len(changed)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folia',type=Path)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--apply',action='store_true');mode.add_argument('--check-only',action='store_true')
    a=p.parse_args();root=a.folia.resolve()
    if a.apply:print('R40 source files changed:',install(root));return
    staged=prepare(root)
    if a.check_only:need(all(p.exists() and p.read_bytes()==raw for p,raw in staged.items()),'R40 source hook is not installed')
    print('R40 installed source verified' if a.check_only else 'R40 exact-source preflight passed; no files changed')
if __name__=='__main__':main()
