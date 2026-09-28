#!/usr/bin/env python3
"""Inspect the exact R3913 kit; produce evidence, not resource acceptance.
No world changes, no replacement of rooms and no update of an installed server.
"""
from pathlib import Path
import collections, difflib, hashlib, importlib.util, io, json, os, sys, urllib.request, zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'resource-evidence'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def sha(b):return hashlib.sha256(b).hexdigest()
def one(paths,label):
    values=list(paths)
    if len(values)!=1:raise ValueError(label+': '+repr(values))
    return values[0]
def main():
    OUT.mkdir(exist_ok=False)
    jar=one((ROOT/'inputs').rglob('server.jar'),'server')
    pack=one((ROOT/'inputs').rglob('NeverOverworld.zip'),'pack')
    nether=one((ROOT/'inputs').rglob('NeverNether.zip'),'nether')
    if sha(pack.read_bytes())!=PACK or sha(nether.read_bytes())!=NETHER:raise ValueError('Changed pinned packs')
    build=one((ROOT/'inputs').rglob('r3913-build.json'),'R3913 build')
    provenance=json.loads(build.read_text())
    if provenance.get('candidate_core_sha256')!=sha(jar.read_bytes()):raise ValueError('Wrong actual R3913 core')
    audit=load('resource_audit',ROOT/'scripts/audit-neveroverworld-r39-resources.py')
    r=audit.audit_files(jar,pack)
    (OUT/'before.json').write_text(json.dumps(r,indent=2)+'\n')
    print('ACTUAL_RESOURCE_COUNTS '+json.dumps(r['counts']),flush=True)
    print('AUDIT_ERRORS '+json.dumps(r['errors']),flush=True)
    own=load('own_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    with zipfile.ZipFile(pack) as z:current={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
    index={n[len('data/'):].split('/structure/',1)[0]+':'+n.split('/structure/',1)[1][:-4]:n for n in current if n.startswith('data/') and '/structure/' in n and n.endswith('.nbt')}
    upstream={}
    for name in ('dat','witch'):
        source=own.SOURCES[name]
        if not source['url'].startswith('https://cdn.modrinth.com/data/'):raise ValueError('Unapproved fixed source')
        with urllib.request.urlopen(source['url'],timeout=90) as response:raw=response.read(80_000_001)
        if len(raw)>80_000_000 or sha(raw)!=source['sha256']:raise ValueError('Wrong pinned original '+name)
        (OUT/('original-'+name+'.zip')).write_bytes(raw)
        upstream[name]=own.flatten_zip(raw)
    missing=[]
    for entry in r['missing']:
        identifier=entry['id'];row=dict(entry)
        if entry['kind']=='template':
            namespace,leaf=identifier.split(':',1);path='data/'+namespace+'/structure/'+leaf+'.nbt'
            exact=[k for k,v in upstream.items() if path in v]
            near=difflib.get_close_matches(identifier,sorted(index),n=3,cutoff=0.70)
            row.update(exact_upstream=exact,nearby_templates=near)
        missing.append(row)
        print('MISSING '+json.dumps({k:v for k,v in row.items() if k in ('kind','id','origins','exact_upstream','nearby_templates')}),flush=True)
    (OUT/'missing-details.json').write_text(json.dumps(missing,indent=2)+'\n')
    funcs=sorted(n for n in current if '/function/' in n)
    print('PACK_FUNCTIONS '+json.dumps(funcs),flush=True)
    candidates=[]
    for folder in ('scripts','native','qa'):
        for p in sorted((ROOT/folder).rglob('*')):
            if p.is_file() and any(w in p.name.lower() for w in ('resource','reference','mob','boss','jockey','restore','fingerprint')):
                candidates.append(str(p.relative_to(ROOT)))
    print('RELEVANT_SOURCE_PATHS '+json.dumps(candidates),flush=True)
    inventory={'provenance':provenance,'jar':str(jar.relative_to(ROOT)),'pack':str(pack.relative_to(ROOT)),
               'pack_sha256':PACK,'original_sources':{k:own.SOURCES[k] for k in upstream},'scope':'Inventory only. A missing graph is not accepted.',
               'resource_acceptance':r['pass'],'inspection_completed':True,'production_accepted':False}
    (OUT/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    (OUT/'source-paths.json').write_text(json.dumps(candidates,indent=2)+'\n')
if __name__=='__main__':main()
