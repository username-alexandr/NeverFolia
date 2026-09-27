#!/usr/bin/env python3
"""Registry/start-stop smoke test only; does not prove structure placement or water.
Uses the existing project's isolated CI Minecraft EULA acceptance convention.
Never uses an existing server/world directory; the TCP listener is loopback only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time

EXPECTED = {'server.jar':'411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32',
            'NeverOverworld.zip':'32ea5160f0bed3a80cf400c907622c7dbb76a9bb4160e309cacb5d712a8bd9f7',
            'NeverNether.zip':'5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'}
OVERLAY = 'NeverOverworld-R39-ReferenceFix.zip'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--overlay',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.candidate=args.candidate.resolve();args.overlay=args.overlay.resolve()
    args.work=args.work.resolve();args.output=args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    report={'schema':1,'pass':False,'scope':'Loopback startup, registry loading, enabled-pack list and graceful stop only; not structure geometry, mobs or water acceptance',
            'source_core_sha':'c6e522c65e5ecd0852c27d724c652189464f51cc','bind':'127.0.0.1','port':25597,
            'seed':-4651369264513492755,'overlay_sha256':sha(args.overlay)}
    proc=None;reader=None;lines=[]
    log_path=args.output/'r39-overlay-startup.log'
    try:
        for name,expected in EXPECTED.items():
            if sha(args.candidate/name)!=expected:raise ValueError('Unexpected candidate input: '+name)
        args.work.mkdir(parents=True,exist_ok=False)
        packs=args.work/'world/datapacks';packs.mkdir(parents=True)
        for name in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(args.candidate/name,packs/name)
        shutil.copyfile(args.overlay,packs/OVERLAY)
        (args.work/'eula.txt').write_text('eula=true\n')
        (args.work/'server.properties').write_text(
            'level-name=world\nlevel-seed=-4651369264513492755\n'
            'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip,file/'+OVERLAY+'\n'
            'server-ip=127.0.0.1\nserver-port=25597\nonline-mode=true\nenforce-secure-profile=true\n'
            'view-distance=2\nsimulation-distance=2\nmax-players=1\nenable-query=false\nenable-rcon=false\n'
            'enable-status=false\npause-when-empty-seconds=-1\n')
        proc=subprocess.Popen(['java','-Xms512M','-Xmx3G','-jar',str(args.candidate/'server.jar'),'--nogui'],
                              cwd=args.work,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              text=True,encoding='utf-8',errors='replace',bufsize=1)
        events=queue.Queue()
        def pump():
            with log_path.open('w') as log:
                for line in proc.stdout:
                    lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start()
        def wait(predicate,seconds):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                try:line=events.get(timeout=min(1,max(0.01,until-time.monotonic())))
                except queue.Empty:
                    if proc.poll() is not None:raise RuntimeError('Server exited before expected event')
                    continue
                if line is None:raise RuntimeError('Server log ended before expected event')
                if predicate(line):return line.rstrip()
            raise TimeoutError('Expected log event not received')
        report['startup_line']=wait(lambda line:'Done (' in line,300)
        # Drain old startup messages: a discovery log is not an enabled-pack proof.
        while not events.empty():events.get_nowait()
        proc.stdin.write('datapack list enabled\n');proc.stdin.flush()
        report['enabled_packs_line']=wait(lambda line:all(v in line for v in (
            'data pack','enabled','file/NeverOverworld.zip','file/NeverNether.zip','file/'+OVERLAY)),30)
        proc.stdin.write('stop\n');proc.stdin.flush()
        report['exit_code']=proc.wait(timeout=90)
        reader.join(timeout=5)
        report['targeted_errors']=[line.rstrip() for line in lines if any(term in line for term in (
            'Failed to load registries','Failed to load datapacks','Unknown registry key',
            'Empty or non-existent pool: betterwitchhuts:mobs',
            'Empty or non-existent pool: nova_structures:pale_residence/decor_inside',
            'Empty or non-existent pool: minecraft:minecraft_empty',
            'Block-attached entity at invalid position','[ChunkTaskScheduler] Chunk system error'))]
        report['pass']=report['exit_code']==0 and not report['targeted_errors']
    except Exception as error:
        report['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=5)
        (args.output/'r39-overlay-startup.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if not report['pass'] and log_path.exists():
        print('--- LAST SERVER LOG LINES ---\n'+''.join(log_path.read_text(errors='replace').splitlines(keepends=True)[-60:]))
    return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
