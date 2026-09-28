#!/usr/bin/env python3
"""Strict combined regression. Only fresh disposable loopback worlds are used.
No user installation is touched and this script never declares full acceptance.
"""
from pathlib import Path
import hashlib,json,queue,secrets,shutil,subprocess,threading,time,zipfile
import combine_content as content
import run_runtime as swift
import run_lifecycle

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts'
WORK=ROOT/'.work/r3916-combined'
SEED=-4651369264513492755
BAD=tuple(sorted(set(swift.BAD+('Empty or non-existent pool:', 'Block-attached entity at invalid position', 'porting_lib:'))))

def need(ok,message):
    if not ok:raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def unique(folder,name):
    paths=[p for p in Path(folder).rglob(name) if p.is_file() and not p.is_symlink()]
    need(len(paths)==1,'Missing/ambiguous input '+name+': '+str(paths))
    return paths[0]

def validate_inputs():
    build=json.loads((OUT/'combined-content.json').read_text())
    need(build.get('pass') is True and build['core_sha256']==content.CORE,'No successful combined build')
    pack=OUT/'NeverOverworld-R3915-Combined.zip'
    need(sha(pack)==build['output_sha256'],'Combined pack changed')
    core=unique('swift-input','server-r3915.jar')
    kernel=json.loads(unique('swift-input','swift-kernel.json').read_text())
    lifecycle=json.loads(unique('swift-input','swift-lifecycle-runtime.json').read_text())
    provenance=json.loads(unique('swift-input','lifecycle-provenance.json').read_text())
    need(provenance['commit']=='a8b3ad56b0dd67fa808efa52976fcffc7c665be5'
         and str(provenance['run_id'])=='36419010757','Unexpected lifecycle source')
    need(kernel.get('pass') is True and lifecycle.get('pass') is True,'Input lifecycle not accepted')
    need(kernel['output_sha256']==lifecycle['new_core_sha256']==sha(core)==content.CORE,'Input core identity disagreement')
    need(lifecycle['new_pack_sha256']==content.SWIFT,'Input pack identity disagreement')
    need(lifecycle.get('dismount_cleanup_pass') is True and lifecycle.get('harness_removal_pass') is True,'Incomplete input lifecycle')
    for label in ('baseline','candidate','restart'):
        phase=lifecycle[label]
        need(phase.get('pass') is True and phase.get('exit_code')==0,'Unsuccessful input phase '+label)
    cases=build['cases']
    expected={f'nova_structures:tavern/tavern_event_trader_car_{role}_{biome}'
              for role in ('cartographer','cleric') for biome in content.BIOMES}
    expected|={f'nova_structures:tavern/tavern_event_trader_car_armorer_{biome}'
               for biome in ('mangrove','pale','swamp')}
    need(len(cases)==25 and {row['id'] for row in cases}==expected,'Wrong combined case set')
    for case in cases:
        # Pale variants intentionally lack the author's villager outlet.
        need(case['expected_villagers']==(0 if case['biome']=='pale' else 1),'Unexpected NPC expectation')
    nether=swift.exact('NeverNether.zip',swift.NETHER)
    return core,pack,nether,cases,build,kernel

def compile_carts(cases):
    classes=WORK/'cart-classes';classes.mkdir()
    cp=(swift.WORK/'classpath.txt').read_text()
    source=ROOT/'qa/field-r3915/R3915CartQa.java'
    proc=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(source)],capture_output=True,text=True,timeout=90)
    (OUT/'combined-cart-javac.log').write_text(proc.stdout+proc.stderr)
    print(proc.stdout+proc.stderr,flush=True);need(proc.returncode==0,'Combined cart QA compile failed')
    plugin=WORK/'R3915CartQa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(classes.rglob('*.class')):archive.write(path,path.relative_to(classes).as_posix())
        archive.writestr('plugin.yml',"name: R3915CartQa\nversion: '3'\nmain: R3915CartQa\napi-version: '26.2'\nfolia-supported: true\n")
        archive.writestr('cases.json',json.dumps(cases))
    return plugin

def setup_carts(pack,nether,plugin,cases):
    folder=WORK/'cart-world';packs=folder/'world/datapacks';packs.mkdir(parents=True)
    plugins=folder/'plugins';plugins.mkdir()
    shutil.copyfile(pack,packs/'NeverOverworld.zip');shutil.copyfile(nether,packs/'NeverNether.zip')
    shutil.copyfile(plugin,plugins/'R3915CartQa.jar')
    with zipfile.ZipFile(pack) as original,zipfile.ZipFile(packs/'CartQa.zip','w',zipfile.ZIP_DEFLATED) as qa:
        qa.writestr('pack.mcmeta',original.read('pack.mcmeta'))
        for index,case in enumerate(cases):
            pool={'fallback':'minecraft:empty','elements':[{'weight':1,'element':{'element_type':'minecraft:single_pool_element','location':case['id'],'processors':'minecraft:empty','projection':'rigid'}}]}
            qa.writestr(f'data/neverfolia_qa/worldgen/template_pool/cart/case_{index}.json',json.dumps(pool))
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip,file/CartQa.zip\nserver-ip=127.0.0.1\nserver-port=25616\nonline-mode=true\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\nenable-query=false\nenable-status=false\n')
    return folder

def cart_phase(name,core,folder,cases):
    nonce=secrets.token_hex(16);report={'pass':False,'nonce':nonce};process=None;pump=None;lines=[];events=queue.Queue()
    result=folder/'plugins/R3915CartQa/result.json'
    try:
        if result.exists():
            with (OUT/(name+'-previous-result.json')).open('xb') as stream:stream.write(result.read_bytes())
            result.unlink()
        command=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r399OceanClosure=true','-Dneverfolia.r3913IceFragments=true','-Dneverfolia.qaNonce='+nonce,'-jar',str(core.resolve()),'--nogui']
        process=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def read_output():
            with (OUT/(name+'-server.log')).open('w',encoding='utf-8') as log:
                for line in process.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        pump=threading.Thread(target=read_output,daemon=True);pump.start()
        done=False;passed=False;deadline=time.monotonic()+420
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if process.poll() is not None:break
                continue
            if line is None:break
            if 'Done (' in line:done=True
            if 'R3915 CART ' in line:print(line.strip(),flush=True)
            if 'R3915 CART QA FAIL' in line:raise ValueError('Current cart fixture reported FAIL')
            if 'R3915 CART QA PASS nonce='+nonce in line:passed=True
            if done and passed:break
        need(done and passed,'Current cart run did not finish')
        observed=json.loads(result.read_text());report['observed']=observed
        need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('seed')==SEED,'Wrong current cart result')
        rows=observed.get('checks',[])
        need(observed.get('completed')==25 and len(rows)==25,'Incomplete cart coverage')
        need([row['id'] for row in rows]==[case['id'] for case in cases],'Unexpected cart order or duplicate')
        for row,case in zip(rows,cases):
            need(row.get('pass') is True and row['observed_villagers']==case['expected_villagers'],'NPC assertion changed')
            need(row['workstations']==1 and row['remaining_jigsaws']==0,'Unfinished cart')
        barriers=observed.get('entity_teardowns',[])
        need(len(barriers)==25 and all(row.get('live_after_barrier')==0 for row in barriers),'Missing clean-scene barriers')
        process.stdin.write('stop\n');process.stdin.flush();report['exit_code']=process.wait(timeout=120);pump.join(timeout=15)
        need(report['exit_code']==0 and not pump.is_alive(),'Unclean cart process stop')
        report['targeted_errors']=[line.strip() for line in lines if any(term in line for term in BAD)]
        need(not report['targeted_errors'],'Targeted cart/server errors');report['pass']=True
    except Exception as error:
        report['error']=repr(error)
        if result.is_file():
            try:report['observed']=json.loads(result.read_text())
            except (ValueError,OSError):pass
    finally:
        if process is not None and process.poll() is None:
            try:process.stdin.write('stop\n');process.stdin.flush();process.wait(timeout=45)
            except Exception:
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
        if pump:pump.join(timeout=15)
        save(name+'-phase.json',report)
        print('COMBINED_CART_PHASE',name,json.dumps({k:v for k,v in report.items() if k!='observed'}),flush=True)
    return report

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False)
    report={'pass':False,'production_accepted':False,'scope':'Combined cart NPC assembly and connected-player Swift lifecycle; not full worldgen, natural mob distribution or remaining resource acceptance.'}
    try:
        core,pack,nether,cases,build,kernel=validate_inputs()
        plugin=compile_carts(cases);folder=setup_carts(pack,nether,plugin,cases)
        report['cart']=cart_phase('combined-cart',core,folder,cases);need(report['cart']['pass'],'Combined cart assembly failed')
        report['cart_restart']=cart_phase('combined-cart-restart',core,folder,cases);need(report['cart_restart']['pass'],'Combined cart restart failed')
        # Reuse the unchanged strict lifecycle runner on the combined datapack.
        # Reports identify this composition; no old runtime report is copied.
        shutil.copyfile(core,OUT/'server-r3915.jar');shutil.copyfile(pack,OUT/'NeverOverworld-R3915.zip')
        save('swift-kernel.json',kernel)
        save('swift-build.json',{'pass':True,'output_sha256':build['output_sha256'],'kind':'combined content composition','combined_report':'combined-content.json','original_swift_pack_sha256':content.SWIFT})
        run_lifecycle.main()
        lifecycle=json.loads((OUT/'swift-lifecycle-runtime.json').read_text());need(lifecycle['pass'] is True,'Combined lifecycle failed')
        report['swift_lifecycle']=lifecycle
        need(sha(core)==content.CORE and sha(pack)==build['output_sha256'] and sha(nether)==swift.NETHER,'Combined input mutated')
        for name,want in (('NeverOverworld.zip',build['output_sha256']),('NeverNether.zip',swift.NETHER)):
            need(sha(folder/'world/datapacks'/name)==want,'Cart server mutated input '+name)
        report.update({'pass':True,'core_sha256':content.CORE,'pack_sha256':build['output_sha256'],'nether_sha256':swift.NETHER})
    except Exception as error:report['error']=repr(error)
    finally:save('combined-runtime.json',report)
    print('COMBINED_RUNTIME',json.dumps({k:v for k,v in report.items() if k not in ('cart','cart_restart','swift_lifecycle')}),flush=True)
    need(report['pass'],'Combined integration not accepted')
if __name__=='__main__':main()
