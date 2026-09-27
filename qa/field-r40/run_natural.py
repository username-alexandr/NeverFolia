#!/usr/bin/env python3
"""Real isolated R40 smoke/geometry checks. Every phase requires current nonce."""
from pathlib import Path
import hashlib,io,json,os,queue,shutil,subprocess,threading,time,uuid,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'runtime';WORK=ROOT/'.work/r40-natural';CAND=ROOT/'compiled/candidate'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67';SEED=-4651369264513492755
BAD=('Failed to load registries','Failed to load datapacks','Overworld settings missing','Unknown registry key','[ChunkTaskScheduler] Chunk system error','Missing chunkholder when required','R40 owner has no','Exception in server tick loop')
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def main():
    OUT.mkdir(exist_ok=False);WORK.mkdir(parents=True,exist_ok=False)
    build=json.loads((ROOT/'compiled/artifacts/build.json').read_text());need(sha(CAND/'server.jar')==build['candidate_core_sha256'],'Wrong compiled candidate')
    need(sha(ROOT/'baseline/server.jar')==BASE,'Wrong baseline')
    libs=WORK/'libs';libs.mkdir()
    with zipfile.ZipFile(CAND/'server.jar') as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
    providers=[]
    for p in libs.glob('*.jar'):
        with zipfile.ZipFile(p) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():providers.append(p)
    if not providers:
        with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
            options=[]
            for n in z.namelist():
                if 'folia-api' in n and n.endswith('.jar'):
                    raw=z.read(n)
                    with zipfile.ZipFile(io.BytesIO(raw)) as j:
                        if 'org/bukkit/Bukkit.class' in j.namelist():options.append(raw)
            need(len(options)==1,'Missing API');(libs/'folia-api.jar').write_bytes(options[0])
    classes=WORK/'classes';classes.mkdir();cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))))
    p=subprocess.run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(ROOT/'qa/field-r40/R40NaturalQa.java')],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (OUT/'qa-javac.log').write_text(p.stdout);need(p.returncode==0,p.stdout)
    plugin=WORK/'R40NaturalQa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R40NaturalQa\nversion: 1\nmain: R40NaturalQa\napi-version: '26.2'\nfolia-supported: true\n")
    def setup(name):
        f=WORK/name;(f/'world/datapacks').mkdir(parents=True);(f/'plugins').mkdir();shutil.copyfile(plugin,f/'plugins/R40NaturalQa.jar')
        for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(CAND/n,f/'world/datapacks'/n)
        (f/'eula.txt').write_text('eula=true\n')
        (f/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25640\nonline-mode=true\nenable-rcon=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
        return f
    report={'production_accepted':False,'build':build,'phases':{}};fixed=setup('candidate')
    for name,folder,jar,enabled in (('candidate',fixed,CAND/'server.jar',True),('restart',fixed,CAND/'server.jar',True),('baseline',setup('baseline'),ROOT/'baseline/server.jar',False)):
        r={'pass':False};nonce=uuid.uuid4().hex;proof=OUT/(name+'-proof');proof.mkdir();resultpath=folder/'plugins/R40NaturalQa/result.json'
        if resultpath.exists():resultpath.rename(OUT/(name+'-previous-result.json'))
        proc=None;reader=None;lines=[];events=queue.Queue();start=time.monotonic()
        try:
            command=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',f'-Dneverfolia.r40Ocean={str(enabled).lower()}',f'-Dneverfolia.r40ReportDirectory={proof}',f'-Dneverfolia.qaNonce={nonce}','-jar',str(jar),'--nogui']
            proc=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
            def pump():
                with (OUT/(name+'.log')).open('w') as out:
                    for line in proc.stdout:out.write(line);out.flush();lines.append(line);events.put(line)
                events.put(None)
            reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+1100;done=False
            while time.monotonic()<deadline:
                try:line=events.get(timeout=1)
                except queue.Empty:
                    if proc.poll() is not None:break
                    continue
                if line is None:break
                if 'R40 SAMPLE' in line:print(name,line.rstrip(),flush=True)
                if 'R40 NATURAL QA' in line:
                    need('R40 NATURAL QA PASS '+nonce in line,'Current process failed');done=True;break
            need(done,'Natural QA did not finish');observed=json.loads(resultpath.read_text());need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('seed')==SEED,'Invalid current report')
            centers=((7,1),(1,-4),(-197,-217),(-169,-250),(-189,-223),(-1699,-769),(-202,-213));expected={(cx+dx,cz+dz) for cx,cz in centers for dx in (-1,0,1) for dz in (-1,0,1)}
            actual=[(row['chunk_x'],row['chunk_z']) for row in observed['chunks']];need(len(actual)==63 and set(actual)==expected,'Incomplete target set')
            proc.stdin.write('stop\n');proc.stdin.flush();r['exit_code']=proc.wait(timeout=180);reader.join(timeout=15)
            need(not reader.is_alive() and r['exit_code']==0 and any('Done (' in line for line in lines),'Unclean process completion')
            r['targeted_errors']=[line.rstrip() for line in lines if any(b in line for b in BAD)];need(not r['targeted_errors'],'Runtime exceptions')
            records=[json.loads(p.read_text()) for p in proof.glob('*.json')];selected=[v for v in records if (v['chunk_x'],v['chunk_z']) in expected]
            r['proof']={'target_records':len(selected),'all_records':len(records),'missing_snapshots':sum(v['missing_snapshots'] for v in records),'owner_conflicts':sum(v['owner_conflicts'] for v in records),'air_to_water':sum(v['air_to_water'] for v in selected),'plants_to_water':sum(v['plants_to_water'] for v in selected),'max_elapsed_ms':max((v['elapsed_ms'] for v in records),default=0)}
            if enabled and name!='restart':need(len(selected)==63 and not r['proof']['missing_snapshots'] and not r['proof']['owner_conflicts'],'Incomplete/unsafe proof')
            r['observed']=observed;r['pass']=True
            with zipfile.ZipFile(OUT/(name+'-world.zip'),'w',zipfile.ZIP_DEFLATED) as z:
                for p in (folder/'world').rglob('*'):
                    if p.is_file() and 'datapacks' not in p.parts:z.write(p,p.relative_to(folder).as_posix())
            save(OUT/(name+'-observed.json'),observed)
        except Exception as error:r['error']=repr(error)
        finally:
            if proc is not None and proc.poll() is None:
                try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=60)
                except Exception:
                    proc.terminate()
                    try:proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=15)
            if reader is not None:reader.join(timeout=15)
            r['seconds']=round(time.monotonic()-start,2);save(OUT/(name+'-phase.json'),r);report['phases'][name]=r
            print('R40_NATURAL_PHASE',name,json.dumps({k:v for k,v in r.items() if k!='observed'}),flush=True)
        if not r['pass']:break
    a=report['phases'].get('candidate',{}).get('observed',{}).get('chunks',[]);b=report['phases'].get('restart',{}).get('observed',{}).get('chunks',[])
    report['restart_equal']=len(a)==len(b)==63 and [(r['chunk_x'],r['chunk_z'],r['full_state_sha256']) for r in a]==[(r['chunk_x'],r['chunk_z'],r['full_state_sha256']) for r in b]
    report['pass']=len(report['phases'])==3 and all(p['pass'] for p in report['phases'].values()) and report['restart_equal']
    save(OUT/'runtime.json',report);print('R40_RUNTIME_PASS',report['pass'],flush=True);need(report['pass'],'R40 runtime not accepted; retained evidence')
if __name__=='__main__':main()
