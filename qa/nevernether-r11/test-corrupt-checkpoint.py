#!/usr/bin/env python3
"""Negative test ONLY in a NEW copy of a marked disposable R11 QA world.

Corrupts one profile string in a copied chunk (not the original), starts an exact
runtime on loopback, and requires refusal with the corrupted payload unchanged.
This is not a repair or a general physical-region corruption test.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time
import zlib
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('runner',ROOT/'qa/nevernether-r8/run-stage-probe.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)


def payload(region:Path,x:int,z:int)->tuple[bytes,bytes,int,int]:
    raw=region.read_bytes();index=4*((x&31)+32*(z&31));entry=int.from_bytes(raw[index:index+4],'big')
    offset=(entry>>8)*4096;capacity=(entry&255)*4096
    if not offset or capacity<4096:raise ValueError('Missing target chunk')
    length=int.from_bytes(raw[offset:offset+4],'big')
    if raw[offset+4]!=2 or length<2 or length>capacity-4:raise ValueError('Expected inline zlib chunk')
    return raw,zlib.decompress(raw[offset+5:offset+4+length]),offset,capacity


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-disposable',type=Path,required=True);p.add_argument('--new-directory',type=Path,required=True)
    p.add_argument('--java',type=Path,required=True);p.add_argument('--runtime-dir',type=Path,required=True)
    p.add_argument('--chunk',default='-216,-46');p.add_argument('--port',type=int,default=25595)
    p.add_argument('--acknowledge-negative-test',action='store_true');a=p.parse_args()
    if not a.acknowledge_negative_test:p.error('Explicit negative-test acknowledgement required')
    source=a.input_disposable.resolve();out=a.new_directory.resolve();runtime=a.runtime_dir.resolve()
    if not (source/'.nevernether-r8-isolated').is_file():p.error('Source is not a marked disposable QA world')
    evidence=json.loads((source/'run-evidence.json').read_text())
    if evidence.get('stage')!='completed' or evidence.get('process_exit_code')!=0:p.error('Source did not stop normally')
    if out.exists() or out.is_relative_to(source):p.error('Destination must be new and outside the source')
    x,z=map(int,a.chunk.split(','));entries,inventory=R.runtime_inventory(runtime)
    for key in ('JDK_JAVA_OPTIONS','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS'):
        if os.environ.get(key):p.error('External JVM injection is forbidden')
    shutil.copytree(source,out)
    shutil.move(out/'plugins/NN-STAGE-R8-QA',out/'prior-positive-observations')
    (out/'stage-plan.json').write_text(json.dumps({'seed':evidence['seed'],'chunks':[[x,z]],'verify_saved_only':True}))
    props=(out/'server.properties').read_text();lines=[line for line in props.splitlines() if not line.startswith(('server-ip=','server-port='))]
    (out/'server.properties').write_text('\n'.join(lines)+f'\nserver-ip=127.0.0.1\nserver-port={a.port}\n')
    region=out/f'world/dimensions/minecraft/the_nether/region/r.{x//32}.{z//32}.mca'
    raw,before,offset,capacity=payload(region,x,z)
    marker=b'NN-R11-SUBSTRATE-1-REMOTE-R10-PRIORITY'
    if before.count(marker)!=64:raise ValueError('Expected all 64 versioned section profiles')
    corrupted=before.replace(marker,b'XX'+marker[2:],1);compressed=zlib.compress(corrupted)
    record=struct.pack('>I',len(compressed)+1)+b'\x02'+compressed
    if len(record)>capacity:raise ValueError('Corrupt fixture does not fit original sector allocation')
    region.write_bytes(raw[:offset]+record+bytes(capacity-len(record))+raw[offset+capacity:])
    report={'schema':1,'test':'R11-invalid-profile-no-regeneration','target':[x,z],
            'original_chunk_sha256':hashlib.sha256(before).hexdigest(),'corrupted_chunk_sha256':hashlib.sha256(corrupted).hexdigest(),
            'runtime_payload_sha256':inventory['payload_sha256'],'production_use':False,'release_ready':False}
    command=[str(a.java.resolve()),*evidence['jvm_flags'],'-cp',os.pathsep.join(entries),'org.bukkit.craftbukkit.Main','--nogui']
    start=time.monotonic();seen=None;forced=False
    with (out/'negative-run.log').open('w') as log:
        proc=subprocess.Popen(command,cwd=out,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True)
        try:
            while time.monotonic()-start<90:
                if proc.poll() is not None:break
                text=(out/'negative-run.log').read_text(errors='replace')
                if 'Refusing R11 substrate load; no empty-chunk fallback' in text:
                    if seen is None:seen=time.monotonic()
                    if time.monotonic()-seen>5:break
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=60)
                except (BrokenPipeError,subprocess.TimeoutExpired):
                    forced=True;proc.terminate()
                    try:proc.wait(timeout=20)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    text=(out/'negative-run.log').read_text(errors='replace');_,after,_,_=payload(region,x,z)
    _,invAfter=R.runtime_inventory(runtime)
    report.update(refusal_logged='Refusing R11 substrate load; no empty-chunk fallback' in text,
        target_payload_unchanged=after==corrupted,process_exit_code=proc.returncode,forced_stop=forced,
        elapsed_seconds=time.monotonic()-start,runtime_unchanged=inventory==invAfter,
        after_chunk_sha256=hashlib.sha256(after).hexdigest())
    report['passed']=report['refusal_logged'] and report['target_payload_unchanged'] and report['runtime_unchanged'] and not forced
    (out/'negative-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 2

if __name__=='__main__':raise SystemExit(main())
