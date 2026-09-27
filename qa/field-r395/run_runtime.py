#!/usr/bin/env python3
"""Bounded live regression; diagnostic failures remain visible, never a release gate bypass."""
from pathlib import Path
import argparse,collections,hashlib,importlib.util,json,os,queue,shutil,subprocess,threading,time,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';OUT.mkdir(exist_ok=True)
WORK=ROOT/'.work/r395-live';WORK.mkdir(parents=True,exist_ok=False)
BASE='411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'

def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def prepare_plugin():
    expected={}
    with zipfile.ZipFile(ROOT/'candidate/NeverOverworld.zip') as z:
        for name in z.namelist():
            if name.startswith('data/nova_structures/enchantment/') and name.endswith('.json'):
                data=json.loads(z.read(name))
                if data.get('description',{}).get('translate')=='enchantment.dnt.non_survival_enchant':
                    expected['nova_structures:'+name.split('/enchantment/',1)[1][:-5]]=False
        legitimate=json.loads(z.read('data/nova_structures/tags/enchantment/all_dnt_enchants.json'))['values']
        need(len(expected)==16 and len(legitimate)==17,'Unexpected technical/gameplay registry scope')
        need(not set(expected)&set(legitimate),'Gameplay/technical sets overlap')
        expected.update({value:True for value in legitimate})
    expected.update({'minecraft:sharpness':True,'minecraft:protection':True})
    classes=WORK/'plugin-classes';classes.mkdir()
    libs=sorted((ROOT/'.work/r395-build/libs').glob('*.jar'))
    source=ROOT/'client/neverland-enchantment-ui/src/cc/neverland/client/EnchantmentVisibility.java'
    result=subprocess.run(['javac','--release','25','-proc:none','-classpath',os.pathsep.join(map(str,libs)),'-d',str(classes),str(source),str(ROOT/'qa/field-r395/R395QaPlugin.java')],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (OUT/'qa-javac.log').write_text(result.stdout);print(result.stdout,flush=True);need(result.returncode==0,'QA plugin compilation failed')
    plugin=WORK/'R395Qa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('expected-enchants.json',json.dumps(expected))
        z.writestr('plugin.yml',"name: R395Qa\nversion: '1'\nmain: R395QaPlugin\napi-version: '26.2'\nfolia-supported: true\n")
    save(OUT/'expected-enchants.json',expected)
    return plugin

def setup(name,plugin):
    folder=WORK/name;folder.mkdir();packs=folder/'world/datapacks';packs.mkdir(parents=True)
    for file in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/file,packs/file)
    (folder/'plugins').mkdir();shutil.copyfile(plugin,folder/'plugins/R395Qa.jar')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25605\nonline-mode=true\nenable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    return folder

def persisted(folder,rows,name):
    observer=load('r395_observer_'+name,ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
    paired=load('r395_paired_'+name,ROOT/'scripts/probe-never-overworld-paired-r12.py')
    nbt=observer.load_nbt(ROOT)
    chunks=[(r['chunk_x'],r['chunk_z']) for r in rows]
    region=folder/'world/dimensions/minecraft/overworld/region'
    volume=paired.saved_volume(observer,nbt,region,chunks,{'normal_stop':True,'exit_code':0})
    hashes={};counts=collections.Counter()
    aquatic={'minecraft:kelp','minecraft:kelp_plant','minecraft:seagrass','minecraft:tall_seagrass','minecraft:bubble_column'}
    for cx,cz in chunks:
        mask=bytearray(640*256)
        for sy in range(-32,9):
            for i,state in enumerate(volume.section((cx,sy,cz))):
                y=sy*16+(i>>8)
                if not -511<=y<=128:continue
                block=state['Name'];counts[block]+=1
                if block=='minecraft:water':mask[((y+511)<<8)|(i&255)]=1+int(state.get('Properties',{}).get('level','0'))
                elif block in aquatic:mask[((y+511)<<8)|(i&255)]=1
        hashes[f'{cx},{cz}']=hashlib.sha256(mask).hexdigest()
    saved={'target_chunks':len(chunks),'water_hashes':hashes,'block_counts':dict(counts),'scope':'Complete saved block-state sections, -511..128; hashes include water state and aquatic blocks, not waterlogged solid blocks.'}
    save(OUT/(name+'-saved.json'),saved)
    with zipfile.ZipFile(OUT/(name+'-saved-regions.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        members=sorted({region/f'r.{cx//32}.{cz//32}.mca' for cx,cz in chunks})
        for p in members:z.write(p,p.relative_to(folder).as_posix())
        for p in sorted((folder/'world').glob('level.dat')):z.write(p,p.relative_to(folder).as_posix())
        # External large-chunk payloads must accompany the selected region files.
        for p in region.glob('c.*.*.mcc'):
            parts=p.name.split('.')
            if len(parts)==4 and (int(parts[1]),int(parts[2])) in chunks:z.write(p,p.relative_to(folder).as_posix())
    return saved

def phase(name,folder,jar,enabled,reverse=False):
    result={'pass':False,'closure_enabled':enabled,'reverse':reverse};proc=None;reader=None;events=queue.Queue();lines=[]
    proof=OUT/('proof-'+name);proof.mkdir(exist_ok=False)
    try:
        command=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',f'-Dneverfolia.r395OceanClosure={str(enabled).lower()}',f'-Dneverfolia.r395ReportDirectory={proof}',f'-Dneverfolia.qaReverse={str(reverse).lower()}','-jar',str(jar),'--nogui']
        result['command']=command
        proc=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'.log')).open('w') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+600;done=False
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'R395 SAMPLE' in line or 'R395 NATURAL QA' in line:print(name,line.rstrip(),flush=True)
            if 'R395 NATURAL QA' in line:done=True;break
        need(done,'Natural generation QA did not finish within bounded time')
        result['observed']=json.loads((folder/'plugins/R395Qa/result.json').read_text())
        proc.stdin.write('stop\n');proc.stdin.flush();result['exit_code']=proc.wait(timeout=150);reader.join(timeout=10)
        result['startup_completed']=any('Done (' in line for line in lines)
        need(result['exit_code']==0 and result['startup_completed'],'Server startup/shutdown did not complete normally')
        result['warnings_and_errors']=[line.rstrip() for line in lines if ' WARN]' in line or ' ERROR]' in line]
        signatures=('Failed to load registries','Failed to load datapacks','Unknown registry key','Block-attached entity at invalid position','[ChunkTaskScheduler] Chunk system error','Missing chunkholder when required','Exception in thread','Cannot retain R395')
        result['targeted_errors']=[line.rstrip() for line in lines if any(s in line for s in signatures)]
        need(result['observed'].get('pass') is True and result['observed'].get('completed_chunks')==54,'Incomplete target sample or enchant test failure')
        result['saved']=persisted(folder,result['observed']['chunks'],name)
        reports=[json.loads(p.read_text()) for p in proof.glob('*.json')]
        wanted={(r['chunk_x'],r['chunk_z']) for r in result['observed']['chunks']}
        target_reports=[r for r in reports if (r['chunk_x'],r['chunk_z']) in wanted]
        result['proof']={'audited_chunks':len(reports),'target_records':len(target_reports),
            'target_missing':sorted(wanted-{(r['chunk_x'],r['chunk_z']) for r in target_reports}),
            'added_air_to_water':sum(r['added_air_to_water'] for r in target_reports),
            'snapshot_conflicts':sum(r['snapshot_write_conflicts'] for r in reports),
            'water_preservation_failures':[r for r in reports if r['native_aquatic_cells']!=r['preserved_aquatic_cells']],
            'global_closure_proven':False}
        if enabled and name!='restart':
            need(not result['proof']['target_missing'],'Missing R395 target evidence')
            need(result['proof']['snapshot_conflicts']==0 and not result['proof']['water_preservation_failures'],'Unsafe snapshot/write transition')
        need(not result['targeted_errors'],'Runtime exception in generated areas')
        result['pass']=True
    except Exception as error:result['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=10)
        save(OUT/(name+'-phase.json'),result)
    print(name,json.dumps({k:v for k,v in result.items() if k in ('pass','error','exit_code','proof')}),flush=True)
    return result

def main():
    build=json.loads((OUT/'build.json').read_text())
    need(sha(ROOT/'baseline/server.jar')==BASE,'Unexpected baseline')
    need(sha(ROOT/'candidate/server.jar')==build['candidate_core_sha256'],'Unexpected compiled candidate')
    need(sha(ROOT/'candidate/NeverOverworld.zip')==PACK and sha(ROOT/'candidate/NeverNether.zip')==NETHER,'Unexpected paired datapacks')
    plugin=prepare_plugin();report={'schema':1,'production_accepted':False,'phases':{},'candidate_core_sha256':build['candidate_core_sha256'],'scope':'Bounded new-world generation and saved-water comparison; finite 3x3 witness cache is not global closure.'}
    report['phases']['baseline']=phase('baseline',setup('baseline',plugin),ROOT/'baseline/server.jar',False)
    target=setup('candidate',plugin)
    report['phases']['candidate']=phase('candidate',target,ROOT/'candidate/server.jar',True)
    if report['phases']['candidate']['pass']:report['phases']['restart']=phase('restart',target,ROOT/'candidate/server.jar',True)
    report['phases']['reverse']=phase('reverse',setup('reverse',plugin),ROOT/'candidate/server.jar',True,True)
    get=lambda key:report['phases'].get(key,{}).get('saved',{}).get('water_hashes')
    first=get('candidate')
    report['restart_equal']=first is not None and first==get('restart')
    report['reverse_equal']=first is not None and first==get('reverse')
    report['reverse_changed_chunks']=sorted(k for k,v in (first or {}).items() if (get('reverse') or {}).get(k)!=v)
    left=report['phases']['baseline'].get('saved',{}).get('block_counts',{})
    right=report['phases']['candidate'].get('saved',{}).get('block_counts',{})
    report['block_count_delta']={key:right.get(key,0)-left.get(key,0) for key in sorted(set(left)|set(right)) if right.get(key,0)!=left.get(key,0)}
    for name in ('baseline','candidate','reverse'):
        rows=report['phases'][name].get('observed',{}).get('chunks',[])
        report[name+'_isolated_air']=sum(r['single_air_with_six_aquatic_neighbours'] for r in rows)
        report[name+'_isolated_ice']=sum(r['single_ice_with_six_aquatic_neighbours'] for r in rows)
    report['bounded_regression_pass']=all(p.get('pass') for p in report['phases'].values()) and report['restart_equal'] and report['reverse_equal'] and report['phases']['candidate'].get('proof',{}).get('added_air_to_water',0)>0
    save(OUT/'runtime.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='phases'},indent=2),flush=True)
    need(report['bounded_regression_pass'],'R395 bounded regression not accepted; evidence retained')
if __name__=='__main__':main()
