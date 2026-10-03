#!/usr/bin/env python3
"""Inventory exact v4.5 Pale Residence feature-pool dependencies against R39.20."""
from pathlib import Path, PurePosixPath
import hashlib, json, re, sys, zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'qa/field-r3918'))
import restore_stray_walls as walls

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts'
POOL='data/nova_structures/worldgen/template_pool/pale_residence/decor_inside.json'
FEATURES=('nova_structures:pale_moss_small','nova_structures:pale_moss_floor')
RID=re.compile(r'^[a-z0-9_.-]+:[a-z0-9_./-]+$')

def need(ok,msg):
    if not ok: raise ValueError(msg)

def read_zip(path):
    with zipfile.ZipFile(path) as z:
        need(z.testzip() is None,'Bad R39.20 ZIP')
        return {n:z.read(n) for n in z.namelist() if not n.endswith('/')}

def strings(node):
    if isinstance(node,str):
        if RID.fullmatch(node): yield node
    elif isinstance(node,dict):
        for v in node.values(): yield from strings(v)
    elif isinstance(node,list):
        for v in node: yield from strings(v)

def resource_candidates(files,rid):
    ns,name=rid.split(':',1)
    suffix='/'+name+'.json'
    return sorted(p for p in files if p.startswith('data/'+ns+'/') and p.endswith(suffix))

def json_doc(files,path):
    raw=files[path]
    try:return json.loads(raw)
    except Exception as e:raise ValueError(f'Invalid JSON {path}: {e}')

def main():
    OUT.mkdir(exist_ok=True)
    base_candidates=list((ROOT/'r3920-input').rglob('NeverOverworld-R3920-Effective.zip'))
    need(len(base_candidates)==1,'Missing/ambiguous R39.20 candidate')
    base=base_candidates[0];base_raw=base.read_bytes()
    need(hashlib.sha256(base_raw).hexdigest()=='9daf27e23300d6687e8cc93cf82c7e6db91f69e4fe605382c6947521f0855590','Wrong R39.20 input')
    current=read_zip(base)
    author=walls.s.read_zip(walls.author_bytes())
    source_pool=json.loads(author[POOL])
    current_pool=json.loads(current[POOL])
    report={'pass':False,'r3920_sha256':hashlib.sha256(base_raw).hexdigest(),
            'author_v45_sha256':walls.AUTHOR_SHA,'source_pool':source_pool,'current_pool':current_pool,
            'features':{},'dependency_files':{},'missing_from_r3920':[]}
    frontier=list(FEATURES);seen=set()
    while frontier:
        rid=frontier.pop(0)
        if rid in seen:continue
        seen.add(rid)
        candidates=resource_candidates(author,rid)
        rows=[]
        for path in candidates:
            obj=json_doc(author,path)
            refs=sorted(set(strings(obj)))
            rows.append({'path':path,'sha256':hashlib.sha256(author[path]).hexdigest(),
                         'present_in_r3920':path in current,
                         'same_bytes_in_r3920':path in current and current[path]==author[path],
                         'json':obj,'resource_refs':refs})
            for ref in refs:
                if ref.startswith(('nova_structures:','minecraft:')) and ref not in seen:
                    if resource_candidates(author,ref):frontier.append(ref)
        report['dependency_files'][rid]=rows
    report['features']={rid:resource_candidates(author,rid) for rid in FEATURES}
    all_paths=sorted({row['path'] for rows in report['dependency_files'].values() for row in rows})
    report['missing_from_r3920']=[p for p in all_paths if p not in current]
    report['different_in_r3920']=[p for p in all_paths if p in current and current[p]!=author[p]]
    report['pass']=all(report['features'].values())
    (OUT/'pale-feature-dependencies.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('PALE_FEATURE_POOL',json.dumps(source_pool,ensure_ascii=False),flush=True)
    for rid,rows in report['dependency_files'].items():
        if rows:
            print('PALE_FEATURE_RESOURCE',json.dumps({'id':rid,'rows':rows},ensure_ascii=False),flush=True)
    print('PALE_FEATURE_SUMMARY',json.dumps({
        'pass':report['pass'],'features':report['features'],
        'missing_from_r3920':report['missing_from_r3920'],
        'different_in_r3920':report['different_in_r3920'],
        'dependency_ids':len(report['dependency_files'])
    },ensure_ascii=False),flush=True)
    need(report['pass'],'Author feature resources unresolved')

if __name__=='__main__':main()
