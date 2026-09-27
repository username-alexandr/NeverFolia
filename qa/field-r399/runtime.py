#!/usr/bin/env python3
"""Ephemeral loopback CI only. Four real Java phases, no user worlds.
Baseline is R396; candidate changes mine membership only.
"""
from pathlib import Path
import hashlib,json,queue,shutil,subprocess,threading,time,uuid,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r399-runtime'
SEED=-4651369264513492755
BAD=('Failed to load registries','Failed to load datapacks','Overworld settings missing','Unknown registry key','[ChunkTaskScheduler] Chunk system error','Exception in server tick loop','IllegalAccessError','NoSuchMethodError')

def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,value):p.write_text(json.dumps(value,indent=2)+'\n')
def prepare(name):
    folder=WORK/name;packs=folder/'world/datapacks';packs.mkdir(parents=True,exist_ok=False)
    for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/n,packs/n)
    (folder/'plugins').mkdir();shutil.copyfile(ROOT/'.work/r399-build/R399MineQa.jar',folder/'plugins/R399MineQa.jar')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25609\nonline-mode=true\nenable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\nmax-players=1\npause-when-empty-seconds=-1\n')
    return folder

def phase(name,folder,jar,fixed,reload):
    result={'pass':False,'fixed':fixed,'reload':reload};proc=None;reader=None;lines=[];events=queue.Queue()
    nonce=uuid.uuid4().hex;report_path=folder/'plugins/R399MineQa/result.json'
    try:
        if report_path.exists():
            with (OUT/(name+'-previous-result.json')).open('xb') as b:b.write(report_path.read_bytes())
            report_path.unlink()
        command=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx3G',
            f'-Dneverfolia.qaFixedMineGuard={str(fixed).lower()}',f'-Dneverfolia.qaMineReload={str(reload).lower()}',
            '-Dneverfolia.qaNonce='+nonce,'-jar',str(jar),'--nogui']
        result['command']=command
        proc=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'.log')).open('w') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+300;success=False
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'R399 MINE QA ' in line:
                need('R399 MINE QA PASS '+nonce in line,'Current test process reported FAIL')
                success=True;break
        need(success,'No fresh PASS from current process')
        fixture=json.loads(report_path.read_text());result['fixture']=fixture
        save(OUT/(name+'-fixture.json'),fixture)
        need(fixture.get('nonce')==nonce and fixture.get('pass') is True,'Stale/failed fixture report')
        need(fixture.get('fixed') is fixed and fixture.get('reload') is reload,'Wrong fixture mode')
        need(fixture.get('seed')==SEED and fixture.get('completed_chunks')==2,'Wrong seed/incomplete chunks')
        rows=fixture.get('cases',[]);need(len(rows)==(54 if reload else 66),'Incomplete case set')
        need(len({r['name'] for r in rows})==len(rows) and all(r.get('pass') is True for r in rows),'Duplicated or failed cases')
        if reload:need(sum(r['name'].endswith('serialized_geometry_roundtrip') for r in rows)==2,'Missing persisted PDC proof')
        proc.stdin.write('stop\n');proc.stdin.flush();result['exit_code']=proc.wait(timeout=100);reader.join(timeout=10)
        need(not reader.is_alive(),'Incomplete log reader')
        need(result['exit_code']==0 and any('Done (' in l for l in lines),'Abnormal start/stop')
        result['targeted_errors']=[l.rstrip() for l in lines if any(b in l for b in BAD)]
        need(not result['targeted_errors'],'Targeted server errors')
        with zipfile.ZipFile(OUT/(name+'-saved-world-evidence.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted((folder/'world').rglob('*')):
                if p.is_file() and p.suffix in ('.dat','.mca','.mcc'):
                    z.write(p,p.relative_to(folder).as_posix())
        result['case_rows']=len(rows);result['pass']=True
    except Exception as e:result['error']=repr(e)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=10)
        save(OUT/(name+'-phase.json'),result)
    print('R399_PHASE',name,json.dumps({k:v for k,v in result.items() if k in ('pass','error','case_rows','exit_code')}),flush=True)
    return result

def main():
    WORK.mkdir(parents=True,exist_ok=False);build=json.loads((OUT/'build.json').read_text())
    baseline=ROOT/'baseline/server.jar';candidate=ROOT/'candidate/server.jar'
    need(sha(baseline)==build['base_core_sha256'] and sha(candidate)==build['candidate_core_sha256'],'Wrong executable input')
    report={'pass':False,'production_accepted':False,'scope':'Synthetic per-piece PDC fixtures and real reload on baseline R396 and fixed candidate; not ocean or natural-mineshaft acceptance.','seed':str(SEED),'build':build,'phases':{}}
    for label,jar,fixed in (('baseline',baseline,False),('candidate',candidate,True)):
        folder=prepare(label)
        report['phases'][label]=phase(label,folder,jar,fixed,False)
        if report['phases'][label]['pass']:report['phases'][label+'_reload']=phase(label+'_reload',folder,jar,fixed,True)
        else:report['phases'][label+'_reload']={'pass':False,'error':'Initial fixture failed; reload not attempted'}
    expected={'released_left_piece','released_right_piece','released_chunk_face','released_sea_bound','released_above_bedrock',
        'invalid_metadata_0','invalid_metadata_1','invalid_metadata_2','invalid_metadata_3','policy_released_inside'}
    a={r['name']:r for r in report['phases']['baseline'].get('fixture',{}).get('cases',[])}
    b={r['name']:r for r in report['phases']['candidate'].get('fixture',{}).get('cases',[])}
    difference=[]
    if a and set(a)==set(b):difference=sorted(n for n in a if a[n].get('actual')!=b[n].get('actual'))
    expected_full={prefix+n for prefix in ('0,0:','-1,-1:') for n in expected}
    report['changed_named_results']=difference
    report['only_expected_changes']=set(difference)==expected_full
    report['inputs_unchanged']=sha(baseline)==build['base_core_sha256'] and sha(candidate)==build['candidate_core_sha256']
    for name in ('baseline','candidate'):
        for f,k in (('NeverOverworld.zip','pack_sha256'),('NeverNether.zip','nether_sha256')):
            report['inputs_unchanged'] &= sha(WORK/name/'world/datapacks'/f)==build[k]
    report['pass']=all(p.get('pass') is True for p in report['phases'].values()) and report['only_expected_changes'] and report['inputs_unchanged']
    save(OUT/'runtime.json',report)
    print('R399_RESULT',json.dumps({k:v for k,v in report.items() if k not in ('build','phases')}),flush=True)
    need(report['pass'],'R399 bounded regression failed; retain all evidence')

if __name__=='__main__':main()
