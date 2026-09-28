#!/usr/bin/env python3
"""Read-only Pale Residence source provenance across pinned D&T releases."""
from pathlib import Path
import gzip, hashlib, json, sys, urllib.request, zlib
import restore_stray_walls as walls

s=walls.s;ROOT=walls.ROOT;OUT=ROOT/'artifacts'
builder=s.load('r3920_pale_source_builder',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
POOL='data/nova_structures/worldgen/template_pool/pale_residence/decor_inside.json'
NEEDLE=b'nova_structures:pale_residence/decor_inside'

def need(ok,msg):
    if not ok: raise ValueError(msg)

def decompressed(raw):
    if raw[:2]==b'\x1f\x8b':
        return gzip.decompress(raw)
    if len(raw)>=2 and raw[0]==0x78:
        try:return zlib.decompress(raw)
        except zlib.error:return raw
    return raw

def dat_532():
    spec=builder.SOURCES['dat']
    req=urllib.request.Request(spec['url'],headers={'User-Agent':'NeverFolia-R3920-pale-probe/1.0'})
    with urllib.request.urlopen(req,timeout=60) as response:
        raw=response.read(60_000_001)
    need(len(raw)<=60_000_000,'Pinned D&T 5.3.2 archive exceeds limit')
    need(hashlib.sha256(raw).hexdigest()==spec['sha256'],'Pinned D&T 5.3.2 hash changed')
    return raw

def locations(node):
    found=[]
    if isinstance(node,dict):
        value=node.get('location')
        if isinstance(value,str):found.append(value)
        for v in node.values():found.extend(locations(v))
    elif isinstance(node,list):
        for v in node:found.extend(locations(v))
    return found

def inspect(label,raw):
    files=builder.flatten_zip(raw)
    pool_obj=json.loads(files[POOL]) if POOL in files else None
    locs=locations(pool_obj) if pool_obj is not None else []
    resolved=[]
    for ident in locs:
        if ':' not in ident:continue
        ns,path=ident.split(':',1);name=f'data/{ns}/structure/{path}.nbt'
        payload=files.get(name)
        resolved.append({'id':ident,'path':name,'present':payload is not None,
                         'sha256':hashlib.sha256(payload).hexdigest() if payload is not None else None})
    refs=[]
    for name,payload in sorted(files.items()):
        if not(name.startswith('data/nova_structures/structure/pale_residence/') and name.endswith('.nbt')):continue
        raw_nbt=decompressed(payload)
        if NEEDLE in raw_nbt:
            refs.append({'path':name,'sha256':hashlib.sha256(payload).hexdigest(),
                         'literal_occurrences':raw_nbt.count(NEEDLE)})
    candidates=sorted(name for name in files if 'pale_residence' in name and
                      ('decor_inside' in name or '/decor/' in name or 'banner' in name.lower()
                       or 'sign' in name.lower() or name.endswith('/pale_house_2.nbt')))
    return {'label':label,'archive_sha256':hashlib.sha256(raw).hexdigest(),
            'pool_present':POOL in files,'pool':pool_obj,'pool_locations':locs,
            'resolved_pool_templates':resolved,'parent_references':refs,
            'candidate_paths':candidates}

def main():
    OUT.mkdir(exist_ok=True)
    rows=[
        inspect('D&T v4.5',walls.author_bytes()),
        inspect('D&T v5.3.2',dat_532()),
        inspect('D&T v6.0.1',walls.author_v6_bytes()),
    ]
    report={'pass':True,'pool_id':'nova_structures:pale_residence/decor_inside','sources':rows}
    (OUT/'pale-source-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    for row in rows:
        print('PALE_SOURCE',json.dumps({
            'label':row['label'],'archive_sha256':row['archive_sha256'],
            'pool_present':row['pool_present'],'pool_locations':row['pool_locations'],
            'resolved_pool_templates':row['resolved_pool_templates'],
            'parent_references':row['parent_references'],
            'candidate_paths':row['candidate_paths']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
