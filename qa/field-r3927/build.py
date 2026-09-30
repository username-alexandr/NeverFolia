#!/usr/bin/env python3
"""R39.27 incremental build on the exact successful R39.26 test kernel."""
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3927-build';CAND=ROOT/'candidate'
BASE='8145b7cb4a7beeb97c27db6804acadaac8c2e74b8c0d68601f62ee648aee2f2d'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
LIGHT_SOURCE='67dbdd00a9a518b273f67a9d90e3885c3a16a112a793a465c4c2048d3d7fb11c'
KEEP=(
 'net/minecraft/world/level/chunk/NeverOverworldWaterPolicyR38.class',
 'net/minecraft/world/level/chunk/NeverOverworldDryMinesR12.class',
 'net/minecraft/world/level/chunk/NeverOverworldDryMinesR12$Mask.class',
 'net/minecraft/world/level/chunk/NeverOverworldOceanClassifierR3926.class',
 'net/minecraft/world/level/chunk/OceanConnectivityR3926.class',
 'net/minecraft/world/level/chunk/OceanConnectivityR3926$Proof.class',
)

def need(ok,msg):
    if not ok:raise ValueError(msg)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def run(args,name):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'Failed '+name);return p.stdout

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=False)
    base=ROOT/'baseline/server.jar';pack=ROOT/'baseline/world/datapacks/NeverOverworld.zip';nether=ROOT/'baseline/world/datapacks/NeverNether.zip'
    need(sha(base)==BASE,'Wrong R39.26 baseline')
    need(sha(pack)==PACK and sha(nether)==NETHER,'Wrong paired datapacks')

    outer=members(base.read_bytes());nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'Unexpected bundled kernel');nested=nested[0];inner=members(outer[nested])
    need(all(k in inner for k in KEEP),'Inherited R39.26/R39.9 classes missing')
    need(not any('R3927' in n for n in inner),'Baseline already has R3927')

    libs=WORK/'libs';libs.mkdir()
    for i,(name,raw) in enumerate(outer.items()):
        if name.endswith('.jar') and name.startswith(('META-INF/versions/','META-INF/libraries/')):
            (libs/(str(i)+'-'+Path(name).name)).write_bytes(raw)
    api=[]
    for p in libs.glob('*.jar'):
        with zipfile.ZipFile(p) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():api.append(p)
    need(len(api)==1,'Missing/ambiguous Bukkit API in exact R39.26 bundle')
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))));(WORK/'classpath.txt').write_text(cp)

    source=ROOT/'debug/ChunkLightTask-R3926.java'
    need(source.is_file() and sha(source)==LIGHT_SOURCE,'Wrong retained R3926 LIGHT source')
    text=source.read_text()
    old='                net.minecraft.world.level.chunk.NeverOverworldOceanClassifierR3926.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R3926_SEA_PLANE_CLASSIFIER\n'
    new='                net.minecraft.world.level.chunk.NeverOverworldOceanClassifierR3927.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R3927_NATIVE_ORIGIN_CLASSIFIER\n'
    need(text.count(old)==1 and 'R3927_NATIVE_ORIGIN_CLASSIFIER' not in text,'Unexpected R3926 LIGHT call')
    text=text.replace(old,new,1)
    light=WORK/'src'/Path(LIGHT+'.java');light.parent.mkdir(parents=True);light.write_text(text)
    (OUT/'ChunkLightTask-R3927.java').write_text(text)

    # Reconstruct the exact final FIELD-R9 ore helper from the production
    # transformer chain. Before adding R39.27, the rebuilt class family MUST
    # be byte-identical to the exact R39.26 kernel.
    base_geo=load('r3927_geo_base',ROOT/'scripts/apply-never-overworld-ore-geology.py')
    geo=base_geo.helper_source()
    geo=load('r3927_geo_ext',ROOT/'scripts/extend-never-overworld-ore-geology.py').patch_helper(geo)
    geo=load('r3927_geo_v2',ROOT/'scripts/tune-never-overworld-ore-balance.py').patch_helper(geo)
    geo=load('r3927_geo_v3',ROOT/'scripts/tune-never-overworld-ore-balance-v3.py').patch_helper(geo)
    geo=load('r3927_geo_r6',ROOT/'scripts/tune-never-overworld-ore-field-r6.py').patch(geo)
    geo=load('r3927_geo_r7',ROOT/'scripts/tune-never-overworld-ore-field-r7.py').patch(geo)
    geo=load('r3927_geo_r9',ROOT/'scripts/tune-never-overworld-ore-field-r9.py').patch_geology(geo)

    geo_rel=Path('net/minecraft/world/level/chunk/NeverOverworldOreGeology.java')
    baseline_geo_src=WORK/'geo-baseline'/geo_rel
    baseline_geo_src.parent.mkdir(parents=True);baseline_geo_src.write_text(geo)
    baseline_geo_classes=WORK/'geo-baseline-classes';baseline_geo_classes.mkdir()
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(baseline_geo_classes),str(baseline_geo_src)],'geology-baseline-javac.log')
    geo_family={p.relative_to(baseline_geo_classes).as_posix():p.read_bytes() for p in baseline_geo_classes.rglob('NeverOverworldOreGeology*.class')}
    geo_prefix='net/minecraft/world/level/chunk/NeverOverworldOreGeology'
    expected_geo={n:inner[n] for n in inner if n==geo_prefix+'.class' or n.startswith(geo_prefix+chr(36))}
    need(set(geo_family)==set(expected_geo),'Reconstructed geology class family mismatch')
    need(all(geo_family[n]==expected_geo[n] for n in geo_family),'Reconstructed FIELD-R9 geology is not byte-identical to R39.26')

    scope='''        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) {
            return;
        }

'''
    need(geo.count(scope)==1,'Geology scope anchor drifted')
    prime='''        // R39.27: capture native NOISE/aquifer WATER provenance while the
        // owner NoiseChunk still exists at SURFACE, before CARVERS/FEATURES can
        // turn final cells into indistinguishable minecraft:air.
        net.minecraft.world.level.levelgen.NeverOverworldNoiseOracleR3927.prime(chunk, -511, 128);

'''
    geo=geo.replace(scope,scope+prime,1)
    geo_src=WORK/'src'/geo_rel;geo_src.parent.mkdir(parents=True,exist_ok=True);geo_src.write_text(geo)
    (OUT/'NeverOverworldOreGeology-R3927.java').write_text(geo)

    classes=WORK/'classes';classes.mkdir()
    sources=sorted((ROOT/'native/overworld-r3927').glob('*.java'));need(len(sources)==3,'Unexpected R3927 source set')
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(light),str(geo_src)]+list(map(str,sources)),'core-javac.log')

    tests=WORK/'test-classes';tests.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes),'-d',str(tests),str(ROOT/'qa/field-r3927/OceanConnectivityR3927Test.java')],'solver-javac.log')
    run(['java','-cp',str(tests)+os.pathsep+str(classes),'OceanConnectivityR3927Test'],'solver-tests.log')

    replacements={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    need(not set(KEEP)&set(replacements),'Attempted overwrite of inherited hotfix/classifier')
    old_family={n for n in inner if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
    new_family={n for n in replacements if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
    need(old_family==new_family,'LIGHT inner-class family mismatch')
    need(all(int.from_bytes(v[6:8],'big')==69 for v in replacements.values()),'Wrong Java 25 bytecode')

    packaging=load('r3927_pack',ROOT/'qa/field-r395/jar_packaging.py')
    run(['python3',str(ROOT/'qa/field-r395/jar_packaging.py')],'packaging-tests.log')
    modified=packaging.rewrite_zip(outer[nested],replacements)
    rows=[];seen=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        f=line.split('\t');need(len(f)==3,'Bad versions row')
        if 'META-INF/versions/'+f[2]==nested:
            need(f[0]==digest(outer[nested]),'Input bundled digest mismatch');f[0]=digest(modified);seen+=1
        rows.append('\t'.join(f))
    need(seen==1,'No unique bundled versions row')
    bundled=packaging.rewrite_zip(base.read_bytes(),{nested:modified,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()})
    newInner=members(modified);newOuter=members(bundled)
    need(all(newInner[k]==inner[k] for k in KEEP),'Inherited class bytes changed')
    need(all(newInner[n]==inner[n] for n in inner if n not in replacements),'Unrelated bundled entry changed')
    need(set(outer)==set(newOuter) and {n for n in outer if outer[n]!=newOuter[n]}=={nested,'META-INF/versions.list'},'Outer bundle drift')

    (CAND/'server.jar').write_bytes(bundled);shutil.copyfile(pack,CAND/'NeverOverworld.zip');shutil.copyfile(nether,CAND/'NeverNether.zip')

    pluginClasses=WORK/'plugin-classes';pluginClasses.mkdir()
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(pluginClasses),str(ROOT/'qa/field-r3927/R3927NaturalQa.java')],'plugin-javac.log')
    with zipfile.ZipFile(WORK/'R3927NaturalQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in pluginClasses.rglob('*.class'):z.write(p,p.relative_to(pluginClasses).as_posix())
        z.writestr('plugin.yml',"name: R3927NaturalQa\nversion: '1'\nmain: R3927NaturalQa\napi-version: '26.2'\nfolia-supported: true\n")

    report={'build_pass':True,'kind':'Incremental javac --release 25 on exact R39.26',
      'base_core_sha256':BASE,'candidate_core_sha256':sha(CAND/'server.jar'),
      'pack_sha256':PACK,'nether_sha256':NETHER,
      'preserved_classes':{k:digest(newInner[k]) for k in KEEP},
      'changed_or_added_classes':{k:digest(v) for k,v in sorted(replacements.items())},
      'production_accepted':False,'strict_manual_test':True}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print('R3927_BUILD '+json.dumps(report),flush=True)

if __name__=='__main__':main()
