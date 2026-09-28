#!/usr/bin/env python3
"""Integrated R3922 field regression for the exact final-candidate lineage."""
from pathlib import Path
import collections,hashlib,importlib.util,json,os,queue,shutil,subprocess,threading,time,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts-r3922';WORK=ROOT/'.work/r3922'
CORE_SHA='845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40'
OW_SHA='9daf27e23300d6687e8cc93cf82c7e6db91f69e4fe605382c6947521f0855590'
NN_SHA='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
SEED=-4651369264513492755
CENTERS=((7,1),(1,-4),(-197,-217),(-169,-250),(-189,-223),(-1699,-769))
TARGETS=frozenset((cx+dx,cz+dz) for cx,cz in CENTERS for dx in (-1,0,1) for dz in (-1,0,1))
AIR={'minecraft:air','minecraft:cave_air','minecraft:void_air'}
ICE={'minecraft:ice','minecraft:packed_ice','minecraft:blue_ice'}
WATER={'Name':'minecraft:water','Properties':{'level':'0'}}

def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,data):
    OUT.mkdir(exist_ok=True);(OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def exact(root,name,digest):
    hits=[p for p in Path(root).rglob(name) if p.is_file() and sha(p)==digest]
    need(len(hits)==1,f'exact input {name}: {hits}')
    return hits[0]

def compile_plugin(core,overworld):
    libs=WORK/'libs';classes=WORK/'classes';libs.mkdir(parents=True);classes.mkdir()
    with zipfile.ZipFile(core) as z:
        for i,name in enumerate(z.namelist()):
            if name.endswith('.jar') and name.startswith(('META-INF/versions/','META-INF/libraries/')):
                (libs/f'{i}-{Path(name).name}').write_bytes(z.read(name))
    expected={}
    with zipfile.ZipFile(overworld) as z:
        for name in z.namelist():
            if name.startswith('data/nova_structures/enchantment/') and name.endswith('.json'):
                data=json.loads(z.read(name))
                if data.get('description',{}).get('translate')=='enchantment.dnt.non_survival_enchant':
                    expected['nova_structures:'+name.split('/enchantment/',1)[1][:-5]]=False
        legitimate=json.loads(z.read('data/nova_structures/tags/enchantment/all_dnt_enchants.json'))['values']
        need(len(expected)==16 and len(legitimate)==17,'technical/gameplay enchantment registry drift')
        need(not set(expected)&set(legitimate),'technical/gameplay overlap')
        expected.update({x:True for x in legitimate})
    expected.update({'minecraft:sharpness':True,'minecraft:protection':True})
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    sources=[ROOT/'client/neverland-enchantment-ui/src/cc/neverland/client/EnchantmentVisibility.java',
             ROOT/'qa/field-r395/R395QaPlugin.java']
    p=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),*map(str,sources)],
                     text=True,capture_output=True)
    OUT.mkdir(exist_ok=True);(OUT/'javac.log').write_text(p.stdout+p.stderr);need(p.returncode==0,'field plugin compilation failed')
    plugin=WORK/'R3922FieldQa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
        for f in classes.rglob('*.class'):z.write(f,f.relative_to(classes).as_posix())
        z.writestr('expected-enchants.json',json.dumps(expected))
        z.writestr('plugin.yml',"name: R395Qa\nversion: '3922'\nmain: R395QaPlugin\napi-version: '26.2'\nfolia-supported: true\n")
    save('expected-enchants.json',expected)
    return plugin

def setup(name,plugin,ow,nn):
    f=WORK/name;packs=f/'world/datapacks';packs.mkdir(parents=True);(f/'plugins').mkdir()
    shutil.copyfile(ow,packs/'NeverOverworld.zip');shutil.copyfile(nn,packs/'NeverNether.zip')
    shutil.copyfile(plugin,f/'plugins/R3922FieldQa.jar')
    (f/'eula.txt').write_text('eula=true\n')
    (f/'server.properties').write_text(
        f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
        'server-ip=127.0.0.1\nserver-port=25622\nonline-mode=false\nenforce-secure-profile=false\n'
        'enable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\n'
        'spawn-protection=0\npause-when-empty-seconds=-1\n')
    return f

def phase(name,folder,core,enabled,reverse=False):
    result={'pass':False,'closure_ice_enabled':enabled,'reverse':reverse};events=queue.Queue();lines=[];p=None;t=None
    proof=OUT/('proof-'+name);ice=OUT/('ice-'+name);proof.mkdir();ice.mkdir()
    resultfile=folder/'plugins/R395Qa/result.json'
    if resultfile.exists():resultfile.unlink()
    try:
        cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',
             '-Dneverfolia.r399OceanClosure='+str(enabled).lower(),
             '-Dneverfolia.r3913IceFragments='+str(enabled).lower(),
             '-Dneverfolia.r399ReportDirectory='+str(proof.resolve()),
             '-Dneverfolia.r3913IceReport='+str(ice.resolve()),
             '-Dneverfolia.qaReverse='+str(reverse).lower(),'-jar',str(core.resolve()),'--nogui']
        p=subprocess.Popen(cmd,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                           text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'.log')).open('w') as log:
                for line in p.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        t=threading.Thread(target=pump,daemon=True);t.start();done=False;deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if p.poll() is not None:break
                continue
            if line is None:break
            if 'R395 SAMPLE' in line and (' 9/' in line or ' 18/' in line or ' 27/' in line or ' 36/' in line or ' 45/' in line or ' 54/' in line):print(name,line.strip(),flush=True)
            if 'R395 NATURAL QA FAIL' in line:raise ValueError('field plugin failed')
            if 'R395 NATURAL QA PASS' in line:done=True;break
        need(done and resultfile.is_file(),'field generation did not finish')
        doc=json.loads(resultfile.read_text());need(doc.get('pass') is True and doc.get('seed')==SEED and doc.get('completed_chunks')==54,'bad field result')
        got={(x['chunk_x'],x['chunk_z']) for x in doc['chunks']};need(got==TARGETS,'target coverage drift')
        p.stdin.write('stop\n');p.stdin.flush();code=p.wait(timeout=180);t.join(timeout=20)
        need(code==0 and not t.is_alive(),'unclean server stop')
        bad=('Failed to load registries','Failed to load datapacks','Unknown registry key','Block-attached entity at invalid position',
             'Empty or non-existent pool:','porting_lib:','[ChunkTaskScheduler] Chunk system error',
             'Missing chunkholder when required','Exception in thread','Exception loading structure','The server has not responded for')
        result['targeted_errors']=[x.strip() for x in lines if any(s in x for s in bad)]
        need(not result['targeted_errors'],'targeted console regression')
        result['observed']=doc
        reports=[json.loads(x.read_text()) for x in proof.glob('*.json')]
        wanted=TARGETS;seen={(x['chunk_x'],x['chunk_z']) for x in reports}
        result['ocean_proof']={'records':len(reports),'target_missing':sorted(wanted-seen),
           'air_to_water':sum(x.get('added_air_to_water',0) for x in reports if (x['chunk_x'],x['chunk_z']) in wanted),
           'protected_air':sum(x.get('protected_owner_air',0) for x in reports if (x['chunk_x'],x['chunk_z']) in wanted),
           'snapshot_conflicts':sum(x.get('snapshot_write_conflicts',0) for x in reports)}
        if enabled:
            need(not result['ocean_proof']['target_missing'],'missing ocean proof for screenshot target')
            need(result['ocean_proof']['snapshot_conflicts']==0,'ocean snapshot conflict')
        result['ice_report_files']=len(list(ice.glob('*.json')))
        result['pass']=True
    except Exception as e:result['error']=repr(e)
    finally:
        if p is not None and p.poll() is None:
            try:p.stdin.write('stop\n');p.stdin.flush();p.wait(timeout=60)
            except Exception:
                p.terminate()
                try:p.wait(timeout=15)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
        if t is not None:t.join(timeout=20)
        save(name+'-phase.json',result)
    print('R3922_PHASE',name,json.dumps({k:v for k,v in result.items() if k not in ('observed','targeted_errors')}),flush=True)
    need(result['pass'],'phase failed: '+name)
    return result

def volume(folder,rows,label):
    observer=load('r3922_observer_'+label,ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
    paired=load('r3922_paired_'+label,ROOT/'scripts/probe-never-overworld-paired-r12.py')
    nbt=observer.load_nbt(ROOT)
    chunks=[(x['chunk_x'],x['chunk_z']) for x in rows]
    region=folder/'world/dimensions/minecraft/overworld/region'
    return paired,paired.saved_volume(observer,nbt,region,chunks,{'normal_stop':True,'exit_code':0})

def compare(left_name,left_folder,left_rows,right_name,right_folder,right_rows,allow_fixes):
    paired,a=volume(left_folder,left_rows,left_name);_,b=volume(right_folder,right_rows,right_name)
    result={'changed':0,'unexpected':0,'protected_changed':0,'transitions':{},'examples':[]};trans=collections.Counter()
    for cx,cz in sorted(TARGETS):
        boxes=paired.pdc_boxes(a.roots[(cx,cz)]);need(boxes==paired.pdc_boxes(b.roots[(cx,cz)]),'dry mine geometry changed')
        protected=set()
        for q in boxes:
            for y in range(max(-511,q[1]-1),min(128,q[4]+1)+1):
                for z in range(max(cz*16,q[2]-1),min(cz*16+15,q[5]+1)+1):
                    for x in range(max(cx*16,q[0]-1),min(cx*16+15,q[3]+1)+1):protected.add((x,y,z))
        for sy in range(-32,9):
            aa=a.section((cx,sy,cz));bb=b.section((cx,sy,cz));need(len(aa)==len(bb)==4096,'incomplete saved section')
            for i,(v,w) in enumerate(zip(aa,bb)):
                if v==w:continue
                y=sy*16+(i>>8)
                if not -511<=y<=128:continue
                pos=(cx*16+(i&15),y,cz*16+((i>>4)&15));result['changed']+=1
                trans[v['Name']+' => '+w['Name']]+=1
                allowed=False
                if allow_fixes:
                    allowed=(v['Name'] in AIR and w==WATER and pos not in protected) or (v['Name'] in ICE and w==WATER)
                if not allowed:
                    result['unexpected']+=1
                    if pos in protected:result['protected_changed']+=1
                    if len(result['examples'])<40:result['examples'].append({'pos':pos,'before':v,'after':w,'protected':pos in protected})
    result['transitions']=dict(trans);result['pass']=result['unexpected']==0
    return result

def isolated(doc,key):
    return sum(x[key] for x in doc['chunks'])

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False)
    core=exact(ROOT/'swift-input','server-r3915.jar',CORE_SHA)
    ow=exact(ROOT/'resource-input','NeverOverworld-R3918-Walls.zip',OW_SHA)
    nn=exact(ROOT/'ice-input','NeverNether.zip',NN_SHA)
    plugin=compile_plugin(core,ow)
    folders={};phases={}
    folders['off']=setup('off',plugin,ow,nn);phases['off']=phase('off',folders['off'],core,False)
    folders['candidate']=setup('candidate',plugin,ow,nn);phases['candidate']=phase('candidate',folders['candidate'],core,True)
    folders['candidate_first']=WORK/'candidate-first'
    shutil.copytree(folders['candidate']/'world',folders['candidate_first']/'world')
    phases['restart']=phase('restart',folders['candidate'],core,True)
    folders['reverse']=setup('reverse',plugin,ow,nn);phases['reverse']=phase('reverse',folders['reverse'],core,True,True)
    comparisons={
      'off_vs_candidate':compare('off',folders['off'],phases['off']['observed']['chunks'],'candidate',folders['candidate_first'],phases['candidate']['observed']['chunks'],True),
      'candidate_vs_restart':compare('candidate',folders['candidate_first'],phases['candidate']['observed']['chunks'],'restart',folders['candidate'],phases['restart']['observed']['chunks'],False),
      'candidate_vs_reverse':compare('candidate',folders['candidate_first'],phases['candidate']['observed']['chunks'],'reverse',folders['reverse'],phases['reverse']['observed']['chunks'],False),
    }
    # Candidate MCA files are copied before restart; persisted comparison is independent
    # of the later restart save, while live water hashes check the observations too.
    candidate_hash={f"{x['chunk_x']},{x['chunk_z']}":x['water_sha256'] for x in phases['candidate']['observed']['chunks']}
    restart_hash={f"{x['chunk_x']},{x['chunk_z']}":x['water_sha256'] for x in phases['restart']['observed']['chunks']}
    reverse_hash={f"{x['chunk_x']},{x['chunk_z']}":x['water_sha256'] for x in phases['reverse']['observed']['chunks']}
    summary={'pass':False,'seed':SEED,'core_sha256':CORE_SHA,'overworld_sha256':OW_SHA,'nether_sha256':NN_SHA,
      'targets':len(TARGETS),'centers':CENTERS,'comparisons':comparisons,
      'candidate_restart_water_hash_equal':candidate_hash==restart_hash,
      'candidate_reverse_water_hash_equal':candidate_hash==reverse_hash,
      'isolated_air':{k:isolated(v['observed'],'single_air_with_six_aquatic_neighbours') for k,v in phases.items()},
      'isolated_ice':{k:isolated(v['observed'],'single_ice_with_six_aquatic_neighbours') for k,v in phases.items()},
      'air_to_water':phases['candidate']['ocean_proof']['air_to_water'],
      'ice_report_files':phases['candidate']['ice_report_files']}
    need(comparisons['off_vs_candidate']['pass'] and comparisons['off_vs_candidate']['changed']>0,'candidate made unsafe/no worldgen changes')
    need(comparisons['candidate_vs_restart']['pass'] and comparisons['candidate_vs_restart']['changed']==0,'restart mutated saved target state')
    need(comparisons['candidate_vs_reverse']['pass'] and comparisons['candidate_vs_reverse']['changed']==0,'target load order changes final blocks')
    need(candidate_hash==restart_hash==reverse_hash,'water hash differs on restart/reverse order')
    need(summary['isolated_air']['candidate']==summary['isolated_air']['restart']==summary['isolated_air']['reverse']==0,'isolated ocean air remains')
    need(summary['isolated_ice']['candidate']==summary['isolated_ice']['restart']==summary['isolated_ice']['reverse']==0,'isolated submerged ice remains')
    summary['pass']=True;save('summary.json',summary);print('R3922_RESULT',json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
