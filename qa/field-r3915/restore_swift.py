#!/usr/bin/env python3
"""Restore the stripped Swift Soar graph from the exact source, without changing
worldgen or globally enabling Folia command dispatchers. No arbitrary pack inputs.
The resulting candidate is not accepted until an actual runtime test completes.
"""
from __future__ import annotations
import copy,hashlib,importlib.util,io,json,sys,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
BASE='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
SOURCE='4096cd6372e0f244efa0e85c4d884bd85afe665a84a050280acd483b3222b4f9'
OLD_ENCHANT='86fa042456bfea7abd4dc088f32f1f2efb844b9f28268983963cd427a2500fa8'
ORIGINAL_ENCHANT='d0e2f2ecb44ba755008c2271710762b8d7b4f7fbda8427ba1248b3a847b597fc'
ENCHANT='data/nova_structures/enchantment/swift_soar.json'
PREDICATES=('forward_key','ridden_by_player','sprint_key')
FP=('neveroverworld-worldgen-fingerprint.json','data/neverfolia/neveroverworld/worldgen_fingerprint.json')
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def read_zip(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if not n.endswith('/')]
        need(z.testzip() is None and len(names)==len(set(names)),'Damaged or duplicate ZIP')
        need(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names),'Unsafe path')
        return {n:z.read(n) for n in names}

def write_zip(files):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path,raw in sorted(files.items()):
            info=zipfile.ZipInfo(path,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,raw,compresslevel=9)
    return stream.getvalue()

def restore(base_raw,original_raw):
    need(sha(base_raw)==BASE,'Unknown base pack; do not silently drop other patches')
    need(sha(original_raw)==SOURCE,'Unknown original source')
    ext=load('r3915_external',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    bridge=load('r3915_bridge',ROOT/'scripts/nevernether_dnt_r6.py')
    fp=load('r3915_fingerprint',ROOT/'scripts/fingerprint-never-overworld-pack.py')
    original=ext.flatten_zip(original_raw);before=read_zip(base_raw)
    need(len(before)==8007 and sha(before[ENCHANT])==OLD_ENCHANT,'Incorrect original baseline')
    need(sha(original[ENCHANT])==ORIGINAL_ENCHANT,'Changed author enchantment')
    need(before[FP[0]]==before[FP[1]] and json.loads(before[FP[0]])==fp.fingerprint_document(before),'Incorrect base fingerprint')
    wanted=json.loads(original[ENCHANT]);old=json.loads(before[ENCHANT]);metadata=copy.deepcopy(wanted);metadata.pop('effects')
    need(old==metadata,'Unreviewed metadata change: only missing effects may be restored')
    effects=wanted['effects'];need(set(effects)=={'minecraft:tick'} and len(effects['minecraft:tick'])==3,'Wrong effect graph')
    ids=['nova_structures:swift_soar_'+str(i) for i in range(1,4)]
    need([e['effect'] for e in effects['minecraft:tick']]==[{'type':'minecraft:run_function','function':name} for name in ids],'Unexpected function reference')
    files=before.copy();changes=[]
    files[ENCHANT]=original[ENCHANT]
    changes.append({'path':ENCHANT,'old_sha256':sha(before[ENCHANT]),'sha256':sha(files[ENCHANT]),'kind':'restore exact author effects; metadata unchanged'})
    profile=json.loads(bridge.PROFILE.read_text())
    for name in ('swift_soar_1','swift_soar_2','swift_soar_3'):
        path='data/nova_structures/function/'+name+'.mcfunction'
        need(path not in files,'Refusing to overwrite another functional implementation')
        raw=original[path];need(sha(raw)==profile['contract_hashes'][path],'Changed function '+name)
        text=bridge.transform_function(name,raw.decode())
        need(text.count('neverfolia:dnt sprint_on')==1 and text.count('neverfolia:dnt sprint_off')==2,'Missing owned bridge')
        need('tag @s ' not in text,'Unsafe tag command remained')
        inverse=text.replace('neverfolia:dnt sprint_on','tag @s add sprinting').replace('neverfolia:dnt sprint_off','tag @s remove sprinting')
        need(inverse==raw.decode(),'Changes outside reviewed substitutions')
        referenced=sorted(set(__import__('re').findall(r'\bpredicate (nova_structures:[a-z_]+)',text)))
        need(referenced==['nova_structures:'+p for p in PREDICATES],'Unreviewed predicate dependency')
        files[path]=text.encode();changes.append({'path':path,'source_sha256':sha(raw),'sha256':sha(files[path]),'kind':'existing exact owned-entity bridge'})
    for name in PREDICATES:
        path='data/nova_structures/predicate/'+name+'.json';raw=original[path]
        if path in files:need(files[path]==raw,'Conflicting predicate '+name)
        obj=json.loads(raw)
        # Predicates are pure tests. Preserve complete original semantics;
        # runtime parsing is mandatory before accepting the pack.
        files[path]=raw;changes.append({'path':path,'sha256':sha(raw),'json':obj,'kind':'exact original predicate'})
        print('RESTORED_PREDICATE',path,json.dumps(obj),flush=True)
    need(len(files)==len(before)+6,'Unexpected addition count')
    for path,raw in before.items():
        if path not in (ENCHANT,*FP):need(files[path]==raw,'Unrelated original entry changed: '+path)
    doc=fp.fingerprint_document(files);encoded=(json.dumps(doc,indent=2,ensure_ascii=False)+'\n').encode()
    for path in FP:files[path]=encoded
    raw=write_zip(files);need(raw==write_zip(files),'Non-deterministic pack encoding');need(read_zip(raw)==files,'ZIP roundtrip failed')
    return raw,{'pass':True,'base_pack_sha256':BASE,'source_sha256':SOURCE,'output_sha256':sha(raw),'changes':changes,'preserved_original_entries':len(before)-3,'changed_original_entries':[ENCHANT,*FP],'added_entries':sorted(set(files)-set(before)),'scope':'Exact restored Swift Soar hook/function/predicate graph only. No worldgen, loot, trade, other enchantment or kernel changes. Runtime is a separate required check.','production_accepted':False}

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,required=True);p.add_argument('--original',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    try:
        need(not a.out.exists(),'Output already exists');base=a.base.read_bytes();original=a.original.read_bytes()
        raw,report=restore(base,original);a.out.parent.mkdir(parents=True,exist_ok=True)
        with a.out.open('xb') as f:f.write(raw)
        need(a.base.read_bytes()==base and a.original.read_bytes()==original,'Input modified')
    except Exception as e:
        report={'pass':False,'error':repr(e),'production_accepted':False};raise
    finally:
        a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        print('SWIFT_PACK',json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
