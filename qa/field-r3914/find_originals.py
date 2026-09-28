#!/usr/bin/env python3
"""Locate exact missing template names in historical author releases. No installation.
Network destinations and compressed-size are constrained; metadata hashes verified.
"""
from pathlib import Path
import hashlib,io,json,urllib.request,urllib.parse,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'resource-evidence'
def get(url,limit):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or p.hostname not in ('api.modrinth.com','cdn.modrinth.com'):raise ValueError('Unexpected upstream host')
    req=urllib.request.Request(url,headers={'User-Agent':'NeverFolia-resource-audit/1.0'})
    with urllib.request.urlopen(req,timeout=60) as response:
        if urllib.parse.urlsplit(response.url).hostname not in ('api.modrinth.com','cdn.modrinth.com'):raise ValueError('Unexpected redirect')
        raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('Oversized original')
    return raw
def main():
    missing=json.loads((OUT/'before.json').read_text())['missing']
    wanted={f"data/{r['id'].replace(':','/structure/',1)}.nbt":r['id'] for r in missing if r['kind']=='template'}
    versions=json.loads((OUT/'upstream-versions.json').read_text());selected=[];series=set()
    for v in versions:
        number=v['version_number'].lower().lstrip('v');family='.'.join(number.split('.')[:2])
        if v['version_type']!='release' or not number.startswith(('5.','4.')) or family in series:continue
        files=[f for f in v['files'] if f['filename'].lower().endswith('.zip')]
        if not files:continue
        series.add(family);selected.append((v,next((f for f in files if f['primary']),files[0])))
        if len(selected)==9:break
    report={'scope':'Exact author filename candidates; no automatic installation','sources':[],'matches':{},'production_accepted':False}
    out=OUT/'original-candidates';out.mkdir(exist_ok=False)
    for v,f in selected:
        raw=get(f['url'],80_000_000)
        if len(raw)!=f['size'] or hashlib.sha512(raw).hexdigest()!=f['hashes']['sha512']:raise ValueError('Original metadata hash mismatch')
        row={'version_id':v['id'],'version':v['version_number'],'url':f['url'],'sha512':f['hashes']['sha512'],'sha256':hashlib.sha256(raw).hexdigest(),'matches':[]}
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for n in z.namelist():
                canonical=n.replace('/structures/','/structure/')
                if canonical not in wanted:continue
                payload=z.read(n);key=wanted[canonical]
                target=out/v['id']/canonical;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
                hit={'version_id':v['id'],'version':v['version_number'],'source_path':n,'candidate_path':str(target.relative_to(OUT)),'sha256':hashlib.sha256(payload).hexdigest()}
                report['matches'].setdefault(key,[]).append(hit);row['matches'].append(key)
        report['sources'].append(row);print('ARCHIVED_MATCHES '+json.dumps(row),flush=True)
    (OUT/'original-matches.json').write_text(json.dumps(report,indent=2)+'\n')
    print('EXACT_ORIGINALS_FOUND '+json.dumps({'count':len(report['matches']),'ids':sorted(report['matches'])}),flush=True)
if __name__=='__main__':main()
