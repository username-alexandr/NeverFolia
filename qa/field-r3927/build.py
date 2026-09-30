#!/usr/bin/env python3
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3927-build';CAND=ROOT/'candidate'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
LIGHT_SHA='e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283'
KEEP=('net/minecraft/world/level/chunk/NeverOverworldWaterPolicyR38.class',
      'net/minecraft/world/level/chunk/NeverOverworldDryMinesR12.class',
      'net/minecraft/world/level/chunk/NeverOverworldDryMinesR12$Mask.class')
def need(ok,msg):
    if not ok:raise ValueError(msg)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid zip')
        return {n:z.read(n) for n in z.namelist()}
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def run(args,name):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'Failed '+name);return p.stdout
def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=False)
    base=ROOT/'baseline/server.jar';need(sha(base)==BASE,'Wrong R39.9 baseline')
    pack=ROOT/'baseline/world/datapacks/NeverOverworld.zip';nether=ROOT/'baseline/world/datapacks/NeverNether.zip'
    need(sha(pack)==PACK and sha(nether)==NETHER,'Wrong paired datapacks')
    outer=members(base.read_bytes());nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'Unexpected bundled kernel');nested=nested[0];inner=members(outer[nested])
    need(all(k in inner for k in KEEP),'Inherited R39.9 hotfix missing')
    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(raw)
    api=[]
    for p in libs.glob('*.jar'):
        with zipfile.ZipFile(p) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():api.append(p)
    need(len(api)==1,'Missing or ambiguous Bukkit API')
    r40=ROOT/'debug/ChunkLightTask-R40.java';need(r40.is_file(),'Missing retained LIGHT source')
    text=r40.read_text()
    retired='                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR395.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R40_ON_R399\n'
    need(text.count(retired)==1,'Unexpected R40 LIGHT source');text=text.replace(retired,'',1)
    need(digest(text.encode())==LIGHT_SHA,'Retained source does not normalize to exact R39.9 LIGHT')
    anchor='                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);'
    call='                net.minecraft.world.level.chunk.NeverOverworldOceanClassifierR3927.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R3927_AIR_PROVENANCE\n'
    need(text.count(anchor)==1,'LIGHT insertion anchor mismatch');text=text.replace(anchor,call+anchor,1)
    light=WORK/'src'/Path(LIGHT+'.java');light.parent.mkdir(parents=True);light.write_text(text);(OUT/'ChunkLightTask-R3927.java').write_text(text)
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))));(WORK/'classpath.txt').write_text(cp)
    classes=WORK/'classes';classes.mkdir();sources=sorted((ROOT/'native/overworld-r3927').glob('*.java'));need(len(sources)==2,'Wrong R3927 source set')
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(light)]+list(map(str,sources)),'core-javac.log')
    tests=WORK/'test-classes';tests.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes),'-d',str(tests),str(ROOT/'qa/field-r3927/OceanConnectivityR3927Test.java')],'solver-javac.log')
    run(['java','-cp',str(tests)+os.pathsep+str(classes),'OceanConnectivityR3927Test'],'solver-tests.log')
    replacements={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    need(not set(KEEP)&set(replacements),'Attempted overwrite of R39.9 hotfix')
    old_family={n for n in inner if n==LIGHT+'.class' or n.startswith(LIGHT+'$')};new_family={n for n in replacements if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
    need(old_family==new_family,'LIGHT family mismatch');need(all(int.from_bytes(v[6:8],'big')==69 for v in replacements.values()),'Wrong bytecode version')
    packaging=load('r3927_pack',ROOT/'qa/field-r395/jar_packaging.py');run(['python3',str(ROOT/'qa/field-r395/jar_packaging.py')],'packaging-tests.log')
    modified=packaging.rewrite_zip(outer[nested],replacements)
    rows=[];seen=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        f=line.split('\t');need(len(f)==3,'Bad versions row')
        if 'META-INF/versions/'+f[2]==nested:need(f[0]==digest(outer[nested]),'Bundled digest mismatch');f[0]=digest(modified);seen+=1
        rows.append('\t'.join(f))
    need(seen==1,'No bundled versions row')
    bundled=packaging.rewrite_zip(base.read_bytes(),{nested:modified,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()})
    new=members(modified);new_outer=members(bundled)
    need(all(new[k]==inner[k] for k in KEEP),'Inherited hotfix bytes changed')
    need(all(new[n]==inner[n] for n in inner if n not in replacements),'Unrelated bundled entry changed')
    need(set(outer)==set(new_outer) and {n for n in outer if outer[n]!=new_outer[n]}=={nested,'META-INF/versions.list'},'Unexpected outer delta')
    (CAND/'server.jar').write_bytes(bundled);shutil.copyfile(pack,CAND/'NeverOverworld.zip');shutil.copyfile(nether,CAND/'NeverNether.zip')
    fixture=WORK/'fixture-classes';fixture.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes)+os.pathsep+cp,'-d',str(fixture),str(ROOT/'qa/field-r3927/R3927ClassifierQa.java')],'fixture-javac.log')
    with zipfile.ZipFile(WORK/'R3927ClassifierQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in fixture.rglob('*.class'):z.write(p,p.relative_to(fixture).as_posix())
        z.writestr('plugin.yml',"name: R3927ClassifierQa\nversion: '1'\nmain: R3927ClassifierQa\napi-version: '26.2'\nfolia-supported: true\n")
    report={'build_pass':True,'base_core_sha256':BASE,'candidate_core_sha256':sha(CAND/'server.jar'),'pack_sha256':PACK,'nether_sha256':NETHER,
      'preserved_hotfix_classes':{k:digest(new[k]) for k in KEEP},'changed_or_added_classes':{k:digest(v) for k,v in sorted(replacements.items())},
      'uses_vanilla_carving_mask':True,'read_max_y':128,'production_accepted':False}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print('R3927_BUILD '+json.dumps(report),flush=True)
if __name__=='__main__':main()
