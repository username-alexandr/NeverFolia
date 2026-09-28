#!/usr/bin/env python3
"""One isolated CI server process; no external player or production world."""
from __future__ import annotations
import hashlib,json,os,queue,shutil,subprocess,threading,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.work/r3912'; OUT=ROOT/'client-output'

def main():
    folder=WORK/'registry-world'; folder.mkdir(exist_ok=False)
    packs=folder/'world/datapacks'; packs.mkdir(parents=True)
    for name in ('NeverOverworld.zip','NeverNether.zip'): shutil.copyfile(WORK/name,packs/name)
    plugins=folder/'plugins'; plugins.mkdir(); shutil.copyfile(WORK/'R3912EnchantmentQa.jar',plugins/'R3912EnchantmentQa.jar')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25612\nonline-mode=true\nwhite-list=true\nenable-rcon=false\nenable-query=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    nonce=uuid.uuid4().hex; result={'pass':False,'nonce':nonce,'client_launch_tested':False}
    proc=None; reader=None; events=queue.Queue(); lines=[]
    try:
        proc=subprocess.Popen(['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx3G',f'-Dneverfolia.r3912Nonce={nonce}','-jar',str(WORK/'server.jar'),'--nogui'],cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/'registry-server.log').open('w',encoding='utf-8') as stream:
                for line in proc.stdout:
                    stream.write(line);stream.flush();lines.append(line);events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True); reader.start()
        done=False; passed=False; deadline=time.monotonic()+240
        while time.monotonic()<deadline and not (done and passed):
            try: line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None: raise RuntimeError('Server exited before current result')
                continue
            if line is None: raise RuntimeError('Log ended before current result')
            if 'R3912 ENCHANT QA FAIL' in line: raise RuntimeError('Current registry check failed')
            if 'R3912 ENCHANT QA PASS '+nonce in line: passed=True
            if 'Done (' in line: done=True
        if not (done and passed): raise TimeoutError('Missing startup/current result')
        data=json.loads((plugins/'R3912EnchantmentQa/result.json').read_text())
        if data.get('nonce')!=nonce or data.get('pass') is not True: raise ValueError('Stale or failed report')
        if data.get('seed')!='-4651369264513492755' or len(data.get('checks',[]))!=35: raise ValueError('Incomplete registry scope')
        if len({r['id'] for r in data['checks']})!=35 or any(r['actual']!=r['expected'] for r in data['checks']): raise ValueError('Wrong check membership')
        proc.stdin.write('stop\n'); proc.stdin.flush(); code=proc.wait(timeout=100); reader.join(timeout=10)
        if code!=0 or reader.is_alive(): raise ValueError('Unclean shutdown/log drain')
        bad=('Failed to load registries','Failed to load datapacks','Overworld settings missing','Unknown registry key','Exception in server tick loop','Chunk system error')
        errors=[s.rstrip() for s in lines if any(b in s for b in bad)]
        if errors: raise RuntimeError('Targeted server errors: '+repr(errors))
        result.update({'pass':True,'exit_code':code,'fixture':data,'targeted_errors':errors,
                       'scope':'Actual compiled predicate against loaded original pack, on isolated R39.9; no player/Mixin/client test.'})
    except Exception as error: result['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try: proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill();proc.wait(timeout=10)
        if reader is not None: reader.join(timeout=10)
        (OUT/'registry-runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('R3912_REGISTRY '+json.dumps(result,ensure_ascii=False),flush=True)
    if not result['pass']: raise SystemExit(1)
if __name__=='__main__': main()
