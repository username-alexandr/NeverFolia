#!/usr/bin/env python3
"""Recover professions from complete biome models, not assumed 100-block boxes.
Derive profession deltas from existing generic carts, apply them to the actual
biome armorer, and verify the procedure against every existing role/biome pair.
The exact sparse block set of each biome is preserved; absent cells are NOT air.
"""
from pathlib import Path
import copy,gzip,hashlib,importlib.util,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
SOURCE='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
BIOMES=('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp')
ROLES=('armorer','butcher','farmer','fisher','fletcher','grindstone','leather_worker','librarian','loom','smithing_table','stonecutter')
RECOVER=('cartographer','cleric');PREFIX='data/nova_structures/structure/tavern/tavern_event_trader_car_'
FP=('neveroverworld-worldgen-fingerprint.json','data/neverfolia/neveroverworld/worldgen_fingerprint.json')
def need(ok,msg):
 if not ok:raise ValueError(msg)
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def sha(b):return hashlib.sha256(b).hexdigest()
def model(root):
 need('palettes' not in root,'Multiple palettes')
 palette=root['palette'][1][1];out={k:copy.deepcopy(v) for k,v in root.items() if k not in ('palette','blocks','DataVersion')};blocks={}
 for b in root['blocks'][1][1]:
  pos=tuple(b['pos'][1][1]);need(pos not in blocks,'Duplicate coordinate')
  blocks[pos]={k:copy.deepcopy(v) for k,v in b.items() if k not in ('pos','state')};blocks[pos]['state']=copy.deepcopy(palette[b['state'][1]])
 out['blocks']=blocks;return out
def patch(a,b,target,path=()):
 if a==b:return copy.deepcopy(target)
 if isinstance(a,dict) and isinstance(b,dict):
  need(isinstance(target,dict),'Type mismatch '+repr(path));out=copy.deepcopy(target)
  for key in a.keys()-b.keys():need(key in out and out[key]==a[key],'Unexpected removed field '+repr(path+(key,)));del out[key]
  for key in b.keys()-a.keys():need(key not in out,'Unexpected existing field');out[key]=copy.deepcopy(b[key])
  for key in a.keys()&b.keys():
   if a[key]!=b[key]:need(key in out,'Missing field '+repr(path+(key,)));out[key]=patch(a[key],b[key],out[key],path+(key,))
  return out
 if isinstance(a,tuple) and isinstance(b,tuple) and len(a)==len(b):
  need(isinstance(target,tuple) and len(target)==len(a),'Tuple mismatch');return tuple(patch(x,y,z,path+(i,)) for i,(x,y,z) in enumerate(zip(a,b,target)))
 need(target==a,'Source mismatch '+repr(path)+' '+repr((a,b,target)))
 return copy.deepcopy(b)
def encode_model(base,desired):
 root={k:copy.deepcopy(v) for k,v in desired.items() if k!='blocks'};root['DataVersion']=base['DataVersion'];palette=[];blocks=[]
 for pos,record in sorted(desired['blocks'].items(),key=lambda v:(v[0][1],v[0][2],v[0][0])):
  r=copy.deepcopy(record);state=r.pop('state')
  if state not in palette:palette.append(state)
  r['pos']=(9,(3,list(pos)));r['state']=(3,palette.index(state));blocks.append(r)
 root['palette']=(9,(10,palette));root['blocks']=(9,(10,blocks));need(model(root)==desired,'Rebuild changed semantics');return root
def validate(root,biome):
 need(root['size']==(9,(3,[5,4,5])),'Wrong cart bounds')
 need(root.get('entities',(9,(10,[])))[1][1]==[],'Direct entities changed')
 m=model(root);need(all(0<=x<5 and 0<=y<4 and 0<=z<5 for x,y,z in m['blocks']),'Out of bounds')
 js={p:r['nbt'][1] for p,r in m['blocks'].items() if r.get('nbt',(10,{}))[1].get('id')==(8,'minecraft:jigsaw')}
 need(set(js)=={(4,0,0),(2,1,1)},'Connector positions changed')
 need(js[(4,0,0)]['name']==(8,'nova_structures:tavern_trader_car_'+biome),'Parent connector changed')
 need(js[(2,1,1)]['target']==(8,'nova_structures:tavern_villager_'+biome),'Villager connector changed')
 need(js[(2,1,1)]['pool']==(8,'nova_structures:tavern_trader'),'Villager pool changed')
def build(source,output):
 source,output=Path(source),Path(output);need(not output.exists(),'Output exists');need(sha(source.read_bytes())==SOURCE,'Wrong original')
 b=load(ROOT/'scripts/build-never-overworld-external-structures-r19.py','r41cartnbt');fp=load(ROOT/'scripts/fingerprint-never-overworld-pack.py','r41cartfp')
 with zipfile.ZipFile(source) as z:need(z.testzip() is None,'Bad ZIP');files={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
 original=files.copy();roots={role:b._nbt_parse(files[PREFIX+role+'.nbt'])[2] for role in ROLES+RECOVER};base=model(roots['armorer']);proof=[];outputs=[];differences=[]
 for biome in BIOMES:
  exemplar=b._nbt_parse(files[PREFIX+'armorer_'+biome+'.nbt'])[2];validate(exemplar,biome);bm=model(exemplar)
  print('CART_BIOME',biome,'explicit_blocks',len(bm['blocks']),flush=True)
  for role in ROLES+RECOVER:
   desired=patch(base,model(roots[role]),bm)
   result=encode_model(roots[role],desired);validate(result,biome)
   if role in ROLES:
    expected=b._nbt_parse(files[PREFIX+role+'_'+biome+'.nbt'])[2];expected_model=model(expected)
    if desired!=expected_model:
     positions=sorted({*desired['blocks'],*expected_model['blocks']});diff=[{'pos':p,'generated':desired['blocks'].get(p),'reference':expected_model['blocks'].get(p)} for p in positions if desired['blocks'].get(p)!=expected_model['blocks'].get(p)]
     differences.append({'biome':biome,'role':role,'differences':diff});print('CART_NONUNIFORM',json.dumps(differences[-1]),flush=True)
    proof.append({'role':role,'biome':biome,'equal':desired==expected_model,'explicit_blocks':len(expected_model['blocks'])})
   else:
    path=PREFIX+role+'_'+biome+'.nbt';need(path not in files,'Would overwrite')
    raw=b._nbt_encode('raw','',result);need(b._nbt_parse(raw)[2]==result,'NBT roundtrip')
    payload=bytearray(gzip.compress(raw,compresslevel=9,mtime=0));payload[9]=255;payload=bytes(payload)
    need(b._nbt_parse(payload)[2]==result,'Compressed NBT roundtrip');files[path]=payload
    outputs.append({'path':path,'sha256':sha(payload),'role':role,'biome':biome,'base_biome':PREFIX+'armorer_'+biome+'.nbt','profession_source':PREFIX+role+'.nbt','explicit_blocks':len(desired['blocks'])})
 report={'validated_existing_variants':proof,'added_templates':outputs,'differences':differences,'pass':not differences,'method':'Exact full-biome model with base-profession delta; 121 independent reference models checked; sparse coordinates preserved'}
 ev=ROOT/'r41-final-evidence';ev.mkdir(exist_ok=True);(ev/'cart-reconstruction-attempt.json').write_text(json.dumps(report,indent=2))
 need(not differences,'Profession recipe differs from actual reference; refusing incomplete reconstruction')
 need(len(proof)==121 and len(outputs)==22,'Wrong verification coverage')
 doc=fp.fingerprint_document(files)
 for n in FP:files[n]=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode()
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for n,raw in sorted(files.items()):
   info=zipfile.ZipInfo(n,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,raw,compresslevel=9)
 with zipfile.ZipFile(output) as z:need(z.testzip() is None and all(z.read(n)==raw for n,raw in files.items()),'Output verification')
 need(all(files[n]==v for n,v in original.items() if n not in FP),'Changed original resource');report['output_sha256']=sha(output.read_bytes());return report
