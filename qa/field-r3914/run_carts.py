#!/usr/bin/env python3
"""Run only disposable CI worlds; binds loopback only, never opens a user's world."""
from pathlib import Path
import hashlib,importlib.util,io,json,os,queue,secrets,shutil,subprocess,threading,time,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3914';SEED=-4651369264513492755
CORE='9571073a77086b04ce54594fe2b91737fdf9daf4019d4ce585016f77c03912f6'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
BAD=('Failed to load datapacks','Failed to load registries','Overworld settings missing','Empty or non-existent pool:', 'Unknown registry key','Block-attached entity at invalid position','Chunk system error','Exception in server tick loop','The server has not responded for','porting_lib:')
def need(ok,message):
    if not ok:raise ValueError(message)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def exact(name,digest):
    paths=list((ROOT/'inputs').rglob(name));need(len(paths)==1 and sha(paths[0])==digest,'Wrong input '+name);return paths[0]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def resolve_api(libs,debug):
    providers=[]
    for path in libs.glob('*.jar'):
        with zipfile.ZipFile(path) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():providers.append(path)
    if not providers:
        need(len(debug)==1,'Ambiguous pinned debug archive')
        with zipfile.ZipFile(debug[0]) as z:
            matches=[]
            for name in z.namelist():
                if not name.endswith('.jar') or 'folia-api' not in name:continue
                raw=z.read(name)
                with zipfile.ZipFile(io.BytesIO(raw)) as candidate:
                    if 'org/bukkit/Bukkit.class' in candidate.namelist():matches.append((name,raw))
            need(len(matches)==1,'Missing or ambiguous actual API provider: '+repr([n for n,r in matches]))
            provider=libs/'folia-api.jar';provider.write_bytes(matches[0][1]);providers.append(provider)
            source=matches[0][0]
    else:source='embedded runtime library'
    need(len(providers)==1,'Multiple Bukkit API providers on classpath')
    row={'file':providers[0].name,'sha256':sha(providers[0]),'source':source,'provenance':'pinned R3913 runtime / pinned R38 DEBUG artifact'}
    save('cart-api-provider.json',row);print('ACTUAL_API',json.dumps(row),flush=True)

def phase(jar,folder,fixture):
    name='placement' if fixture else 'restart';nonce=secrets.token_hex(16);proc=None;reader=None;lines=[];events=queue.Queue();result={'pass':False,'nonce':nonce,'fixture':fixture}
    try:
        command=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r399OceanClosure=true','-Dneverfolia.r3913IceFragments=true','-Dneverfolia.qaNonce='+nonce,'-jar',str(jar),'--nogui']
        proc=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/('cart-'+name+'.log')).open('w',encoding='utf-8') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+540;done=False;passed=not fixture
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'Done (' in line:done=True
            if 'R3914 CART ' in line:print(line.strip(),flush=True)
            if 'R3914 CART QA FAIL' in line:raise ValueError('Current plugin reported failure')
            if 'R3914 CART QA PASS nonce='+nonce in line:passed=True
            if done and passed:break
        need(done and passed,'Current server did not complete')
        if fixture:
            observed=json.loads((folder/'plugins/R3914CartQa/result.json').read_text())
            need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('seed')==SEED,'Wrong fresh result')
            need(observed.get('completed')==22 and len(observed['checks'])==22 and all(r['pass'] is True for r in observed['checks']),'Incomplete coverage')
            expected=[f'nova_structures:tavern/tavern_event_trader_car_{role}_{biome}' for biome in ('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp') for role in ('cartographer','cleric')]
            need([r['id'] for r in observed['checks']]==expected,'Unexpected or duplicate variant')
            result['observed']=observed;save('cart-placement-observed.json',observed)
        proc.stdin.write('stop\n');proc.stdin.flush();result['exit_code']=proc.wait(timeout=120);reader.join(timeout=15)
        need(result['exit_code']==0 and not reader.is_alive(),'Unclean stop')
        result['targeted_errors']=[s.strip() for s in lines if any(t in s for t in BAD)];need(not result['targeted_errors'],'Targeted runtime error')
        result['pass']=True
    except Exception as e:result['error']=repr(e)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=15)
        save('cart-'+name+'-phase.json',result)
    print('CART_PHASE',name,json.dumps({k:v for k,v in result.items() if k!='observed'}),flush=True);return result

def main():
    WORK.mkdir(parents=True,exist_ok=False);build=json.loads((OUT/'cart-build.json').read_text());need(build['pass'] is True,'Pack was not built')
    pack=OUT/'NeverOverworld-R3914.zip';need(sha(pack)==build['output_sha256'],'Pack changed since build')
    jar=exact('server.jar',CORE);nether=exact('NeverNether.zip',NETHER);libs=WORK/'libs';libs.mkdir();classes=WORK/'classes';classes.mkdir()
    with zipfile.ZipFile(jar) as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
    resolve_api(libs,list((ROOT/'debug').rglob('diagnostics.zip')))
    compiler=subprocess.run(['javac','-version'],capture_output=True,text=True,check=True);need('javac 25' in compiler.stdout+compiler.stderr,'Java 25 required')
    command=['javac','--release','25','-proc:none','-classpath',os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar'))),'-d',str(classes),str(ROOT/'qa/field-r3914/R3914CartQa.java')]
    done=subprocess.run(command,capture_output=True,text=True);(OUT/'cart-javac.log').write_text(done.stdout+done.stderr);print(done.stdout+done.stderr,flush=True);need(done.returncode==0,'QA compiler failure')
    folder=WORK/'world';packs=folder/'world/datapacks';packs.mkdir(parents=True);plugins=folder/'plugins';plugins.mkdir()
    shutil.copyfile(pack,packs/'NeverOverworld.zip');shutil.copyfile(nether,packs/'NeverNether.zip')
    helper=load('r3914_root_fixture',ROOT/'qa/field-r394/run_checks.py');fixture=helper.fixtures(pack,packs/'CartQa.zip');save('cart-root-fixture.json',fixture)
    with zipfile.ZipFile(plugins/'R3914CartQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3914CartQa\nversion: '1'\nmain: R3914CartQa\napi-version: '26.2'\nfolia-supported: true\n")
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip,file/CartQa.zip\nserver-ip=127.0.0.1\nserver-port=25614\nonline-mode=true\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\nenable-query=false\nenable-status=false\n')
    report={'pass':False,'core_sha256':CORE,'pack_sha256':build['output_sha256'],'production_accepted':False,'scope':'Actual synthetic cart assemblies, source NPC child pools and same-world startup restart. Not full natural dungeon or combat acceptance.'}
    try:
        report['placement']=phase(jar,folder,True);need(report['placement']['pass'],'Cart placement failed')
        (plugins/'R3914CartQa.jar').rename(plugins/'R3914CartQa.disabled')
        report['restart']=phase(jar,folder,False);need(report['restart']['pass'],'Restart failed')
        need(sha(jar)==CORE and sha(pack)==build['output_sha256'] and sha(packs/'NeverOverworld.zip')==build['output_sha256'] and sha(packs/'NeverNether.zip')==NETHER,'Inputs modified by run')
        report['pass']=True
    except Exception as e:report['error']=repr(e)
    finally:save('cart-runtime.json',report)
    print('CART_RUNTIME',json.dumps({k:v for k,v in report.items() if k not in ('placement','restart')}),flush=True)
    need(report['pass'],'Bounded runtime not accepted')
if __name__=='__main__':main()
