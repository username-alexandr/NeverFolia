#!/usr/bin/env python3
from pathlib import Path, PurePosixPath
import hashlib,io,json,shutil,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts'
WORK=ROOT/'.work/r3937-build'
CAND=ROOT/'candidate'
BASE=ROOT/'baseline-r3936'
SRC=ROOT/'sources-r3937'

BASE_CORE='c717e3e444fbec7c5d0f3c0d08d24e2c0a221c1ac37d59551edbb3c500bb2ff0'
BASE_OVERWORLD='d4771781192ce17b73e3bc46443c4d66adceb6c3c78d3dd8008708db5a1f71ef'
BASE_NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'

SOURCE_FILES={
  'hearths':'Hearths v1.0.5.dp.zip',
  'dungeons_and_taverns':'Dungeons and Taverns v5.3.2.zip',
  'explorify':'Explorify v1.6.5.dp.zip',
  'structory_towers':'Structory_Towers_v1.0.17.zip',
  'better_monuments':'Repurposed_Structures-Better_Monuments_v7.zip',
}

def need(v,m):
    if not v:raise ValueError(m)

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def files(path):
    with zipfile.ZipFile(path) as z:
        need(z.testzip() is None,'invalid ZIP '+str(path))
        return {i.filename:z.read(i.filename) for i in z.infolist() if not i.is_dir()}

def run(args,name,timeout=600):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout)
    print(p.stdout,flush=True)
    need(p.returncode==0,'failed '+name)

def alias_id(sid):
    ns,path=sid.split(':',1)
    safe=(ns+'__'+path).replace('/','__')
    return 'neverfolia:never_nether/start/'+safe

def pool_path(pool):
    ns,path=pool.split(':',1)
    return f'data/{ns}/worldgen/template_pool/{path}.json'

def structure_path(sid):
    ns,path=sid.split(':',1)
    return f'data/{ns}/worldgen/structure/{path}.json'

def main():
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(parents=True,exist_ok=False)
    CAND.mkdir(exist_ok=True)

    server=BASE/'server.jar'
    overworld=BASE/'world/datapacks/NeverOverworld.zip'
    nether=BASE/'world/datapacks/NeverNether.zip'
    need(server.is_file() and overworld.is_file() and nether.is_file(),'R39.36 baseline incomplete')
    need(sha(server)==BASE_CORE,'wrong R39.36 server')
    need(sha(overworld)==BASE_OVERWORLD,'wrong R39.36 NeverOverworld')
    need(sha(nether)==BASE_NETHER,'wrong R39.36 NeverNether')

    # Fetch exact user-approved source releases and verify pinned SHA256.
    run(['python3',str(ROOT/'qa/field-r3937/fetch_sources.py'),str(SRC)],'sources.log',timeout=600)

    # Builder/hardener own synthetic regression suites must remain green.
    run(['python3',str(ROOT/'scripts/build-never-nether-structure-pack.py'),'--self-test'],
        'builder-selftest.log',timeout=300)
    run(['python3',str(ROOT/'scripts/harden-never-nether-structure-pack.py'),'--self-test'],
        'hardener-selftest.log',timeout=300)

    integration=WORK/'NeverNether-structures-integration.zip'
    cmd=[
      'python3',str(ROOT/'scripts/build-never-nether-structure-pack.py'),
      '--core',str(nether),
    ]
    for key,name in SOURCE_FILES.items():
        cmd += ['--source',f'{key}={SRC/name}']
    cmd += ['--output',str(integration)]
    run(cmd,'integration-build.log',timeout=900)

    final_pack=CAND/'NeverNether.zip'
    run([
      'python3',str(ROOT/'scripts/harden-never-nether-structure-pack.py'),
      '--input',str(integration),
      '--output',str(final_pack)
    ],'integration-harden.log',timeout=600)

    shutil.copyfile(server,CAND/'server.jar')
    shutil.copyfile(overworld,CAND/'NeverOverworld.zip')

    base=files(nether)
    out=files(final_pack)

    # NeverNether terrain/core bytes are immutable through structure integration.
    for name,payload in base.items():
        need(name in out,'base NeverNether entry disappeared: '+name)
        need(out[name]==payload,'base NeverNether entry changed: '+name)

    spec=json.loads((ROOT/'worldgen-spec/never-nether-structures.json').read_text())
    ids=[]
    for group in spec['placement_groups'].values():
        for row in group['structures']:
            ids.append(row['id'])
    need(len(ids)==20 and len(set(ids))==20,'expected 20 unique custom structures')

    for sid in ids:
        sp=structure_path(sid)
        need(sp in out,'custom structure missing: '+sid)
        data=json.loads(out[sp])
        need(data.get('type')=='minecraft:jigsaw',sid+' not native jigsaw')
        need(data.get('start_pool')==alias_id(sid),sid+' start_pool alias mismatch')
        need(data.get('dimension_padding')=={'bottom':5,'top':517},sid+' dimension padding mismatch')
        need(pool_path(alias_id(sid)) in out,sid+' alias pool missing')

    structure_jsons=[
      n for n in out
      if '/worldgen/structure/' in n and n.endswith('.json')
      and any(n==structure_path(sid) for sid in ids)
    ]
    need(len(structure_jsons)==20,'custom structure JSON count mismatch')

    expected_sets={
      'data/neverfolia/worldgen/structure_set/never_nether/custom_major.json',
      'data/neverfolia/worldgen/structure_set/never_nether/custom_medium.json',
      'data/neverfolia/worldgen/structure_set/never_nether/custom_ambient.json',
      'data/neverfolia/worldgen/structure_set/never_nether/nether_monument.json',
    }
    actual_sets={n for n in out if '/worldgen/structure_set/' in n and n.endswith('.json')}
    need(actual_sets==expected_sets,'structure_set mismatch: '+repr(sorted(actual_sets)))

    manifest=json.loads(out['nevernether-structure-integration-manifest.json'])
    need(manifest.get('approved_structure_count')==20,'integration manifest structure count')
    need(manifest.get('third_party_structure_sets_imported') is False,'third-party placement survived')
    hard=manifest.get('neverfolia_hardening',{})
    need(hard.get('effective_bounding_box_y')==[-123,378],'hardening bounds missing')

    # Confirm the current R39.36 kernel already contains the 20-alias Nether resolver.
    outer=files(server)
    nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'unexpected bundled kernel')
    inner=files(io.BytesIO(outer[nested[0]]))
    helper='net/minecraft/world/level/levelgen/structure/structures/NeverNetherStructurePlacement.class'
    need(helper in inner,'NeverNetherStructurePlacement missing from kernel')
    helper_bytes=inner[helper]
    missing_alias=[alias_id(sid) for sid in ids if alias_id(sid).encode() not in helper_bytes]
    need(not missing_alias,'Nether placement helper missing aliases: '+repr(missing_alias))

    required_classes=[
      'net/minecraft/world/level/levelgen/structure/templatesystem/NeverNetherNativeProcessors.class',
      'net/minecraft/world/level/levelgen/structure/pools/NeverNetherLimitedPoolElement.class',
      'net/minecraft/world/level/levelgen/structure/pools/NeverNetherPieceBudget.class',
    ]
    need(all(x in inner for x in required_classes),'NeverNether native compatibility classes missing')

    report={
      'build_pass':True,
      'base_core_sha256':BASE_CORE,
      'candidate_core_sha256':sha(CAND/'server.jar'),
      'overworld_sha256':BASE_OVERWORLD,
      'base_nether_sha256':BASE_NETHER,
      'candidate_nether_sha256':sha(final_pack),
      'approved_custom_structures':sorted(ids),
      'approved_custom_structure_count':20,
      'structure_set_count':4,
      'base_nether_entries_preserved':len(base),
      'final_nether_entries':len(out),
      'third_party_structure_sets_imported':False,
      'kernel_netherit_placement_aliases':20,
      'production_accepted':False,
    }
    (OUT/'build-r3937.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('R3937_BUILD '+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
