#!/usr/bin/env python3
"""Reconstruct two missing profession-cart families from their actual source models.
A biome recipe is accepted only if it reproduces every voxel and typed NBT of
all eleven existing profession variants. No nearest-name substitutions, pool
weight changes, registry changes, or edits to existing structure templates.
"""
from __future__ import annotations
from pathlib import Path
import argparse, copy, hashlib, importlib.util, io, json, sys, zipfile
ROOT=Path(__file__).resolve().parents[2]
PACK_SHA='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
PREFIX='data/nova_structures/structure/tavern/tavern_event_trader_car_'
BIOMES=('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp')
ROLES=('armorer','butcher','farmer','fisher','fletcher','grindstone','leather_worker','librarian','loom','smithing_table','stonecutter')
RECOVER=('cartographer','cleric')
BASE_SHA={'cartographer':'6e6312ee2b2a8a569a9a85ab877afa9d3764779a1faafef97bede8bdea9dd21e','cleric':'8ca276de099594ff75a4bc46f982ea7cfb1e0b99b9d698d7edcbe678fc304b79'}
FINGERPRINTS=('neveroverworld-worldgen-fingerprint.json','data/neverfolia/neveroverworld/worldgen_fingerprint.json')
def need(ok,message):
    if not ok: raise ValueError(message)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def semantic(root):
    need('palettes' not in root,'Multiple palettes require a separate review')
    need(root.get('DataVersion',(0,))[0]==3,'Missing original DataVersion')
    palette=root['palette']; need(palette[0]==9 and palette[1][0]==10,'Invalid palette')
    blocks=root['blocks'];need(blocks[0]==9 and blocks[1][0]==10,'Invalid blocks')
    value={k:copy.deepcopy(v) for k,v in root.items() if k not in ('DataVersion','palette','blocks')};value['blocks']={}
    for block in blocks[1][1]:
        pos=tuple(block['pos'][1][1]);i=block['state'][1]
        need(len(pos)==3 and pos not in value['blocks'],'Duplicate/invalid position')
        need(block['state'][0]==3 and 0<=i<len(palette[1][1]),'Invalid state index')
        record={k:copy.deepcopy(v) for k,v in block.items() if k!='pos'};record['state']=copy.deepcopy(palette[1][1][i]);value['blocks'][pos]=record
    return value

def diff(a,b,path=()):
    if a==b:return []
    if type(a) is type(b) and isinstance(a,dict):
        out=[]
        for key in sorted(a.keys()-b.keys()):out.append(('remove',path+(key,),a[key],None))
        for key in sorted(b.keys()-a.keys()):out.append(('add',path+(key,),None,b[key]))
        for key in sorted(a.keys()&b.keys()):out.extend(diff(a[key],b[key],path+(key,)))
        return out
    if type(a) is type(b) and isinstance(a,(tuple,list)) and len(a)==len(b):
        return [change for i,(x,y) in enumerate(zip(a,b)) for change in diff(x,y,path+(i,))]
    return [('replace',path,a,b)]

def edit(value,operation,path,before,after):
    if not path:
        need(operation=='replace' and value==before,'Recipe source mismatch')
        return copy.deepcopy(after)
    key=path[0]
    if len(path)==1 and operation in ('add','remove'):
        need(isinstance(value,dict),'Recipe inserts/removes dictionary entries only')
        result=copy.deepcopy(value)
        if operation=='add':
            need(key not in result,'Recipe insertion would overwrite a field');result[key]=copy.deepcopy(after)
        else:
            need(key in result and result[key]==before,'Recipe deletion mismatch');del result[key]
        return result
    if isinstance(value,tuple):
        result=list(value);result[key]=edit(result[key],operation,path[1:],before,after);return tuple(result)
    result=copy.deepcopy(value)
    need(not isinstance(result,dict) or key in result,'Missing recipe field')
    result[key]=edit(result[key],operation,path[1:],before,after);return result

def apply(value,ops):
    out=copy.deepcopy(value)
    for op,path,before,after in ops:
        need(path and path[0] in ('blocks','size'),'Recipe attempted unrelated root mutation')
        out=edit(out,op,path,before,after)
    restored=copy.deepcopy(out)
    for op,path,before,after in reversed(ops):
        inverse={'add':'remove','remove':'add','replace':'replace'}[op]
        restored=edit(restored,inverse,path,after,before)
    need(restored==value,'Recipe is not reversible')
    return out

def encode_model(original,model):
    root=copy.deepcopy(original);palette=[];blocks=[]
    for k,v in model.items():
        if k!='blocks':root[k]=copy.deepcopy(v)
    for pos,record in sorted(model['blocks'].items(),key=lambda x:(x[0][1],x[0][2],x[0][0])):
        item=copy.deepcopy(record);state=item.pop('state')
        if state not in palette:palette.append(state)
        item['state']=(3,palette.index(state));item['pos']=(9,(3,list(pos)));blocks.append(item)
    root['palette']=(9,(10,palette));root['blocks']=(9,(10,blocks))
    need(root['DataVersion']==original['DataVersion'],'Original DataVersion lost')
    need(semantic(root)==model,'Encoded model differs')
    return root

def validate(root,biome=None):
    size=root['size'][1][1]; expected=[5,5,5] if biome=='snowy' else [5,4,5]
    need(size==expected,'Unexpected cart envelope: '+repr((biome,size)))
    need(root.get('entities',(9,(10,[])))[1][1]==[],'Unexpected direct cart entities')
    obj=semantic(root);need(len(obj['blocks'])==size[0]*size[1]*size[2],'Cart voxel coverage incomplete')
    need(all(all(0<=p[i]<size[i] for i in range(3)) for p in obj['blocks']),'Out-of-bounds cart voxel')
    joints={p:r['nbt'][1] for p,r in obj['blocks'].items() if r.get('nbt',(10,{}))[1].get('id')==(8,'minecraft:jigsaw')}
    expected_positions={(4,0,0)} if biome=='pale' else {(4,0,0),(2,1,1)}
    need(set(joints)==expected_positions,'Unreviewed jigsaw geometry: '+repr((biome,list(joints))))
    suffix='' if biome is None else '_'+biome
    need(joints[(4,0,0)]['name']==(8,'nova_structures:tavern_trader_car'+suffix),'Parent joint does not match biome')
    if biome not in (None,'pale'):
        need(joints[(2,1,1)]['target']==(8,'nova_structures:tavern_villager'+suffix),'Villager target does not match biome')
        need(joints[(2,1,1)]['pool']==(8,'nova_structures:tavern_trader'),'Unexpected villager pool')

def zip_bytes(files):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(files.items()):
            need(not name.startswith('/') and '..' not in Path(name).parts and '\\' not in name,'Invalid ZIP path')
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,data,compresslevel=9)
    return buf.getvalue()

def build(source,output):
    source=Path(source);output=Path(output);need(not output.exists(),'Output must be new')
    data=source.read_bytes();need(sha(data)==PACK_SHA,'Wrong original pack')
    b=load('r3914_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    fp=load('r3914_fp',ROOT/'scripts/fingerprint-never-overworld-pack.py')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        need(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),'Invalid input ZIP')
        original={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
    need(len(original)==8007,'Wrong original entry count')
    need(original[FINGERPRINTS[0]]==original[FINGERPRINTS[1]] and json.loads(original[FINGERPRINTS[0]])==fp.fingerprint_document(original),'Invalid original fingerprint')
    source_models={role:b._nbt_parse(original[PREFIX+role+'.nbt']) for role in ROLES+RECOVER}
    for role in RECOVER:
        need(sha(original[PREFIX+role+'.nbt'])==BASE_SHA[role],'Changed profession source');validate(source_models[role][2])
    files=original.copy();proof=[];added=[];recipes={}
    for biome in BIOMES:
        donor=b._nbt_parse(original[PREFIX+'armorer_'+biome+'.nbt'])[2];validate(donor,biome)
        recipe=diff(semantic(source_models['armorer'][2]),semantic(donor));recipes[biome]=recipe
        for role in ROLES:
            wanted=b._nbt_parse(original[PREFIX+role+'_'+biome+'.nbt'])[2]
            actual=apply(semantic(source_models[role][2]),recipe)
            if actual!=semantic(wanted):
                raise ValueError('Biome recipe is not role-independent: '+role+'_'+biome+' '+repr(diff(actual,semantic(wanted))[:4]))
            validate(encode_model(source_models[role][2],actual),biome)
            proof.append({'role':role,'biome':biome,'all_voxels_and_typed_NBT_equal':True,'reference_sha256':sha(original[PREFIX+role+'_'+biome+'.nbt'])})
        for role in RECOVER:
            path=PREFIX+role+'_'+biome+'.nbt';need(path not in original,'Existing template cannot be overwritten')
            compression,name,base=source_models[role];root=encode_model(base,apply(semantic(base),recipe));validate(root,biome)
            payload=b._nbt_encode(compression,name,root);need(b._nbt_parse(payload)==(compression,name,root),'NBT roundtrip mismatch')
            files[path]=payload;row={'path':path,'role':role,'biome':biome,'source_sha256':BASE_SHA[role],'sha256':sha(payload),'size':root['size'][1][1],'DataVersion':root['DataVersion'][1],'recipe_operations':len(recipe)};added.append(row)
            print('RECONSTRUCTED_CART',json.dumps(row),flush=True)
    need(len(proof)==121 and len(added)==22,'Incomplete recipe validation')
    doc=fp.fingerprint_document(files);encoded=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode()
    for name in FINGERPRINTS:files[name]=encoded
    need(all(files[n]==v for n,v in original.items() if n not in FINGERPRINTS),'Existing resource changed')
    raw=zip_bytes(files);need(raw==zip_bytes(files),'Packaging is not reproducible')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(z.testzip() is None and set(z.namelist())==set(files),'Invalid output ZIP')
        need(all(z.read(n)==v for n,v in files.items()),'Output changed bytes')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(raw)
    need(source.read_bytes()==data,'Input modified')
    return {'pass':True,'original_pack_sha256':PACK_SHA,'output_sha256':sha(raw),'added_templates':added,'existing_variants':proof,'recipes':recipes,'fingerprint':doc,'preserved_original_files':8005,'changed_original_files':list(FINGERPRINTS),'scope':'Reconstructed missing carts using biome transformations validated on every existing profession. Not author-restored originals; runtime placement/spawn validation separate.','production_accepted':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    try:r=build(a.input,a.output)
    except Exception as e:r={'pass':False,'error':repr(e),'production_accepted':False}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
    print('CART_BUILD',json.dumps({k:v for k,v in r.items() if k not in ('existing_variants','added_templates','recipes')},ensure_ascii=False),flush=True)
    return 0 if r['pass'] else 1
if __name__=='__main__':raise SystemExit(main())
