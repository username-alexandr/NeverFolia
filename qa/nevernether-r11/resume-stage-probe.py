#!/usr/bin/env python3
"""Resume ONLY an R11-owned disposable CARVERS checkpoint, after normal stop.

Does not create missing snapshots, migrate ordinary worlds, or change fingerprint
locks. Identity/coverage checks precede any modification; old evidence is retained.
"""
from __future__ import annotations
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import sys

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('stage_runner',ROOT/'qa/nevernether-r8/run-stage-probe.py')
RUNNER=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(RUNNER)


def validate(directory:Path,runtime:Path,java:Path,mode:str='carvers')->tuple[dict,dict,list[str],dict]:
    if not (directory/'.nevernether-r8-isolated').is_file():raise ValueError('Not a marked disposable probe world')
    if 'server-ip=127.0.0.1\n' not in (directory/'server.properties').read_text():raise ValueError('Loopback binding required')
    saved_name='checkpoint-evidence' if mode=='carvers' else 'before-full-readback'
    if (directory/saved_name).exists():raise ValueError('This checkpoint was already resumed')
    if mode not in ('carvers', 'full-readback'):raise ValueError('Unknown resume mode')
    old=json.loads((directory/'run-evidence.json').read_text())
    if old.get('schema')!=2 or old.get('stage')!='completed' or old.get('process_exit_code')!=0 or old.get('forced_stop') is not False or old.get('runtime_unchanged') is not True or old.get('inputs_unchanged') is not True:
        raise ValueError('Checkpoint did not stop cleanly')
    if old.get('jvm_flags') != RUNNER.SUPERVISOR.JVM_FLAGS:raise ValueError('Checkpoint JVM flags differ from the inspected probe profile')
    plan=RUNNER.checked_plan(directory/'stage-plan.json',old['seed'],False)
    if mode=='carvers' and plan.get('stop_after_carvers') is not True:raise ValueError('Not a CARVERS checkpoint')
    report=json.loads((directory/'plugins/NN-STAGE-R8-QA/report.json').read_text())
    if report.get('plan') != plan or report.get('seed') != old['seed']:raise ValueError('Checkpoint report/plan identity mismatch')
    states=directory/'plugins/NN-STAGE-R8-QA/states.json'
    if not states.is_file() or RUNNER.sha(states)!=report.get('state_dictionary_sha256'):raise ValueError('Checkpoint state dictionary checksum mismatch')
    pairs={tuple(c) for c in plan['chunks']}
    observations=report.get('observations',[])
    relevant=observations if mode=='carvers' else [r for r in observations if r.get('phase')=='settled']
    phase='carvers' if mode=='carvers' else 'settled'
    status='minecraft:carvers' if mode=='carvers' else 'minecraft:full'
    if report.get('stage')!='completed' or len(relevant)!=len(pairs) or {(r['x'],r['z']) for r in relevant}!=pairs or any(r.get('phase')!=phase or r.get('status')!=status or r.get('simulation_frozen') is not True for r in relevant):
        raise ValueError('Incomplete or contaminated checkpoint observations')
    for r in relevant:
        block_name=f"{phase}/{r['x']}_{r['z']}.bin.gz"
        block=directory/'plugins/NN-STAGE-R8-QA'/block_name
        if r.get('file')!=block_name or not block.is_file() or RUNNER.sha(block)!=r.get('sha256') or block.stat().st_size!=r.get('bytes'):
            raise ValueError('Block snapshot checksum/size mismatch')
        expected=f"{phase}/{r['x']}_{r['z']}.substrate.nbt"
        if r.get('metadata_file')!=expected or r.get('metadata_sections')!=64:
            raise ValueError('Missing per-section metadata evidence')
        path=directory/'plugins/NN-STAGE-R8-QA'/expected
        if not path.is_file() or RUNNER.sha(path)!=r.get('metadata_sha256'):
            raise ValueError('Metadata snapshot checksum mismatch')
    entries,inventory=RUNNER.runtime_inventory(runtime)
    if inventory['manifest_sha256'] != old['classpath_manifest_sha256']:raise ValueError('Runtime classpath manifest changed since checkpoint')
    if inventory['payload_sha256']!=old['runtime_payload_sha256'] or RUNNER.sha(java)!=old['java_executable_sha256']:
        raise ValueError('Runtime/Java identity changed since checkpoint')
    if RUNNER.sha(directory/'world/datapacks/NeverNether.zip')!=old['pack_sha256'] or RUNNER.sha(directory/'plugins/survey-qa.jar')!=old['qa_plugin_sha256']:
        raise ValueError('Datapack/plugin changed since checkpoint')
    with (directory/'world/session.lock').open('r+b') as lock:
        fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fcntl.lockf(lock,fcntl.LOCK_UN)
    return old,plan,entries,inventory


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resume-directory',type=Path,required=True)
    p.add_argument('--runtime-dir',type=Path,required=True)
    p.add_argument('--java',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=600)
    p.add_argument('--mode',choices=('carvers','full-readback'),default='carvers')
    p.add_argument('--acknowledge-disposable-checkpoint',action='store_true')
    p.add_argument('--check-only',action='store_true',help='Validate checkpoint without moving evidence or starting Java')
    p.add_argument('--heartbeat-seconds',type=int,default=15)
    p.add_argument('--stall-timeout',type=int,default=180)
    a=p.parse_args()
    if not a.acknowledge_disposable_checkpoint:p.error('Explicit disposable checkpoint acknowledgement required')
    if not 60<=a.timeout<=3600:p.error('Invalid bounded timeout')
    if not 1<=a.heartbeat_seconds<=300 or not 10<=a.stall_timeout<=3600:p.error('Invalid heartbeat or no-progress timeout')
    directory=a.resume_directory.resolve();runtime=a.runtime_dir.resolve();java=a.java.resolve()
    print('[NN-PROBE] checking saved checkpoint and runtime inventory',file=sys.stderr,flush=True)
    for key in ('JDK_JAVA_OPTIONS','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS'):
        if os.environ.get(key):p.error('External JVM injection is not permitted: '+key)
    try:old,plan,entries,inventory=validate(directory,runtime,java,a.mode)
    except (OSError,KeyError,ValueError,TypeError) as ex:p.error(str(ex))
    if a.check_only:
        print(json.dumps({'preflight':'PASS','mode':a.mode,'chunks':len(plan['chunks']),'evidence_moved':False,'process_started':False}))
        return 0
    saved=directory/('checkpoint-evidence' if a.mode=='carvers' else 'before-full-readback');saved.mkdir()
    for name in ('run-evidence.json','runtime-inventory.json','run.log','stage-plan.json'):
        shutil.move(str(directory/name),saved/name)
    for name in ('probe-progress.json','probe-supervisor-result.json'):
        if (directory/name).is_file():shutil.move(str(directory/name),saved/name)
    shutil.move(str(directory/'plugins/NN-STAGE-R8-QA'),saved/'observations')
    plan.pop('stop_after_carvers',None)
    if a.mode=='full-readback':plan['verify_saved_only']=True
    (directory/'stage-plan.json').write_text(json.dumps(plan))
    (directory/'runtime-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    evidence={k:old[k] for k in ('schema','seed','pack_sha256','qa_plugin_sha256','java_executable_sha256','runtime_payload_sha256','classpath_manifest_sha256','order','jvm_flags','release_ready')}
    evidence['real_jvm_restart']=True;evidence['resume_mode']=a.mode;evidence['checkpoint_run_evidence_sha256']=RUNNER.sha(saved/'run-evidence.json')
    command=[str(java),*old['jvm_flags'],'-cp',os.pathsep.join(entries),'org.bukkit.craftbukkit.Main','--nogui']
    result=RUNNER.SUPERVISOR.execute(command,directory,a.timeout,env=RUNNER.SUPERVISOR.checked_environment(),
        heartbeat=a.heartbeat_seconds,stall_timeout=a.stall_timeout)
    evidence.update(result)
    return RUNNER.finish(evidence,directory,runtime,inventory,
        directory/'world/datapacks/NeverNether.zip',directory/'plugins/survey-qa.jar')


if __name__=='__main__':raise SystemExit(main())
