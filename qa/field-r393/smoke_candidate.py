#!/usr/bin/env python3
"""Bounded real-server registry/start/restart test for the full R39.3 pack.
Uses the existing repository's isolated CI EULA convention, never a user's world.
No player, template placement, combat or water-geometry acceptance is claimed.
"""
from pathlib import Path
import argparse,hashlib,json,queue,shutil,subprocess,threading,time
EXPECTED={'server.jar':'411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32','NeverOverworld.zip':'a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be','NeverNether.zip':'5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'}
SEED=-4651369264513492755

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def phase(candidate,folder,out,name):
    report={'pass':False};proc=None;reader=None;lines=[];events=queue.Queue()
    try:
        proc=subprocess.Popen(['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx3G','-jar',str(candidate/'server.jar'),'--nogui'],cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (out/(name+'.log')).open('w') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start()
        def wait(predicate,seconds):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                try:line=events.get(timeout=1)
                except queue.Empty:
                    if proc.poll() is not None:raise RuntimeError('Server exited before expected event')
                    continue
                if line is None:raise RuntimeError('Log ended before expected event')
                if predicate(line):return line.rstrip()
            raise TimeoutError('Expected server event not received')
        report['startup_line']=wait(lambda s:'Done (' in s,300)
        while not events.empty():events.get_nowait()
        proc.stdin.write('datapack list enabled\n');proc.stdin.flush()
        report['enabled_line']=wait(lambda s:all(v in s for v in ('data pack','enabled','file/NeverOverworld.zip','file/NeverNether.zip')),30)
        proc.stdin.write('stop\n');proc.stdin.flush();report['exit_code']=proc.wait(timeout=90);reader.join(timeout=5)
        patterns=('Failed to load registries','Failed to load datapacks','Unknown registry key','Block-attached entity at invalid position','Empty or non-existent pool','[ChunkTaskScheduler] Chunk system error','Failed to load function','Failed to parse','Couldn\'t load tag','Error loading registry data')
        report['targeted_errors']=[s.rstrip() for s in lines if any(p in s for p in patterns)]
        report['warnings_and_errors']=[s.rstrip() for s in lines if ' WARN]' in s or ' ERROR]' in s]
        report['pass']=report['exit_code']==0 and not report['targeted_errors']
    except Exception as error:report['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=5)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','work','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.candidate=a.candidate.resolve();a.work=a.work.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    report={'pass':False,'scope':'Registry loading, enabled full packs, graceful start/stop and second startup only. No template placement, water geometry or mob behavior proof.','seed':str(SEED),'bind':'127.0.0.1:25599','inputs':EXPECTED,'production_accepted':False}
    try:
        java=subprocess.run(['java','-version'],capture_output=True,text=True,check=True)
        report['java_version']=java.stderr+java.stdout
        if 'version "25' not in report['java_version']:raise ValueError('Java 25 required')
        for name,value in EXPECTED.items():
            if sha(a.candidate/name)!=value:raise ValueError('Unexpected candidate bytes: '+name)
        a.work.mkdir(parents=True,exist_ok=False);packs=a.work/'world/datapacks';packs.mkdir(parents=True)
        for name in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(a.candidate/name,packs/name)
        (a.work/'eula.txt').write_text('eula=true\n')
        (a.work/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25599\nonline-mode=true\nenforce-secure-profile=true\nview-distance=2\nsimulation-distance=2\nmax-players=1\nenable-query=false\nenable-rcon=false\nenable-status=false\npause-when-empty-seconds=-1\n')
        report['first']=phase(a.candidate,a.work,a.output,'r393-start')
        if report['first']['pass']:report['restart']=phase(a.candidate,a.work,a.output,'r393-restart')
        report['copied_packs_unchanged']=all(sha(packs/name)==EXPECTED[name] for name in ('NeverOverworld.zip','NeverNether.zip'))
        report['pass']=report['first']['pass'] and report.get('restart',{}).get('pass',False) and report['copied_packs_unchanged']
    except Exception as error:report['error']=repr(error)
    finally:(a.output/'r393-startup.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['pass'] else 1
if __name__=='__main__':raise SystemExit(main())
