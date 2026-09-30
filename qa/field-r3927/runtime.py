#!/usr/bin/env python3
from pathlib import Path
import json,queue,shutil,subprocess,threading,time,uuid
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3927-runtime'
def need(v,m):
    if not v:raise ValueError(m)
def main():
    f=WORK/'fixture';p=f/'world/datapacks';p.mkdir(parents=True)
    for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/n,p/n)
    (f/'plugins').mkdir();shutil.copyfile(ROOT/'.work/r3927-build/R3927ClassifierQa.jar',f/'plugins/R3927ClassifierQa.jar')
    (f/'eula.txt').write_text('eula=true\n');(f/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25613\nonline-mode=true\nenable-status=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    nonce=uuid.uuid4().hex;proof=OUT/'proof';proof.mkdir();cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r3927OceanClassifier=true',f'-Dneverfolia.r3927ReportDirectory={proof}',f'-Dneverfolia.qaNonce={nonce}','-jar',str(ROOT/'candidate/server.jar'),'--nogui']
    lines=[];q=queue.Queue();proc=subprocess.Popen(cmd,cwd=f,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
    def pump():
        with (OUT/'runtime.log').open('w') as s:
            for line in proc.stdout:lines.append(line);s.write(line);s.flush();q.put(line)
        q.put(None)
    t=threading.Thread(target=pump,daemon=True);t.start();ok=False;deadline=time.monotonic()+420
    try:
        while time.monotonic()<deadline:
            try:line=q.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'R3927 FIXTURE ' in line:need('R3927 FIXTURE PASS '+nonce in line,line.rstrip());ok=True;break
        need(ok,'No R3927 PASS');rp=f/'plugins/R3927ClassifierQa/result.json';need(rp.is_file(),'Missing result');r=json.loads(rp.read_text());need(r.get('pass') is True and r.get('nonce')==nonce,'Bad result');need(len(r.get('cases',[]))==6,'Case count')
        proc.stdin.write('stop\n');proc.stdin.flush();code=proc.wait(timeout=120);t.join(timeout=10);need(code==0 and any('Done (' in x for x in lines),'Lifecycle')
        reports=[json.loads(x.read_text()) for x in proof.glob('*.json')];need(all(x.get('read_max_y')==128 and x.get('reads_above_sea_level')==0 for x in reports),'Above sea read')
        summary={'pass':True,'exit_code':code,'cases':r['cases'],'proof_reports':len(reports),'read_max_y':128,'reads_above_sea_level':0,'production_accepted':False};(OUT/'runtime.json').write_text(json.dumps(summary,indent=2)+'\n');print('R3927_RUNTIME '+json.dumps(summary),flush=True)
    finally:
        if proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:proc.kill();proc.wait(timeout=10)
        t.join(timeout=10)
if __name__=='__main__':main()
