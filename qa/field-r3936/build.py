#!/usr/bin/env python3
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts'
WORK=ROOT/'.work/r3936-build'
CAND=ROOT/'candidate'
BASE=ROOT/'baseline-r3935'

BASE_CORE='d84650ac22746d51f6b530af4407a851695da577cb18a6baf9500064f11d609f'
BASE_PACK='d4771781192ce17b73e3bc46443c4d66adceb6c3c78d3dd8008708db5a1f71ef'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'

MAIN='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.class'
MODE='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement$Mode.class'
PROFILE='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement$Profile.class'
CHANGED=(MAIN,MODE,PROFILE)

def need(v,m):
    if not v:raise ValueError(m)

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run(args,name,timeout=300):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout)
    print(p.stdout,flush=True)
    need(p.returncode==0,'failed '+name)

def main():
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(parents=True,exist_ok=False)
    CAND.mkdir(exist_ok=True)

    server=BASE/'server.jar'
    pack=BASE/'world/datapacks/NeverOverworld.zip'
    nether=BASE/'world/datapacks/NeverNether.zip'
    need(server.is_file() and pack.is_file() and nether.is_file(),'R39.35 baseline incomplete')
    need(sha(server)==BASE_CORE,'wrong R39.35 server')
    need(sha(pack)==BASE_PACK,'wrong R39.35 NeverOverworld')
    need(sha(nether)==NETHER,'wrong NeverNether')

    spec=json.loads((ROOT/'worldgen-spec/never-overworld-structures.json').read_text())
    allh=spec['global_rules']['underground_all_heights']
    need(allh.get('enabled') is True,'all-height underground policy disabled')
    need(allh.get('minimum_start_y')==-480 and allh.get('maximum_start_y')==480,
         'unexpected global underground Y span')
    need(allh.get('surface_heightmap')=='OCEAN_FLOOR_WG','wrong dynamic surface heightmap')

    profiles=spec['vertical_profiles']
    for name,p in profiles.items():
        need(p.get('vertical_policy')=='all_underground_heights',name+' is still banded')
        need(p.get('preferred_y')==[-480,480],name+' preferred_y drifted')
        need(p.get('hard_y')==[-480,480],name+' hard_y drifted')
        need(int(p.get('minimum_surface_cover',0))>=12,name+' surface cover too small')
    need(profiles['flooded_surface_or_cavern'].get('allows_surface_connected_flood') is False,
         'flooded_ruins still allows open-surface flood placement')

    placement=load('r3936_placement',ROOT/'scripts/apply-never-overworld-placement-hook.py')
    run(['python3',str(ROOT/'scripts/apply-never-overworld-placement-hook.py'),'--self-test'],
        'placement-selftest.log')
    source=placement.helper_source(spec)

    for marker in (
      'UNDERGROUND_MIN_Y = -480',
      'UNDERGROUND_MAX_Y = 480',
      'Heightmap.Types.OCEAN_FLOOR_WG',
      'terrainFloorY - profile.surfaceCover',
      'R39.36 removes per-structure vertical bands'
    ):
        need(marker in source,'generated helper missing '+marker)
    for obsolete in ('-384','-320','-300','-220','preferredMinY','hardMinY'):
        need(obsolete not in source,'obsolete vertical band survived: '+obsolete)

    outer=members(server.read_bytes())
    nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'unexpected bundled kernel')
    nested=nested[0]
    inner=members(outer[nested])
    need(all(k in inner for k in CHANGED),'R39.35 placement helper classes missing')

    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):
            (libs/(str(i)+'-'+Path(n).name)).write_bytes(raw)
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))))
    (WORK/'classpath.txt').write_text(cp)

    src=WORK/'generated/net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.java'
    src.parent.mkdir(parents=True)
    src.write_text(source)
    classes=WORK/'classes';classes.mkdir()

    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(src)],
        'placement-javac.log')

    replacements={k:(classes/k).read_bytes() for k in CHANGED}
    need(all(int.from_bytes(v[6:8],'big')==69 for v in replacements.values()),
         'wrong Java bytecode')

    run([
      'javap','-classpath',str(classes)+os.pathsep+cp,'-p','-c',
      'net.minecraft.world.level.levelgen.structure.structures.NeverOverworldStructurePlacement'
    ],'placement-javap.log')
    javap=(OUT/'placement-javap.log').read_text()
    for marker in ('OCEAN_FLOOR_WG','getBaseHeight','UNDERGROUND_MIN_Y','UNDERGROUND_MAX_Y'):
        need(marker in javap,'compiled helper missing '+marker)

    packaging=load('r3936_packaging',ROOT/'qa/field-r395/jar_packaging.py')
    modified=packaging.rewrite_zip(outer[nested],replacements)
    new=members(modified)
    changed={n for n in set(inner)|set(new) if inner.get(n)!=new.get(n)}
    need(changed==set(CHANGED),'unexpected kernel delta: '+repr(sorted(changed)))

    # R39.34 monument and other inherited kernel changes must remain untouched.
    inherited=(
      'net/minecraft/world/level/levelgen/structure/structures/OceanMonumentStructure.class',
      'net/minecraft/world/level/levelgen/structure/structures/NeverOverworldOceanMonumentR34.class',
      'net/minecraft/world/level/chunk/NeverOverworldFlood.class',
      'net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.class'
    )
    for name in inherited:
        need(name in inner and new[name]==inner[name],'inherited class changed: '+name)

    rows=[];seen=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        fields=line.split('\t')
        need(len(fields)==3,'bad versions row')
        if 'META-INF/versions/'+fields[2]==nested:
            need(fields[0]==digest(outer[nested]),'bundled digest mismatch')
            fields[0]=digest(modified);seen+=1
        rows.append('\t'.join(fields))
    need(seen==1,'missing versions row')

    bundled=packaging.rewrite_zip(
      server.read_bytes(),
      {nested:modified,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()}
    )
    (CAND/'server.jar').write_bytes(bundled)
    shutil.copyfile(pack,CAND/'NeverOverworld.zip')
    shutil.copyfile(nether,CAND/'NeverNether.zip')

    custom=[]
    for group in spec['placement_groups'].values():
        for row in group['structures']:
            custom.append(row['id'])
    need(len(custom)==8,'unexpected custom underground structure count')

    report={
      'build_pass':True,
      'base_r3935_core_sha256':BASE_CORE,
      'candidate_core_sha256':sha(CAND/'server.jar'),
      'neveroverworld_sha256':BASE_PACK,
      'nether_sha256':NETHER,
      'changed_kernel_entries':list(CHANGED),
      'custom_underground_structures':sorted(custom),
      'custom_structure_count':len(custom),
      'per_profile_y_bands_removed':True,
      'global_start_y':[-480,480],
      'dynamic_upper_bound':'local OCEAN_FLOOR_WG - profile surface cover',
      'surface_covers':{name:int(p['minimum_surface_cover']) for name,p in profiles.items()},
      'flooded_ruins_surface_connected':False,
      'vanilla_mineshaft_trial_rules_changed':False,
      'production_accepted':False
    }
    (OUT/'build-r3936.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('R3936_BUILD '+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
