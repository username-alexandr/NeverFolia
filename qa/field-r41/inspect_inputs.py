#!/usr/bin/env python3
"""Read-only discovery for a consolidated repair. Never changes input packs."""
from pathlib import Path
import collections,difflib,hashlib,importlib.util,io,json,sys,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'r41-evidence';OUT.mkdir(exist_ok=True)
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def get(url):
    if not url.startswith(('https://api.modrinth.com/','https://cdn.modrinth.com/')):raise ValueError('Unexpected source host')
    req=urllib.request.Request(url,headers={'User-Agent':'NeverFolia-repair-audit/1 (owner requested compatibility inspection)'})
    with urllib.request.urlopen(req,timeout=45) as r:return r.read()
def main():
    bases=list((ROOT/'inputs').rglob('server.jar'));packs=list((ROOT/'inputs').rglob('NeverOverworld.zip'))
    if len(bases)!=1 or len(packs)!=1:raise ValueError('Ambiguous exact inputs')
    if hashlib.sha256(bases[0].read_bytes()).hexdigest()!='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67':raise ValueError('Wrong R399')
    if hashlib.sha256(packs[0].read_bytes()).hexdigest()!='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be':raise ValueError('Wrong pack')
    a=load(ROOT/'scripts/audit-neveroverworld-r39-resources.py','r41audit');report=a.audit_files(bases[0],packs[0]);(OUT/'resource-before.json').write_text(json.dumps(report,indent=2))
    print('RESOURCE_COUNTS',json.dumps(report['counts']),flush=True)
    versions=json.loads(get('https://api.modrinth.com/v2/project/dungeons-and-taverns/version?game_versions=%5B%2226.2%22%5D&loaders=%5B%22datapack%22%5D'))
    print('UPSTREAM_VERSIONS',json.dumps([{k:v.get(k) for k in ('id','version_number','game_versions','loaders')} for v in versions]),flush=True)
    official={};provenance=[]
    for version in versions[:4]:
        if version.get('version_type')!='release' or '26.2' not in version['game_versions']:continue
        files=version['files'];chosen=next((f for f in files if f.get('primary')),files[0]);raw=get(chosen['url'])
        if hashlib.sha512(raw).hexdigest()!=chosen['hashes']['sha512']:raise ValueError('Upstream hash mismatch')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if z.testzip() is not None or len(z.namelist())!=len(set(z.namelist())):raise ValueError('Bad upstream archive')
            official[version['version_number']]={n:z.read(n) for n in z.namelist() if n.startswith('data/')}
        provenance.append({'version':version['version_number'],'id':version['id'],'file':chosen,'sha256':hashlib.sha256(raw).hexdigest()})
        (OUT/('upstream-'+version['id']+'.zip')).write_bytes(raw)
    (OUT/'upstream-provenance.json').write_text(json.dumps(provenance,indent=2))
    with zipfile.ZipFile(packs[0]) as z:
        names=z.namelist();rids={n.split('/')[1]+':'+n.split('/structure/',1)[1][:-4]:n for n in names if n.startswith('data/') and '/structure/' in n and n.endswith('.nbt')}
        enriched=[]
        for row in report['missing']:
            ns,ident=row['id'].split(':',1);path='data/'+ns+'/structure/'+ident+'.nbt'
            found={v:hashlib.sha256(entries[path]).hexdigest() for v,entries in official.items() if path in entries}
            candidates=difflib.get_close_matches(row['id'],rids,n=3,cutoff=.72)
            enriched.append({**row,'exact_upstream':found,'near_existing':candidates})
            print('MISSING',json.dumps({'id':row['id'],'kind':row['kind'],'exact_upstream':list(found),'near':candidates}),flush=True)
        (OUT/'missing-details.json').write_text(json.dumps(enriched,indent=2))
        for n in names:
            if n.endswith('.json') and any(t in n.lower() for t in ('manifest','fingerprint','source','trial_spawner')):
                try:
                    data=json.loads(z.read(n)); print('META',n,json.dumps(data)[:3000],flush=True)
                except (ValueError,UnicodeError):pass
        print('PACK_FUNCTIONS',json.dumps([n for n in names if '/function/' in n]),flush=True)
        print('PACK_METADATA',z.read('pack.mcmeta').decode(),flush=True)
    print('MOB_SOURCES',json.dumps([str(p.relative_to(ROOT)) for p in (ROOT/'native').rglob('*.java') if any(t in p.name.lower() for t in ('mob','boss','jock','trial','function'))]),flush=True)
    print('QA_FILES',json.dumps([str(p.relative_to(ROOT)) for p in (ROOT/'qa').rglob('*') if p.is_file() and any(t in str(p).lower() for t in ('r394','r393','r38','r3913'))]),flush=True)
if __name__=='__main__':main()
