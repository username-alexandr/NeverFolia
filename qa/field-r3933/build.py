#!/usr/bin/env python3
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3933-build';CAND=ROOT/'candidate'
BASE32=ROOT/'baseline-r3932'
BASE_CORE='2d896721645190a20d5855ba76decd01418d26bb53c5eeee6af1bcc4b790c62f'
BASE_PACK='59c81a64916cf025215ab8f8b7421cd156b90d197be6d42c6b8a62d0faf985e3'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
PLACEMENT='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.class'
MODE='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement$Mode.class'
PROFILE='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement$Profile.class'
CHANGED=(PLACEMENT,MODE,PROFILE)

def need(v,m):
    if not v:raise ValueError(m)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def run(args,name,timeout=300):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'failed '+name)

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=True)
    server=BASE32/'server.jar';pack=BASE32/'world/datapacks/NeverOverworld.zip';nether=BASE32/'world/datapacks/NeverNether.zip'
    need(server.is_file() and pack.is_file() and nether.is_file(),'R39.32 baseline artifact incomplete')
    need(sha(server)==BASE_CORE,'wrong R39.32 server')
    need(sha(pack)==BASE_PACK,'wrong R39.32 NeverOverworld')
    need(sha(nether)==NETHER,'wrong R39.32 NeverNether')

    outer=members(server.read_bytes())
    nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'unexpected bundled kernel');nested=nested[0]
    inner=members(outer[nested])
    need(all(k in inner for k in CHANGED),'R39.32 placement classes missing')

    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):
            (libs/(str(i)+'-'+Path(n).name)).write_bytes(raw)
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))));(WORK/'classpath.txt').write_text(cp)

    maker=load('r3933_make_placement',ROOT/'qa/field-r3933/make_placement.py')
    src=WORK/'generated/net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.java'
    src.parent.mkdir(parents=True);source=maker.source();src.write_text(source)
    for marker in (
      'TRIDENT_START_POOL = "nova_structures:trident_monument/start"',
      'TRIDENT_SEABED_RADIUS = 48',
      'TRIDENT_SEABED_STEP = 24',
      'TRIDENT_MAX_RELIEF = 6',
      'Heightmap.Types.OCEAN_FLOOR_WG',
      'hasStableTridentSeabed(context) ? previousStartY : REJECT_Y'
    ):need(marker in source,'generated placement source missing '+marker)

    classes=WORK/'classes';classes.mkdir()
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(src)],'placement-javac.log')
    replacements={k:(classes/k).read_bytes() for k in CHANGED}
    need(all(int.from_bytes(v[6:8],'big')==69 for v in replacements.values()),'wrong Java bytecode')
    run(['javap','-classpath',str(classes),'-p','net.minecraft.world.level.levelgen.structure.structures.NeverOverworldStructurePlacement'],'placement-javap.log')
    javap=(OUT/'placement-javap.log').read_text()
    need('hasStableTridentSeabed' in javap and 'resolveStartY' in javap,'R39.33 placement methods missing')

    packaging=load('r3933_packaging',ROOT/'qa/field-r395/jar_packaging.py')
    modified=packaging.rewrite_zip(outer[nested],replacements)
    new=members(modified)
    need({n for n in inner if inner[n]!=new[n]}==set(CHANGED),'unexpected R39.33 kernel delta')

    rows=[];seen=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        f=line.split('\t');need(len(f)==3,'bad versions row')
        if 'META-INF/versions/'+f[2]==nested:
            need(f[0]==digest(outer[nested]),'bundled digest mismatch');f[0]=digest(modified);seen+=1
        rows.append('\t'.join(f))
    need(seen==1,'missing versions row')
    bundled=packaging.rewrite_zip(server.read_bytes(),{nested:modified,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()})
    (CAND/'server.jar').write_bytes(bundled)

    run(['python3',str(ROOT/'qa/field-r3933/patch_pack.py'),str(pack),str(CAND/'NeverOverworld.zip')],'r3933-pack.log',timeout=420)
    shutil.copyfile(nether,CAND/'NeverNether.zip')

    patcher=load('r3933_patch',ROOT/'qa/field-r3933/patch_pack.py')
    audit=patcher.verify((CAND/'NeverOverworld.zip').read_bytes())
    need(audit['trident_definition']['start_height']=={'absolute':-3},'trident offset not applied')
    need(audit['conduit_definition']['start_height']=={'absolute':0},'small conduit placement changed')
    need(audit['ocean_pillar_definition']['start_height']=={'absolute':0},'small ocean pillar placement changed')

    report={
      'build_pass':True,
      'base_r3932_core_sha256':BASE_CORE,
      'candidate_core_sha256':sha(CAND/'server.jar'),
      'base_r3932_pack_sha256':BASE_PACK,
      'candidate_pack_sha256':sha(CAND/'NeverOverworld.zip'),
      'nether_sha256':NETHER,
      'changed_kernel_entries':list(CHANGED),
      'small_structure_placement_unchanged':True,
      'small_structure_water_only':True,
      'trident_start_offset':-3,
      'trident_seabed_radius':48,
      'trident_seabed_step':24,
      'trident_max_relief':6,
      'trident_terrain_adaptation':'none',
      'production_accepted':False
    }
    (OUT/'build-r3933.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R3933_BUILD '+json.dumps(report),flush=True)

if __name__=='__main__':main()
