#!/usr/bin/env python3
"""Explicit readback of an already accepted, STOPPED, disposable R14 world.

Never generate new target chunks during preflight; existing FULL targets, matching
world locks and input identities must be present. Archives previous evidence.
"""
from __future__ import annotations
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[2]
def mod(n,p):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
P=mod('r14_resume_profile',Path(__file__).with_name('run-roof-probe.py'))
R=P.R
C=mod('r14_resume_validation',Path(__file__).with_name('compare-roof-r14.py'))
H=mod('r14_resume_nbt',ROOT/'scripts/hash-never-nether-chunks.py')

def validate(world,runtime,java):
    if not (world/'.nevernether-r8-isolated').is_file() or 'server-ip=127.0.0.1\n' not in (world/'server.properties').read_text():raise ValueError('Not a disposable loopback world')
    if (world/'before-r14-readback').exists():raise ValueError('Already resumed; no checkpoint overwrite')
    observations=C.load(world);old=observations['run'];plan=observations['report']['plan']
    if plan.get('test_mutations') or plan.get('readback'):raise ValueError('Only clean non-mutating initial observations')
    if old['jvm_flags']!=R.SUPERVISOR.JVM_FLAGS:raise ValueError('Changed JVM flags')
    entries,inventory=R.runtime_inventory(runtime)
    if inventory['payload_sha256']!=old['runtime_payload_sha256'] or inventory['manifest_sha256']!=old['classpath_manifest_sha256'] or R.sha(java)!=old['java_executable_sha256']:raise ValueError('Changed runtime or Java')
    for f,key in [('world/datapacks/NeverNether.zip','pack_sha256'),('plugins/survey-qa.jar','qa_plugin_sha256')]:
        if R.sha(world/f)!=old[key]:raise ValueError('Changed '+key)
    if (world/'world/.neverfolia-nevernether-height.lock').read_text()!=C.PROFILE+'\n':raise ValueError('Missing/different R14 height lock')
    region=world/'world/dimensions/minecraft/the_nether/region'
    for x,z in plan['chunks']:
        nbt=H.read_chunk_nbt(region,x,z)
        if (nbt.get('xPos'),nbt.get('zPos'))!=(x,z) or nbt.get('Status')!='minecraft:full':raise ValueError('Missing saved FULL target')
    with (world/'world/session.lock').open('r+b') as lock:fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.lockf(lock,fcntl.LOCK_UN)
    return old,plan,entries,inventory

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('world','runtime-dir','java'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--acknowledge-disposable-checkpoint',action='store_true');p.add_argument('--check-only',action='store_true');a=p.parse_args()
    if not a.acknowledge_disposable_checkpoint:p.error('Explicit acknowledgement required')
    world=a.world.resolve();runtime=a.runtime_dir.resolve();java=a.java.resolve();env=R.SUPERVISOR.checked_environment()
    old,plan,entries,inventory=validate(world,runtime,java)
    if a.check_only:print(json.dumps({'preflight':'PASS','process_started':False,'files_moved':False}));return 0
    archive=world/'before-r14-readback';archive.mkdir()
    for name in ('run-evidence.json','runtime-inventory.json','stage-plan.json','run.log','probe-progress.json','probe-supervisor-result.json'):
        if (world/name).exists():shutil.move(world/name,archive/name)
    (archive/'plugins').mkdir();shutil.move(world/'plugins/NN-STAGE-R8-QA',archive/'plugins/NN-STAGE-R8-QA')
    plan=dict(plan,readback=True);(world/'stage-plan.json').write_text(json.dumps(plan));(world/'runtime-inventory.json').write_text(json.dumps(inventory,indent=2))
    evidence={k:old[k] for k in ('schema','seed','pack_sha256','qa_plugin_sha256','java_executable_sha256','runtime_payload_sha256','classpath_manifest_sha256','order','jvm_flags','release_ready')}
    evidence.update(real_jvm_restart=True,checkpoint_evidence_sha256=R.sha(archive/'run-evidence.json'))
    result=R.SUPERVISOR.execute([str(java),*old['jvm_flags'],'-cp',os.pathsep.join(entries),'org.bukkit.craftbukkit.Main','--nogui'],world,900,env=env)
    evidence.update(result)
    return R.finish(evidence,world,runtime,inventory,world/'world/datapacks/NeverNether.zip',world/'plugins/survey-qa.jar')
if __name__=='__main__':raise SystemExit(main())
