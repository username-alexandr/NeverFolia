#!/usr/bin/env python3
"""Exercise the SAME composed pack and pinned kernel in isolated CI servers.
No user kit is emitted: this is scoped content integration, not all-bug acceptance.
"""
from pathlib import Path
import copy,hashlib,importlib.util,json,os,queue,secrets,shutil,subprocess,threading,time,zipfile
import combine_content as c
import run_runtime as swift
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3915'
SEED=swift.SEED
BAD=tuple(dict.fromkeys(swift.BAD+('Empty or non-existent pool:','Block-attached entity at invalid position','porting_lib:','Exception loading structure')))

def need(ok,message):
    if not ok:raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(name,value):
    OUT.mkdir(exist_ok=True)
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def one(folder,name):
    paths=[p for p in Path(folder).rglob(name) if p.is_file() and not p.is_symlink()]
    need(len(paths)==1,'Missing/ambiguous input '+str(folder)+'/'+name)
    return paths[0]

def exact_file(folder,name,expected):
    p=one(folder,name);need(sha(p)==expected,'Changed pinned input '+str(p));return p

def expected_ids():
    ids={f'nova_structures:tavern/tavern_event_trader_car_{role}_{biome}' for role in ('cartographer','cleric') for biome in c.BIOMES}
    ids|={f'nova_structures:tavern/tavern_event_trader_car_armorer_{b}' for b in ('mangrove','pale','swamp')}
    return ids

def validate_cases(cases):
    need(isinstance(cases,list) and len(cases)==25,'Incomplete input case list')
    ids=[row['id'] for row in cases]
    need(len(set(ids))==25 and set(ids)==expected_ids(),'Wrong/duplicate input cases')
    for row in cases:
        need(type(row['expected_villagers']) is int and row['expected_villagers'] in (0,1),'Unreviewed NPC expectation')
        need(row['expected_villagers']==1 or row['biome']=='pale','Unexpected empty NPC expectation')
        need(row['role'] in ('cartographer','cleric','armorer'),'Unknown role')

def validate_cart(observed,nonce,cases):
    validate_cases(cases)
    need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('seed')==SEED,'Not a fresh successful cart result')
    rows=observed.get('checks',[])
    need(observed.get('completed')==25 and len(rows)==25,'Incomplete actual cart coverage')
    need([x['id'] for x in rows]==[x['id'] for x in cases],'Actual variant order/identity changed')
    for actual,want in zip(rows,cases):
        need(actual.get('pass') is True,'A cart check failed')
        need(all(actual.get(k)==want[k] for k in ('role','biome','expected_villagers','target','root_size')),'Fixture metadata changed')
        need(actual.get('observed_villagers')==want['expected_villagers'],'Wrong actual villager count')
        need(actual.get('workstations')==1 and actual.get('remaining_jigsaws')==0 and actual.get('nonair_cart_blocks',0)>8,'Incomplete assembly')
        npcs=actual.get('npc_observations',[])
        need(len(npcs)==want['expected_villagers'] and len({x['uuid'] for x in npcs})==len(npcs),'Missing/duplicate NPC evidence')
    teardown=observed.get('entity_teardowns',[])
    need(len(teardown)==25 and [x['next_case'] for x in teardown]==list(range(25)),'Missing case-isolation barriers')
    need(all(x.get('live_after_barrier')==0 for x in teardown),'Prior NPC contaminated a fixture')

def root_fixture(pack,cases,output):
    """Choose authored parent elements only; child pools/NPCs are never replaced."""
    validate_cases(cases);found={r['id']:[] for r in cases}
    with zipfile.ZipFile(pack) as z:
        meta={'pack':copy.deepcopy(json.loads(z.read('pack.mcmeta'))['pack'])}
        meta['pack']['description']='CI ONLY: select reviewed cart roots; original child pools remain unchanged'
        def walk(obj):
            if isinstance(obj,dict):
                location=obj.get('location')
                if location in found and obj.get('element_type') in ('minecraft:single_pool_element','minecraft:legacy_single_pool_element'):found[location].append(obj)
                for value in obj.values():walk(value)
            elif isinstance(obj,list):
                for value in obj:walk(value)
        for name in z.namelist():
            if '/worldgen/template_pool/' in name and name.endswith('.json'):walk(json.loads(z.read(name)))
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
        z.writestr('pack.mcmeta',json.dumps(meta))
        for i,row in enumerate(cases):
            elements=found[row['id']]
            need(bool(elements),'No authored parent for '+row['id'])
            need(len({json.dumps(e,sort_keys=True) for e in elements})==1,'Ambiguous parent processors '+row['id'])
            z.writestr(f'data/neverfolia_qa/worldgen/template_pool/cart/case_{i}.json',json.dumps({'fallback':'minecraft:empty','elements':[{'weight':1,'element':elements[0]}]}))
    return {'sha256':sha(output),'cases':cases,'source_elements_preserved':True,'child_pools_replaced':False}

def compile_plugin(name,source,cp,extra=None):
    folder=WORK/('combined-compile-'+name);folder.mkdir(exist_ok=False)
    java=folder/(name+'.java');java.write_text(source)
    (OUT/(name+'-compiled-source.java.txt')).write_text(source)
    classes=folder/'classes';classes.mkdir()
    result=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(java)],text=True,capture_output=True,timeout=120)
    (OUT/(name+'-javac.log')).write_text(result.stdout+result.stderr)
    need(result.returncode==0,'Actual QA compilation failed '+name+': '+result.stderr)
    jar=folder/(name+'.jar')
    with zipfile.ZipFile(jar,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(classes.rglob('*.class')):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('plugin.yml',f"name: {name}\nversion: 'combined-1'\nmain: {name}\napi-version: '26.2'\nfolia-supported: true\n")
        for path,raw in (extra or {}).items():z.writestr(path,raw)
    return jar

def classpath(kernel):
    libs=WORK/'combined-libs';libs.mkdir(exist_ok=False)
    with zipfile.ZipFile(kernel) as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
    spec=importlib.util.spec_from_file_location('combined_api',ROOT/'qa/field-r3914/run_carts.py')
    api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
    api.resolve_api(libs,list((ROOT/'debug').rglob('diagnostics.zip')))
    return os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))

def cart_world(pack,nether,plugin,cases):
    folder=WORK/'combined-cart-world';packs=folder/'world/datapacks';packs.mkdir(parents=True,exist_ok=False)
    plugins=folder/'plugins';plugins.mkdir()
    shutil.copyfile(pack,packs/'NeverOverworld.zip');shutil.copyfile(nether,packs/'NeverNether.zip')
    shutil.copyfile(plugin,plugins/'R3915CartQa.jar')
    fixture=root_fixture(pack,cases,packs/'CartQa.zip');save('combined-root-fixture.json',fixture)
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip,file/CartQa.zip\nserver-ip=127.0.0.1\nserver-port=25616\nonline-mode=true\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\nenable-query=false\nenable-status=false\n')
    return folder

def cart_phase(name,jar,folder,cases):
    nonce=secrets.token_hex(16);report={'pass':False,'nonce':nonce};proc=None;reader=None;lines=[];events=queue.Queue()
    result=folder/'plugins/R3915CartQa/result.json'
    try:
        if result.exists():
            need(not result.is_symlink() and result.is_file(),'Invalid result path')
            with (OUT/(name+'-previous-result.json')).open('xb') as f:f.write(result.read_bytes())
            result.unlink()
        args=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r399OceanClosure=true','-Dneverfolia.r3913IceFragments=true','-Dneverfolia.qaNonce='+nonce,'-jar',str(jar),'--nogui']
        proc=subprocess.Popen(args,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'-server.log')).open('w',encoding='utf-8') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start();end=time.monotonic()+360;done=False;passed=False
        while time.monotonic()<end:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'Done (' in line:done=True
            if 'R3915 CART ' in line:print(line.strip(),flush=True)
            if 'R3915 CART QA FAIL' in line:raise ValueError('Current cart fixture failed')
            if 'R3915 CART QA PASS nonce='+nonce in line:passed=True
            if done and passed:break
        need(done and passed,'No fresh completed cart phase')
        observed=json.loads(result.read_text());report['observed']=observed;validate_cart(observed,nonce,cases)
        proc.stdin.write('stop\n');proc.stdin.flush();report['exit_code']=proc.wait(timeout=120);reader.join(timeout=15)
        need(report['exit_code']==0 and not reader.is_alive(),'Unclean cart shutdown')
        report['targeted_errors']=[x.strip() for x in lines if any(b in x for b in BAD)]
        need(not report['targeted_errors'],'Targeted server errors');report['pass']=True
    except Exception as e:
        report['error']=repr(e)
        if result.is_file():
            try:report['observed']=json.loads(result.read_text())
            except Exception:pass
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader:reader.join(timeout=15)
        save(name+'-phase.json',report)
        print('COMBINED_CART_PHASE',name,json.dumps({k:v for k,v in report.items() if k!='observed'}),flush=True)
    return report

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
    report={'pass':False,'production_accepted':False,'all_reported_bugs_fixed':False,'scope':'Same composed datapack: original jigsaw child NPCs and real connected-player Swift lifecycle. No natural spawn-frequency, all-worldgen, GUI or all-resource acceptance.'}
    try:
        build=json.loads((OUT/'combined-content.json').read_text());need(build.get('pass') is True,'No combined build')
        pack=exact_file(OUT,'NeverOverworld-R3915-Combined.zip',build['output_sha256'])
        kernel=exact_file(ROOT/'swift-input','server-r3915.jar',c.CORE)
        nether=exact_file(ROOT/'inputs','NeverNether.zip',swift.NETHER)
        original_core=exact_file(ROOT/'inputs','server.jar',swift.CORE)
        original_pack=exact_file(ROOT/'inputs','NeverOverworld.zip',swift.BASE)
        prior=json.loads(one(ROOT/'swift-input','swift-lifecycle-runtime.json').read_text())
        need(prior.get('pass') is True and prior.get('new_core_sha256')==c.CORE,'Wrong completed lifecycle input')
        need(prior.get('dismount_cleanup_pass') is True and prior.get('harness_removal_pass') is True,'Missing inherited lifecycle checks')
        cases=build['cases'];validate_cases(cases)
        cp=classpath(kernel)
        lifecycle=one(ROOT/'swift-input','R3915SwiftQa-lifecycle.java.txt').read_text()
        need('EnchantmentHelper.tickEffects(level,driver)' in lifecycle and 'no fixture repair is needed after dismount' in lifecycle,'Not the strict executed lifecycle QA')
        swift_plugin=compile_plugin('R3915SwiftQa',lifecycle,cp)
        cart_plugin=compile_plugin('R3915CartQa',(Path(__file__).parent/'R3915CartQa.java').read_text(),cp,{'cases.json':json.dumps(cases)})
        swift.BAD=BAD;Client,cfg=swift.wire_config()
        report['swift_baseline']=swift.phase('combined-swift-baseline',original_core,swift.setup('combined-swift-baseline',original_pack,nether,swift_plugin),True,Client,cfg)
        need(report['swift_baseline']['pass'],'Original control failed')
        sf=swift.setup('combined-swift',pack,nether,swift_plugin)
        report['swift']=swift.phase('combined-swift',kernel,sf,False,Client,cfg);need(report['swift']['pass'],'Combined Swift failed')
        report['swift_restart']=swift.phase('combined-swift-restart',kernel,sf,False,Client,cfg);need(report['swift_restart']['pass'],'Combined Swift restart failed')
        for name in ('swift','swift_restart'):
            rows=report[name]['observed']['levels'];need([x['tier'] for x in rows]==[1,2,3] and not any(x['residual_rider_modifier_after_detach'] for x in rows),'Incomplete lifecycle cleanup')
        cf=cart_world(pack,nether,cart_plugin,cases)
        report['carts']=cart_phase('combined-carts',kernel,cf,cases);need(report['carts']['pass'],'Combined cart placement failed')
        report['carts_restart']=cart_phase('combined-carts-restart',kernel,cf,cases);need(report['carts_restart']['pass'],'Combined cart rerun after restart failed')
        for folder in (sf,cf):
            need(sha(folder/'world/datapacks/NeverOverworld.zip')==build['output_sha256'] and sha(folder/'world/datapacks/NeverNether.zip')==swift.NETHER,'Test pack copy changed')
        need(sha(kernel)==c.CORE and sha(original_core)==swift.CORE and sha(original_pack)==swift.BASE,'Original inputs modified')
        report.update({'pass':True,'core_sha256':c.CORE,'pack_sha256':build['output_sha256'],'nether_sha256':swift.NETHER,'cart_cases':len(cases),'cart_restart_kind':'fresh full fixture rerun after loading the same world, not a saved-NPC persistence claim','inherited_lifecycle_source_sha256':hashlib.sha256(lifecycle.encode()).hexdigest(),'user_kit_published':False})
    except Exception as e:report['error']=repr(e)
    finally:save('combined-runtime.json',report)
    print('COMBINED_RUNTIME',json.dumps({k:v for k,v in report.items() if k not in ('swift_baseline','swift','swift_restart','carts','carts_restart')},ensure_ascii=False),flush=True)
    need(report['pass'],'Combined runtime not accepted')
if __name__=='__main__':main()
