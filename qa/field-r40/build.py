#!/usr/bin/env python3
"""R40: exact R399 plus the opt-in ocean closure. Incremental, not full Gradle.
Never touches user worlds. All inherited fixes and unrelated JAR members are checked.
"""
from pathlib import Path
import hashlib, importlib.util, io, json, os, shutil, subprocess, zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts'; WORK=ROOT/'.work/r40-build'; CAND=ROOT/'candidate'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
LIGHT_SHA='e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283'
KEEP=('net/minecraft/world/level/chunk/NeverOverworldWaterPolicyR38.class',
      'net/minecraft/world/level/chunk/NeverOverworldDryMinesR12.class',
      'net/minecraft/world/level/chunk/NeverOverworldDryMinesR12$Mask.class')
def need(ok,message):
    if not ok: raise ValueError(message)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def find(folder,pattern,expected):
    values=[p for p in folder.rglob(pattern) if p.is_file() and sha(p)==expected]
    need(len(values)==1,'Missing or ambiguous exact input '+str(folder)+' '+pattern);return values[0]
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}
def run(args,name):
    r=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
    (OUT/name).write_text(r.stdout);print(r.stdout,flush=True);need(r.returncode==0,'Failed '+name);return r.stdout

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=False)
    need('25' in run(['javac','-version'],'java-version.log'),'JDK 25 required')
    base=find(ROOT/'baseline','server.jar',BASE)
    pack=find(ROOT/'baseline','NeverOverworld.zip',PACK);nether=find(ROOT/'baseline','NeverNether.zip',NETHER)
    outer=members(base.read_bytes());nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'Unexpected server bundle');nested=nested[0];inner=members(outer[nested])
    need(all(n in inner for n in KEEP),'Inherited R399 hotfix classes missing')
    need(not any('OceanClosureR395' in n or 'OceanConnectivityR395' in n for n in inner),'Baseline already contains closure')
    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(raw)
    api=[]
    for p in libs.glob('*.jar'):
        with zipfile.ZipFile(p) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():api.append(p)
    with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
        names=[n for n in z.namelist() if n.endswith('/src/minecraft/java/'+LIGHT+'.java')]
        need(len(names)==1,'Missing materialized LIGHT source');source=z.read(names[0]);need(digest(source)==LIGHT_SHA,'Unexpected LIGHT source')
        if not api:
            options=[]
            for n in z.namelist():
                if 'folia-api' in n and n.endswith('.jar'):
                    raw=z.read(n)
                    with zipfile.ZipFile(io.BytesIO(raw)) as a:
                        if 'org/bukkit/Bukkit.class' in a.namelist():options.append(raw)
            need(len(options)==1,'Ambiguous pinned API');p=libs/'folia-api.jar';p.write_bytes(options[0]);api.append(p)
    need(len(api)==1,'Ambiguous API classpath')
    anchor='                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);'
    text=source.decode();need(text.count(anchor)==1,'Wrong LIGHT hook')
    text=text.replace(anchor,'                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR395.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R40_ON_R399\n'+anchor,1)
    light=WORK/'src'/Path(LIGHT+'.java');light.parent.mkdir(parents=True);light.write_text(text)
    (OUT/'ChunkLightTask-R40.java').write_text(text)
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))));(WORK/'classpath.txt').write_text(cp)
    classes=WORK/'classes';classes.mkdir()
    sources=sorted((ROOT/'native/overworld-r395').glob('*.java'));need(len(sources)==2,'Unexpected closure source set')
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(light)]+list(map(str,sources)),'core-javac.log')
    replacement={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    need(not set(KEEP)&set(replacement),'Attempted overwrite of inherited fixes')
    old_family={n for n in inner if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
    new_family={n for n in replacement if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
    need(old_family==new_family,'LIGHT inner-class family mismatch')
    need(all(int.from_bytes(v[6:8],'big')==69 for v in replacement.values()),'Wrong bytecode version')
    tests=WORK/'test-classes';tests.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes),'-d',str(tests),str(ROOT/'qa/field-r395/OceanConnectivityTest.java')],'solver-javac.log')
    run(['java','-cp',str(tests)+os.pathsep+str(classes),'OceanConnectivityTest'],'solver-tests.log')
    packaging=load('r40_packaging',ROOT/'qa/field-r395/jar_packaging.py')
    run(['python3',str(ROOT/'qa/field-r395/jar_packaging.py')],'packaging-tests.log')
    modified=packaging.rewrite_zip(outer[nested],replacement)
    rows=[];matched=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        f=line.split('\t');need(len(f)==3,'Invalid versions entry')
        if 'META-INF/versions/'+f[2]==nested:
            need(f[0]==digest(outer[nested]),'Invalid bundled digest');f[0]=digest(modified);matched+=1
        rows.append('\t'.join(f))
    need(matched==1,'Missing unique versions entry')
    bundled=packaging.rewrite_zip(base.read_bytes(),{nested:modified,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()})
    new=members(modified);new_outer=members(bundled)
    need(set(new)==set(inner)|set(replacement),'Unexpected member set')
    need(all(new[n]==inner[n] for n in inner if n not in replacement),'Unrelated bundled entry changed')
    need(all(new[n]==inner[n] for n in KEEP),'Lost R396/R399 fixes')
    need(set(outer)==set(new_outer) and {n for n in outer if outer[n]!=new_outer[n]}=={nested,'META-INF/versions.list'},'Unexpected outer delta')
    (CAND/'server.jar').write_bytes(bundled);shutil.copyfile(pack,CAND/'NeverOverworld.zip');shutil.copyfile(nether,CAND/'NeverNether.zip')
    # The fixture uses actual classes, never replacements for Minecraft APIs.
    plugin_classes=WORK/'fixture-classes';plugin_classes.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes)+os.pathsep+cp,'-d',str(plugin_classes),str(ROOT/'qa/field-r40/R40ClosureQa.java')],'fixture-javac.log')
    with zipfile.ZipFile(WORK/'R40ClosureQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in plugin_classes.rglob('*.class'):z.write(p,p.relative_to(plugin_classes).as_posix())
        z.writestr('plugin.yml',"name: R40ClosureQa\nversion: '1'\nmain: R40ClosureQa\napi-version: '26.2'\nfolia-supported: true\n")
    report={'build_pass':True,'build_kind':'Incremental Java 25 against exact R399, not full Gradle','base_core_sha256':BASE,'candidate_core_sha256':sha(CAND/'server.jar'),'pack_sha256':PACK,'nether_sha256':NETHER,'preserved_hotfix_classes':{n:digest(new[n]) for n in KEEP},'changed_or_added_classes':{n:digest(v) for n,v in replacement.items()},'unchanged_bundled_entries':sum(n not in replacement for n in inner),'closure_enabled_by_default':False,'production_accepted':False}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print('R40_BUILD '+json.dumps(report),flush=True)
if __name__=='__main__':main()
