#!/usr/bin/env python3
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3932-build'
CAND=ROOT/'candidate'
PLACEMENT='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.class'
PLACEMENT_MODE='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement$Mode.class'
PLACEMENT_PROFILE='net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement$Profile.class'
CHANGED=(PLACEMENT,PLACEMENT_MODE,PLACEMENT_PROFILE)

def need(v,m):
    if not v:raise ValueError(m)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);need(spec is not None and spec.loader is not None,'Cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def run(args,name,timeout=300):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'Failed '+name)

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False)

    # Rebuild the last accepted native-sea candidate first.
    run(['python3',str(ROOT/'qa/field-r3931/build.py')],'r3931-build.log',timeout=420)
    r31=json.loads((OUT/'build.json').read_text())
    need(r31.get('build_pass') is True,'R39.31 base build did not pass')
    server=CAND/'server.jar';pack=CAND/'NeverOverworld.zip';nether=CAND/'NeverNether.zip'
    need(sha(server)==r31['candidate_core_sha256'],'R39.31 server changed before R39.32')
    need(sha(pack)==r31['candidate_pack_sha256'],'R39.31 pack changed before R39.32')

    # Generate the canonical placement helper from the same source transformer,
    # now with the R39.32 roof requirement for WATER_BOUNDARY structures.
    placement_module=load('r3932_placement',ROOT/'scripts/apply-never-overworld-placement-hook.py')
    spec=json.loads((ROOT/'worldgen-spec/never-overworld-structures.json').read_text())
    source=placement_module.helper_source(spec)
    need('Require a real rock ceiling above the local water.' in source,'R39.32 open-ocean guard missing')
    src=WORK/'generated/net/minecraft/world/level/levelgen/structure/structures/NeverOverworldStructurePlacement.java'
    src.parent.mkdir(parents=True);src.write_text(source)
    run(['python3',str(ROOT/'scripts/apply-never-overworld-placement-hook.py'),'--self-test'],'placement-selftest.log')

    cp=(ROOT/'.work/r3931-build/classpath.txt').read_text()
    classes=WORK/'classes';classes.mkdir()
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(src)],'placement-javac.log')
    replacements={k:(classes/k).read_bytes() for k in CHANGED}
    need(all(int.from_bytes(v[6:8],'big')==69 for v in replacements.values()),'Wrong placement bytecode version')
    run(['javap','-classpath',str(classes),'-p','net.minecraft.world.level.levelgen.structure.structures.NeverOverworldStructurePlacement'],'placement-javap.log')
    javap=(OUT/'placement-javap.log').read_text()
    need('resolveStartY' in javap and 'isWaterBoundary' in javap,'Placement ABI missing')

    packaging=load('r3932_packaging',ROOT/'qa/field-r395/jar_packaging.py')
    outer=members(server.read_bytes())
    nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'Unexpected bundled kernel');nested=nested[0]
    inner=members(outer[nested])
    need(all(k in inner for k in CHANGED),'R39.31 placement classes missing')
    modified=packaging.rewrite_zip(outer[nested],replacements)
    newinner=members(modified)
    need({n for n in inner if inner[n]!=newinner[n]}==set(CHANGED),'Unexpected placement kernel delta')

    rows=[];seen=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        f=line.split('\t');need(len(f)==3,'Bad versions row')
        if 'META-INF/versions/'+f[2]==nested:
            need(f[0]==digest(outer[nested]),'Bundled digest mismatch');f[0]=digest(modified);seen+=1
        rows.append('\t'.join(f))
    need(seen==1,'Missing versions row')
    bundled=packaging.rewrite_zip(server.read_bytes(),{nested:modified,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()})
    server.write_bytes(bundled)

    # Apply the full R39.32 data audit/normalization on top of R39.31.
    tmp=CAND/'NeverOverworld-R3932.zip'
    run(['python3',str(ROOT/'qa/field-r3932/patch_pack.py'),str(pack),str(tmp)],'r3932-pack.log',timeout=420)
    tmp.replace(pack)

    report={
      'build_pass':True,
      'base_r3931_core_sha256':r31['candidate_core_sha256'],
      'candidate_core_sha256':sha(server),
      'base_r3931_pack_sha256':r31['candidate_pack_sha256'],
      'candidate_pack_sha256':sha(pack),
      'nether_sha256':sha(nether),
      'changed_kernel_entries':list(CHANGED),
      'ancient_cistern_open_ocean_rejected':True,
      'ocean_structures_floor_anchored':[
        'structory_towers:ocean_pillar',
        'nova_structures:conduit_ruin',
        'nova_structures:trident_trial_monument'
      ],
      'production_accepted':False
    }
    (OUT/'build-r3932.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R3932_BUILD '+json.dumps(report),flush=True)

if __name__=='__main__':main()
