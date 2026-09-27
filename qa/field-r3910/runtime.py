#!/usr/bin/env python3
"""Real isolated integration tests. Bounded geometry acceptance is not production.
No user worlds, no old result reuse, no modification of inherited order-test results.
"""
from pathlib import Path
import collections,hashlib,importlib.util,json,os,re,shutil,subprocess,threading,time,uuid,zipfile
import witness
from build import BASE,PACK,NETHER
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3910-live'
SEED=-4651369264513492755
CENTERS=((7,1),(1,-4),(-197,-217),(-169,-250),(-189,-223),(-1699,-769))
TARGETS={(cx+dx,cz+dz) for cx,cz in CENTERS for dx in (-1,0,1) for dz in (-1,0,1)}
BAD=('Failed to load registries','Failed to load datapacks','Overworld settings missing','Unknown registry key','Block-attached entity at invalid position','[ChunkTaskScheduler] Chunk system error','Exception in server tick loop','R3910 owner changed','Cannot retain R3910','R3910 invalid','R3910 wrong')

def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,data):path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def prepare(name,fixture=False):
    folder=WORK/name;packs=folder/'world/datapacks';packs.mkdir(parents=True,exist_ok=False)
    for filename in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/filename,packs/filename)
    plugins=folder/'plugins';plugins.mkdir();name='R3910CavityQa' if fixture else 'R395Qa'
    shutil.copyfile(ROOT/'.work/r3910-build'/(name+'.jar'),plugins/(name+'.jar'))
    # Existing repository convention: EULA acceptance is for this ephemeral CI
    # process only. The distributable test kit must keep eula=false.
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25610\nonline-mode=true\nenable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    return folder

def phase(name,folder,jar,enabled,reverse=False,fixture=False):
    result={'pass':False,'enabled':enabled,'reverse':reverse,'fixture':fixture};proc=None;reader=None;lines=[]
    proof=OUT/('proof-'+name);proof.mkdir(exist_ok=False);nonce=uuid.uuid4().hex
    plugin='R3910CavityQa' if fixture else 'R395Qa';path=folder/'plugins'/plugin/'result.json'
    marker='R3910 CAVITY QA ' if fixture else 'R395 NATURAL QA '
    try:
        if path.exists():
            need(not path.is_symlink(),'Unsafe old result');shutil.copyfile(path,OUT/(name+'-previous-result.json'));path.unlink()
        command=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',f'-Dneverfolia.r3910OceanClosure={str(enabled).lower()}',f'-Dneverfolia.r3910ReportDirectory={proof}', '-Dneverfolia.r3910SaveWitnesses=true',f'-Dneverfolia.qaReverse={str(reverse).lower()}',f'-Dneverfolia.qaNonce={nonce}','-jar',str(jar),'--nogui']
        result['command']=command
        proc=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'.log')).open('w') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush()
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+650
        while time.monotonic()<deadline:
            if any(marker in line for line in lines):break
            if proc.poll() is not None:raise RuntimeError('Exited before current QA result')
            time.sleep(.2)
        need(any(marker+'PASS' in line for line in lines) and not any(marker+'FAIL' in line for line in lines),'No current successful QA marker')
        need(path.is_file() and not path.is_symlink(),'Fresh report missing')
        observed=json.loads(path.read_text());need(observed.get('pass') is True,'Current report failed')
        if fixture:
            need(observed.get('nonce')==nonce,'Stale fixture report')
            cases=observed.get('cases',[]);need(len(cases)>=30 and all(r['pass'] is True for r in cases),'Incomplete fixtures')
        else:
            need(observed.get('seed')==SEED and observed.get('reverse_order') is reverse,'Wrong seed/order')
            rows=observed.get('chunks',[]);actual=[(r['chunk_x'],r['chunk_z']) for r in rows]
            expected=sorted(TARGETS,key=lambda p:f'{p[0]},{p[1]}',reverse=reverse)
            need(actual==expected and len(set(actual))==54 and observed.get('completed_chunks')==54,'Wrong/missing natural target')
        result['observed']=observed;save(OUT/(name+'-observed.json'),observed)
        proc.stdin.write('stop\n');proc.stdin.flush();result['exit_code']=proc.wait(timeout=150);reader.join(timeout=15)
        need(not reader.is_alive(),'Incomplete log')
        need(result['exit_code']==0 and any('Done (' in line for line in lines),'Unclean startup/shutdown')
        result['targeted_errors']=[line.rstrip() for line in lines if any(b in line for b in BAD)]
        need(not result['targeted_errors'],'Targeted server error')
        need(sha(folder/'world/datapacks/NeverOverworld.zip')==PACK and sha(folder/'world/datapacks/NeverNether.zip')==NETHER,'Datapack changed')
        result['pass']=True
    except Exception as error:result['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=15)
        save(OUT/(name+'-phase.json'),result)
    print('R3910_PHASE '+name+' '+json.dumps({k:result[k] for k in ('pass','exit_code','error') if k in result}),flush=True)
    return result

def volume(folder,name):
    observer=load('observer3910_'+name,ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
    paired=load('paired3910_'+name,ROOT/'scripts/probe-never-overworld-paired-r12.py')
    nbt=observer.load_nbt(ROOT);region=folder/'world/dimensions/minecraft/overworld/region'
    v=paired.saved_volume(observer,nbt,region,sorted(TARGETS),{'normal_stop':True,'exit_code':0})
    with zipfile.ZipFile(OUT/(name+'-saved-regions.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted({region/f'r.{cx//32}.{cz//32}.mca' for cx,cz in TARGETS}):z.write(p,p.relative_to(folder).as_posix())
        for p in region.glob('c.*.*.mcc'):
            parts=p.name.split('.')
            if len(parts)==4 and (int(parts[1]),int(parts[2])) in TARGETS:z.write(p,p.relative_to(folder).as_posix())
        p=folder/'world/level.dat'
        if p.is_file():z.write(p,'world/level.dat')
    return v

def compare(a,b):
    counts=collections.Counter();changed_chunks=set();writes=set();bad=[];changed=0;non_air=0
    for cx,cz in sorted(TARGETS):
        for sy in range(-32,32):
            left=a.section((cx,sy,cz));right=b.section((cx,sy,cz))
            need(len(left)==len(right)==4096,'Incomplete saved section')
            if left==right:continue
            for i,(old,new) in enumerate(zip(left,right)):
                if old==new:continue
                pos=(cx*16+(i&15),sy*16+(i>>8),cz*16+((i>>4)&15));changed+=1;changed_chunks.add((cx,cz))
                counts[old['Name']+' => '+new['Name']]+=1
                if old['Name'] in ('minecraft:air','minecraft:cave_air','minecraft:void_air') and new['Name']=='minecraft:water' and str(new.get('Properties',{}).get('level','0'))=='0' and -511<=pos[1]<=128:writes.add(pos)
                else:
                    non_air+=1
                    if len(bad)<100:bad.append({'position':pos,'old':old,'new':new})
    return {'changed_cells':changed,'changed_chunks':len(changed_chunks),'non_air_to_source_changes':non_air,'transitions':dict(counts),'bad_examples':bad},writes

def certify_phase(name,expected_writes=None,fixture=False):
    directory=OUT/('proof-'+name);records=[];seen=set();observed_writes=set();visits=0
    for path in sorted(directory.glob('*.json')):
        d=json.loads(path.read_text());key=(d['chunk_x'],d['chunk_z'])
        if not fixture and key not in TARGETS:continue
        need(d['revision']=='R3910-R399-positive-ocean-integration','Wrong witness revision')
        if not fixture:need(key not in seen,'Duplicate target witness')
        seen.add(key);filename=d.get('witness_file','')
        need(re.fullmatch(r'-?\d+_-?\d+_\d+\.witness\.gz',filename) is not None,'Unsafe/missing witness filename')
        certificate=witness.read(directory/filename)
        need(tuple(certificate['chunk'])==key and certificate['added']==d['added_air_to_water'] and certificate['visited']==d['visited_witness_cells'],'Witness counts/identity differ')
        observed_writes.update(certificate['writes']);visits+=certificate['visited']
        records.append({'chunk':key,'added':certificate['added'],'missing_cache_chunks':d['missing_cache_chunks'],'protected_owner_air':d['protected_owner_air'],'unproven_owner_air':d['unproven_owner_air'],'elapsed_ms':d['elapsed_ms'],'witness':filename,'sha256':sha(directory/filename)})
    need(bool(records),'No replayed proofs')
    if not fixture:need(seen==TARGETS,'Missing target witnesses')
    if expected_writes is not None:need(observed_writes==expected_writes,'Saved AIR-to-WATER differences do not equal certified writes')
    result={'pass':True,'records':records,'unique_writes':len(observed_writes),'visited_total':visits,'global_closure_proven':False,'scope':'Independent Python reachability replay of recorded finite snapshots. Does not prove acquisition race-freedom or global closure.'}
    save(OUT/(name+'-witness-replay.json'),result);print('R3910_WITNESSES '+name+' '+str(len(records))+' writes='+str(len(observed_writes)),flush=True)
    return result

def main():
    WORK.mkdir(parents=True,exist_ok=False)
    build=json.loads((OUT/'build.json').read_text());base=ROOT/'baseline/server.jar';candidate=ROOT/'candidate/server.jar'
    need(sha(base)==BASE and sha(candidate)==build['candidate_core_sha256'],'Wrong compiled inputs')
    summary={'production_accepted':False,'global_closure_proven':False,'bounded_integration_pass':False,'build':build,'phases':{},'comparisons':{},'witnesses':{},'seed':str(SEED)}
    volumes={};folders={}
    try:
        fixtures=prepare('fixtures',True);summary['phases']['fixtures']=phase('fixtures',fixtures,candidate,True,fixture=True)
        need(summary['phases']['fixtures']['pass'],'Detached real-chunk fixtures failed')
        summary['witnesses']['fixtures']=certify_phase('fixtures',fixture=True)
        plans=[('baseline',base,False,False),('baseline_reverse',base,False,True),('candidate_off',candidate,False,False),('candidate',candidate,True,False),('reverse',candidate,True,True)]
        for name,jar,enabled,reverse in plans:
            folder=prepare(name);folders[name]=folder;summary['phases'][name]=phase(name,folder,jar,enabled,reverse)
            need(summary['phases'][name]['pass'],'Phase failed: '+name)
            volumes[name]=volume(folder,name)
        # The same saved candidate world is restarted, not rebuilt.
        summary['phases']['restart']=phase('restart',folders['candidate'],candidate,True)
        need(summary['phases']['restart']['pass'],'Restart failed');volumes['restart']=volume(folders['candidate'],'restart')
        for label,left,right in [('disabled','baseline','candidate_off'),('forward','baseline','candidate'),('reverse','baseline_reverse','reverse'),('restart','candidate','restart'),('inherited_order','baseline','baseline_reverse')]:
            report,writes=compare(volumes[left],volumes[right]);summary['comparisons'][label]=report
            save(OUT/(label+'-comparison.json'),report)
            if label in ('disabled','restart'):need(report['changed_cells']==0,label+' altered saved blocks')
            elif label in ('forward','reverse'):
                need(report['changed_cells']>0 and report['non_air_to_source_changes']==0,'Unexpected same-order block changes: '+label)
                summary['witnesses'][label]=certify_phase(right,writes)
        # Inherited order differences stay visible and are NOT called a pass of
        # the earlier strict R397 order test. This is a separate bounded contract.
        summary['strict_cross_order_match']=summary['comparisons']['inherited_order']['changed_cells']==0
        summary['bounded_integration_pass']=True
        summary['inputs_unchanged']=sha(base)==BASE and sha(candidate)==build['candidate_core_sha256']
        need(summary['inputs_unchanged'],'Input kernel changed during QA')
    except Exception as error:summary['error']=repr(error);summary['bounded_integration_pass']=False
    finally:
        save(OUT/'r3910-runtime.json',summary)
        print('R3910_RESULT '+json.dumps({k:v for k,v in summary.items() if k not in ('phases','witnesses','build')}),flush=True)
    need(summary['bounded_integration_pass'],'R3910 integration not accepted; evidence retained')
if __name__=='__main__':main()
