#!/usr/bin/env python3
"""Incremental R40 integration on exact R399; no full Gradle or client mod build."""
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r395-build';CAND=ROOT/'candidate'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
LIGHT_SOURCE='e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283'
KEEP=['net/minecraft/world/level/chunk/'+name+'.class' for name in ('NeverOverworldWaterPolicyR38','NeverOverworldDryMinesR12','NeverOverworldDryMinesR12$Mask')]

def need(ok,message):
    if not ok:raise ValueError(message)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def run(command,name):
    r=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (OUT/name).write_text(r.stdout);print(r.stdout,flush=True);need(r.returncode==0,'Failed: '+name)
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=False)
    base=ROOT/'baseline/server.jar';need(sha(base)==BASE,'Not the verified R399 core')
    for n,h in [('NeverOverworld.zip',PACK),('NeverNether.zip',NETHER)]:
        p=ROOT/'baseline/world/datapacks'/n;need(sha(p)==h,'Unexpected paired pack '+n);shutil.copyfile(p,CAND/n)
    raw=base.read_bytes();outer=members(raw)
    nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'Ambiguous embedded kernel');nested=nested[0];inner=members(outer[nested])
    need(all(n in inner for n in KEEP),'Required hotfix classes missing')
    libs=WORK/'libs';libs.mkdir()
    for i,(n,data) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(data)
    api=[]
    for p in libs.glob('*.jar'):
        with zipfile.ZipFile(p) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():api.append(p)
    with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
        paths=[n for n in z.namelist() if n.endswith('/src/minecraft/java/'+LIGHT+'.java')]
        need(len(paths)==1,'Materialized LIGHT source missing');source=z.read(paths[0]);need(digest(source)==LIGHT_SOURCE,'Uninspected LIGHT input')
        if not api:
            candidates=[]
            for n in z.namelist():
                if 'folia-api' in n and n.endswith('.jar'):
                    data=z.read(n)
                    with zipfile.ZipFile(io.BytesIO(data)) as a:
                        if 'org/bukkit/Bukkit.class' in a.namelist():candidates.append(data)
            need(len(candidates)==1,'Missing exact API');p=libs/'folia-api.jar';p.write_bytes(candidates[0]);api.append(p)
    need(len(api)==1,'Ambiguous API')
    anchor='                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);'
    text=source.decode();need(text.count(anchor)==1,'Unexpected LIGHT hook')
    text=text.replace(anchor,'                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR40.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R40_COMBINED_OCEAN\n'+anchor,1)
    light=WORK/'src'/Path(LIGHT+'.java');light.parent.mkdir(parents=True);light.write_text(text);(OUT/'ChunkLightTask-R40.java').write_text(text)
    classes=WORK/'classes';classes.mkdir();tests=WORK/'tests';tests.mkdir()
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))))
    sources=[ROOT/'native/overworld-r395/OceanConnectivityR395.java',ROOT/'native/overworld-r40/NeverOverworldOceanClosureR40.java',light]
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes)]+list(map(str,sources)),'core-javac.log')
    run(['javac','--release','25','-cp',str(classes),'-d',str(tests),str(ROOT/'qa/field-r395/OceanConnectivityTest.java')],'solver-javac.log')
    run(['java','-cp',str(tests)+os.pathsep+str(classes),'OceanConnectivityTest'],'solver-tests.log')
    replacements={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    light_family={n for n in inner if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
    expected=light_family|{'net/minecraft/world/level/chunk/'+n+'.class' for n in ('NeverOverworldOceanClosureR40','OceanConnectivityR395','OceanConnectivityR395$Proof')}
    need(set(replacements)==expected,'Unexpected compiled class family')
    need(not set(KEEP)&set(replacements),'Attempt to recompile shipped hotfix')
    need(all(int.from_bytes(v[6:8],'big')==69 for v in replacements.values()),'Wrong Java class target')
    packager=ROOT/'qa/field-r395/jar_packaging.py';run(['python3',str(packager)],'packaging-tests.log');zp=load(packager,'r40_zip')
    new_inner=zp.rewrite_zip(outer[nested],replacements);rows=[];found=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        parts=line.split('\t');need(len(parts)==3,'Invalid versions list')
        if 'META-INF/versions/'+parts[2]==nested:
            need(parts[0]==digest(outer[nested]),'Invalid input bundled hash');parts[0]=digest(new_inner);found+=1
        rows.append('\t'.join(parts))
    need(found==1,'No exact bundled version row')
    new=zp.rewrite_zip(raw,{nested:new_inner,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()})
    ni=members(new_inner);no=members(new)
    need(set(ni)==set(inner)|set(replacements),'Unexpected kernel membership change')
    need(all(inner[n]==ni[n] for n in inner if n not in replacements),'Unrelated class changed')
    need(all(inner[n]==ni[n] for n in KEEP),'Prior fixes lost')
    need(set(outer)==set(no) and {n for n in outer if outer[n]!=no[n]}=={nested,'META-INF/versions.list'},'Unexpected outer delta')
    (CAND/'server.jar').write_bytes(new)
    fixture=WORK/'fixture-classes';fixture.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes)+os.pathsep+cp,'-d',str(fixture),str(ROOT/'qa/field-r40/R40Fixture.java')],'fixture-javac.log')
    with zipfile.ZipFile(WORK/'R40Fixture.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in fixture.rglob('*.class'):z.write(p,p.relative_to(fixture).as_posix())
        z.writestr('plugin.yml',"name: R40Fixture\nversion: '1'\nmain: R40Fixture\napi-version: '26.2'\nfolia-supported: true\n")
    report={'build_pass':True,'build_kind':'Incremental Java 25 on exact R399; NOT full Gradle',
        'base_core_sha256':BASE,'candidate_core_sha256':sha(CAND/'server.jar'),'pack_sha256':PACK,'nether_sha256':NETHER,
        'preserved_fix_classes':{n:digest(ni[n]) for n in KEEP},'changed_or_added_classes':{n:digest(v) for n,v in replacements.items()},
        'preserved_bundled_entries':sum(n not in replacements for n in inner),'production_accepted':False,'global_closure_proven':False,
        'ocean_enabled_by_default':False,'client_mod_included':False}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print('R40_BUILD '+json.dumps(report),flush=True)
if __name__=='__main__':main()
