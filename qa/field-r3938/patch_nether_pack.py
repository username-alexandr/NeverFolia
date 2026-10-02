#!/usr/bin/env python3
from pathlib import Path, PurePosixPath
import argparse,importlib.util,json,zipfile

ROOT=Path(__file__).resolve().parents[2]
HARDENER=ROOT/'scripts/harden-never-nether-structure-pack.py'
SPEC=ROOT/'worldgen-spec/never-nether-structures.json'

def need(v,m):
    if not v: raise ValueError(m)

def load_hardener():
    spec=importlib.util.spec_from_file_location('r3938_hardener',HARDENER)
    need(spec is not None and spec.loader is not None,'cannot load hardener')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def structure_path(sid):
    ns,path=sid.split(':',1)
    return PurePosixPath('data',ns,'worldgen','structure',path+'.json')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('src',type=Path)
    ap.add_argument('dst',type=Path)
    a=ap.parse_args()

    hard=load_hardener()
    files=hard.load_zip(a.src)
    spec=json.loads(SPEC.read_text())
    ids=[
      row['id']
      for group in spec['placement_groups'].values()
      for row in group['structures']
    ]
    need(len(ids)==20 and len(set(ids))==20,'expected 20 structures')

    changed=[]
    for sid in ids:
        p=structure_path(sid)
        need(p in files,'missing structure '+sid)
        d=json.loads(files[p])
        before=d.get('dimension_padding')
        need(before=={'bottom':5,'top':517},sid+' unexpected old padding '+repr(before))
        d['dimension_padding']={'bottom':5,'top':149}
        files[p]=(json.dumps(d,indent=2,ensure_ascii=False)+'\n').encode()
        changed.append(sid)

    manifest_path=PurePosixPath('nevernether-structure-integration-manifest.json')
    if manifest_path in files:
        manifest=json.loads(files[manifest_path])
        h=manifest.setdefault('neverfolia_hardening',{})
        h['dimension_padding']={'bottom':5,'top':149}
        h['effective_bounding_box_y']=[-123,378]
        h['r14_technical_max_y']=527
        files[manifest_path]=(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n').encode()

    hard.refresh_fingerprint(files)
    hard.validate(files,tuple(sorted(ids)),{'bottom':5,'top':149})
    hard.write_zip(a.dst,files)

    verify=hard.load_zip(a.dst)
    for sid in ids:
        d=json.loads(verify[structure_path(sid)])
        need(d.get('dimension_padding')=={'bottom':5,'top':149},sid+' final padding mismatch')

    docs=[json.loads(verify[p]) for p in hard.FINGERPRINT_PATHS]
    need(docs[0]==docs[1],'fingerprint docs differ')
    need(docs[0]['content_sha256']==hard.content_fingerprint(verify),'fingerprint mismatch')

    print('R3938_NETHER_PACK '+json.dumps({
      'structures_patched':len(changed),
      'dimension_padding':{'bottom':5,'top':149},
      'effective_bounding_box_y':[-123,378],
      'fingerprint':docs[0]['content_sha256'],
      'entries':len(verify)
    }))

if __name__=='__main__':
    main()
