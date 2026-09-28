#!/usr/bin/env python3
"""Isolated real-kernel placement check. Never reads or modifies a player world."""
from pathlib import Path
import hashlib,importlib.util,json,os,queue,shutil,subprocess,sys,threading,time,uuid,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'resource-evidence';WORK=ROOT/'.work/r3914-runtime'
SEED=-4651369264513492755
BAD=('Failed to load registries','Failed to load datapacks','Overworld settings missing','Block-attached entity at invalid position','[ChunkTaskScheduler] Chunk system error','porting_lib:', 'Empty or non-existent pool:')
def need(ok,message):
    if not ok:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def replace(text,a,b):
    need(text.count(a)==1,'Unexpected fixture source anchor '+a[:80]);return text.replace(a,b,1)
def main():
    WORK.mkdir(parents=True,exist_ok=False);libs=WORK/'libs';libs.mkdir();classes=WORK/'classes';classes.mkdir()
    jar=next((ROOT/'inputs').rglob('server.jar'));pack=ROOT/'candidate-resources/NeverOverworld.zip';nether=next((ROOT/'inputs').rglob('NeverNether.zip'))
    build=json.loads(next((ROOT/'inputs').rglob('r3913-build.json')).read_text())
    need(sha(jar)==build['candidate_core_sha256'],'Wrong combined ice/water kernel')
    with zipfile.ZipFile(jar) as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
    providers=[]
    for p in libs.glob('*.jar'):
        with zipfile.ZipFile(p) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():providers.append(p)
    if not providers:
        with zipfile.ZipFile(next((ROOT/'debug').rglob('diagnostics.zip'))) as z:
            names=[n for n in z.namelist() if n.endswith('/folia-api/build/libs/folia-api-26.2-R0.1-SNAPSHOT.jar')]
            need(len(names)==1,'Exact API unavailable');(libs/'api.jar').write_bytes(z.read(names[0]))
    text=(ROOT/'qa/field-r394/R394CartQaPlugin.java').read_text()
    text=replace(text,'int cx=300+index*3;','int cx=300; // Reuse only this private fixture chunk, clearing each prior villager.')
    text=replace(text,'try{world.setChunkForceLoaded(cx,300,true);world.getChunkAtAsync','try{world.getChunkAtAsync')
    text=replace(text,'String role=ROLES[index%2],biome=BIOMES[index/2];','world.setChunkForceLoaded(cx,300,true);\n  String role=ROLES[index%2],biome=BIOMES[index/2];')
    text=replace(text,'Bukkit.getGlobalRegionScheduler().execute(this,()->world.setChunkForceLoaded(cx,300,false));next(index+1);','for(var entity:entities)entity.discard();\n     world.setChunkForceLoaded(cx,300,false);next(index+1);')
    text=replace(text,'report.addProperty("completed",checks.size());','report.addProperty("completed",checks.size());report.addProperty("nonce",System.getProperty("neverfolia.qaNonce"));report.addProperty("actual_seed",Long.toString(world.getSeed()));')
    source=WORK/'R394CartQaPlugin.java';source.write_text(text);(OUT/'R3914-actual-fixture-source.java').write_text(text)
    command=['javac','--release','25','-proc:none','-classpath',os.pathsep.join(map(str,libs.glob('*.jar'))),'-d',str(classes),str(source)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=90);(OUT/'cart-javac.log').write_text(result.stdout+result.stderr);need(result.returncode==0,'Cart javac failed: '+result.stderr)
    folder=WORK/'server';packs=folder/'world/datapacks';packs.mkdir(parents=True);plugins=folder/'plugins';plugins.mkdir()
    with zipfile.ZipFile(plugins/'CartQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R394CartQa\nversion: 'R3914'\nmain: R394CartQaPlugin\napi-version: '26.2'\nfolia-supported: true\n")
    old=load('r3914_selection_fixture',ROOT/'qa/field-r394/run_checks.py');old.fixtures(pack,packs/'CartQa.zip')
    for src,name in ((pack,'NeverOverworld.zip'),(nether,'NeverNether.zip')):shutil.copyfile(src,packs/name)
    (folder/'eula.txt').write_text('eula=true\n') # Existing ephemeral CI test-world convention only.
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip,file/CartQa.zip\nserver-ip=127.0.0.1\nserver-port=25614\nonline-mode=true\nenable-rcon=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    nonce=uuid.uuid4().hex;events=queue.Queue();lines=[];proc=None;reader=None
    report={'pass':False,'nonce':nonce,'kernel_sha256':sha(jar),'pack_sha256':sha(pack),'production_accepted':False,'scope':'Actual loaded new templates, selection-only root pools, original child pools. Not all dungeon mobs/trades or general worldgen acceptance.'}
    def pump():
        with (OUT/'cart-server.log').open('w') as log:
            for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
        events.put(None)
    try:
        proc=subprocess.Popen(['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx3G','-Dneverfolia.r395OceanClosure=true','-Dneverfolia.r3911WideOceanClosure=true','-Dneverfolia.r3913IceFragments=true','-Dneverfolia.qaNonce='+nonce,'-jar',str(jar),'--nogui'],cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+500;success=False
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'R394 CART ' in line:print(line.rstrip(),flush=True)
            if 'R394 CART QA ' in line:
                need('R394 CART QA PASS' in line,'Current placement failed');success=True;break
        need(success,'Current fixture did not finish')
        observed=json.loads((plugins/'R394CartQa/result.json').read_text());report['observed']=observed
        need(observed.get('pass') is True and observed.get('completed')==22 and observed.get('nonce')==nonce and observed.get('actual_seed')==str(SEED),'Incomplete/stale/wrong-seed report')
        checks=observed['checks'];expected={(b,r) for b in ('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp') for r in ('cartographer','cleric')}
        need(len(checks)==22 and {(r['biome'],r['cart_variant']) for r in checks}==expected and all(r['pass'] for r in checks),'Wrong scenario coverage')
        proc.stdin.write('stop\n');proc.stdin.flush();report['exit_code']=proc.wait(timeout=120);reader.join(timeout=10);need(not reader.is_alive(),'Incomplete logs')
        report['targeted_errors']=[l.strip() for l in lines if any(x in l for x in BAD)];need(not report['targeted_errors'],'Targeted runtime error')
        need(report['exit_code']==0,'Unclean shutdown');need(sha(jar)==report['kernel_sha256'] and sha(pack)==report['pack_sha256'],'Input changed')
        report['pass']=True
    except Exception as e:report['error']=repr(e)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader:reader.join(timeout=5)
        (OUT/'cart-runtime.json').write_text(json.dumps(report,indent=2)+'\n')
    print('CART_RUNTIME '+json.dumps(report),flush=True);need(report['pass'],'Cart runtime not accepted')
if __name__=='__main__':main()
