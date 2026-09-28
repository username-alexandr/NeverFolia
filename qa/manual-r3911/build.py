#!/usr/bin/env python3
"""Build an explicitly experimental manual-test kernel on pinned R39.9.
This is incremental javac, not a full Gradle build or visual acceptance.
"""
from pathlib import Path
import hashlib, importlib.util, io, json, os, shutil, subprocess, sys, zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts'; WORK=ROOT/'.work/manual-r3911'; CAND=ROOT/'candidate'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
PYRAMID='net/minecraft/world/level/chunk/status/ChunkPyramid'
GUARDS=['net/minecraft/world/level/chunk/NeverOverworldWaterPolicyR38.class','net/minecraft/world/level/chunk/NeverOverworldDryMinesR12.class','net/minecraft/world/level/chunk/NeverOverworldDryMinesR12$Mask.class']
def need(ok,msg):
    if not ok: raise ValueError(msg)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def pick(root,name,expected):
    paths=[p for p in root.rglob(name) if p.is_file() and sha(p)==expected]
    need(len(paths)==1,'Missing/ambiguous exact input: '+name); return paths[0]
def once(text,old,new):
    need(text.count(old)==1,'Source anchor mismatch: '+old[:120]); return text.replace(old,new,1)
def run(args,name):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
    (OUT/name).write_text(p.stdout,encoding='utf-8'); print(p.stdout,flush=True)
    need(p.returncode==0,'Failed build step: '+name)
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}
def main():
    OUT.mkdir(exist_ok=True); WORK.mkdir(parents=True,exist_ok=False); CAND.mkdir(exist_ok=False)
    libs=WORK/'libs'; libs.mkdir(); src=WORK/'src'; src.mkdir(); classes=WORK/'classes';classes.mkdir()
    base=pick(ROOT/'baseline','server.jar',BASE); outer=members(base.read_bytes())
    nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'Unexpected bundled core');nested=nested[0];inner=members(outer[nested])
    for i,(n,b) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):
            (libs/(str(i)+'-'+Path(n).name)).write_bytes(b)
    with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
        step_names=[n for n in z.namelist() if n.endswith('/src/minecraft/java/net/minecraft/world/level/chunk/status/ChunkStep.java')]
        need(len(step_names)==1,'Missing exact dependency builder')
        step=z.read(step_names[0]);need(digest(step)=='337d7b40fd6a3301994d6c40545b28160da5427b4eef20ca32d415fbf4ac427c','Dependency builder changed')
        (OUT/'reference-ChunkStep.java').write_bytes(step)
        need(b'getRadiusOfParent(this.parent.targetStatus)' in step,'Unexpected accumulated-dependency algorithm')
        for target,expected in ((LIGHT,'e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283'),(PYRAMID,'24c0e2b6c1cf7f644031126573055a4994f697bc61286e36727b1661da9074f5')):
            names=[n for n in z.namelist() if n.endswith('/src/minecraft/java/'+target+'.java')]
            need(len(names)==1,'Missing materialized source: '+target);b=z.read(names[0]);need(digest(b)==expected,'Unexpected materialized source')
            text=b.decode('utf-8')
            if target==LIGHT:
                anchor='                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);'
                text=once(text,anchor,anchor+'\n                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR399.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R3911_MANUAL_WIDE_OCEAN')
            else:
                anchor='.step(ChunkStatus.LIGHT, s -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, 1).setTask(ChunkStatusTasks::light))'
                # ChunkStep accumulates transitive distances through its parent.
                # FEATURES@3 with only INITIALIZE_LIGHT@1 requests neighbours outside
                # the propagated ticket footprint. Widen the parent as well.
                text=once(text,anchor,'.step(ChunkStatus.LIGHT, s -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, 3).addRequirement(ChunkStatus.FEATURES, 3).setTask(ChunkStatusTasks::light))')
            p=src/(target+'.java');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
        providers=[]
        for p in libs.glob('*.jar'):
            with zipfile.ZipFile(p) as j:
                if 'org/bukkit/Bukkit.class' in j.namelist():providers.append(p)
        if not providers:
            options=[]
            for n in z.namelist():
                if 'folia-api' in n and n.endswith('.jar'):
                    raw=z.read(n)
                    with zipfile.ZipFile(io.BytesIO(raw)) as j:
                        if 'org/bukkit/Bukkit.class' in j.namelist(): options.append(raw)
            need(len(options)==1,'Missing/ambiguous API');p=libs/'folia-api.jar';p.write_bytes(options[0]);providers.append(p)
        need(len(providers)==1,'Ambiguous API providers')
    source_manifest={}
    for p in sorted((ROOT/'native/overworld-r399').glob('*.java')):
        raw=p.read_bytes();text=raw.decode('utf-8');source_manifest[p.name]=digest(raw)
        if p.name=='NeverOverworldOceanClosureR399.java':
            blob=hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
            need(blob=='af99a057ea46ae86d019bd349b3fb9b96c7835ee','Unexpected ocean adapter input')
            # Lava must remain a lava barrier even inside a protected volume.
            text=once(text,'if(protectedCells.get(((y-chunk.getMinY())<<8)|(z<<4)|x))cells[index]=OceanConnectivityR399.PROTECTED;',
                'if(state.is(Blocks.LAVA))cells[index]=OceanConnectivityR399.LAVA;\n                    else if(protectedCells.get(((y-chunk.getMinY())<<8)|(z<<4)|x))cells[index]=OceanConnectivityR399.PROTECTED;')
            text=once(text,'                    else if(state.is(Blocks.LAVA))cells[index]=OceanConnectivityR399.LAVA;\n','')
            text=once(text,'R399-5x5-completed-feature-halo-v1','R3911-manual-5x5-R399-base-lava-priority')
        (src/p.name).write_text(text,encoding='utf-8')
    need(len(source_manifest)==2,'Expected two ocean helper sources')
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes)]+[str(p) for p in sorted(src.rglob('*.java'))],'core-javac.log')
    tests=WORK/'tests';tests.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes),'-d',str(tests),str(ROOT/'qa/field-r399/ConnectivityTest.java')],'solver-javac.log')
    run(['java','-Xmx256M','-cp',str(tests)+os.pathsep+str(classes),'ConnectivityTest'],'solver-tests.log')
    changes={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    need(all(b[:4]==b'\xca\xfe\xba\xbe' and int.from_bytes(b[6:8],'big')==69 for b in changes.values()),'Wrong class target')
    for family in (LIGHT,PYRAMID):
        need({n for n in inner if n==family+'.class' or n.startswith(family+'$')}=={n for n in changes if n==family+'.class' or n.startswith(family+'$')},'Changed nested class family')
    need(not set(GUARDS)&set(changes),'Attempted overwrite of inherited hotfix')
    module_path=ROOT/'qa/field-r395/jar_packaging.py'
    spec=importlib.util.spec_from_file_location('manual_zip',module_path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    run([sys.executable,str(module_path)],'zip-tests.log')
    newinner=mod.rewrite_zip(outer[nested],changes);updated=[];count=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        fields=line.split('\t');need(len(fields)==3,'Invalid versions list')
        if 'META-INF/versions/'+fields[2]==nested:
            need(fields[0]==digest(outer[nested]),'Invalid original bundled hash');fields[0]=digest(newinner);count+=1
        updated.append('\t'.join(fields))
    need(count==1,'Missing bundled manifest row')
    newraw=mod.rewrite_zip(base.read_bytes(),{nested:newinner,'META-INF/versions.list':('\n'.join(updated)+'\n').encode()})
    newmembers=members(newinner)
    need(set(newmembers)==set(inner)|set(changes),'Unexpected archive membership')
    need(all(inner[n]==newmembers[n] for n in inner if n not in changes),'Unrelated entry changed')
    preserved={n:digest(inner[n]) for n in GUARDS}
    need(all(newmembers[n]==inner[n] for n in GUARDS),'Hotfix byte preservation failed')
    (CAND/'server.jar').write_bytes(newraw)
    for name,expected in (('NeverOverworld.zip',PACK),('NeverNether.zip',NETHER)):
        shutil.copyfile(pick(ROOT/'baseline',name,expected),CAND/name)
    report={'version':'R39.11-manual','build_pass':True,'build_environment':'GitHub Actions','kind':'incremental javac --release 25; not full Gradle','base_core_sha256':BASE,'candidate_core_sha256':digest(newraw),'pack_sha256':PACK,'nether_sha256':NETHER,'preserved_hotfix_classes':preserved,'changed_or_added_classes':{n:digest(b) for n,b in sorted(changes.items())},'witness_chunks':25,'feature_dependency_radius':3,'initialize_light_dependency_radius':3,'ocean_flag':'neverfolia.r399OceanClosure','production_accepted':False,'visual_tested':False,'ice_fix_included':False,'enchantment_ui_fix_included':False,'source_inputs':source_manifest}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');(WORK/'classpath.txt').write_text(cp)
    shutil.copytree(src,OUT/'compiled-source')
    print('R3911_BUILD '+json.dumps(report),flush=True)
if __name__=='__main__':main()
