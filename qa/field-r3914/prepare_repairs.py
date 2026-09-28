#!/usr/bin/env python3
"""Build a staged resource candidate; never publish as full acceptance here."""
from pathlib import Path
import collections,hashlib,importlib.util,io,json,subprocess,sys,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'resource-evidence'
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def plain(tag):
    t,v=tag
    if t==10:return {k:plain(c) for k,c in v.items()}
    if t==9:return [plain((v[0],c)) for c in v[1]]
    if t==7:return {'byte_array_sha256':hashlib.sha256(v).hexdigest()}
    return v
def main():
    OUT.mkdir(exist_ok=True)
    nbt=load('nbt3914',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    source=next((ROOT/'inputs').rglob('NeverOverworld.zip'))
    result=subprocess.run([sys.executable,str(ROOT/'qa/field-r394/build_candidate.py'),'--self-test'],capture_output=True,text=True,timeout=60)
    (OUT/'cart-tests.log').write_text(result.stdout+result.stderr);print(result.stdout+result.stderr)
    if result.returncode:raise ValueError('Cart transformer unit tests failed')
    candidate=ROOT/'candidate-resources/NeverOverworld.zip';candidate.parent.mkdir(exist_ok=False)
    result=subprocess.run([sys.executable,str(ROOT/'qa/field-r394/build_candidate.py'),'--input',str(source),'--output',str(candidate),'--report',str(OUT/'cart-build.json')],capture_output=True,text=True,timeout=180)
    (OUT/'cart-build.log').write_text(result.stdout+result.stderr);print('CART_BUILD '+result.stdout+result.stderr,flush=True)
    with zipfile.ZipFile(source) as z:files={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
    missing=json.loads((OUT/'before.json').read_text())['missing']
    templates={n:raw for n,raw in files.items() if '/structure/' in n and n.endswith('.nbt')}
    selected={}
    terms=('stray_fort/','badlands_miner_outpost_path_t','catacomb_path_2','catacomb_path_snake_2','deko_center_','deko_mirror_center_','deko_furnace','deko_mirror_furnace','pale_residence_main_4','pale_residence_main_e','desert_ruins_temple_main','jungle_village_path','swamp_village_path','swamp_village_big_house','swamp_village_house1','swamp_village_house2','toxic_surface_deco_2','spawner_boss_slime','spawner_slime','small_room_6','bunker_underground_hallway_21','bunker_underground_hallway_2.nbt','bunker_underground_hallway_1.nbt')
    for path,raw in sorted(templates.items()):
        if not any(t in path for t in terms):continue
        _,_,root=nbt._nbt_parse(raw);data=plain((10,root));joints=[]
        palettes=data.get('palette',data.get('palettes',[[]])[0])
        for b in data.get('blocks',[]):
            state=palettes[b['state']]
            if state.get('Name')=='minecraft:jigsaw':joints.append({'pos':b['pos'],'state':state,'nbt':b.get('nbt')})
        row={'size':data.get('size'),'jigsaws':joints,'block_types':dict(collections.Counter(s['Name'] for s in palettes)),'entities':data.get('entities',[]),'sha256':hashlib.sha256(raw).hexdigest()}
        selected[path]=row
        print('GEOMETRY '+json.dumps({'path':path,'size':row['size'],'jigsaws':row['jigsaws'],'entities':len(row['entities'])}),flush=True)
    (OUT/'geometry.json').write_text(json.dumps(selected,indent=2)+'\n')
    for path,raw in sorted(files.items()):
        if '/template_pool/' in path and any(t in path for t in ('stray_fort_walls','illager_mansion_room','random_pillager_book')):print('POOL '+path+' '+raw.decode(),flush=True)
    # Metadata only: do not install any newer/older upstream data automatically.
    request=urllib.request.Request('https://api.modrinth.com/v2/project/tpehi7ww/version?loaders=%5B%22datapack%22%5D',headers={'User-Agent':'NeverFolia-resource-audit/1.0'})
    with urllib.request.urlopen(request,timeout=45) as response:versions=json.load(response)
    (OUT/'upstream-versions.json').write_text(json.dumps(versions,indent=2)+'\n')
    for v in versions:
        if v.get('version_type')=='release':print('UPSTREAM_VERSION '+json.dumps({k:v[k] for k in ('id','version_number','game_versions','files')}),flush=True)
    if result.returncode:raise ValueError('Staged biome cart build failed; inspect exact data, no candidate acceptance')
if __name__=='__main__':main()
