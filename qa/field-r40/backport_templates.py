#!/usr/bin/env python3
"""Backport missing geometry only; retain target-version runtime, loot and entities.
Input is the previously audited reference pack. Runtime acceptance is separate.
"""
from pathlib import Path
from collections import Counter
import copy,hashlib,importlib.util,io,json,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'template-output';OUT.mkdir(exist_ok=False)
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def check(ok,msg):
 if not ok:raise ValueError(msg)
def save(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
def plain(tag):
 t,v=tag
 if t==10:return {k:plain(w) for k,w in v.items()}
 if t==9:return [plain((v[0],w)) for w in v[1]]
 if t==7:return {'bytes':len(v)}
 return v
fp=load('fp40',ROOT/'scripts/fingerprint-never-overworld-pack.py');audit=load('a40',ROOT/'scripts/audit-neveroverworld-r39-resources.py');nbt=load('n40',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
input_pack=ROOT/'refs/resource-output/NeverOverworld-R40-references.zip';prior=json.loads((ROOT/'refs/resource-output/changes.json').read_text());check(hashlib.sha256(input_pack.read_bytes()).hexdigest()==prior['sha256'],'Reference pack mismatch')
entries=fp.read_entries(input_pack);old=dict(entries);expected=[];be_types=Counter();all_keys={};added=[]
for p in sorted((ROOT/'donor/donor-review/exact-templates').rglob('*.nbt')):
 name=p.relative_to(ROOT/'donor/donor-review/exact-templates').as_posix();check(name not in entries,'Not a missing template '+name)
 raw=p.read_bytes();compression,root_name,root=nbt._nbt_parse(raw);data=plain((10,root));check(not data.get('entities'),'Donor entity runtime requires separate review')
 check(isinstance(data.get('palette'),list) and 'palettes' not in data,'Unexpected multiple palette template')
 for block in data.get('blocks',[]):
  payload=block.get('nbt')
  if payload:
   be_id=payload.get('id','<jigsaw-without-id>');be_types[be_id]+=1;all_keys.setdefault(be_id,set()).update(payload)
   # No entity spawner or command block can enter unnoticed.
   check(be_id in ('minecraft:jigsaw','<jigsaw-without-id>','minecraft:barrel','minecraft:chest','minecraft:trapped_chest','minecraft:sign','minecraft:hanging_sign','minecraft:brewing_stand','minecraft:furnace','minecraft:blast_furnace','minecraft:smoker'),'Unreviewed donor block entity '+be_id)
   check(not any(k in payload for k in ('SpawnData','spawn_data','SpawnPotentials','spawn_potentials','Items','items','Command','command')),'Donor gameplay payload must be reviewed separately: '+name)
   if 'LootTable' in payload:
    ns,loc=payload['LootTable'].split(':',1);check(f'data/{ns}/loot_table/{loc}.json' in entries or ns=='minecraft','Missing donor loot '+payload['LootTable'])
 expected.append({'id':name[len('data/'):].split('/structure/',1)[0]+':'+name.split('/structure/',1)[1][:-4],'size':data['size'],'data_version':data.get('DataVersion'),'palette':data['palette'],'block_count':len(data.get('blocks',[])),'entity_count':0,'jigsaws':[b for b in data['blocks'] if data['palette'][b['state']]['Name']=='minecraft:jigsaw']})
 entries[name]=raw;added.append(name)
check(len(added)==27,'Expected exact 27 author files')
for n,raw in old.items():
 if n not in fp.FINGERPRINT_ENTRIES:check(entries[n]==raw,'Changed existing resource '+n)
for n in fp.FINGERPRINT_ENTRIES:entries.pop(n,None)
doc=fp.fingerprint_document(entries);encoded=(json.dumps(doc,indent=2,ensure_ascii=False)+'\n').encode()
for n in fp.FINGERPRINT_ENTRIES:entries[n]=encoded
pack=OUT/'NeverOverworld-R40-templates.zip'
with zipfile.ZipFile(pack,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n in sorted(entries):
  info=zipfile.ZipInfo(n,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,entries[n])
fp.verify(pack);report=audit.audit_files(ROOT/'baseline/server.jar',pack);save(OUT/'resources.json',report)
save(OUT/'expected-templates.json',expected)
save(OUT/'build.json',{'added':added,'sha256':hashlib.sha256(pack.read_bytes()).hexdigest(),'counts':report['counts'],'errors':report['errors'],'runtime_tested':False,'production_accepted':False,'donor_block_entity_types':dict(be_types),'donor_block_entity_keys':{k:sorted(v) for k,v in all_keys.items()}})
print('TEMPLATE_BACKPORT',json.dumps({'added':len(added),'counts':report['counts'],'block_entities':dict(be_types),'keys':{k:sorted(v) for k,v in all_keys.items()}}),flush=True)
for row in expected:
 if '/tavern_' in row['id']:print('CART_JIGSAW',row['id'],json.dumps(row['jigsaws'],ensure_ascii=False),flush=True)
