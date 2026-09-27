#!/usr/bin/env python3
"""Isolated CI diagnostics for the exact full candidate. Never operates on user worlds."""
from pathlib import Path
import argparse,copy,hashlib,importlib.util,io,json,os,queue,shutil,subprocess,sys,threading,time,zipfile
ROOT=Path(__file__).resolve().parents[2]
SEED=-4651369264513492755
CORE='411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def need(ok,message):
    if not ok:raise ValueError(message)

def extract_one(z,suffix,output):
    names=[n for n in z.namelist() if n.endswith(suffix)];need(len(names)==1,'Ambiguous debug member '+suffix)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(z.read(names[0]));return output

def prepare(candidate,debug,out):
    need(sha(candidate/'server.jar')==CORE,'Wrong core');need(sha(candidate/'NeverNether.zip')==NETHER,'Wrong Nether')
    build=json.loads((out/'r394-build.json').read_text());need(sha(candidate/'NeverOverworld.zip')==build['output_sha256'],'Wrong Overworld')
    libs=ROOT/'.work/r394-classpath';libs.mkdir(parents=True,exist_ok=True)
    inputs={n:sha(candidate/n) for n in ('server.jar','NeverOverworld.zip','NeverNether.zip')};save(out/'r394-inputs.json',inputs)
    with zipfile.ZipFile(debug/'diagnostics.zip') as z:
        for suffix,path in [('qa/field-r37/R37DungeonQa.jar',ROOT/'.work/r394-plugins/R37DungeonQa.jar'),('qa/field-r38/R38TrialQa.jar',ROOT/'.work/r394-plugins/R38TrialQa.jar'),('materialized/folia-server/src/minecraft/java/net/minecraft/network/protocol/game/GameProtocols.java',ROOT/'.work/Folia/folia-server/src/minecraft/java/net/minecraft/network/protocol/game/GameProtocols.java'),('folia-api/build/libs/folia-api-26.2-R0.1-SNAPSHOT.jar',libs/'folia-api.jar')]:extract_one(z,suffix,path)
        # Keep exact source used to reason about placement; all diagnostics remain outside the gameplay pack.
        for suffix in ('JigsawPlacement.java','StructureTemplate.java','SinglePoolElement.java'):
            extract_one(z,'/'+suffix,out/'engine-source'/suffix)
    with zipfile.ZipFile(candidate/'server.jar') as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+n.rsplit('/',1)[-1])).write_bytes(z.read(n))
    need(any(p.name.endswith('folia-26.2.jar') for p in libs.glob('*.jar')),'Actual bundled server missing')
    classes=ROOT/'.work/r394-classes';classes.mkdir(parents=True,exist_ok=True)
    command=['javac','--release','25','-classpath',os.pathsep.join(map(str,sorted(libs.glob('*.jar')))),'-d',str(classes),str(ROOT/'qa/field-r394/R394CartQaPlugin.java')]
    result=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(out/'r394-javac.log').write_text(result.stdout);print(result.stdout,flush=True);need(result.returncode==0,'Actual-core Java compilation failed')
    with zipfile.ZipFile(ROOT/'.work/r394-plugins/R394CartQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,str(p.relative_to(classes)))
        z.writestr('plugin.yml',"name: R394CartQa\nversion: '1'\nmain: R394CartQaPlugin\napi-version: '26.2'\nfolia-supported: true\n")
    save(out/'r394-java-build.json',{'pass':True,'core_sha256':CORE,'plugin_sha256':sha(ROOT/'.work/r394-plugins/R394CartQa.jar'),'compiler':subprocess.run(['javac','-version'],text=True,capture_output=True,check=True).stdout})

def fixtures(pack,output):
    biomes=('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp');roles=('cartographer','cleric')
    targets={f'nova_structures:tavern/tavern_event_trader_car_{role}_{biome}':f'{role}_{biome}' for biome in biomes for role in roles};found={k:[] for k in targets}
    with zipfile.ZipFile(pack) as z:
        metadata={'pack':copy.deepcopy(json.loads(z.read('pack.mcmeta'))['pack'])};metadata['pack']['description']='CI ONLY: isolated root choices, NOT a gameplay modification'
        def walk(obj):
            if isinstance(obj,dict):
                location=obj.get('location')
                if location in targets and obj.get('element_type') in ('minecraft:single_pool_element','minecraft:legacy_single_pool_element'):found[location].append(obj)
                for value in obj.values():walk(value)
            elif isinstance(obj,list):
                for value in obj:walk(value)
        for n in z.namelist():
            if '/worldgen/template_pool/' in n and n.endswith('.json'):walk(json.loads(z.read(n)))
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('pack.mcmeta',json.dumps(metadata))
        for location,name in targets.items():
            elements=found[location];need(bool(elements),'No original parent reference for '+location)
            need(len({json.dumps(e,sort_keys=True) for e in elements})==1,'Ambiguous parent element settings')
            z.writestr('data/neverfolia_qa/worldgen/template_pool/cart/'+name+'.json',json.dumps({'fallback':'minecraft:empty','elements':[{'weight':1,'element':elements[0]}]}))
    return {'sha256':sha(output),'root_count':22,'source_elements_preserved':True,'scope':'Selection-only CI root pools; not shipped in NeverOverworld'}

def carts(candidate,out):
    folder=ROOT/'.work/r394-cart-world';folder.mkdir(parents=True,exist_ok=False);packs=folder/'world/datapacks';packs.mkdir(parents=True)
    for name in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(candidate/name,packs/name)
    fixture=fixtures(candidate/'NeverOverworld.zip',packs/'CartQa.zip');save(out/'r394-cart-fixture-pack.json',fixture)
    (folder/'plugins').mkdir();shutil.copyfile(ROOT/'.work/r394-plugins/R394CartQa.jar',folder/'plugins/R394CartQa.jar')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip,file/CartQa.zip\nserver-ip=127.0.0.1\nserver-port=25601\nonline-mode=true\nenable-query=false\nenable-rcon=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    result={'pass':False,'fixture':fixture,'candidate_sha256':sha(candidate/'NeverOverworld.zip')};proc=None;reader=None;lines=[];events=queue.Queue()
    try:
        proc=subprocess.Popen(['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx3G','-jar',str(candidate/'server.jar'),'--nogui'],cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        def pump():
            with (out/'r394-carts.log').open('w') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+480;completed=False
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'R394 CART ' in line:print(line.rstrip(),flush=True)
            if 'R394 CART QA ' in line:completed=True;break
        need(completed,'Cart fixture did not complete')
        observed=json.loads((folder/'plugins/R394CartQa/result.json').read_text());result['placement']=observed
        proc.stdin.write('stop\n');proc.stdin.flush();result['exit_code']=proc.wait(timeout=120);reader.join(timeout=5)
        result['warnings_and_errors']=[line.rstrip() for line in lines if ' WARN]' in line or ' ERROR]' in line]
        result['targeted_errors']=[line.rstrip() for line in lines if any(v in line for v in ('Failed to load registries','Block-attached entity at invalid position','[ChunkTaskScheduler] Chunk system error','porting_lib:'))]
        result['pass']=observed.get('pass') is True and observed.get('completed')==22 and result['exit_code']==0 and not result['targeted_errors']
    except Exception as error:result['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=5)
        result['pack_copies_unchanged']=all(sha(candidate/n)==sha(packs/n) for n in ('NeverOverworld.zip','NeverNether.zip'));result['pass']=result['pass'] and result['pack_copies_unchanged'];save(out/'r394-cart-placement.json',result)
    print(json.dumps(result,indent=2),flush=True);need(result['pass'],'Live cart placement not accepted')

def water(candidate,out):
    harness=load('r394_live_harness',ROOT/'qa/field-r38/run-live.py')
    harness.TARGETS=tuple(harness.TARGETS)+((-202,-213),(-204,-213))
    harness.CHUNKS=sorted({(cx+dx,cz+dz) for cx,cz in harness.TARGETS for dx in (-1,0,1) for dz in (-1,0,1)})
    need(len(harness.CHUNKS)==63,'Unexpected expanded coverage')
    original_save=harness.save
    def save_with_scope(path,data):
        if path.name=='r38-live-qa.json':
            data['scope']='63 saved target chunks: original 48 plus 15 around reported distant dungeon; full LIGHT water provenance, ordinary-player trial fixtures, restart and reverse generation. Not every seed, full visual geometry or every custom mob.'
            data['target_chunks']=harness.CHUNKS;data['harness_revision']='R38 harness reused for exact R39.4 inputs';data['production_accepted']=False
        original_save(path,data)
    harness.save=save_with_scope
    save(out/'r394-water-targets.json',{'seed':SEED,'chunks':harness.CHUNKS,'reported_positions':[[-3217,46,-3398],[-3259,46,-3397]],'diagnostic_only_positions':True})
    sys.argv=['run-live.py','--jar',str(candidate/'server.jar'),'--overworld',str(candidate/'NeverOverworld.zip'),'--nether',str(candidate/'NeverNether.zip'),'--controller-plugin',str(ROOT/'.work/r394-plugins/R37DungeonQa.jar'),'--trial-plugin',str(ROOT/'.work/r394-plugins/R38TrialQa.jar'),'--output',str(out/'live'),'--work',str(ROOT/'.work/r394-live-worlds'),'--source-sha',os.environ.get('GITHUB_SHA','unknown')]
    harness.main()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('prepare','carts','water'));p.add_argument('--candidate',type=Path,required=True);p.add_argument('--debug',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.candidate=a.candidate.resolve();a.debug=a.debug.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    if a.phase=='prepare':prepare(a.candidate,a.debug,a.output)
    elif a.phase=='carts':carts(a.candidate,a.output)
    else:water(a.candidate,a.output)
if __name__=='__main__':main()
