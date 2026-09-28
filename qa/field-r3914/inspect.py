#!/usr/bin/env python3
"""Read-only inventory of exact R3913 and its original D&T source.
No world, datapack, or existing source is modified. No inferred reference fixes.
"""
from pathlib import Path
import collections, difflib, hashlib, importlib.util, io, json, sys, urllib.request, zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts'; OUT.mkdir(exist_ok=True)
BASE='9571073a77086b04ce54594fe2b91737fdf9daf4019d4ce585016f77c03912f6'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
SOURCE='4096cd6372e0f244efa0e85c4d884bd85afe665a84a050280acd483b3222b4f9'
URL='https://cdn.modrinth.com/data/tpehi7ww/versions/CS77UwHE/Dungeons%20and%20Taverns%20v5.3.2.zip'
def need(ok,msg):
    if not ok: raise ValueError(msg)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def save(name,value): (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); sys.modules[name]=m; spec.loader.exec_module(m); return m
def find(name,expected):
    hits=list((ROOT/'inputs').rglob(name)); need(len(hits)==1,'Missing/ambiguous '+name)
    need(digest(hits[0].read_bytes())==expected,'Wrong '+name); return hits[0]
def plain(value):
    t,v=value
    if t==10: return {k:plain(x) for k,x in v.items()}
    if t==9: return [plain((v[0],x)) for x in v[1]]
    if t==7: return list(v)
    return v
jar=find('server.jar',BASE); packpath=find('NeverOverworld.zip',PACK)
audit=module('r3914_audit',ROOT/'scripts/audit-neveroverworld-r39-resources.py')
builder=module('r3914_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
report=audit.audit_files(jar,packpath);save('resource-before.json',report)
need(not report['errors'],'Resource parser errors must be fixed before inferring references')
print('RESOURCE_COUNTS',json.dumps(report['counts']),flush=True)
req=urllib.request.Request(URL,headers={'User-Agent':'NeverFolia/R3914-resource-inspection'})
with urllib.request.urlopen(req,timeout=60) as response: raw=response.read(128*1024*1024+1)
need(len(raw)<=128*1024*1024 and digest(raw)==SOURCE,'Wrong original D&T source')
source=builder.flatten_zip(raw)
with zipfile.ZipFile(packpath) as archive:
    need(len(archive.namelist())==len(set(archive.namelist())),'Duplicate ZIP entries')
    files={n:archive.read(n) for n in archive.namelist() if not n.endswith('/')}
paths=sorted(n for n in files if n.startswith('data/') and '/structure/' in n and n.endswith('.nbt'))
cache={}
def describe(path):
    if path not in cache:
        _,_,tree=builder._nbt_parse(files[path]); d=plain((10,tree))
        palette=d.get('palette',[])
        if not palette and d.get('palettes'): palette=d['palettes'][0]
        connectors=[]
        for b in d.get('blocks',[]):
            be=b.get('nbt',{})
            if be.get('id')=='minecraft:jigsaw' or 'pool' in be:
                state=palette[b['state']] if b.get('state',-1) in range(len(palette)) else {}
                connectors.append({'pos':b.get('pos'),'orientation':state.get('Properties',{}).get('orientation'),
                    **{k:be[k] for k in ('name','target','pool','joint','final_state') if k in be}})
        cache[path]={'path':path,'sha256':digest(files[path]),'size':d.get('size'),
                     'connectors':connectors,'entities':len(d.get('entities',[]))}
    return cache[path]
rows=[]
for missing in report['missing']:
    ns,name=missing['id'].split(':',1); leaf=name.rsplit('/',1)[-1]
    wanted=f'data/{ns}/structure/{name}.nbt'
    same_leaf=[n for n in paths if n.rsplit('/',1)[-1]==leaf+'.nbt']
    pool_paths=[f'data/{x.split(":",2)[1]}/worldgen/template_pool/{x.split(":",2)[2]}.json' for x in missing['origins'] if x.startswith('pool:')]
    prefix=name.rsplit('/',1)[0]+'/' if '/' in name else ''
    local=[n for n in paths if n.startswith(f'data/{ns}/structure/{prefix}')]
    candidates=same_leaf+difflib.get_close_matches(wanted,local or paths,n=5,cutoff=0.55)
    candidates=list(dict.fromkeys(candidates))[:5]
    row={**missing,'exact_in_source':wanted in source,'same_leaf_in_source':sorted(n for n in source if n.endswith('/'+leaf+'.nbt')),
         'candidates':[describe(n) for n in candidates]}
    rows.append(row)
    print('MISSING',json.dumps({'id':missing['id'],'origins':missing['origins'],'exact_in_source':row['exact_in_source'],
        'same_leaf_in_source':row['same_leaf_in_source'],'candidates':[{'path':v['path'],'size':v['size'],'ports':len(v['connectors'])} for v in row['candidates']]}),flush=True)
save('missing-candidates.json',rows)
functions={n[5:].split('/function/',1)[0]+':'+n.split('/function/',1)[1][:-11] for n in files if '/function/' in n and n.endswith('.mcfunction')}
# len('.mcfunction') is eleven; typed run_function references are reported verbatim.
function_refs=[]
def walk(value,where):
    if isinstance(value,dict):
        if value.get('type') in ('minecraft:run_function','run_function'):
            target=value.get('function'); function_refs.append({'source':where,'function':target,'present':isinstance(target,str) and target in functions})
        for v in value.values():walk(v,where)
    elif isinstance(value,list):
        for v in value:walk(v,where)
for n,raw in files.items():
    if n.startswith('data/') and n.endswith('.json'):walk(json.loads(raw),n)
save('runtime-function-references.json',function_refs)
for row in function_refs:
    if not row['present']:print('MISSING_FUNCTION',json.dumps(row),flush=True)
# Retain provenance, small actual source snippets and structural descriptions, not the full upstream archive.
source_meta={'url':URL,'sha256':SOURCE,'effective_source_files':len(source),'base_sha256':BASE,'pack_sha256':PACK}
save('source-provenance.json',source_meta)
print('INVENTORY_COMPLETE',json.dumps({'missing_resources':len(rows),'function_refs':len(function_refs),'missing_functions':sum(not r['present'] for r in function_refs)}),flush=True)
