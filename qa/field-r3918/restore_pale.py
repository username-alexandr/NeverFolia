#!/usr/bin/env python3
"""Restore an existing authored decoration, never synthesize a missing model.
Exact combined input; only the stub pool and content fingerprint may change.
"""
from pathlib import Path
import argparse, copy, hashlib, importlib.util, json, sys, zipfile
import inspect_resources as inspector
ROOT=Path(__file__).resolve().parents[2]
BASE=inspector.PACK_SHA
POOL='data/nova_structures/worldgen/template_pool/pale_residence/decor_inside.json'
BANNER='data/nova_structures/structure/pale_residence/decor/banner.nbt'
PARENT='data/nova_structures/structure/pale_residence/pale_residence.nbt'
ID='nova_structures:pale_residence/decor_inside'
FP='data/neveroverworld/dimension_fingerprint.json'
EMPTY={'fallback':'minecraft:empty','elements':[{'weight':1,'element':{'element_type':'minecraft:empty_pool_element'}}]}
RESTORED={'fallback':'minecraft:empty','elements':[{'weight':1,'element':{'element_type':'minecraft:single_pool_element','location':'nova_structures:pale_residence/decor/banner','processors':'minecraft:empty','projection':'rigid'}}]}

def need(ok,msg):
    if not ok:raise ValueError(msg)

def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(obj):return (json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def geometry(parent,child):
    need(child['size']==[1,4,1],'Unexpected authored decoration extent')
    need(len(child['joints'])==1,'Expected one terminal decoration connector')
    j=child['joints'][0];n=j['nbt']
    need(j['pos']==[0,0,0] and j['state']['Properties'][1]['orientation'][1]=='down_south','Decoration orientation changed')
    need(n['name']==ID and n['pool']=='minecraft:empty' and n['target']=='minecraft:empty' and n['final_state']=='minecraft:air','Decoration joint contract changed')
    need(child['entities'][1][1]==[],'Decoration must not introduce entities')
    need(child['blocks'].get('minecraft:white_banner')==1 and child['blocks'].get('minecraft:birch_wall_sign')==1,'Missing authored decoration blocks')
    matches=[x for x in parent['joints'] if x['nbt'].get('pool')==ID]
    expected={(19,8,6),(22,8,6),(22,8,9),(19,8,9)}
    need(len(matches)==4 and {tuple(x['pos']) for x in matches}==expected,'Parent output set changed')
    for x in matches:
        need(x['nbt'].get('target')==ID and x['state']['Properties'][1]['orientation'][1]=='up_south','Parent connector incompatible')
    return matches

def patch(files):
    need(json.loads(files[POOL])==EMPTY,'Pool is not the exact reviewed empty stub')
    reader=inspector.load_reader()
    parent=inspector.inspect_template(files[PARENT],reader)
    child=inspector.inspect_template(files[BANNER],reader)
    joints=geometry(parent,child)
    # Retain source cell context. This is a geometry observation, not a
    # replacement for the actual jigsaw placement test.
    root=reader._nbt_parse(files[PARENT])[2]
    palette=root['palette'][1][1]
    cells={tuple(b['pos'][1][1]):palette[b['state'][1]] for b in root['blocks'][1][1]}
    context=[]
    for j in joints:
        x,y,z=j['pos']
        context.append({'connector':j['pos'],'above_cells':[{'pos':[x,y+d,z],'state':cells.get((x,y+d,z))} for d in range(1,5)]})
    new=dict(files);new[POOL]=encoded(RESTORED)
    fingerprint=json.loads(new[FP]);names=sorted(k for k in new if k.startswith('data/') and k not in (FP,'data/neveroverworld/dimension_fingerprint_base.txt'))
    fingerprint['generated_files']=len(names)
    fingerprint['generated_files_sha256']=digest('\n'.join(names).encode())
    fingerprint['generated_content_sha256']=digest('\n'.join(k+':'+digest(new[k]) for k in names).encode())
    new[FP]=encoded(fingerprint)
    changed=sorted(k for k in files if files[k]!=new[k])
    need(changed==sorted([POOL,FP]) and set(new)==set(files),'Unexpected changed members')
    return new,{'changed':changed,'unchanged_members':len(files)-len(changed),'authored_parent_sha256':digest(files[PARENT]),'authored_banner_sha256':digest(files[BANNER]),'parent_connectors':context,'restored_pool':RESTORED,'nbt_files_unchanged':True,'core_unchanged':True}

def read(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist();need(len(names)==len(set(names)),'Duplicate ZIP members');need(z.testzip() is None,'ZIP CRC failure')
        need(all(not n.startswith('/') and '..' not in Path(n).parts and '\\' not in n for n in names),'Unsafe ZIP path')
        return {n:z.read(n) for n in names if not n.endswith('/')}

def write(path,files):
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    need(digest(a.input.read_bytes())==BASE,'Unreviewed base pack')
    files=read(a.input);new,report=patch(files)
    a.output.mkdir(parents=True,exist_ok=False)
    out=a.output/'NeverOverworld-R3918-Combined.zip';write(out,new)
    need(read(out)==new,'Pack round-trip failed')
    again=a.output/'reproduced.zip';write(again,new);need(out.read_bytes()==again.read_bytes(),'Nonreproducible packaging');again.unlink()
    report.update({'pass':True,'input_sha256':BASE,'output_sha256':digest(out.read_bytes()),'packaging_reproducible':True,'runtime_tested':False,'all_reported_bugs_fixed':False})
    (a.output/'pale-build.json').write_bytes(encoded(report));print('PALE_BUILD',json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
