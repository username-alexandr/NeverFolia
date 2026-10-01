#!/usr/bin/env python3
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts'
WORK=ROOT/'.work/r3934fix-build'
CAND=ROOT/'candidate'
BASE=ROOT/'baseline-r3933'

BASE_CORE='33b959dad4201fcef988bca631b3b4ed6632fc9420799130b21ca550d5e5d046'
BASE_PACK='6df2efd420da0952f1b8c19cf79737581d4c53c58fc44ada7ae6138d2b96a876'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'

MONUMENT='net/minecraft/world/level/levelgen/structure/structures/OceanMonumentStructure.class'
HELPER='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldOceanMonumentR34.class'

def need(v,m):
    if not v: raise ValueError(m)

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

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
    need(server.is_file() and pack.is_file() and nether.is_file(),'R39.33 baseline incomplete')
    need(sha(server)==BASE_CORE,'wrong R39.33 server')
    need(sha(pack)==BASE_PACK,'wrong R39.33 NeverOverworld')
    need(sha(nether)==NETHER,'wrong R39.33 NeverNether')

    outer=members(server.read_bytes())
    nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'unexpected bundled kernel')
    nested=nested[0]
    inner=members(outer[nested])
    need(MONUMENT in inner,'OceanMonumentStructure missing')

    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):
            (libs/(str(i)+'-'+Path(n).name)).write_bytes(raw)
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))))
    (WORK/'classpath.txt').write_text(cp)

    classes=WORK/'classes';classes.mkdir()
    helper_src=ROOT/'native/overworld-r3934/NeverOverworldOceanMonumentR34.java'
    patcher_src=ROOT/'qa/field-r3934fix/R3934PatchOceanMonument.java'
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(helper_src),str(patcher_src)],'javac.log')

    target_in=WORK/'OceanMonumentStructure.class'
    target_out=WORK/'patched/OceanMonumentStructure.class'
    target_in.write_bytes(inner[MONUMENT])
    run(['java','-cp',str(classes)+os.pathsep+cp,'R3934PatchOceanMonument',str(target_in),str(target_out)],'asm-patch.log')

    replacements={
      MONUMENT:target_out.read_bytes(),
      HELPER:(classes/HELPER).read_bytes(),
    }
    need(all(int.from_bytes(v[6:8],'big')==69 for v in replacements.values()),'wrong Java bytecode version')

    inspect=WORK/'inspect';inspect.mkdir()
    (inspect/MONUMENT).parent.mkdir(parents=True,exist_ok=True)
    (inspect/MONUMENT).write_bytes(replacements[MONUMENT])
    (inspect/HELPER).parent.mkdir(parents=True,exist_ok=True)
    (inspect/HELPER).write_bytes(replacements[HELPER])
    run([
      'javap','-classpath',str(inspect)+os.pathsep+cp,'-p','-c',
      'net.minecraft.world.level.levelgen.structure.structures.OceanMonumentStructure',
      'net.minecraft.world.level.levelgen.structure.structures.NeverOverworldOceanMonumentR34'
    ],'javap.log')
    javap=(OUT/'javap.log').read_text()
    need('NeverOverworldOceanMonumentR34.resolveBaseY' in javap,'patched monument does not call R39.34 base helper')
    need('NeverOverworldOceanMonumentR34.allowsGeneration' in javap,'patched monument does not call R39.34 relief gate')
    need('OCEAN_FLOOR_WG' in javap,'R39.34 helper lost ocean-floor sampling')
    need('bipush        104' not in javap.split('neverOverworldMonumentBaseY',1)[1].split('createTopPiece',1)[0],
         'old fixed Y=104 resolver survived')

    packaging=load('r3934_packaging',ROOT/'qa/field-r395/jar_packaging.py')
    modified=packaging.rewrite_zip(outer[nested],replacements)
    new=members(modified)
    changed={n for n in set(inner)|set(new) if inner.get(n)!=new.get(n)}
    need(changed=={MONUMENT,HELPER},'unexpected kernel delta: '+repr(sorted(changed)))

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
    run(['python3',str(ROOT/'qa/field-r3934fix/patch_pack.py'),str(pack),str(CAND/'NeverOverworld.zip')],'r3934-pack.log',timeout=420)
    shutil.copyfile(nether,CAND/'NeverNether.zip')

    report={
      'build_pass':True,
      'base_r3933_core_sha256':BASE_CORE,
      'candidate_core_sha256':sha(CAND/'server.jar'),
      'base_neveroverworld_sha256':BASE_PACK,
      'candidate_neveroverworld_sha256':sha(CAND/'NeverOverworld.zip'),
      'nether_sha256':NETHER,
      'changed_kernel_entries':[MONUMENT,HELPER],
      'old_monument_base_y':104,
      'new_monument_policy':'reject relief >12; otherwise OCEAN_FLOOR_WG base=min(median,min+6), capped at 104',
      'sample_spacing':2,'sample_radius':28,'max_seabed_relief':12,
      'ocean_pillar_detached_cells_after':0,'ocean_pillar_explicit_water_after':0,
      'production_accepted':False
    }
    (OUT/'build-r3934.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R3934_BUILD '+json.dumps(report),flush=True)

if __name__=='__main__':
    main()
