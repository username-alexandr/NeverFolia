#!/usr/bin/env python3
"""Read-only donor comparison. 26.3 resources are NOT installed on 26.2."""
from pathlib import Path
import copy,hashlib,io,json,urllib.request,zipfile,difflib
OUT=Path('donor-review');OUT.mkdir(exist_ok=False)
def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'NeverFolia-compatibility-review/1.0'})
 with urllib.request.urlopen(req,timeout=90) as r:return r.read()
def keep(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
root=Path('inventory')
source=(root/'NeverOverworldFlood.java').read_text();lines=source.splitlines();ix=set()
for i,line in enumerate(lines):
 if any(t in line for t in ('isDrownedFrozenOverlay','repairDrowned','reweather','FROZEN','frozen','Frozen','ICE')):ix.update(range(max(0,i-12),min(len(lines),i+30)))
print('FROZEN_CONTEXT','\n'.join(f'{i+1}: {lines[i]}' for i in sorted(ix)),flush=True)
version=json.loads(fetch('https://api.modrinth.com/v2/version/A6LcZGsV'))
assert version['project_id']=='tpehi7ww' and version['version_number']=='6.0.1+mod' and '26.3' in version['game_versions']
f=next(v for v in version['files'] if v['primary']);assert f['url'].startswith('https://cdn.modrinth.com/')
raw=fetch(f['url']);assert hashlib.sha512(raw).hexdigest()==f['hashes']['sha512']
keep(OUT/'donor-version.json',version)
gaps=json.loads((root/'resource-gaps.json').read_text());report={'donor':version['id'],'target_game':'26.2','donor_game':'26.3','installed':False,'exact_templates':[],'pool_changes':{},'suggested_locations':[],'candidate_paths':{}}
with zipfile.ZipFile(io.BytesIO(raw)) as donor,zipfile.ZipFile('baseline/world/datapacks/NeverOverworld.zip') as base:
 names=set(donor.namelist());bn=set(base.namelist())
 def paths(node):
  if isinstance(node,dict):
   if isinstance(node.get('location'),str):yield node['location']
   for v in node.values():yield from paths(v)
  elif isinstance(node,list):
   for v in node:yield from paths(v)
 for row in gaps['missing']:
  ns,p=row['id'].split(':',1);n=f'data/{ns}/structure/{p}.nbt'
  if n in names:
   report['exact_templates'].append(n);dest=OUT/'exact-templates'/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(donor.read(n))
  for origin in row['origins']:
   if not origin.startswith('pool:'):continue
   ons,op=origin[5:].split(':',1);pool=f'data/{ons}/worldgen/template_pool/{op}.json'
   if pool in names and pool in bn and pool not in report['pool_changes']:
    old=json.loads(base.read(pool));new=json.loads(donor.read(pool));oldp=list(paths(old));newp=list(paths(new))
    report['pool_changes'][pool]={'before_locations':oldp,'after_locations':newp,'diff':'\n'.join(difflib.unified_diff(json.dumps(old,indent=2).splitlines(),json.dumps(new,indent=2).splitlines()))}
   if pool in names:
    locs=list(paths(json.loads(donor.read(pool))));current=list(paths(json.loads(base.read(pool)))) if pool in bn else []
    added=[p for p in locs if p not in current]
    for p2 in added:
     ns2,s2=(p2.split(':',1) if ':' in p2 else ('minecraft',p2));n2=f'data/{ns2}/structure/{s2}.nbt'
     report['suggested_locations'].append({'missing':row['id'],'pool':origin,'author_added':p2,'already_in_26_2_pack':n2 in bn,'only_donor':n2 in names and n2 not in bn})
  group=p.rsplit('/',1)[0]+'/'
  candidates=sorted(n for n in bn if n.startswith(f'data/{ns}/structure/{group}') and n.endswith('.nbt'))
  report['candidate_paths'][row['id']]=candidates
 keep(OUT/'donor-review.json',report)
 print('EXACT_RECOVERABLE',len(report['exact_templates']),json.dumps(report['exact_templates']),flush=True)
 for p,d in report['pool_changes'].items():
  removed=set(d['before_locations'])-set(d['after_locations']);added=set(d['after_locations'])-set(d['before_locations'])
  print('AUTHOR_POOL_DIFF',p,'removed=',json.dumps(sorted(removed)),'added=',json.dumps(sorted(added)),flush=True)
 for row in report['suggested_locations']:print('AUTHOR_TARGET',json.dumps(row),flush=True)
