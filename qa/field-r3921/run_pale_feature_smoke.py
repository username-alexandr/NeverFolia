#!/usr/bin/env python3
"""Boot exact R39.21 on Folia 26.2 and execute both restored Pale placed features."""
from pathlib import Path
import hashlib,json,queue,secrets,shutil,subprocess,threading,time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/pale-runtime'
WORK=ROOT/'.work/r3921-pale-runtime'
CORE='845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
SEED=-4651369264513492755

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def need(ok,msg):
    if not ok:raise ValueError(msg)

def exact(root,expected):
    hits=[p for p in Path(root).rglob('*') if p.is_file() and not p.is_symlink() and sha(p)==expected]
    need(len(hits)==1,'Missing/ambiguous exact input '+expected+': '+repr([str(x) for x in hits]))
    return hits[0].resolve()

def main():
    OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=False)
    report={'pass':False,'production_accepted':False,'user_kit_published':False};proc=None;thread=None;lines=[];q=queue.Queue()
    try:
        core=exact(ROOT/'swift-input',CORE);nether=exact(ROOT/'inputs',NETHER)
        build=json.loads((ROOT/'artifacts/pale-feature-build.json').read_text())
        candidate=exact(ROOT/'artifacts',build['output_sha256'])
        dp=WORK/'world/datapacks';dp.mkdir(parents=True);(WORK/'plugins').mkdir()
        shutil.copyfile(candidate,dp/'NeverOverworld.zip');shutil.copyfile(nether,dp/'NeverNether.zip')
        (WORK/'eula.txt').write_text('eula=true\n')
        (WORK/'server.properties').write_text(
            'level-name=world\n'
            f'level-seed={SEED}\n'
            'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
            'server-ip=127.0.0.1\nserver-port=25619\nonline-mode=false\n'
            'view-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n'
            'enable-rcon=false\nenable-status=false\nenable-query=false\n')
        nonce=secrets.token_hex(16)
        cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',
             '-Dneverfolia.r399OceanClosure=true','-Dneverfolia.r3913IceFragments=true',
             '-Dneverfolia.qaNonce='+nonce,'-jar',str(core),'--nogui']
        proc=subprocess.Popen(cmd,cwd=WORK,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/'server.log').open('w') as log:
                for line in proc.stdout:
                    lines.append(line);log.write(line);log.flush();q.put(line)
            q.put(None)
        thread=threading.Thread(target=pump,daemon=True);thread.start()
        done=False;deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            try:line=q.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'Done (' in line:done=True;break
        need(done,'Folia did not reach Done')
        commands=[
            'fill 0 99 0 20 99 20 minecraft:pale_oak_planks',
            'fill 0 100 0 20 110 20 minecraft:air',
            'place feature nova_structures:pale_moss_small 5 100 5',
            'place feature nova_structures:pale_moss_floor 15 100 15',
            'save-all flush',
        ]
        for command in commands:
            proc.stdin.write(command+'\n');proc.stdin.flush();time.sleep(2)
        time.sleep(6)
        proc.stdin.write('stop\n');proc.stdin.flush();code=proc.wait(timeout=120);thread.join(timeout=10)
        need(code==0 and not thread.is_alive(),'Unclean Folia shutdown')
        bad=(
          'Failed to load datapacks','Failed to load function','Failed to parse','Unknown registry key',
          'Serialization errors','Failed to decode value','Empty or non-existent pool:',
          'Couldn\'t load tag','Couldn\'t parse','Exception loading structure','porting_lib:',
          'NoSuchMethodError','NoClassDefFoundError','Failed to place feature'
        )
        targeted=[x.strip() for x in lines if any(t in x for t in bad)]
        placed=[x.strip() for x in lines if 'Placed feature' in x]
        report.update({'exit_code':code,'nonce':nonce,'core_sha256':CORE,'nether_sha256':NETHER,
                       'pack_sha256':build['output_sha256'],'targeted_errors':targeted,
                       'placed_feature_feedback':placed,'commands':commands})
        need(not targeted,'Targeted runtime errors: '+repr(targeted[:20]))
        need(len(placed)>=2,'Both Pale features did not report successful placement: '+repr(placed))
        report['pass']=True
    except Exception as e:
        report['error']=repr(e)
    finally:
        if proc and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.kill()
                try:proc.wait(timeout=10)
                except Exception:pass
        if thread:thread.join(timeout=5)
        (OUT/'pale-feature-runtime.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print('R3921_PALE_RUNTIME',json.dumps(report,ensure_ascii=False),flush=True)
    need(report['pass'],'Pale feature runtime failed')

if __name__=='__main__':main()
