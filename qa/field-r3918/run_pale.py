#!/usr/bin/env python3
"""Real JigsawPlacement of unchanged child from source-cropped host contexts.
No production kit. Server, Nether, authored parent and child NBT stay unchanged.
"""
from pathlib import Path
import collections, copy, hashlib, io, json, os, queue, secrets, shutil, subprocess, threading, time, zipfile
import restore_pale as p
ROOT=p.ROOT;OUT=ROOT/'r3918-evidence';WORK=ROOT/'.work/r3918-runtime'
CORE='845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
SEED=-4651369264513492755

def exact(folder,name,expected):
    found=[x for x in Path(folder).rglob(name) if x.is_file() and p.digest(x.read_bytes())==expected]
    p.need(len(found)==1,'Missing/ambiguous pinned '+name);return found[0].resolve()

def final_state(state):
    name=state['Name'][1];properties=state.get('Properties',(10,{}))[1]
    return name+('['+','.join(k+'='+v[1] for k,v in sorted(properties.items()))+']' if properties else '')

def fixture(files,path):
    reader=p.inspector.load_reader();compression,root_name,root=reader._nbt_parse(files[p.PARENT]);palette=root['palette'][1][1]
    child=reader._nbt_parse(files[p.BANNER])[2]
    source={tuple(b['pos'][1][1]):b for b in root['blocks'][1][1]}
    templates={};cases=[]
    for i,(px,py,pz) in enumerate(((19,8,6),(22,8,6),(22,8,9),(19,8,9))):
        origin=(px-1,py-1,pz-1);host=copy.deepcopy(root);host['size']=(9,(3,[3,7,3]));host['entities']=(9,(10,[]));blocks=[];pal=copy.deepcopy(palette)
        counts=collections.Counter();joint_count=0
        for pos,block in source.items():
            rel=[pos[d]-origin[d] for d in range(3)]
            if not(0<=rel[0]<3 and 0<=rel[1]<7 and 0<=rel[2]<3):continue
            b=copy.deepcopy(block);b['pos']=(9,(3,rel));state=palette[b['state'][1]];name=state['Name'][1]
            if rel==[1,0,1]:
                p.need(name not in ('minecraft:white_banner','minecraft:birch_wall_sign','minecraft:jigsaw'),'Unreviewed anchor substrate')
                b['state']=(3,len(pal));pal.append({'Name':(8,'minecraft:jigsaw'),'Properties':(10,{'orientation':(8,'down_south')})})
                b['nbt']=(10,{'name':(8,'neverfolia_qa:pale_anchor'),'target':(8,'minecraft:empty'),'pool':(8,'minecraft:empty'),'final_state':(8,final_state(state)),'joint':(8,'rollable'),'selection_priority':(3,0),'placement_priority':(3,0)})
            if name=='minecraft:jigsaw':
                p.need(b['nbt'][1].get('pool')==(8,p.ID),'Unrelated joint in crop');joint_count+=1
            else:counts[name]+=1
            blocks.append(b)
        p.need(joint_count==1,'Each source crop must contain its one actual output')
        p.need(any(b['pos'][1][1]==[1,0,1] for b in blocks),'Missing QA anchor')
        host['palette']=(9,(10,pal));host['blocks']=(9,(10,blocks))
        name=f'data/neverfolia_qa/structure/pale/host_{i}.nbt';templates[name]=reader._nbt_encode(compression,root_name,host)
        templates[f'data/neverfolia_qa/worldgen/template_pool/pale/case_{i}.json']=p.encoded({'fallback':'minecraft:empty','elements':[{'weight':1,'element':{'element_type':'minecraft:single_pool_element','location':f'neverfolia_qa:pale/host_{i}','processors':'minecraft:empty','projection':'rigid'}}]})
        cases.append({'case':i,'source_connector':[px,py,pz],'baseline_banners':counts['minecraft:white_banner'],'baseline_signs':counts['minecraft:birch_wall_sign'],'host_sha256':p.digest(templates[name])})
    meta=json.loads(files['pack.mcmeta']);meta['pack']['description']='CI ONLY source-cropped Pale parent contexts, original child pool untouched';templates['pack.mcmeta']=p.encoded(meta)
    p.write(path,templates);(OUT/'pale-fixture.json').write_bytes(p.encoded({'cases':cases,'fixture_sha256':p.digest(path.read_bytes()),'crop_size':[3,7,3],'authored_child_modified':False,'original_parent_in_game_pack_modified':False,'source_crop_anchor_added':True}));return cases

def compile_qa(core):
    libs=WORK/'libs';libs.mkdir()
    with zipfile.ZipFile(core) as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
    providers=[]
    for path in libs.glob('*.jar'):
        with zipfile.ZipFile(path) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():providers.append(path)
    if not providers:
        diagnostics=list((ROOT/'debug').rglob('diagnostics.zip'));p.need(len(diagnostics)==1,'Missing diagnostic API')
        with zipfile.ZipFile(diagnostics[0]) as z:
            choices=[]
            for n in z.namelist():
                if 'folia-api' in n and n.endswith('.jar'):
                    data=z.read(n)
                    with zipfile.ZipFile(io.BytesIO(data)) as inner:
                        if 'org/bukkit/Bukkit.class' in inner.namelist():choices.append(data)
        p.need(len(choices)==1,'Ambiguous diagnostic API');api=libs/'folia-api.jar';api.write_bytes(choices[0]);providers=[api]
    p.need(len(providers)==1,'Ambiguous runtime API');classes=WORK/'classes';classes.mkdir()
    command=['javac','--release','25','-proc:none','-classpath',os.pathsep.join(str(x) for x in sorted(libs.glob('*.jar'))),'-d',str(classes),str(Path(__file__).with_name('PaleDecorQa.java'))]
    result=subprocess.run(command,text=True,capture_output=True,timeout=120);(OUT/'pale-javac.log').write_text(result.stdout+result.stderr);p.need(result.returncode==0,'QA compilation failed: '+result.stderr)
    return classes

def world(name,pack,nether,plugin,host):
    folder=WORK/name;dp=folder/'world/datapacks';dp.mkdir(parents=True);(folder/'plugins').mkdir()
    shutil.copyfile(pack,dp/'NeverOverworld.zip');shutil.copyfile(nether,dp/'NeverNether.zip');shutil.copyfile(host,dp/'PaleQa.zip');shutil.copyfile(plugin,folder/'plugins/PaleDecorQa.jar')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip,file/PaleQa.zip\nserver-ip=127.0.0.1\nserver-port=25618\nonline-mode=true\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\nenable-status=false\n')
    return folder

def phase(name,core,folder,baseline=False,reload=False):
    nonce=secrets.token_hex(16);result={'pass':False,'nonce':nonce,'baseline':baseline,'reload':reload};proc=None;thread=None;q=queue.Queue();lines=[]
    output=folder/'plugins/PaleDecorQa/result.json'
    try:
        if output.exists():
            (OUT/(name+'-previous.json')).write_bytes(output.read_bytes());output.unlink()
        command=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r399OceanClosure=true','-Dneverfolia.r3913IceFragments=true','-Dneverfolia.qaNonce='+nonce,'-Dneverfolia.qaBaseline='+str(baseline).lower(),'-Dneverfolia.qaReload='+str(reload).lower(),'-jar',str(core),'--nogui']
        proc=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'.log')).open('w') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();q.put(line)
            q.put(None)
        thread=threading.Thread(target=pump,daemon=True);thread.start();end=time.monotonic()+300;done=False;success=False
        while time.monotonic()<end:
            try:line=q.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'Done (' in line:done=True
            if 'R3918 PALE' in line:print(line.strip(),flush=True)
            if 'R3918 PALE QA FAIL' in line:raise ValueError('Fixture failed')
            if 'R3918 PALE QA PASS nonce='+nonce in line:success=True
            if done and success:break
        p.need(done and success,'No new successful runtime result')
        observed=json.loads(output.read_text());result['observed']=observed
        p.need(observed['pass'] is True and observed['nonce']==nonce and observed['seed']==SEED and observed['baseline']==baseline and observed['reload']==reload,'Wrong runtime identity')
        p.need(len(observed['checks'])==(1 if reload else 4),'Incomplete fixture coverage')
        if reload:p.need(observed['checks'][0]['reload_equal'] and observed['checks'][0]['positions']==4096,'Reload mismatch')
        else:p.need([r['case'] for r in observed['checks']]==[0,1,2,3] and all(r['pass'] for r in observed['checks']),'Cases incomplete')
        proc.stdin.write('stop\n');proc.stdin.flush();result['exit_code']=proc.wait(timeout=120);thread.join(timeout=10)
        p.need(result['exit_code']==0 and not thread.is_alive(),'Unclean shutdown')
        bad=('Empty or non-existent pool:','Block-attached entity at invalid position','porting_lib:','Failed to load datapacks','R3918 PALE QA FAIL','Exception loading structure')
        result['targeted_errors']=[x.strip() for x in lines if any(t in x for t in bad)];p.need(not result['targeted_errors'],'Targeted server errors')
        result['pass']=True
    except Exception as e:
        result['error']=repr(e)
        if output.is_file():
            try:result['observed']=json.loads(output.read_text())
            except Exception:pass
    finally:
        if proc and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if thread:thread.join(timeout=10)
        (OUT/(name+'.json')).write_bytes(p.encoded(result));print('PALE_PHASE',name,json.dumps({k:v for k,v in result.items() if k!='observed'}),flush=True)
    return result

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);report={'pass':False,'all_reported_bugs_fixed':False,'user_kit_published':False}
    try:
        core=exact(ROOT/'swift-input','server-r3915.jar',CORE);nether=exact(ROOT/'inputs','NeverNether.zip',NETHER)
        original=exact(ROOT/'combined-input','NeverOverworld-R3915-Combined.zip',p.BASE)
        build=json.loads((OUT/'pale-build/pale-build.json').read_text());candidate=exact(OUT/'pale-build','NeverOverworld-R3918-Combined.zip',build['output_sha256'])
        files=p.read(original);host=WORK/'PaleQa.zip';cases=fixture(files,host);classes=compile_qa(core);plugin=WORK/'PaleDecorQa.jar'
        with zipfile.ZipFile(plugin,'x',zipfile.ZIP_DEFLATED) as z:
            for f in sorted(classes.rglob('*.class')):z.write(f,f.relative_to(classes).as_posix())
            z.writestr('plugin.yml',"name: PaleDecorQa\nversion: '3918'\nmain: PaleDecorQa\napi-version: '26.2'\nfolia-supported: true\n");z.writestr('cases.json',json.dumps(cases))
        base_world=world('baseline',original,nether,plugin,host);cand_world=world('candidate',candidate,nether,plugin,host)
        report['baseline']=phase('pale-baseline',core,base_world,True);p.need(report['baseline']['pass'],'Baseline failed')
        report['candidate']=phase('pale-candidate',core,cand_world);p.need(report['candidate']['pass'],'Candidate failed')
        # Same seed per fixture, same authored host, same runtime. Compare exact
        # states; only two decoration block positions per host may be added.
        changes=[]
        for a,b in zip(report['baseline']['observed']['checks'],report['candidate']['observed']['checks']):
            p.need(len(a['states'])==len(b['states'])==4096,'Incomplete block snapshot')
            diff=[{'index':i,'before':x,'after':y} for i,(x,y) in enumerate(zip(a['states'],b['states'])) if x!=y]
            p.need(len(diff)==2,'Unexpected geometry difference')
            p.need(all(x['before']=='Block{minecraft:air}' for x in diff),'Decoration overwrote source solids')
            p.need(sum('minecraft:white_banner' in x['after'] for x in diff)==1 and sum('minecraft:birch_wall_sign' in x['after'] for x in diff)==1,'Wrong decoration writes');changes.append({'case':a['case'],'changes':diff})
        report['exact_changes']=changes
        report['restart']=phase('pale-restart',core,cand_world,False,True);p.need(report['restart']['pass'],'Saved scene changed')
        p.need(p.digest(core.read_bytes())==CORE and p.digest(original.read_bytes())==p.BASE and p.digest(nether.read_bytes())==NETHER,'Input modified')
        report.update({'pass':True,'core_sha256':CORE,'pack_sha256':build['output_sha256'],'original_pack_sha256':p.BASE,'source_contexts':4,'added_banners':4,'added_signs':4,'other_block_changes':0,'whole_natural_building_tested':False,'core_changed':False})
    except Exception as e:report['error']=repr(e)
    finally:(OUT/'pale-runtime.json').write_bytes(p.encoded(report))
    print('PALE_RUNTIME',json.dumps({k:v for k,v in report.items() if k not in ('baseline','candidate','restart')},ensure_ascii=False),flush=True);p.need(report['pass'],'Pale runtime not accepted')

if __name__=='__main__':main()
