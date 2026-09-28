#!/usr/bin/env python3
"""Read-only inventory. Does not replace resources, change saves or accept release gates."""
from pathlib import Path
import difflib, hashlib, importlib.util, io, json, os, urllib.request, urllib.parse, zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'full-fix-evidence';OUT.mkdir(exist_ok=True)

def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def unique(root,name,digest):
    values=[p for p in Path(root).rglob(name) if p.is_file() and sha(p.read_bytes())==digest]
    need(len(values)==1,'Missing or ambiguous exact input: '+name);return values[0]
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def request(url,limit=80*1024*1024):
    parsed=urllib.parse.urlparse(url)
    need(parsed.scheme=='https' and parsed.netloc in ('api.modrinth.com','cdn.modrinth.com'),'Unapproved upstream host')
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'NeverFolia/ResourceCompatibilityAudit'}),timeout=45) as r:
        actual=urllib.parse.urlparse(r.url);need(actual.scheme=='https' and actual.netloc in ('api.modrinth.com','cdn.modrinth.com'),'Unapproved redirect')
        data=r.read(limit+1);need(len(data)<=limit,'Oversized response');return data

def main():
    jar=unique(ROOT/'baseline','server.jar','c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67')
    pack=unique(ROOT/'baseline','NeverOverworld.zip','a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be')
    audit=load_module('resourceaudit',ROOT/'scripts/audit-neveroverworld-r39-resources.py')
    report=audit.audit_files(jar,pack)
    (OUT/'current-resource-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('CURRENT_AUDIT',json.dumps({k:report[k] for k in ('pass','counts','errors')}),flush=True)
    need(not report['errors'],'Audit parsing failed; do not infer missing resources')
    with zipfile.ZipFile(pack) as z:
        names=z.namelist();need(len(names)==len(set(names)) and z.testzip() is None,'Invalid pack')
        current={n:z.read(n) for n in names}
    metadata=json.loads(request('https://api.modrinth.com/v2/version/y9AUViOD'))
    need(metadata['project_id']=='tpehi7ww' and '26.2' in metadata['game_versions'] and metadata['version_number'].startswith('5.3.2'),'Wrong upstream version')
    files=[f for f in metadata['files'] if f.get('primary')];need(len(files)==1,'Ambiguous upstream primary')
    file=files[0];need(file['url'].startswith('https://cdn.modrinth.com/data/tpehi7ww/versions/'),'Wrong upstream path')
    raw=request(file['url']);need(len(raw)==file['size'] and hashlib.sha512(raw).hexdigest()==file['hashes']['sha512'],'Upstream integrity failure')
    upstream_dir=ROOT/'.work/r3914-upstream';upstream_dir.mkdir(parents=True,exist_ok=False)
    (upstream_dir/'dnt-5.3.2.jar').write_bytes(raw)
    (OUT/'upstream-provenance.json').write_text(json.dumps({'version':metadata,'sha256':sha(raw)},indent=2)+'\n')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid upstream ZIP')
        upstream={n:z.read(n) for n in z.namelist() if n.startswith('data/')}
    nbt=load_module('nbtreader',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    def description(payload):
        _,_,root=nbt._nbt_parse(payload)
        values={'size':root.get('size'),'DataVersion':root.get('DataVersion'),'jigsaws':[]}
        for block in root.get('blocks',(9,(10,[])))[1][1]:
            data=block.get('nbt',(10,{}))[1]
            if 'pool' in data:values['jigsaws'].append({'pos':block.get('pos'),'data':data})
        return values
    rows=[]
    for item in report['missing']:
        kind=item['kind'];ns,key=item['id'].split(':',1)
        family={'template':('structure','nbt'),'pool':('worldgen/template_pool','json')}.get(kind)
        if family is None:continue
        path=f'data/{ns}/{family[0]}/{key}.{family[1]}'
        alternatives=difflib.get_close_matches(path,list(current),n=5,cutoff=.75)
        row={**item,'path':path,'exact_upstream':path in upstream,'similar_current':alternatives}
        if path in upstream:
            row['upstream_sha256']=sha(upstream[path])
            if kind=='template':row['upstream_nbt']=description(upstream[path])
        rows.append(row)
        print('MISSING_RESOURCE',json.dumps({'id':item['id'],'exact_upstream':path in upstream,'origins':item['origins'],'similar_current':alternatives}),flush=True)
    (OUT/'resource-recovery-candidates.json').write_text(json.dumps(rows,indent=2)+'\n')
    summary={'missing':len(rows),'exact_upstream':sum(r['exact_upstream'] for r in rows),'upstream_version':metadata['id'],'no_resources_changed':True}
    print('RECOVERY_SUMMARY',json.dumps(summary),flush=True)
    # Preserve names/keys of old runtime evidence without pretending it is a new test.
    for p in sorted((ROOT/'prior-ice').rglob('*runtime*.json')):
        value=json.loads(p.read_text());print('PRIOR_ICE_RUNTIME',str(p.relative_to(ROOT)),json.dumps(value)[:20000],flush=True)
    (OUT/'inventory-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
if __name__=='__main__': main()
