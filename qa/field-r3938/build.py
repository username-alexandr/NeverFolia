#!/usr/bin/env python3
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3938-build';CAND=ROOT/'candidate';BASE=ROOT/'baseline-r3937'

BASE_CORE='c717e3e444fbec7c5d0f3c0d08d24e2c0a221c1ac37d59551edbb3c500bb2ff0'
BASE_OVERWORLD='d4771781192ce17b73e3bc46443c4d66adceb6c3c78d3dd8008708db5a1f71ef'
BASE_NETHER='f7d71702f2b0261762a70b019a5cae6862228d040dd89544d755853fb773b7ce'

OW_FAST='net/minecraft/world/level/chunk/NeverOverworldFastLocate.class'
NN_POLICY='net/minecraft/world/level/chunk/NeverNetherFastLocatePolicy.class'
NN_PLACE='net/minecraft/world/level/levelgen/structure/structures/NeverNetherStructurePlacement.class'
NN_MODE='net/minecraft/world/level/levelgen/structure/structures/NeverNetherStructurePlacement$Mode.class'
NN_PROFILE='net/minecraft/world/level/levelgen/structure/structures/NeverNetherStructurePlacement$Profile.class'
CHANGED={OW_FAST,NN_POLICY}

def need(v,m):
    if not v: raise ValueError(m)

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(z.testzip() is None,'invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run(args,name,timeout=300):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'failed '+name)

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=True)
    server=BASE/'server.jar';over=BASE/'world/datapacks/NeverOverworld.zip';nether=BASE/'world/datapacks/NeverNether.zip'
    need(server.is_file() and over.is_file() and nether.is_file(),'R39.37 baseline incomplete')
    need(sha(server)==BASE_CORE,'wrong R39.37 server')
    need(sha(over)==BASE_OVERWORLD,'wrong R39.37 NeverOverworld')
    need(sha(nether)==BASE_NETHER,'wrong R39.37 NeverNether')

    outer=members(server.read_bytes())
    nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'unexpected bundled kernel');nested=nested[0]
    inner=members(outer[nested])
    for name in (OW_FAST,NN_PLACE,NN_MODE,NN_PROFILE):
        need(name in inner,'baseline kernel missing '+name)
    need(NN_POLICY not in inner,'NeverNetherFastLocatePolicy already present unexpectedly')

    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):
            (libs/(str(i)+'-'+Path(n).name)).write_bytes(raw)
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))))
    (WORK/'classpath.txt').write_text(cp)

    classes=WORK/'classes';classes.mkdir()
    run([
      'javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),
      str(ROOT/'native/nevernether-r3938/NeverNetherFastLocatePolicy.java'),
      str(ROOT/'qa/field-r3938/R3938PatchOverworldFastLocate.java')
    ],'javac.log',timeout=300)

    old_fast=WORK/'NeverOverworldFastLocate.class';old_fast.write_bytes(inner[OW_FAST])
    new_fast=WORK/'patched/NeverOverworldFastLocate.class'
    run([
      'java','-cp',str(classes)+os.pathsep+cp,
      'R3938PatchOverworldFastLocate',str(old_fast),str(new_fast)
    ],'asm-patch.log')

    replacements={
      OW_FAST:new_fast.read_bytes(),
      NN_POLICY:(classes/NN_POLICY).read_bytes(),
    }
    need(all(int.from_bytes(v[6:8],'big')==69 for v in replacements.values()),'wrong bytecode version')

    inspect=WORK/'inspect';inspect.mkdir()
    for name,raw in replacements.items():
        p=inspect/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    run([
      'javap','-classpath',str(inspect)+os.pathsep+cp,'-p','-c',
      'net.minecraft.world.level.chunk.NeverOverworldFastLocate',
      'net.minecraft.world.level.chunk.NeverNetherFastLocatePolicy'
    ],'javap.log')
    jp=(OUT/'javap.log').read_text()
    need('NeverNetherFastLocatePolicy.handles' in jp,'fast locate handles router missing')
    need('NeverNetherFastLocatePolicy.isCustomNether' in jp,'Nether terrain branch missing')
    need('NeverNetherFastLocatePolicy.passesNetherTerrain' in jp,'Nether terrain policy missing')
    need('findValidGenerationPoint' in jp,'exact candidate confirmation missing')

    packaging=load('r3938_packaging',ROOT/'qa/field-r395/jar_packaging.py')
    modified=packaging.rewrite_zip(outer[nested],replacements)
    new=members(modified)
    delta={n for n in set(inner)|set(new) if inner.get(n)!=new.get(n)}
    need(delta==CHANGED,'unexpected kernel delta: '+repr(sorted(delta)))

    # R39.37 generation semantics must remain byte-identical. R39.38 changes
    # locate only; actual Jigsaw generation continues through the accepted
    # NeverNetherStructurePlacement implementation.
    for name in (NN_PLACE,NN_MODE,NN_PROFILE):
        need(new[name]==inner[name],'normal Nether generation resolver changed: '+name)

    inherited=(
      'net/minecraft/world/level/levelgen/structure/structures/OceanMonumentStructure.class',
      'net/minecraft/world/level/levelgen/structure/structures/NeverOverworldOceanMonumentR34.class',
      'net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.class',
      'net/minecraft/server/NeverNetherFingerprintGuard.class',
      'net/minecraft/world/level/levelgen/placement/NeverNetherHeightR14.class',
    )
    for name in inherited:
        need(name in inner and new[name]==inner[name],'inherited class changed: '+name)

    rows=[];seen=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        f=line.split('\t');need(len(f)==3,'bad versions row')
        if 'META-INF/versions/'+f[2]==nested:
            need(f[0]==digest(outer[nested]),'bundled digest mismatch')
            f[0]=digest(modified);seen+=1
        rows.append('\t'.join(f))
    need(seen==1,'missing bundled versions row')

    bundled=packaging.rewrite_zip(
      server.read_bytes(),
      {nested:modified,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()}
    )
    (CAND/'server.jar').write_bytes(bundled)
    shutil.copyfile(over,CAND/'NeverOverworld.zip')
    shutil.copyfile(nether,CAND/'NeverNether.zip')

    report={
      'build_pass':True,
      'base_core_sha256':BASE_CORE,
      'candidate_core_sha256':sha(CAND/'server.jar'),
      'overworld_sha256':BASE_OVERWORLD,
      'nether_sha256':BASE_NETHER,
      'changed_kernel_entries':sorted(CHANGED),
      'normal_generation_resolver_preserved':True,
      'existing_fast_locate_engine_reused':True,
      'nether_sparse_density_prefilter':True,
      'nether_exact_generation_confirmation':True,
      'full_jigsaw_check_only_after_prefilter':True,
      'production_accepted':False
    }
    (OUT/'build-r3938.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R3938_BUILD '+json.dumps(report),flush=True)

if __name__=='__main__':main()
