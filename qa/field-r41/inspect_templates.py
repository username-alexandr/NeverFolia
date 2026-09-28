#!/usr/bin/env python3
from pathlib import Path
import collections,hashlib,importlib.util,io,json,re,sys,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'r41-details';OUT.mkdir(exist_ok=True)
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def rid(s):return s if ':' in s else 'minecraft:'+s
def main():
 pack=next((ROOT/'inputs').rglob('NeverOverworld.zip'));jar=next((ROOT/'inputs').rglob('server.jar'))
 if hashlib.sha256(pack.read_bytes()).hexdigest()!='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be':raise ValueError('Wrong pack')
 with zipfile.ZipFile(jar) as z:raw=z.read(next(n for n in z.namelist() if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')))
 with zipfile.ZipFile(io.BytesIO(raw)) as z:files={n:z.read(n) for n in z.namelist() if n.startswith('data/')}
 with zipfile.ZipFile(pack) as z:files.update({n:z.read(n) for n in z.namelist() if n.startswith('data/')})
 b=load(ROOT/'scripts/build-never-overworld-external-structures-r19.py','r41nbt')
 missing=json.loads((ROOT/'prior/resource-before.json').read_text())['missing'];missing_ids={r['id'] for r in missing}
 names={n.split('/')[1]+':'+n.split('/structure/',1)[1][:-4]:n for n in files if '/structure/' in n and n.endswith('.nbt')}
 pools={n.split('/')[1]+':'+n.split('/worldgen/template_pool/',1)[1][:-5]:json.loads(v) for n,v in files.items() if '/worldgen/template_pool/' in n and n.endswith('.json')}
 def meta(id):
  root=b._nbt_parse(files[names[id]])[2];palette=root.get('palette',(9,(10,[])))[1][1];j=[];blocks=root.get('blocks',(9,(10,[])))[1][1]
  for block in blocks:
   nbt=block.get('nbt',(10,{}))[1]
   if nbt.get('id',(8,''))[1]=='minecraft:jigsaw':j.append({'pos':block['pos'][1][1],**{k:nbt[k][1] for k in ('name','target','pool','joint','final_state') if k in nbt},'state':palette[block['state'][1]]})
  return {'size':root['size'][1][1],'blocks':len(blocks),'entities':len(root.get('entities',(9,(10,[])))[1][1]),'jigsaws':j,'sha256':hashlib.sha256(files[names[id]]).hexdigest()}
 allmeta={};details=[]
 for row in missing:
  if row['id'].startswith('nova_structures:tavern/'):continue
  ns,name=row['id'].split(':',1);base=name.rsplit('/',1)[-1];parent=name.rsplit('/',1)[0]
  candidates=[id for id in names if id.rsplit('/',1)[-1]==base]
  if not candidates:
   if 'stray_fort_wall' in base:candidates=[id for id in names if 'stray_fort/' in id and ('wall' in id or 'frame' in id)]
   elif 'deko_mirror_center_' in base:candidates=[row['id'].replace('deko_mirror_center_','deko_center_')]
   elif 'deko_mirror_furnace_shelf' in base or 'deko_furnace_shelf' in base:candidates=[id for id in names if 'lone_citadel/room_content/' in id and ('furnace' in id or 'shelf' in id)]
   else:candidates=[id for id in names if id.startswith(ns+':'+parent+'/') and any(token in id.rsplit('/',1)[-1] for token in [base[:max(1,len(base)-3)],base.replace('_5','_4').replace('_6','_5').replace('_8','_7'),base.replace('_4_','_e_')])]
  candidates=[id for id in candidates if id in names][:20]
  entry={'id':row['id'],'roots':row['roots'],'origins':row['origins'],'candidates':candidates}
  details.append(entry);print('MISSING_DETAIL',json.dumps(entry),flush=True)
  for id in candidates:
   if id not in allmeta:allmeta[id]=meta(id);print('TEMPLATE',id,json.dumps(allmeta[id],separators=(',',':')),flush=True)
 usedpools=sorted({origin[5:] for r in missing for origin in r['origins'] if origin.startswith('pool:')})
 for id in usedpools:
  print('PARENT_POOL',id,json.dumps(pools[id],separators=(',',':')),flush=True)
 (OUT/'template-details.json').write_text(json.dumps({'missing':details,'templates':allmeta,'pools':{id:pools[id] for id in usedpools}},indent=2))
 for n,v in files.items():
  if n.endswith('.mcfunction') and '/nova_structures/' in n:print('FUNCTION',n,v.decode()[:7000],flush=True)
 # Find native function dispatch installation, not just filenames.
 hits=[]
 for p in (ROOT/'scripts').glob('*.py'):
  t=p.read_text()
  if any(x in t for x in ('spawn_zautilus_jockey','NeverOverworldExternalMobs','ghast_boss_summon_child','spawn_cave_spider_minion')):
   rows=t.splitlines(); excerpts=[]
   for i,s in enumerate(rows):
    if any(x in s for x in ('spawn_zautilus_jockey','ghast_boss_summon_child','spawn_cave_spider_minion','class Never')):excerpts.append({'line':i+1,'text':s})
   hits.append({'path':str(p.relative_to(ROOT)),'matches':excerpts[:60]})
 print('NATIVE_DISPATCH',json.dumps(hits),flush=True)
 # Exact missing loot/equipment/custom effect targets, retaining paths and context.
 loot={rid(n.split('/')[1]+':'+n.split('/loot_table/',1)[1][:-5]) for n in files if '/loot_table/' in n and n.endswith('.json')};bad=[]
 def walk(v,path,source):
  if isinstance(v,dict):
   for k,val in v.items():
    if k in ('loot_table','DeathLootTable','items_to_drop_when_ominous') and isinstance(val,str) and rid(val) not in loot:bad.append({'source':source,'path':path+[k],'id':rid(val)})
    if k=='loot_tables_to_eject' and isinstance(val,list):
     for e in val:
      if isinstance(e.get('data'),str) and rid(e['data']) not in loot:bad.append({'source':source,'path':path+[k],'id':rid(e['data'])})
    walk(val,path+[k],source)
  elif isinstance(v,list):
   for i,val in enumerate(v):walk(val,path+[i],source)
 for n,v in files.items():
  if n.endswith('.json'):
   try:walk(json.loads(v),[],n)
   except ValueError:pass
 print('MISSING_LOOT',json.dumps(bad),flush=True);(OUT/'missing-loot.json').write_text(json.dumps(bad,indent=2))
 (OUT/'loot-names.json').write_text(json.dumps(sorted(loot),indent=2))
 print('INTERESTING_LOOT',json.dumps(sorted(id for id in loot if any(x in id for x in ('equipment/lone_citadel','equipment/shrine','projectiles_port','projectiles_nether_port','toxic','boss_slime')))),flush=True)
 cart=load(ROOT/'qa/field-r394/build_candidate.py','r41cart')
 try:r=cart.build(pack,OUT/'NeverOverworld-with-carts.zip');print('CART_RESULT',r['pass'],len(r['added_templates']),flush=True)
 except Exception as e:r={'pass':False,'error':repr(e)};print('CART_FAILED',repr(e),flush=True)
 (OUT/'carts.json').write_text(json.dumps(r,indent=2))
if __name__=='__main__':main()
