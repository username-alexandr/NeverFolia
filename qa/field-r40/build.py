#!/usr/bin/env python3
"""Pinned incremental R40 build. Does not change old worlds or source artifacts."""
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r40-build';CAND=ROOT/'candidate'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be';NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
JAVA='materialized/folia-server/src/minecraft/java/'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
TASKS='net/minecraft/world/level/chunk/status/ChunkStatusTasks'
PYRAMID='net/minecraft/world/level/chunk/status/ChunkPyramid'
KEEP=['net/minecraft/world/level/chunk/'+n+'.class' for n in ('NeverOverworldWaterPolicyR38','NeverOverworldDryMinesR12','NeverOverworldDryMinesR12$Mask')]

def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def run(args,log):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (OUT/log).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'Failed '+log)
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(set(z.namelist()))==len(z.namelist()) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}
def replace(text,before,after):
    need(text.count(before)==1,'Ambiguous source anchor: '+before[:140]);return text.replace(before,after,1)
def method(text,signature):
    need(text.count(signature)==1,'Missing method '+signature);a=text.index(signature);o=text.index('{',a);depth=1
    for i in range(o+1,len(text)):
        if text[i]=='{':depth+=1
        elif text[i]=='}':
            depth-=1
            if depth==0:return a,i+1
    raise ValueError('Unclosed Java method')

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=False)
    base=(ROOT/'baseline/server.jar').read_bytes();need(sha(base)==BASE,'Wrong R399 input')
    for name,digest in (('NeverOverworld.zip',PACK),('NeverNether.zip',NETHER)):
        path=ROOT/'baseline/world/datapacks'/name;need(sha(path.read_bytes())==digest,'Wrong paired pack');shutil.copyfile(path,CAND/name)
    outer=members(base);nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')];need(len(nested)==1,'Wrong bundled engine');nested=nested[0];inner_raw=outer[nested];inner=members(inner_raw)
    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(raw)
    sources={};source_hashes={}
    with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
        api=[]
        for n in z.namelist():
            if 'folia-api' in n and n.endswith('.jar'):
                raw=z.read(n)
                with zipfile.ZipFile(io.BytesIO(raw)) as j:
                    if 'org/bukkit/Bukkit.class' in j.namelist():api.append(raw)
        providers=[p for p in libs.glob('*.jar') if 'org/bukkit/Bukkit.class' in members(p.read_bytes())]
        if not providers:need(len(api)==1,'Missing API');(libs/'folia-api.jar').write_bytes(api[0])
        for name in (LIGHT,TASKS,PYRAMID):
            raw=z.read(JAVA+name+'.java');sources[name]=raw.decode();source_hashes[name]=sha(raw)
        for leaf in ('ChunkAccess.java','ProtoChunk.java','SurfaceSystem.java','IcebergFeature.java','BlueIceFeature.java','SnowAndFreezeFeature.java','NeverOverworldFlood.java','NeverOverworldFloodConnectivityR15.java'):
            names=[n for n in z.namelist() if n.startswith(JAVA) and n.endswith('/'+leaf)];need(len(names)==1,'Source not unique '+leaf)
            out=OUT/'inspection'/leaf;out.parent.mkdir(exist_ok=True);out.write_bytes(z.read(names[0]))
    need(source_hashes[LIGHT]=='e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283','LIGHT source drift')
    text=sources[LIGHT];begin='                final var waterAuditR38 =';end='                // NEVERFOLIA: NeverNether R15 post-FEATURES cleanup'
    need(text.count(begin)==text.count(end)==1,'LIGHT pipeline ambiguity');a=text.index(begin);b=text.index(end,a);old=text[a:b]
    sources[LIGHT]=text[:a]+'                if (net.minecraft.world.level.chunk.NeverOverworldOceanR40.scope(task.world, task.fromChunk)) {\n                    net.minecraft.world.level.chunk.NeverOverworldOceanR40.close(task.world, task.neverOverworldNeighbours, task.fromChunk);\n                } else {\n'+old+'                }\n'+text[b:]
    text=sources[TASKS];a,b=method(text,'public static CompletableFuture<ChunkAccess> initializeLight(');section=text[a:b];brace=section.index('{')
    section=section[:brace+1]+'\n        net.minecraft.world.level.chunk.NeverOverworldOceanR40.prepare(context.level(), chunk);'+section[brace+1:];sources[TASKS]=text[:a]+section+text[b:]
    text=sources[PYRAMID];marker='    public static final ChunkPyramid LOADING_PYRAMID'
    need(text.count(marker)==1,'Generation/loading boundary missing');generation,loading=text.split(marker,1)
    generation=replace(generation,'.step(ChunkStatus.INITIALIZE_LIGHT, s -> s.setTask(ChunkStatusTasks::initializeLight))', '.step(ChunkStatus.INITIALIZE_LIGHT, s -> {\n            if (net.minecraft.world.level.chunk.NeverOverworldOceanR40.ENABLED) s.addRequirement(ChunkStatus.FEATURES, 1).blockStateWriteRadius(0);\n            return s.setTask(ChunkStatusTasks::initializeLight);\n        })')
    generation=replace(generation,'.step(ChunkStatus.LIGHT, s -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, 1).setTask(ChunkStatusTasks::light))','.step(ChunkStatus.LIGHT, s -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, net.minecraft.world.level.chunk.NeverOverworldOceanR40.ENABLED ? net.minecraft.world.level.chunk.NeverOverworldOceanR40.RADIUS : 1).setTask(ChunkStatusTasks::light))')
    sources[PYRAMID]=generation+marker+loading
    source_dir=WORK/'src';classes=WORK/'classes';classes.mkdir();paths=[]
    for name,text in sources.items():
        path=source_dir/(name+'.java');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);paths.append(str(path))
    paths += [str(p) for p in (ROOT/'native/overworld-r40').glob('*.java')]
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')));(WORK/'classpath.txt').write_text(cp)
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes)]+paths,'core-javac.log')
    testclasses=WORK/'test-classes';testclasses.mkdir()
    tests=sorted((ROOT/'qa/field-r40').glob('*Test.java'))
    run(['javac','--release','25','-cp',str(classes),'-d',str(testclasses)]+[str(p) for p in tests],'tests-javac.log')
    for test in tests:run(['java','-cp',str(testclasses)+os.pathsep+str(classes),test.stem],test.stem+'.log')
    replacements={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    need(not set(KEEP)&set(replacements),'A previously accepted hotfix would be replaced')
    spec=importlib.util.spec_from_file_location('packaging40',ROOT/'qa/field-r395/jar_packaging.py');packaging=importlib.util.module_from_spec(spec);spec.loader.exec_module(packaging)
    newinner=packaging.rewrite_zip(inner_raw,replacements);lines=[];found=0
    for row in outer['META-INF/versions.list'].decode().splitlines():
        parts=row.split('\t');need(len(parts)==3,'Versions manifest malformed')
        if 'META-INF/versions/'+parts[2]==nested:need(parts[0]==sha(inner_raw),'Invalid input manifest');parts[0]=sha(newinner);found+=1
        lines.append('\t'.join(parts))
    need(found==1,'No bundled manifest entry')
    newouter=packaging.rewrite_zip(base,{nested:newinner,'META-INF/versions.list':('\n'.join(lines)+'\n').encode()});(CAND/'server.jar').write_bytes(newouter)
    after=members(newinner);untouched=[n for n in inner if n not in replacements];need(all(inner[n]==after[n] for n in untouched),'Unrelated entries changed')
    for n in KEEP:need(inner[n]==after[n],'Lost prior fix '+n)
    report={'build_pass':True,'kind':'incremental javac25 from pinned R399; NOT full Gradle','base_core_sha256':BASE,'candidate_core_sha256':sha(newouter),'pack_sha256':PACK,'nether_sha256':NETHER,'source_inputs':source_hashes,'changed_or_added':{n:sha(raw) for n,raw in replacements.items()},'preserved_hotfixes':{n:sha(after[n]) for n in KEEP},'preserved_entries':len(untouched),'runtime_tested':False,'production_accepted':False}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print('R40_BUILD '+json.dumps(report),flush=True)
    with zipfile.ZipFile(OUT/'source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in source_dir.rglob('*.java'):z.write(p,p.relative_to(source_dir).as_posix())
        for p in (ROOT/'native/overworld-r40').glob('*.java'):z.write(p,'net/minecraft/world/level/chunk/'+p.name)
if __name__=='__main__':main()
