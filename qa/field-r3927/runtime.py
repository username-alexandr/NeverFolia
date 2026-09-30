#!/usr/bin/env python3
"""Natural paired R39.26 -> R39.27 regression on fresh worlds."""
from pathlib import Path
import collections,hashlib,importlib.util,json,os,queue,shutil,subprocess,threading,time,uuid
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3927-runtime'
SEED=-4651369264513492755
CENTERS=((7,1),(1,-4),(-197,-217),(-169,-250),(-189,-223),(-1699,-769))
TARGETS=sorted({(cx+dx,cz+dz) for cx,cz in CENTERS for dx in (-1,0,1) for dz in (-1,0,1)},key=lambda p:f'{p[0]},{p[1]}')
BAD=('Failed to load registries','Failed to load datapacks','Unknown registry key','[ChunkTaskScheduler] Chunk system error','Exception in server tick loop','R3927 strict AIR provenance failed')

def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,obj):path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def prepare(name):
    folder=WORK/name;folder.mkdir();packs=folder/'world/datapacks';packs.mkdir(parents=True)
    source=ROOT/'baseline' if name=='baseline' else ROOT/'candidate'
    for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(source/n if name!='baseline' else source/'world/datapacks'/n,packs/n)
    (folder/'plugins').mkdir();shutil.copyfile(ROOT/'.work/r3927-build/R3927NaturalQa.jar',folder/'plugins/R3927NaturalQa.jar')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25613\nonline-mode=true\nenable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    return folder

def phase(name,folder,jar,candidate):
    result={'pass':False};lines=[];events=queue.Queue();nonce=uuid.uuid4().hex
    proof=OUT/('proof-'+name);proof.mkdir();proc=None;reader=None
    try:
        flags=[f'-Dneverfolia.qaNonce={nonce}']
        if candidate:
            flags += ['-Dneverfolia.r3927OceanClassifier=true','-Dneverfolia.r3927StrictAir=true',f'-Dneverfolia.r3927ReportDirectory={proof}']
        else:
            flags += ['-Dneverfolia.r3926OceanClassifier=true',f'-Dneverfolia.r3926ReportDirectory={proof}']
        cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx5G']+flags+['-jar',str(jar),'--nogui']
        result['command']=cmd
        proc=subprocess.Popen(cmd,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'.log')).open('w') as f:
                for line in proc.stdout:lines.append(line);f.write(line);f.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start()
        success=False;deadline=time.monotonic()+700
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'R3927 NATURAL QA ' in line:
                need('R3927 NATURAL QA PASS '+nonce in line,'Natural QA failed: '+line.rstrip());success=True;break
        need(success,'No fresh natural QA PASS')
        report_path=folder/'plugins/R3927NaturalQa/result.json';need(report_path.is_file(),'Missing QA report')
        observed=json.loads(report_path.read_text());result['observed']=observed
        need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('completed_chunks')==54,'Stale/incomplete QA')
        proc.stdin.write('stop\n');proc.stdin.flush();result['exit_code']=proc.wait(timeout=150);reader.join(timeout=10)
        need(result['exit_code']==0 and any('Done (' in l for l in lines),'Abnormal lifecycle')
        result['targeted_errors']=[l.rstrip() for l in lines if any(b in l for b in BAD)];need(not result['targeted_errors'],'Targeted server errors')
        rows=[json.loads(p.read_text()) for p in proof.glob('*.json')]
        by={(r['chunk_x'],r['chunk_z']):r for r in rows if (r.get('chunk_x'),r.get('chunk_z')) in set(TARGETS)}
        result['proof_target_count']=len(by)
        result['proof']=list(by.values())
        if candidate:
            need(len(by)==54,'Missing R3927 target proof')
            need(all(r.get('noise_oracle_available') is True for r in by.values()),'Noise oracle unavailable in natural target')
            need(all(r.get('missed_expected_water')==0 and r.get('remaining_oracle_unknown_air')==0 and r.get('oracle_unavailable_air')==0 for r in by.values()),'Strict provenance residue')
            need(all(r.get('reads_above_sea_level')==0 and r.get('read_max_y')==128 for r in by.values()),'Above-sea read regression')
        result['pass']=True
    except Exception as e:result['error']=repr(e)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=40)
            except Exception:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=10)
        save(OUT/(name+'-phase.json'),result)
    print('R3927_PHASE '+name+' '+json.dumps({k:result.get(k) for k in ('pass','error','exit_code','proof_target_count')}),flush=True)
    return result

def compare_worlds(a_folder,b_folder):
    observer=load('r3927_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
    paired=load('r3927_pair',ROOT/'scripts/probe-never-overworld-paired-r12.py')
    nbt=observer.load_nbt(ROOT)
    a=paired.saved_volume(observer,nbt,a_folder/'world/dimensions/minecraft/overworld/region',TARGETS,{'normal_stop':True,'exit_code':0})
    b=paired.saved_volume(observer,nbt,b_folder/'world/dimensions/minecraft/overworld/region',TARGETS,{'normal_stop':True,'exit_code':0})
    counts=collections.Counter();bad=[];changed=0;protected=0;geometry=0
    for cx,cz in TARGETS:
        boxes=paired.pdc_boxes(a.roots[(cx,cz)])
        if boxes!=paired.pdc_boxes(b.roots[(cx,cz)]):geometry+=1
        for sy in range(-32,32):
            left=a.section((cx,sy,cz));right=b.section((cx,sy,cz))
            for i,(old,new) in enumerate(zip(left,right)):
                if old==new:continue
                x=cx*16+(i&15);y=sy*16+(i>>8);z=cz*16+((i>>4)&15);changed+=1
                key=old['Name']+' => '+new['Name'];counts[key]+=1
                allowed=old['Name'] in ('minecraft:air','minecraft:cave_air','minecraft:void_air') and new=={'Name':'minecraft:water','Properties':{'level':'0'}} and y<=128
                if not allowed and len(bad)<40:bad.append({'pos':[x,y,z],'old':old,'new':new})
                if any(bb[0]-1<=x<=bb[3]+1 and max(-511,bb[1]-1)<=y<=min(128,bb[4]+1) and bb[2]-1<=z<=bb[5]+1 for bb in boxes):
                    protected+=1
    return {'pass':changed>0 and not bad and protected==0 and geometry==0,'changed_cells':changed,'transitions':dict(counts),'bad_examples':bad,'protected_changes':protected,'piece_metadata_changed_chunks':geometry}

def main():
    WORK.mkdir(parents=True,exist_ok=False)
    build=json.loads((OUT/'build.json').read_text())
    base=ROOT/'baseline/server.jar';candidate=ROOT/'candidate/server.jar'
    need(sha(base)==build['base_core_sha256'] and sha(candidate)==build['candidate_core_sha256'],'Wrong core inputs')
    folders={'baseline':prepare('baseline'),'candidate':prepare('candidate')}
    report={'pass':False,'production_accepted':False,'phases':{}}
    report['phases']['baseline']=phase('baseline',folders['baseline'],base,False)
    report['phases']['candidate']=phase('candidate',folders['candidate'],candidate,True)
    need(all(p['pass'] for p in report['phases'].values()),'Natural phase failed')
    report['comparison']=compare_worlds(folders['baseline'],folders['candidate'])
    need(report['comparison']['pass'],'R39.26 -> R39.27 changed non-water state or no useful delta')
    base_iso=sum(r['isolated_air'] for r in report['phases']['baseline']['observed']['chunks'])
    cand_iso=sum(r['isolated_air'] for r in report['phases']['candidate']['observed']['chunks'])
    report['isolated_air_baseline']=base_iso;report['isolated_air_candidate']=cand_iso
    need(cand_iso<=base_iso,'Isolated-air regression')
    proof=report['phases']['candidate']['proof']
    report['native_sea_seed_cells']=sum(r.get('native_sea_seed_cells',0) for r in proof)
    report['restored_noise_water']=sum(r.get('restored_noise_water',0) for r in proof)
    report['connected_air_to_water']=sum(r.get('connected_air_to_water',0) for r in proof)
    report['carved_air_witness']=sum(r.get('carved_air_witness',0) for r in proof)
    need(report['native_sea_seed_cells']>0,'Native sea fallback never activated in natural sample')
    report['pass']=True;save(OUT/'runtime.json',report)
    print('R3927_RESULT '+json.dumps({k:v for k,v in report.items() if k not in ('phases',)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
