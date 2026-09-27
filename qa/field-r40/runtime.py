#!/usr/bin/env python3
"""Fresh isolated CI servers. No edits to user saves or accepted release gates.
Fixture cache is synthetic; natural phases use the real Folia chunk scheduler.
"""
from pathlib import Path
import collections, hashlib, importlib.util, json, os, queue, shutil, subprocess, threading, time, uuid, zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r40-runtime'
SEED=-4651369264513492755
CENTERS=((7,1),(1,-4),(-197,-217),(-169,-250),(-189,-223),(-1699,-769))
TARGETS=sorted({(cx+dx,cz+dz) for cx,cz in CENTERS for dx in (-1,0,1) for dz in (-1,0,1)},key=lambda p:f'{p[0]},{p[1]}')
BAD=('Failed to load registries','Failed to load datapacks','Overworld settings missing','Unknown registry key','Block-attached entity at invalid position','[ChunkTaskScheduler] Chunk system error','Missing chunkholder when required','Exception in server tick loop','Cannot retain R395')

def need(ok,message):
    if not ok:raise ValueError(message)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,obj):path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def prepare_natural():
    source=ROOT/'qa/field-r395/R395QaPlugin.java';raw=source.read_bytes()
    need(hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()=='98ade98abd0cff51db3611a2499c6b207aab9cd3','Unexpected original observer')
    text=raw.decode().replace('public final class R395QaPlugin','public final class R40NaturalQa')
    anchor='        result.addProperty("reverse_order",Boolean.getBoolean("neverfolia.qaReverse"));'
    need(text.count(anchor)==1,'Observer nonce anchor')
    text=text.replace(anchor,anchor+'\n        result.addProperty("nonce",System.getProperty("neverfolia.qaNonce",""));')
    target=WORK/'R40NaturalQa.java';target.write_text(text)
    expected={}
    with zipfile.ZipFile(ROOT/'candidate/NeverOverworld.zip') as z:
        for name in z.namelist():
            if name.startswith('data/nova_structures/enchantment/') and name.endswith('.json'):
                data=json.loads(z.read(name))
                if data.get('description',{}).get('translate')=='enchantment.dnt.non_survival_enchant':expected['nova_structures:'+name.split('/enchantment/',1)[1][:-5]]=False
        legitimate=json.loads(z.read('data/nova_structures/tags/enchantment/all_dnt_enchants.json'))['values']
        need(len(expected)==16 and len(legitimate)==17 and not set(expected)&set(legitimate),'Unexpected registry scope')
        expected.update({v:True for v in legitimate});expected.update({'minecraft:sharpness':True,'minecraft:protection':True})
    classes=WORK/'natural-classes';classes.mkdir()
    cp=(ROOT/'.work/r40-build/classpath.txt').read_text()
    p=subprocess.run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(target),str(ROOT/'client/neverland-enchantment-ui/src/cc/neverland/client/EnchantmentVisibility.java')],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (OUT/'natural-javac.log').write_text(p.stdout);need(p.returncode==0,p.stdout)
    plugin=WORK/'R40NaturalQa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
        for path in classes.rglob('*.class'):z.write(path,path.relative_to(classes).as_posix())
        z.writestr('expected-enchants.json',json.dumps(expected))
        z.writestr('plugin.yml',"name: R395Qa\nversion: 'r40'\nmain: R40NaturalQa\napi-version: '26.2'\nfolia-supported: true\n")
    return plugin

def prepare(name,plugin):
    folder=WORK/name;folder.mkdir();packs=folder/'world/datapacks';packs.mkdir(parents=True)
    for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/n,packs/n)
    (folder/'plugins').mkdir();shutil.copyfile(plugin,folder/'plugins'/plugin.name)
    # Existing project convention: ephemeral CI worlds only. User archive ships eula=false.
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25610\nonline-mode=true\nenable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    return folder

def phase(name,folder,jar,enabled,reader_module=None,reverse=False,fixture=False):
    result={'pass':False,'closure_enabled':enabled,'reverse':reverse};proc=None;pump=None;lines=[];events=queue.Queue()
    nonce=uuid.uuid4().hex;proof=OUT/('proof-'+name);proof.mkdir(exist_ok=False)
    target=folder/('plugins/R40ClosureQa/result.json' if fixture else 'plugins/R395Qa/result.json')
    if target.exists():
        with (OUT/(name+'-previous-result.json')).open('xb') as f:f.write(target.read_bytes())
        target.unlink()
    try:
        command=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',f'-Dneverfolia.qaNonce={nonce}',f'-Dneverfolia.r395OceanClosure={str(enabled).lower()}',f'-Dneverfolia.r395ReportDirectory={proof}',f'-Dneverfolia.qaReverse={str(reverse).lower()}','-jar',str(jar),'--nogui']
        result['command']=command
        proc=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def read_log():
            with (OUT/(name+'.log')).open('w') as stream:
                for line in proc.stdout:lines.append(line);stream.write(line);stream.flush();events.put(line)
            events.put(None)
        pump=threading.Thread(target=read_log,daemon=True);pump.start()
        marker='R40 FIXTURE ' if fixture else 'R395 NATURAL QA '
        deadline=time.monotonic()+600;success=False
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if marker in line:
                need(marker+'PASS' in line,'Current process reported failure: '+line.rstrip());success=True;break
        need(success,'No current successful QA completion')
        need(target.is_file() and not target.is_symlink(),'Current result missing')
        observed=json.loads(target.read_text());result['observed']=observed
        need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('seed')==SEED,'Stale/wrong current report')
        if fixture:
            need(len(observed.get('cases',[]))==10 and all(r.get('pass') is True for r in observed['cases']),'Incomplete fixtures')
        else:
            coordinates=[(r['chunk_x'],r['chunk_z']) for r in observed['chunks']]
            need(observed.get('reverse_order') is reverse and observed.get('completed_chunks')==54 and coordinates==(list(reversed(TARGETS)) if reverse else TARGETS),'Wrong coordinate sequence')
        proc.stdin.write('stop\n');proc.stdin.flush();result['exit_code']=proc.wait(timeout=150);pump.join(timeout=10)
        need(not pump.is_alive() and result['exit_code']==0 and any('Done (' in line for line in lines),'Incomplete normal lifecycle')
        result['targeted_errors']=[line.rstrip() for line in lines if any(bad in line for bad in BAD)];need(not result['targeted_errors'],'Targeted runtime errors')
        if not fixture:
            result['saved']=reader_module.persisted(folder,observed['chunks'],name)
            result['snapshot_water_equal']=all(r['water_sha256']==result['saved']['water_hashes'][f"{r['chunk_x']},{r['chunk_z']}"] for r in observed['chunks'])
            need(result['snapshot_water_equal'],'Snapshot/save water drift')
            rows=[json.loads(p.read_text()) for p in proof.glob('*.json')]
            selected=[r for r in rows if (r['chunk_x'],r['chunk_z']) in set(TARGETS)]
            result['proof']={'target_count':len(selected),'added':sum(r['added_air_to_water'] for r in selected),'conflicts':sum(r['snapshot_write_conflicts'] for r in rows),'preservation_failures':sum(r['native_aquatic_cells']!=r['preserved_aquatic_cells'] for r in rows),'missing':sorted(set(TARGETS)-{(r['chunk_x'],r['chunk_z']) for r in selected})}
            if enabled and name!='restart':
                need(not result['proof']['missing'] and len(selected)==54,'Missing/duplicate target proof')
                need(result['proof']['conflicts']==0 and result['proof']['preservation_failures']==0,'Unsafe closure observation')
        result['pass']=True
    except Exception as error:result['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if pump is not None:pump.join(timeout=10)
        save(OUT/(name+'-phase.json'),result)
    print('R40_PHASE '+json.dumps({'name':name,**{k:result.get(k) for k in ('pass','error','exit_code','proof')}}),flush=True)
    return result

def compare_pair(before,after,observer,paired,nbt,allow_fill):
    a=paired.saved_volume(observer,nbt,before/'world/dimensions/minecraft/overworld/region',TARGETS,{'normal_stop':True,'exit_code':0})
    b=paired.saved_volume(observer,nbt,after/'world/dimensions/minecraft/overworld/region',TARGETS,{'normal_stop':True,'exit_code':0})
    counts=collections.Counter();changed_chunks=set();examples=[];non_water=0;protected_changes=0;geometry_changes=0;block_entity_changes=0;piece_count=0
    for cx,cz in TARGETS:
        boxes=paired.pdc_boxes(a.roots[(cx,cz)]);piece_count+=len(boxes)
        if boxes!=paired.pdc_boxes(b.roots[(cx,cz)]):geometry_changes+=1
        if a.roots[(cx,cz)].get('block_entities',[])!=b.roots[(cx,cz)].get('block_entities',[]):block_entity_changes+=1
        for sy in range(-32,32):
            left=a.section((cx,sy,cz));right=b.section((cx,sy,cz))
            for i,(old,new) in enumerate(zip(left,right)):
                if old==new:continue
                x=cx*16+(i&15);y=sy*16+(i>>8);z=cz*16+((i>>4)&15)
                counts[old['Name']+' => '+new['Name']]+=1;changed_chunks.add((cx,cz))
                allowed=old['Name'] in ('minecraft:air','minecraft:cave_air','minecraft:void_air') and new=={'Name':'minecraft:water','Properties':{'level':'0'}} and -511<=y<=128
                if not allowed:non_water+=1
                protected=any(bb[0]-1<=x<=bb[3]+1 and max(-511,bb[1]-1)<=y<=min(128,bb[4]+1) and bb[2]-1<=z<=bb[5]+1 for bb in boxes)
                if protected:protected_changes+=1
                if len(examples)<30:examples.append({'position':[x,y,z],'before':old,'after':new})
    total=sum(counts.values())
    return {'pass':(total>0 and non_water==0 if allow_fill else total==0) and protected_changes==0 and geometry_changes==0 and block_entity_changes==0,'changed_cells':total,'changed_chunks':len(changed_chunks),'transitions':dict(counts),'non_air_to_water_changes':non_water,'protected_envelope_changes':protected_changes,'recorded_piece_references':piece_count,'piece_metadata_changed_chunks':geometry_changes,'block_entity_changed_chunks':block_entity_changes,'examples':examples,'scope':'All saved block names/properties Y=-512..511; recorded mine envelopes. Not all natural dry rooms.'}

def main():
    WORK.mkdir(parents=True,exist_ok=False);build=json.loads((OUT/'build.json').read_text())
    base=ROOT/'baseline/server.jar';candidate=ROOT/'candidate/server.jar'
    need(sha(base)==build['base_core_sha256'] and sha(candidate)==build['candidate_core_sha256'],'Wrong core input')
    old=load('r40_saved_reader',ROOT/'qa/field-r395/run_runtime.py')
    plugin=prepare_natural();report={'production_accepted':False,'build':build,'phases':{},'paired_comparisons':{},'bounded_integration_pass':False}
    folders={}
    try:
        folders['fixture']=prepare('fixture',ROOT/'.work/r40-build/R40ClosureQa.jar')
        report['phases']['fixture']=phase('fixture',folders['fixture'],candidate,True,fixture=True)
        for name,jar,enabled,reverse in (('baseline',base,False,False),('candidate_off',candidate,False,False),('candidate',candidate,True,False),('baseline_reverse',base,False,True),('reverse',candidate,True,True)):
            folders[name]=prepare(name,plugin);report['phases'][name]=phase(name,folders[name],jar,enabled,old,reverse)
        # Save the candidate before restart so both actual persisted snapshots remain independent.
        if report['phases']['candidate']['pass']:
            folders['candidate_before_restart']=WORK/'candidate-before-restart'
            shutil.copytree(folders['candidate']/'world',folders['candidate_before_restart']/'world')
            report['phases']['restart']=phase('restart',folders['candidate'],candidate,True,old)
        need(all(p['pass'] for p in report['phases'].values()) and 'restart' in report['phases'],'A required process failed; evidence retained')
        observer=load('r40_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
        paired=load('r40_pair',ROOT/'scripts/probe-never-overworld-paired-r12.py');nbt=observer.load_nbt(ROOT)
        for label,left,right,fill in (('disabled_matches_R399','baseline','candidate_off',False),('forward_effect','baseline','candidate_before_restart',True),('reverse_effect','baseline_reverse','reverse',True),('restart_exact','candidate_before_restart','candidate',False)):
            r=compare_pair(folders[left],folders[right],observer,paired,nbt,fill);report['paired_comparisons'][label]=r
            print('R40_PAIR '+label+' '+json.dumps({k:v for k,v in r.items() if k!='examples'}),flush=True)
        for effect,phase_name in (('forward_effect','candidate'),('reverse_effect','reverse')):
            need(report['paired_comparisons'][effect]['changed_cells']==report['phases'][phase_name]['proof']['added'],'Observed additions differ from kernel proof')
        report['bounded_integration_pass']=all(r['pass'] for r in report['paired_comparisons'].values())
        need(report['bounded_integration_pass'],'Paired integration failed')
        report['inputs_unchanged']=sha(base)==build['base_core_sha256'] and sha(candidate)==build['candidate_core_sha256']
        need(report['inputs_unchanged'],'Core mutated during testing')
    except Exception as error:report['error']=repr(error)
    finally:save(OUT/'r40-runtime.json',report)
    print('R40_RESULT '+json.dumps({'bounded_integration_pass':report['bounded_integration_pass'],'production_accepted':False,'error':report.get('error')}),flush=True)
    need(report['bounded_integration_pass'] and 'error' not in report,'No integrated candidate acceptance')
if __name__=='__main__':main()
