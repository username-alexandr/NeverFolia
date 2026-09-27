#!/usr/bin/env python3
"""Narrow 26.2 JSON corrections backed by author's 6.0.1 reference changes.
No 26.3 entities, enchantments, loot or predicates are copied into the output.
"""
from pathlib import Path
import copy,hashlib,importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'resource-output';OUT.mkdir(exist_ok=False)
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def check(ok,msg):
 if not ok:raise ValueError(msg)
def save(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
fp=load('fingerprint40',ROOT/'scripts/fingerprint-never-overworld-pack.py');audit=load('audit40',ROOT/'scripts/audit-neveroverworld-r39-resources.py');nbt=load('nbt40',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
pack=ROOT/'baseline/world/datapacks/NeverOverworld.zip';jar=ROOT/'baseline/server.jar'
check(hashlib.sha256(pack.read_bytes()).hexdigest()=='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be','Wrong exact input pack')
entries=fp.read_entries(pack);before=dict(entries);changes=[];count={}
MAP={
'nova_structures:badlands_miner_outpost/badlands_miner_outpost_path_t_curve_big':'nova_structures:badlands_miner_outpost/badlands_miner_outpost_path_t_curve_large',
'nova_structures:catacomb/hallway/catacomb_path_2_1':'nova_structures:catacomb/hallway/catacomb_path_snake_2_1',
'nova_structures:catacomb/hallway/catacomb_path_2_2':'nova_structures:catacomb/hallway/catacomb_path_snake_2_2',
'nova_structures:toxic_lair/spawner/spawner_boss_slime':'nova_structures:toxic_lair/spawner/spawner_slime_miniboss'}
donor=json.loads((ROOT/'donor/donor-review/donor-review.json').read_text())
for old,new in MAP.items():
 ns,p=new.split(':',1);check(f'data/{ns}/structure/{p}.nbt' in entries,'Absent correction target')
 supported=[r for r in donor['suggested_locations'] if r['missing']==old and r['author_added']==new and r['already_in_26_2_pack']]
 check(bool(supported),'No author evidence for '+old)
def edit(node,path,source):
 changed=False
 if isinstance(node,dict):
  if node.get('location') in MAP:
   old=node['location'];node['location']=MAP[old];count[old]=count.get(old,0)+1;changes.append({'file':source,'field':path+'/location','old':old,'new':node['location']});changed=True
  if node.get('element_type') in ('minecraft:single_pool_element','minecraft:legacy_single_pool_element') and node.get('location')=='minecraft/empty':
   check(source in ('data/minecraft/worldgen/template_pool/illager_mansion/illager_mansion_room.json','data/minecraft/worldgen/template_pool/illager_mansion/illager_mansion_room_basement.json'),'Unexpected empty entry')
   previous=copy.deepcopy(node);node.clear();node['element_type']='minecraft:empty_pool_element';changes.append({'file':source,'field':path,'old':previous,'new':dict(node),'reason':'Explicit intentional empty choice, not a missing room replacement'});changed=True
  for k,v in list(node.items()):changed=edit(v,path+'/'+k,source) or changed
 elif isinstance(node,list):
  for i,v in enumerate(node):changed=edit(v,path+'/'+str(i),source) or changed
 return changed
for name,raw in before.items():
 if '/worldgen/template_pool/' in name and name.endswith('.json'):
  data=json.loads(raw)
  if edit(data,'',name):entries[name]=(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode()
check(set(count)==set(MAP),'Not all expected source references found')
# Keep all payloads and weights except the explicit locations/intentional empty elements.
for name,raw in before.items():
 if name.endswith('.nbt') or '/enchantment/' in name or '/function/' in name or '/loot_table/' in name:check(entries[name]==raw,'Gameplay or binary template unexpectedly changed')
for n in fp.FINGERPRINT_ENTRIES:entries.pop(n,None)
fingerprint=fp.fingerprint_document(entries);encoded=(json.dumps(fingerprint,indent=2,ensure_ascii=False)+'\n').encode()
for n in fp.FINGERPRINT_ENTRIES:entries[n]=encoded
result=OUT/'NeverOverworld-R40-references.zip'
with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for name in sorted(entries):
  info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,entries[name])
fp.verify(result);old=audit.audit_files(jar,pack);new=audit.audit_files(jar,result)
oldmissing={r['id'] for r in old['missing']};newmissing={r['id'] for r in new['missing']}
check(not(newmissing-oldmissing),'Unexpected new missing reference')
check(oldmissing-newmissing==set(MAP)|{'minecraft:minecraft/empty'},'Unexpected resolved target set')
save(OUT/'changes.json',{'changes':changes,'counts':count,'before':old['counts'],'after':new['counts'],'resolved':sorted(oldmissing-newmissing),'sha256':hashlib.sha256(result.read_bytes()).hexdigest(),'runtime_tested':False,'production_accepted':False});save(OUT/'remaining-resources.json',new)
print('R40_REFERENCE_FIX',json.dumps({'fields':len(changes),'resolved':sorted(oldmissing-newmissing),'before':old['counts'],'after':new['counts']}),flush=True)
# Analyse donor templates before considering any backport. No donor NBT is installed.
analysis=[]
for path in sorted((ROOT/'donor/donor-review/exact-templates').rglob('*.nbt')):
 compression,rootname,root=nbt._nbt_parse(path.read_bytes())
 def plain(tag):
  t,v=tag
  if t==10:return {k:plain(w) for k,w in v.items()}
  if t==9:return [plain((v[0],w)) for w in v[1]]
  if t==7:return {'bytes':len(v)}
  return v
 data=plain((10,root));row={'path':path.relative_to(ROOT/'donor/donor-review/exact-templates').as_posix(),'data_version':data.get('DataVersion'),'size':data.get('size'),'palette':data.get('palette'),'entities':data.get('entities'),'block_entities':[b for b in data.get('blocks',[]) if b.get('nbt')]}
 analysis.append(row)
 print('DONOR_TEMPLATE',row['path'],'size=',row['size'],'entities=',json.dumps(row['entities'],ensure_ascii=False)[:2000],flush=True)
save(OUT/'donor-nbt-analysis-NOT-INSTALLED.json',analysis)
for gap,candidates in donor['candidate_paths'].items():
 if 'stray_fort_wall' in gap or 'book/pillager' in gap or 'lone_citadel/room_content/deko_' in gap:
  terms=gap.split('/')[-1].split('_');ranked=sorted(candidates,key=lambda p:(-sum(t in Path(p).stem.split('_') for t in terms),len(p),p))[:4]
  print('UNRESOLVED_CANDIDATES',gap,json.dumps(ranked),flush=True)
