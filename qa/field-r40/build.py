#!/usr/bin/env python3
"""Build old 3x3 and new 5x5 ocean candidates from the SAME R399 binaries.
Incremental Java 25 build; not a full Gradle build. No saved-world changes.
"""
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r40-build'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
PYRAMID='net/minecraft/world/level/chunk/status/ChunkPyramid'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(ok,msg):
    if not ok:raise ValueError(msg)
def replace(text,old,new,count=1):
    require(text.count(old)==count,'Unexpected source anchor: '+old[:120]);return text.replace(old,new)
def run(cmd,name):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=240)
    (OUT/name).write_text(p.stdout);print(name,p.stdout,flush=True);require(p.returncode==0,'Failed '+name)
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        require(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}
def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False)
    base=(ROOT/'baseline/server.jar').read_bytes();require(sha(base)==BASE,'Wrong R399')
    paired={n:(ROOT/'baseline/world/datapacks'/n).read_bytes() for n in ('NeverOverworld.zip','NeverNether.zip')}
    require(sha(paired['NeverOverworld.zip'])==PACK and sha(paired['NeverNether.zip'])==NETHER,'Wrong pack')
    outer=members(base);names=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')];require(len(names)==1,'Wrong server family')
    nested=names[0];innerraw=outer[nested];inner=members(innerraw)
    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/f'{i}-{Path(n).name}').write_bytes(raw)
    with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
        source={}
        for full in (LIGHT,PYRAMID):
            names=[n for n in z.namelist() if n.endswith('/src/minecraft/java/'+full+'.java')];require(len(names)==1,'Missing exact source '+full)
            source[full]=z.read(names[0]).decode()
        require(sha(source[LIGHT].encode())=='e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283','LIGHT drift')
        require(sha(source[PYRAMID].encode())=='24c0e2b6c1cf7f644031126573055a4994f697bc61286e36727b1661da9074f5','Pyramid drift')
        providers=[p for p in libs.glob('*.jar') if 'org/bukkit/Bukkit.class' in zipfile.ZipFile(p).namelist()]
        if not providers:
            found=[]
            for n in z.namelist():
                if 'folia-api' in n and n.endswith('.jar'):
                    raw=z.read(n)
                    if 'org/bukkit/Bukkit.class' in zipfile.ZipFile(io.BytesIO(raw)).namelist():found.append(raw)
            require(len(found)==1,'Missing actual API');(libs/'folia-api.jar').write_bytes(found[0])
        for leaf in ('NewChunkHolder.java','ChunkTaskScheduler.java'):
            for n in z.namelist():
                if n.endswith('/'+leaf) and '/src/minecraft/java/' in n:
                    text=z.read(n).decode();(OUT/leaf).write_text(text);lines=text.splitlines()
                    for i,l in enumerate(lines):
                        if 'new ChunkLightTask' in l or 'neverOverworldNeighbours' in l:print('CACHE_CONTRACT',leaf,'\n'.join(lines[max(0,i-8):i+9]),flush=True)
    spec=importlib.util.spec_from_file_location('packaging40',ROOT/'qa/field-r395/jar_packaging.py');pkg=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkg)
    run(['python3',str(ROOT/'qa/field-r395/jar_packaging.py')],'zip-tests.log')
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')));(WORK/'classpath.txt').write_text(cp)
    original={p.name:p.read_text() for p in (ROOT/'native/overworld-r395').glob('*.java')}
    require(set(original)=={'OceanConnectivityR395.java','NeverOverworldOceanClosureR395.java'},'Unexpected ocean sources')
    report={'production_accepted':False,'base':BASE,'pack':PACK,'nether':NETHER,'kind':'Incremental javac25, not full Gradle','variants':{}}
    for variant in ('reference3910','wide40'):
        folder=WORK/variant;src=folder/'src';classes=folder/'classes';src.mkdir(parents=True);classes.mkdir()
        code=dict(original);light=source[LIGHT]
        anchor='                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);'
        name='NeverOverworldOceanClosureR395' if variant=='reference3910' else 'NeverOverworldOceanClosureR40'
        light=replace(light,anchor,f'                net.minecraft.world.level.chunk.{name}.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R395_FINAL_AIR_CLOSURE\n'+anchor)
        if variant=='wide40':
            solver=code.pop('OceanConnectivityR395.java').replace('R395','R40');solver=replace(solver,'count>2_000_000','count>5_000_000')
            adapter=code.pop('NeverOverworldOceanClosureR395.java').replace('R395','R40').replace('r395','r40')
            for old,new,count in [('positive-ocean-proof-v1','positive-ocean-proof-5x5-v1',1),('WIDTH=48','WIDTH=80',1),('new ChunkAccess[9];chunks[4]=owner','new ChunkAccess[25];chunks[12]=owner',1),('for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++)','for(int dz=-2;dz<=2;dz++)for(int dx=-2;dx<=2;dx++)',1),('(dz+1)*3+dx+1','(dz+2)*5+dx+2',2),('tile<9','tile<25',1),('(tile%3)*16,oz=(tile/3)*16','(tile%5)*16,oz=(tile/5)*16',1),('tile==4','tile==12',1),('(z+16)*WIDTH+x+16','(z+32)*WIDTH+x+32',1),('positive 3D proof','positive 3D proof over 5x5 chunks',1)]:adapter=replace(adapter,old,new,count)
            code={'OceanConnectivityR40.java':solver,'NeverOverworldOceanClosureR40.java':adapter}
            pyramid=replace(source[PYRAMID],'s -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, 1).setTask(ChunkStatusTasks::light)', 's -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, 1).addRequirement(ChunkStatus.FEATURES, Boolean.getBoolean("neverfolia.r40OceanClosure") ? 3 : 0).setTask(ChunkStatusTasks::light)')
            # Radius 3 FEATURES finishes every possible feature writer into the read radius 2.
            # No global lock, neighbour writes or runtime loads are introduced.
            code['ChunkPyramid.java']=pyramid
        code['ChunkLightTask.java']=light
        for leaf,text in code.items():(src/leaf).write_text(text)
        run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes)]+[str(p) for p in sorted(src.glob('*.java'))],variant+'-javac.log')
        test=(ROOT/'qa/field-r395/OceanConnectivityTest.java').read_text()
        if variant=='wide40':test=test.replace('R395','R40')
        (src/'OceanConnectivityTest.java').write_text(test)
        run(['javac','--release','25','-classpath',str(classes),'-d',str(classes),str(src/'OceanConnectivityTest.java')],variant+'-solver-javac.log')
        run(['java','-cp',str(classes),'OceanConnectivityTest'],variant+'-solver.log')
        replacements={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class') if not p.name.startswith('OceanConnectivityTest')}
        oldlight={n for n in inner if n==LIGHT+'.class' or n.startswith(LIGHT+'$')};newlight={n for n in replacements if n==LIGHT+'.class' or n.startswith(LIGHT+'$')};require(oldlight==newlight,'LIGHT family drift')
        protected=['net/minecraft/world/level/chunk/'+s+'.class' for s in ('NeverOverworldWaterPolicyR38','NeverOverworldDryMinesR12','NeverOverworldDryMinesR12$Mask')]
        require(not set(protected)&set(replacements),'Prior hotfix overwritten')
        patched=pkg.rewrite_zip(innerraw,replacements);updated=[];changed=0
        for l in outer['META-INF/versions.list'].decode().splitlines():
            f=l.split('\t');require(len(f)==3,'Bad manifest')
            if 'META-INF/versions/'+f[2]==nested:require(f[0]==sha(innerraw),'Bad base digest');f[0]=sha(patched);changed+=1
            updated.append('\t'.join(f))
        require(changed==1,'Ambiguous nested entry')
        result=pkg.rewrite_zip(base,{nested:patched,'META-INF/versions.list':('\n'.join(updated)+'\n').encode()})
        verify=members(patched)
        require(all(verify[n]==raw for n,raw in inner.items() if n not in replacements),'Unrelated byte changed')
        dest=ROOT/variant;dest.mkdir(exist_ok=False);(dest/'server.jar').write_bytes(result)
        for n,raw in paired.items():(dest/n).write_bytes(raw)
        report['variants'][variant]={'jar_sha256':sha(result),'modified_existing':[n for n in replacements if n in inner and inner[n]!=replacements[n]],'added':[n for n in replacements if n not in inner],'previous_fixes':{n:sha(verify[n]) for n in protected}}
        shutil.copytree(src,OUT/(variant+'-source'))
    (OUT/'build40.json').write_text(json.dumps(report,indent=2));print('R40_BUILD',json.dumps(report),flush=True)
if __name__=='__main__':main()
