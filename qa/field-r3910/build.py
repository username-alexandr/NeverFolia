#!/usr/bin/env python3
"""Opt-in, incremental ocean integration on exact R399. Not full Gradle.
No saved world or existing branch is modified. R399 and R396 classes stay byte-identical.
"""
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3910-build';CAND=ROOT/'candidate'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
LIGHT_SHA='e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283'
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def run(cmd,name):
    r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=240)
    (OUT/name).write_text(r.stdout);print(r.stdout,flush=True);need(r.returncode==0,'Failed '+name);return r.stdout
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist();need(len(names)==len(set(names)) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in names}
def find(pattern,wanted):
    found=[p for p in (ROOT/'baseline').rglob(pattern) if p.is_file() and sha(p)==wanted]
    need(len(found)==1,'Missing/ambiguous baseline '+pattern);return found[0]
def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=False)
    base=find('server.jar',BASE);pack=find('NeverOverworld.zip',PACK);nether=find('NeverNether.zip',NETHER)
    outer_raw=base.read_bytes();outer=members(outer_raw)
    names=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(names)==1,'Bundled server identity');nested=names[0];inner_raw=outer[nested];inner=members(inner_raw)
    libs=WORK/'libs';libs.mkdir()
    for i,(n,b) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(b)
    providers=[]
    for p in libs.glob('*.jar'):
        with zipfile.ZipFile(p) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():providers.append(p)
    debug=list((ROOT/'debug').rglob('diagnostics.zip'));need(len(debug)==1,'Exact diagnostics missing')
    with zipfile.ZipFile(debug[0]) as z:
        exact=[n for n in z.namelist() if n.endswith('/src/minecraft/java/'+LIGHT+'.java')]
        need(len(exact)==1,'LIGHT materialization missing');raw=z.read(exact[0])
        need(hashlib.sha256(raw).hexdigest()==LIGHT_SHA,'Uninspected LIGHT source')
        if not providers:
            api=[]
            for n in z.namelist():
                if 'folia-api' in n and n.endswith('.jar'):
                    payload=z.read(n)
                    with zipfile.ZipFile(io.BytesIO(payload)) as a:
                        if 'org/bukkit/Bukkit.class' in a.namelist():api.append(payload)
            need(len(api)==1,'Exact Bukkit provider');p=libs/'folia-api.jar';p.write_bytes(api[0]);providers.append(p)
    need(len(providers)==1,'Ambiguous API')
    text=raw.decode();anchor='                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);'
    need(text.count(anchor)==1,'LIGHT hook drift')
    # Preserve the historical audit's meaning; new closure has its own evidence.
    text=text.replace(anchor,anchor+'\n                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR3910.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R3910_OCEAN_INTEGRATION',1)
    light=WORK/'src'/Path(LIGHT+'.java');light.parent.mkdir(parents=True);light.write_text(text)
    (OUT/'ChunkLightTask-R3910.java').write_text(text)
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    classes=WORK/'classes';classes.mkdir()
    sources=[ROOT/'native/overworld-r395/OceanConnectivityR395.java',ROOT/'qa/field-r3910/native/NeverOverworldOceanClosureR3910.java',light]
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes)]+[str(p) for p in sources],'core-javac.log')
    replacement={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    allowed=lambda n:n==LIGHT+'.class' or n.startswith(LIGHT+'$') or n in {'net/minecraft/world/level/chunk/OceanConnectivityR395.class','net/minecraft/world/level/chunk/OceanConnectivityR395$Proof.class','net/minecraft/world/level/chunk/NeverOverworldOceanClosureR3910.class'}
    need(all(allowed(n) for n in replacement),'Unexpected compiled class')
    need(all(int.from_bytes(b[6:8],'big')==69 for b in replacement.values()),'Wrong Java version')
    family=lambda names:{n for n in names if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
    need(family(inner)==family(replacement),'LIGHT family changed')
    pkg=load('r3910_packaging',ROOT/'qa/field-r395/jar_packaging.py')
    run([sys.executable,str(ROOT/'qa/field-r395/jar_packaging.py')],'zip-tests.log')
    updated_inner=pkg.rewrite_zip(inner_raw,replacement)
    lines=[];count=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        fields=line.split('\t');need(len(fields)==3,'Bad version row')
        if 'META-INF/versions/'+fields[2]==nested:
            need(fields[0]==hashlib.sha256(inner_raw).hexdigest(),'Bad original version hash')
            fields[0]=hashlib.sha256(updated_inner).hexdigest();count+=1
        lines.append('\t'.join(fields))
    need(count==1,'Version row identity')
    output=pkg.rewrite_zip(outer_raw,{nested:updated_inner,'META-INF/versions.list':('\n'.join(lines)+'\n').encode()})
    result_inner=members(updated_inner);result_outer=members(output)
    need(set(result_inner)==set(inner)|set(replacement),'Unexpected bundled membership')
    need(all(inner[n]==result_inner[n] for n in inner if n not in replacement),'Unrelated class changed')
    need(set(result_outer)==set(outer) and {n for n in outer if outer[n]!=result_outer[n]}=={nested,'META-INF/versions.list'},'Unrelated outer change')
    guards={}
    for leaf in ('NeverOverworldWaterPolicyR38','NeverOverworldDryMinesR12','NeverOverworldDryMinesR12$Mask'):
        name='net/minecraft/world/level/chunk/'+leaf+'.class';need(inner[name]==result_inner[name],'Regression in '+leaf)
        guards[leaf]=hashlib.sha256(inner[name]).hexdigest()
    (CAND/'server.jar').write_bytes(output)
    shutil.copyfile(pack,CAND/'NeverOverworld.zip');shutil.copyfile(nether,CAND/'NeverNether.zip')
    plugin_classes=WORK/'fixture-classes';plugin_classes.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes)+os.pathsep+cp,'-d',str(plugin_classes),str(ROOT/'qa/field-r3910/R3910CavityQa.java')],'fixture-javac.log')
    with zipfile.ZipFile(WORK/'R3910CavityQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in plugin_classes.rglob('*.class'):z.write(p,p.relative_to(plugin_classes).as_posix())
        z.writestr('plugin.yml',"name: R3910CavityQa\nversion: '1'\nmain: R3910CavityQa\napi-version: '26.2'\nfolia-supported: true\n")
    natural=WORK/'natural-classes';natural.mkdir()
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(natural),str(ROOT/'client/neverland-enchantment-ui/src/cc/neverland/client/EnchantmentVisibility.java'),str(ROOT/'qa/field-r395/R395QaPlugin.java')],'natural-javac.log')
    expected={}
    with zipfile.ZipFile(pack) as z:
        for n in z.namelist():
            if n.startswith('data/nova_structures/enchantment/') and n.endswith('.json'):
                d=json.loads(z.read(n))
                if d.get('description',{}).get('translate')=='enchantment.dnt.non_survival_enchant':expected['nova_structures:'+n.split('/enchantment/')[1][:-5]]=False
        legitimate=json.loads(z.read('data/nova_structures/tags/enchantment/all_dnt_enchants.json'))['values']
        need(len(expected)==16 and len(legitimate)==17 and not set(expected)&set(legitimate),'Unexpected enchantment scope')
        expected.update({x:True for x in legitimate});expected.update({'minecraft:sharpness':True,'minecraft:protection':True})
    with zipfile.ZipFile(WORK/'R395Qa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in natural.rglob('*.class'):z.write(p,p.relative_to(natural).as_posix())
        z.writestr('expected-enchants.json',json.dumps(expected));z.writestr('plugin.yml',"name: R395Qa\nversion: '1'\nmain: R395QaPlugin\napi-version: '26.2'\nfolia-supported: true\n")
    (WORK/'classpath.txt').write_text(cp)
    report={'build_pass':True,'kind':'incremental javac --release 25 on exact R399; not full Gradle','base_core_sha256':BASE,'candidate_core_sha256':sha(CAND/'server.jar'),'pack_sha256':PACK,'nether_sha256':NETHER,'preserved_guards':guards,'changed_or_added_classes':{n:hashlib.sha256(b).hexdigest() for n,b in replacement.items()},'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sources},'runtime_tested':False,'production_accepted':False,'default_enabled':False,'radius_chunks':1}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print('R3910_BUILD '+json.dumps(report),flush=True)
if __name__=='__main__':main()
