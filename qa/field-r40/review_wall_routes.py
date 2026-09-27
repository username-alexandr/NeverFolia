#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import hashlib,importlib.util,io,json,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'route-review';OUT.mkdir(exist_ok=False)
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
nbt=load('nbt_routes',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
def plain(t):
 k,v=t
 if k==10:return {n:plain(w) for n,w in v.items()}
 if k==9:return [plain((v[0],w)) for w in v[1]]
 if k==7:return {'byte_array':list(v)}
 return v
def decode(raw):return plain((10,nbt._nbt_parse(raw)[2]))
def blocks(d):
 return {tuple(b['pos']):{'state':d['palette'][b['state']],'nbt':b.get('nbt')} for b in d['blocks']}
def fetch(url):
 r=urllib.request.Request(url,headers={'User-Agent':'NeverFolia-compatibility-research/1.0'})
 with urllib.request.urlopen(r,timeout=90) as s:return s.read()
version=json.loads(Path('donor/donor-review/donor-version.json').read_text());f=next(x for x in version['files'] if x['primary']);raw=fetch(f['url']);assert hashlib.sha512(raw).hexdigest()==f['hashes']['sha512']
report=json.loads(Path('refs/resource-output/remaining-resources.json').read_text());badpools={o[5:] for row in report['missing'] if 'stray_fort_wall' in row['id'] for o in row['origins'] if o.startswith('pool:')}
print('OBSOLETE_WALL_POOLS',sorted(badpools),flush=True);records=[]
with zipfile.ZipFile(io.BytesIO(raw)) as donor,zipfile.ZipFile('baseline/world/datapacks/NeverOverworld.zip') as base:
 donor_names=set(donor.namelist());base_names=set(base.namelist())
 for n in base_names:
  if not n.startswith('data/nova_structures/structure/stray_fort/') or not n.endswith('.nbt'):continue
  old=decode(base.read(n));a=blocks(old);bad={p:v for p,v in a.items() if v['nbt'] and v['nbt'].get('pool') in badpools}
  if not bad:continue
  new=decode(donor.read(n)) if n in donor_names else None;b=blocks(new) if new else {}
  row={'path':n,'donor_exists':new is not None,'size':old['size'],'donor_size':new['size'] if new else None,'connectors':[]}
  for p,v in bad.items():row['connectors'].append({'pos':p,'before':v,'after':b.get(p)})
  non_jig=lambda m:{p:v for p,v in m.items() if v['state']['Name']!='minecraft:jigsaw'}
  row['non_jigsaw_geometry_equal']=new is not None and non_jig(a)==non_jig(b) and old.get('entities',[])==new.get('entities',[])
  records.append(row);print('WALL_ROUTE',json.dumps(row,ensure_ascii=False),flush=True)
 for n in sorted(donor_names):
  if '/worldgen/template_pool/' in n and 'stray_fort' in n and n.endswith('.json'):
   print('AUTHOR_WALL_POOL',n,'already_present=',n in base_names,flush=True)
 # The book identifiers may refer to the wrong resource family; inspect the actual input.
 for n in sorted(base_names):
  if n.startswith('data/structory_towers/') and n.endswith('.json'):
   text=base.read(n).decode()
   if 'book/pillager_' in text:print('PILLAGER_REFERENCE',n,text,flush=True)
 source=nbt.SOURCES['towers'];original=fetch(source['url']);assert hashlib.sha256(original).hexdigest()==source['sha256']
 with zipfile.ZipFile(io.BytesIO(original)) as z:
  print('ORIGINAL_BOOK_PATHS',[n for n in z.namelist() if 'pillager' in n or '/book/' in n],flush=True)
 (OUT/'routes.json').write_text(json.dumps(records,indent=2,ensure_ascii=False))
# Summarize all ice clusters from the retained observation, without classifying structure absence.
ice=json.loads(Path('ice/ice-review/ice-details.json').read_text());groups={}
for row in ice['ice']:
 x,y,z=row['pos'];key=f'{x//16},{z//16}:{row["state"]["Name"]}';g=groups.setdefault(key,{'count':0,'ys':[],'examples':[]});g['count']+=1;g['ys'].append(y)
 if len(g['examples'])<5:g['examples'].append(row)
for k,g in groups.items():print('ICE_GROUP',k,json.dumps({'count':g['count'],'min_y':min(g['ys']),'max_y':max(g['ys']),'examples':g['examples']}),flush=True)
