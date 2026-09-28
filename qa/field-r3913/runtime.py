#!/usr/bin/env python3
"""Disposable loopback server tests; fresh results and full block snapshots."""
from pathlib import Path
import collections,gzip,hashlib,json,queue,secrets,shutil,struct,subprocess,threading,time
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3913-runtime';SEED=-4651369264513492755
TARGETS=sorted({(cx+dx,cz+dz) for cx,cz in ((-189,-223),(-169,-253),(-197,-217)) for dx in (-1,0,1) for dz in (-1,0,1)},key=lambda c:f'{c[0]},{c[1]}')
def need(ok,why):
    if not ok:raise ValueError(why)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,r):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
def setup(name):
    p=WORK/name;(p/'world/datapacks').mkdir(parents=True,exist_ok=False);(p/'plugins').mkdir()
    for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/n,p/'world/datapacks'/n)
    shutil.copyfile(ROOT/'.work/r3913/R3913IceQa.jar',p/'plugins/R3913IceQa.jar')
    (p/'eula.txt').write_text('eula=true\n')
    (p/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25613\nonline-mode=true\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\n')
    return p

def phase(name,jar,folder,enabled,fixtures=False):
    nonce=secrets.token_hex(16);p=None;thread=None;events=queue.Queue();lines=[]
    r={'pass':False,'name':name,'nonce':nonce,'ice_enabled':enabled,'fixtures':fixtures};dest=OUT/'r3913-phases'/name;dest.mkdir(parents=True,exist_ok=False)
    result=folder/'plugins/R3913IceQa/result.json'
    if result.exists():result.rename(dest/'previous-result.json')
    try:
        cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r399OceanClosure=true',
            '-Dneverfolia.r3913IceFragments='+str(enabled).lower(),'-Dneverfolia.r3913IceReport='+str(dest/'ice-traces'),
            '-Dneverfolia.iceQaNonce='+nonce,'-Dneverfolia.iceQaFixtures='+str(fixtures).lower(),'-jar',str(jar),'--nogui']
        p=subprocess.Popen(cmd,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def readlog():
            with (dest/'server.log').open('w',encoding='utf-8') as f:
                for line in p.stdout:f.write(line);f.flush();lines.append(line);events.put(line)
            events.put(None)
        thread=threading.Thread(target=readlog,daemon=True);thread.start();done=False;passed=False;deadline=time.monotonic()+650
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if p.poll() is not None:break
                continue
            if line is None:break
            if 'ICE_SAMPLE ' in line or 'ICE_FIXTURE ' in line:print(name,line.strip(),flush=True)
            if 'R3913 QA FAIL '+nonce in line:raise ValueError('Current QA reported FAIL')
            if 'R3913 QA PASS '+nonce in line:passed=True
            if 'Done (' in line:done=True
            if done and passed:break
        need(done and passed,'Current server never completed fresh QA')
        observed=json.loads(result.read_text());need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('seed')==SEED,'Wrong fresh result')
        need(observed.get('fixtures') is fixtures,'Wrong QA mode')
        if fixtures:need(len(observed['rows'])==21 and all(x.get('pass') is True for x in observed['rows']),'Incomplete fixture coverage')
        else:need([(x['chunk_x'],x['chunk_z']) for x in observed['rows']]==TARGETS,'Wrong ordered natural targets')
        p.stdin.write('stop\n');p.stdin.flush();r['exit_code']=p.wait(timeout=120);thread.join(timeout=15)
        need(r['exit_code']==0 and not thread.is_alive(),'Unclean stop')
        bad=('Failed to load datapacks','Overworld settings missing','Chunk system error','snapshot changed before commit','requires completed FEATURES','Exception in server tick loop','The server has not responded for')
        r['targeted_errors']=[s.strip() for s in lines if any(t in s for t in bad)];need(not r['targeted_errors'],'Targeted kernel error')
        r['observed']=observed;shutil.copytree(result.parent,dest/'observed')
        if not fixtures:
            saved=dest/'saved';saved.mkdir()
            for region in (folder/'world').rglob('*.mca'):
                target=saved/region.relative_to(folder/'world');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(region,target)
            for ext in (folder/'world').rglob('*.mcc'):
                target=saved/ext.relative_to(folder/'world');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ext,target)
            for dat in (folder/'world').rglob('level.dat'):
                target=saved/dat.relative_to(folder/'world');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dat,target)
        r['pass']=True
    except Exception as error:r['error']=repr(error)
    finally:
        if p is not None and p.poll() is None:
            try:p.stdin.write('stop\n');p.stdin.flush();p.wait(timeout=40)
            except Exception:
                p.terminate()
                try:p.wait(timeout=15)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
        if thread is not None:thread.join(timeout=15)
        save(dest/'phase.json',r)
    print('ICE_PHASE '+json.dumps({k:v for k,v in r.items() if k!='observed'}),flush=True);return r

def blocks(path,coordinates):
    raw=gzip.decompress(path.read_bytes());offset=0
    def read(n):
        nonlocal offset
        need(n>=0 and offset+n<=len(raw),'Truncated block snapshot');s=raw[offset:offset+n];offset+=n;return s
    def integer():return struct.unpack('>i',read(4))[0]
    def text():return read(struct.unpack('>H',read(2))[0]).decode('utf-8')
    need(text()=='R3913S1','Unknown snapshot format');need((integer(),integer())==coordinates,'Wrong chunk snapshot')
    need(integer()==-512 and integer()==1024,'Wrong full height');n=integer();need(0<n<4096,'Invalid palette size');palette=[text() for _ in range(n)]
    count=integer();need(count==1024*256,'Incomplete block coverage');indices=read(count*4);need(offset==len(raw),'Trailing snapshot data')
    values=[]
    for (i,) in struct.iter_unpack('>i',indices):need(0<=i<n,'Invalid palette index');values.append(palette[i])
    return values

def compare(left,right,allow_ice):
    result={'pass':True,'changed':0,'unexpected':0,'chunks':[]};transitions=collections.Counter()
    for cx,cz in TARGETS:
        name=f'{cx}_{cz}.blocks.gz';a=blocks(OUT/'r3913-phases'/left/'observed'/name,(cx,cz));b=blocks(OUT/'r3913-phases'/right/'observed'/name,(cx,cz))
        changed=bad=0;examples=[]
        for i,(before,after) in enumerate(zip(a,b)):
            if before==after:continue
            changed+=1;transitions[before+' -> '+after]+=1
            allowed=allow_ice and before in ('Block{minecraft:ice}','Block{minecraft:packed_ice}','Block{minecraft:blue_ice}') and after=='Block{minecraft:water}[level=0]'
            if not allowed:bad+=1
            if len(examples)<64:examples.append({'x':cx*16+(i&15),'y':-512+(i>>8),'z':cz*16+((i>>4)&15),'before':before,'after':after,'allowed':allowed})
        result['changed']+=changed;result['unexpected']+=bad;result['chunks'].append({'x':cx,'z':cz,'changed':changed,'unexpected':bad,'examples':examples})
    result['pass']=result['unexpected']==0;result['transitions']=dict(transitions)
    result['scope']='Complete live block snapshots. Independent saved-MCA check is a separate required stage.'
    return result

def main():
    WORK.mkdir(parents=True,exist_ok=False);build=json.loads((OUT/'r3913-build.json').read_text());jar=ROOT/'candidate/server.jar';need(sha(jar)==build['candidate_core_sha256'],'Wrong candidate')
    report={'pass':False,'production_accepted':False,'seed':str(SEED),'phases':{}}
    try:
        report['phases']['fixtures']=phase('fixtures',jar,setup('fixtures'),True,True);need(report['phases']['fixtures']['pass'],'Fixture failure')
        for name,binary,enabled in (('parent',ROOT/'control/server.jar',False),('off',jar,False),('candidate',jar,True)):
            report['phases'][name]=phase(name,binary,setup(name),enabled);need(report['phases'][name]['pass'],'Natural phase failed: '+name)
        report['phases']['restart']=phase('restart',jar,WORK/'candidate',True);need(report['phases']['restart']['pass'],'Restart failed')
        report['comparisons']={'parent_vs_off':compare('parent','off',False),'off_vs_candidate':compare('off','candidate',True),'candidate_vs_restart':compare('candidate','restart',False)}
        need(all(p['pass'] for p in report['comparisons'].values()),'Unexpected state changes')
        # A safe no-op is NOT field acceptance. The independent saved-world stage
        # additionally checks the exact naturally observed ice-sheet witness.
        need(report['comparisons']['off_vs_candidate']['changed']>0,'No natural ice was fixed; do not issue an ineffective release')
        need(sha(jar)==build['candidate_core_sha256'],'Candidate bytes changed')
        for phase_name in ('fixtures','parent','off','candidate'):
            for filename,field in (('NeverOverworld.zip','pack_sha256'),('NeverNether.zip','nether_sha256')):
                need(sha(WORK/phase_name/'world/datapacks'/filename)==build[field],'Input pack changed')
        report['final_candidate_ice_blocks']=sum(row['ice_blocks'] for row in report['phases']['candidate']['observed']['rows'])
        report['pass']=True
    except Exception as e:report['error']=repr(e)
    finally:save(OUT/'r3913-runtime.json',report)
    brief={'pass':report['pass'],'error':report.get('error'),'comparisons':{k:{key:v[key] for key in ('pass','changed','unexpected','transitions')} for k,v in report.get('comparisons',{}).items()}}
    print('R3913_RESULT '+json.dumps(brief),flush=True);need(report['pass'],'Limited ice regression not accepted')
if __name__=='__main__':main()
