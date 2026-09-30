#!/usr/bin/env python3
from pathlib import Path
import json,queue,shutil,subprocess,threading,time,uuid
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3926-runtime'
SEED=-4651369264513492755

def need(ok,msg):
    if not ok:raise ValueError(msg)

def main():
    folder=WORK/'fixture';packs=folder/'world/datapacks';packs.mkdir(parents=True)
    for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/n,packs/n)
    (folder/'plugins').mkdir();shutil.copyfile(ROOT/'.work/r3926-build/R3926ClassifierQa.jar',folder/'plugins/R3926ClassifierQa.jar')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25612\nonline-mode=true\nenable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    nonce=uuid.uuid4().hex;proof=OUT/'proof';proof.mkdir()
    cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r3926OceanClassifier=true',f'-Dneverfolia.r3926ReportDirectory={proof}',f'-Dneverfolia.qaNonce={nonce}','-jar',str(ROOT/'candidate/server.jar'),'--nogui']
    lines=[];events=queue.Queue()
    proc=subprocess.Popen(cmd,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
    def pump():
        with (OUT/'runtime.log').open('w') as f:
            for line in proc.stdout:lines.append(line);f.write(line);f.flush();events.put(line)
        events.put(None)
    t=threading.Thread(target=pump,daemon=True);t.start()
    success=False;deadline=time.monotonic()+420
    try:
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'R3926 FIXTURE ' in line:
                need('R3926 FIXTURE PASS '+nonce in line,'Fixture failed: '+line.rstrip());success=True;break
        need(success,'No fresh R3926 fixture PASS')
        result_path=folder/'plugins/R3926ClassifierQa/result.json'
        need(result_path.is_file(),'Missing fixture result')
        result=json.loads(result_path.read_text())
        need(result.get('pass') is True and result.get('nonce')==nonce,'Stale/failed fixture result')
        need(len(result.get('cases',[]))==8 and all(x.get('pass') for x in result['cases']),'Incomplete fixture matrix')
        proc.stdin.write('stop\n');proc.stdin.flush();exit_code=proc.wait(timeout=120);t.join(timeout=10)
        need(exit_code==0 and any('Done (' in x for x in lines),'Abnormal server lifecycle')
        reports=[json.loads(p.read_text()) for p in proof.glob('*.json')]
        need(all(r.get('read_max_y')==128 and r.get('reads_above_sea_level')==0 for r in reports),'Above-sea read contract violated')
        summary={'pass':True,'nonce':nonce,'exit_code':exit_code,'cases':result['cases'],'proof_reports':len(reports),'read_max_y':128,'reads_above_sea_level':0,'production_accepted':False}
        (OUT/'runtime.json').write_text(json.dumps(summary,indent=2)+'\n')
        print('R3926_RUNTIME '+json.dumps(summary),flush=True)
    finally:
        if proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:proc.kill();proc.wait(timeout=10)
        t.join(timeout=10)

if __name__=='__main__':main()
