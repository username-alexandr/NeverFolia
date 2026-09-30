#!/usr/bin/env python3
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3931-build';CAND=ROOT/'candidate'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
FLOOD='net/minecraft/world/level/chunk/NeverOverworldFlood.class'
KEEP=('net/minecraft/world/level/chunk/NeverOverworldWaterPolicyR38.class',
      'net/minecraft/world/level/chunk/NeverOverworldDryMinesR12.class',
      'net/minecraft/world/level/chunk/NeverOverworldDryMinesR12$Mask.class')
def need(v,m):
    if not v:raise ValueError(m)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def run(args,name):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'Failed '+name)
def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=False)
    base=ROOT/'baseline/server.jar';pack=ROOT/'baseline/world/datapacks/NeverOverworld.zip';nether=ROOT/'baseline/world/datapacks/NeverNether.zip'
    need(sha(base)==BASE,'Wrong R39.9 baseline');need(sha(pack)==PACK and sha(nether)==NETHER,'Wrong paired packs')
    outer=members(base.read_bytes());nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'Unexpected bundled kernel');nested=nested[0];inner=members(outer[nested])
    need(FLOOD in inner,'Historical flood class missing');need(all(k in inner for k in KEEP),'R39.9 hotfix missing')
    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(raw)
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))));(WORK/'classpath.txt').write_text(cp);classes=WORK/'classes';classes.mkdir()
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(ROOT/'native/overworld-r3931/NeverOverworldFlood.java')],'flood-javac.log')
    replacement=(classes/FLOOD).read_bytes();need(int.from_bytes(replacement[6:8],'big')==69,'Wrong Java bytecode')
    packaging=load('r3931_packaging',ROOT/'qa/field-r395/jar_packaging.py');run(['python3',str(ROOT/'qa/field-r395/jar_packaging.py')],'packaging-tests.log')
    modified=packaging.rewrite_zip(outer[nested],{FLOOD:replacement})
    rows=[];seen=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        f=line.split('\t');need(len(f)==3,'Bad versions row')
        if 'META-INF/versions/'+f[2]==nested:
            need(f[0]==digest(outer[nested]),'Bundled digest mismatch');f[0]=digest(modified);seen+=1
        rows.append('\t'.join(f))
    need(seen==1,'Missing versions row')
    bundled=packaging.rewrite_zip(base.read_bytes(),{nested:modified,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()})
    new=members(modified);new_outer=members(bundled)
    need({n for n in inner if inner[n]!=new[n]}=={FLOOD},'Unexpected kernel delta')
    need(all(new[k]==inner[k] for k in KEEP),'Inherited hotfix changed')
    need(set(outer)==set(new_outer) and {n for n in outer if outer[n]!=new_outer[n]}=={nested,'META-INF/versions.list'},'Unexpected outer delta')
    (CAND/'server.jar').write_bytes(bundled)
    run(['python3',str(ROOT/'qa/field-r3931/patch_pack.py'),str(pack),str(CAND/'NeverOverworld.zip')],'pack.log')
    shutil.copyfile(nether,CAND/'NeverNether.zip')
    with zipfile.ZipFile(CAND/'NeverOverworld.zip') as z:
        settings=json.loads(z.read('data/minecraft/worldgen/noise_settings/overworld.json'))
    need(settings['sea_level']==128,'Candidate sea level not 128')
    report={'build_pass':True,'base_core_sha256':BASE,'candidate_core_sha256':sha(CAND/'server.jar'),
      'base_pack_sha256':PACK,'candidate_pack_sha256':sha(CAND/'NeverOverworld.zip'),'nether_sha256':NETHER,
      'sea_level':128,'retired_light_flood':True,'changed_kernel_entries':[FLOOD],
      'preserved_hotfix_classes':{k:digest(new[k]) for k in KEEP},'production_accepted':False}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print('R3931_BUILD '+json.dumps(report),flush=True)
if __name__=='__main__':main()
