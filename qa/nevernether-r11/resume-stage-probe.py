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

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('stage_runner',ROOT/'qa/nevernether-r8/run-stage-probe.py')
RUNNER=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(RUNNER)


def validate(directory:Path,runtime:Path,java:Path,mode:str='carvers')->tuple[dict,dict,list[str],dict]:
    if not (directory/'.nevernether-r8-isolated').is_file():raise ValueError('Not a marked disposable probe world')
    if 'server-ip=127.0.0.1\n' not in (directory/'server.properties').read_text():raise ValueError('Loopback binding required')
    saved_name='checkpoint-evidence' if mode=='carvers' else 'before-full-readback'
    if (directory/saved_name).exists():raise ValueError('This checkpoint was already resumed')
    old=json.loads((directory/'run-evidence.json').read_text())
    if old.get('schema')!=2 or old.get('stage')!='completed' or old.get('process_exit_code')!=0 or old.get('forced_stop') is not False or old.get('runtime_unchanged') is not True or old.get('inputs_unchanged') is not True:
        raise ValueError('Checkpoint did not stop cleanly')
    plan=RUNNER.checked_plan(directory/'stage-plan.json',old['seed'],False)
    if mode=='carvers' and plan.get('stop_after_carvers') is not True:raise ValueError('Not a CARVERS checkpoint')
    report=json.loads((directory/'plugins/NN-STAGE-R8-QA/report.json').read_text())
    pairs={tuple(c) for c in plan['chunks']}
    observations=report.get('observations',[])
    relevant=observations if mode=='carvers' else [r for r in observations if r.get('phase')=='settled']
    phase='carvers' if mode=='carvers' else 'settled'
    status='minecraft:carvers' if mode=='carvers' else 'minecraft:full'
    if report.get('stage')!='completed' or len(relevant)!=len(pairs) or {(r['x'],r['z']) for r in relevant}!=pairs or any(r.get('phase')!=phase or r.get('status')!=status or r.get('simulation_frozen') is not True for r in relevant):
        raise ValueError('Incomplete or contaminated checkpoint observations')
    for r in relevant:
        expected=f"{phase}/{r['x']}_{r['z']}.substrate.nbt"
        if r.get('metadata_file')!=expected or r.get('metadata_sections')!=64:
            raise ValueError('Missing per-section metadata evidence')
        path=directory/'plugins/NN-STAGE-R8-QA'/expected
        if not path.is_file() or RUNNER.sha(path)!=r.get('metadata_sha256'):
            raise ValueError('Metadata snapshot checksum mismatch')
    entries,inventory=RUNNER.runtime_inventory(runtime)
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
    a=p.parse_args()
    if not a.acknowledge_disposable_checkpoint:p.error('Explicit disposable checkpoint acknowledgement required')
    if not 60<=a.timeout<=3600:p.error('Invalid bounded timeout')
    directory=a.resume_directory.resolve();runtime=a.runtime_dir.resolve();java=a.java.resolve()
    for key in ('JDK_JAVA_OPTIONS','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS'):
        if os.environ.get(key):p.error('External JVM injection is not permitted: '+key)
    try:old,plan,entries,inventory=validate(directory,runtime,java,a.mode)
    except (OSError,KeyError,ValueError,TypeError) as ex:p.error(str(ex))
    saved=directory/('checkpoint-evidence' if a.mode=='carvers' else 'before-full-readback');saved.mkdir()
    for name in ('run-evidence.json','runtime-inventory.json','run.log','stage-plan.json'):
        shutil.move(str(directory/name),saved/name)
    shutil.move(str(directory/'plugins/NN-STAGE-R8-QA'),saved/'observations')
    plan.pop('stop_after_carvers',None)
    if a.mode=='full-readback':plan['verify_saved_only']=True
    (directory/'stage-plan.json').write_text(json.dumps(plan))
    (directory/'runtime-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    evidence={k:old[k] for k in ('schema','seed','pack_sha256','qa_plugin_sha256','java_executable_sha256','runtime_payload_sha256','classpath_manifest_sha256','order','jvm_flags','release_ready')}
    evidence['real_jvm_restart']=True;evidence['resume_mode']=a.mode;evidence['checkpoint_run_evidence_sha256']=RUNNER.sha(saved/'run-evidence.json')
    command=[str(java),*old['jvm_flags'],'-cp',os.pathsep.join(entries),'org.bukkit.craftbukkit.Main','--nogui']
    outcome='timeout';forced=False;start=time.monotonic();report=directory/'plugins/NN-STAGE-R8-QA/report.json'
    with (directory/'run.log').open('w') as log:
        process=subprocess.Popen(command,cwd=directory,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True)
        try:
            while time.monotonic()-start<a.timeout:
                if process.poll() is not None:outcome='exited_early';break
                if report.is_file():
                    status=json.loads(report.read_text()).get('stage')
                    if status in ('completed','failed'):outcome=status;break
                time.sleep(1)
        finally:
            if process.poll() is None:
                try:process.stdin.write('stop\n');process.stdin.flush();process.wait(timeout=90)
                except (BrokenPipeError,subprocess.TimeoutExpired):
                    forced=True;process.terminate()
                    try:process.wait(timeout=30)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
    _,after=RUNNER.runtime_inventory(runtime)
    evidence.update(stage=outcome,process_exit_code=process.returncode,forced_stop=forced,elapsed_seconds=time.monotonic()-start,
        runtime_unchanged=after==inventory,inputs_unchanged=RUNNER.sha(directory/'world/datapacks/NeverNether.zip')==old['pack_sha256'] and RUNNER.sha(directory/'plugins/survey-qa.jar')==old['qa_plugin_sha256'])
    (directory/'run-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence,indent=2))
    return 0 if outcome=='completed' and process.returncode==0 and not forced and evidence['runtime_unchanged'] and evidence['inputs_unchanged'] else 2

if __name__=='__main__':raise SystemExit(main())
