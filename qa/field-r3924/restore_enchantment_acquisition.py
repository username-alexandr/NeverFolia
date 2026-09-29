#!/usr/bin/env python3
"""Restore authored D&T player-acquisition enchantment tags onto the R3920 pack.

Only IDs in #nova_structures:all_dnt_enchants are eligible. Technical controller
enchantments remain registry-only. Source is the exact pinned D&T v5.3.2 archive
already used by NeverOverworld; SHA256 drift fails closed.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, io, json, urllib.request, zipfile
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[2]
GAMEPLAY_TAG='data/nova_structures/tags/enchantment/all_dnt_enchants.json'
TECH_TAG='data/nova_structures/tags/enchantment/non_survival_enchants.json'
PUBLIC_PREFIX='data/minecraft/tags/enchantment/'

def need(ok,msg):
    if not ok: raise ValueError(msg)

def sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def load_builder():
    path=ROOT/'scripts/build-never-overworld-external-structures-r19.py'
    spec=importlib.util.spec_from_file_location('r3924_builder',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def read_zip(raw:bytes)->dict[str,bytes]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if not n.endswith('/')]
        need(z.testzip() is None and len(names)==len(set(names)),'invalid/duplicate pack ZIP')
        need(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names),'unsafe ZIP path')
        return {n:z.read(n) for n in names}

def write_zip(files:dict[str,bytes])->bytes:
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(files.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,raw,compresslevel=9)
    return out.getvalue()

def ids(obj:dict)->list[tuple[str,object]]:
    out=[]
    for value in obj.get('values',[]):
        rid=value if isinstance(value,str) else value.get('id') if isinstance(value,dict) else None
        if isinstance(rid,str):out.append((rid,value))
    return out

def fetch_source(builder)->bytes:
    spec=builder.SOURCES['dat']
    req=urllib.request.Request(spec['url'],headers={'User-Agent':'NeverFolia-R3924-enchant-acquisition/1.0'})
    with urllib.request.urlopen(req,timeout=120) as response:
        raw=response.read(60_000_001)
    need(len(raw)<=60_000_000,'D&T archive exceeds size limit')
    need(sha(raw)==spec['sha256'],'pinned D&T source SHA256 changed')
    return raw

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--source',type=Path)
    a=p.parse_args()

    report={'pass':False}
    try:
        builder=load_builder()
        base_raw=a.base.read_bytes();files=read_zip(base_raw)
        need(GAMEPLAY_TAG in files and TECH_TAG in files,'D&T enchantment marker tags missing')
        gameplay={rid for rid,_ in ids(json.loads(files[GAMEPLAY_TAG]))}
        technical={rid for rid,_ in ids(json.loads(files[TECH_TAG]))}
        need(len(gameplay)==17,'expected exactly 17 gameplay D&T enchantments')
        need(len(technical)>=15 and not gameplay&technical,'gameplay/technical enchantment partition invalid')

        source_raw=a.source.read_bytes() if a.source else fetch_source(builder)
        need(sha(source_raw)==builder.SOURCES['dat']['sha256'],'wrong supplied D&T source')
        source=builder.flatten_zip(source_raw)

        authored={}
        additions={}
        for name,payload in sorted(source.items()):
            if not(name.startswith(PUBLIC_PREFIX) and name.endswith('.json')):continue
            rel=name[len(PUBLIC_PREFIX):]
            if '/' in rel: # exclusive_set and other mechanics are already imported separately
                continue
            src=json.loads(payload)
            selected=[value for rid,value in ids(src) if rid in gameplay]
            if not selected:continue
            authored[name]=[rid for rid,_ in ids(src) if rid in gameplay]
            current=json.loads(files[name]) if name in files else {'values':[]}
            values=list(current.get('values',[]))
            present={rid for rid,_ in ids(current)}
            added=[]
            for value in selected:
                rid=value if isinstance(value,str) else value.get('id')
                if rid not in present:
                    values.append(value);present.add(rid);added.append(rid)
            current=dict(current);current['values']=values
            current.pop('replace',None)
            files[name]=(json.dumps(current,indent=2,ensure_ascii=False)+'\n').encode()
            if added:additions[name]=added

        need(authored,'source exposes no gameplay enchantment public tags')
        for name,expected in authored.items():
            got={rid for rid,_ in ids(json.loads(files[name]))}
            need(set(expected)<=got,'authored public enchantment tag incomplete: '+name)
            need(not(got&technical),'technical enchantment leaked into public tag: '+name)

        # These two were previously stripped after their functions had become Folia-safe.
        for rid in ('nova_structures:swift_soar','nova_structures:ghasted'):
            path='data/nova_structures/enchantment/'+rid.split(':',1)[1]+'.json'
            need(path in files and json.loads(files[path]).get('effects'),'safe gameplay enchantment lacks effects: '+rid)

        for name in ('swift_soar_1','swift_soar_2','swift_soar_3','ghasted_fireball_1','ghasted_fireball_2','ghasted_fireball_3'):
            need('data/nova_structures/function/'+name+'.mcfunction' in files,'safe runtime function missing: '+name)

        raw=write_zip(files)
        need(read_zip(raw)==files and raw==write_zip(files),'non-deterministic output pack')
        a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_bytes(raw)
        report={
          'pass':True,'base_sha256':sha(base_raw),'source_sha256':sha(source_raw),
          'pre_fingerprint_output_sha256':sha(raw),'gameplay_count':len(gameplay),
          'technical_count':len(technical),'authored_public_tags':authored,
          'added_public_entries':additions,
          'gameplay_ids':sorted(gameplay),'technical_ids':sorted(technical)
        }
    except Exception as e:
        report={'pass':False,'error':repr(e)}
        raise
    finally:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        print('R3924_ENCHANT_ACQUISITION '+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
