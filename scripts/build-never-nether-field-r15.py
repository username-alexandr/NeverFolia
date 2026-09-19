#!/usr/bin/env python3
"""Add the required NeverNether R15 native-runtime profile to an exact R14 pack.

The R14 geometry/storage payload is retained. A native profile document and a
registry-decoded required processor marker make R15 pack/runtime pairing
bidirectional: R15 rejects an R14-only pack, while an older R14 runtime cannot
decode the R15-only processor type. The canonical content fingerprint is then
recomputed for the changed pack.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FP_PATH=ROOT/'scripts/fingerprint-never-nether-pack.py'
NATIVE_PROFILE='NN-R15-FIELD-CLEANUP-1'
R14_PROFILE='NN-R14-SUBSTRATE-1-ROOF512'
NATIVE_MARKER='data/neverfolia/nevernether/native_profile.json'
REQUIRED_PROCESSOR='data/neverfolia/worldgen/processor_list/never_nether/field_r15_required.json'
HEIGHT_MARKER='data/neverfolia/nevernether/height_profile.json'


def load_fp():
    spec=importlib.util.spec_from_file_location('r15_fp',FP_PATH)
    if spec is None or spec.loader is None:raise RuntimeError('fingerprint module unavailable')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def encoded(value:object)->bytes:
    return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode('utf-8')


def deterministic_zip(path:Path,entries:dict[str,bytes])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise ValueError('output already exists: '+str(path))
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as t:
        tmp=Path(t.name)
    try:
        with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for name,payload in sorted(entries.items()):
                info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,payload)
        with zipfile.ZipFile(tmp) as z:
            if z.testzip() is not None:raise ValueError('R15 output ZIP corrupt')
        os.link(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)


def transform(source:Path,output:Path)->dict:
    if source.resolve()==output.resolve():raise ValueError('output must be a new path')
    fp=load_fp()
    source_doc=fp.verify(source)
    entries=fp.read_entries(source)
    for name in fp.FINGERPRINT_ENTRIES:entries.pop(name,None)

    if NATIVE_MARKER in entries or REQUIRED_PROCESSOR in entries:
        raise ValueError('source already contains an R15 native profile')
    if HEIGHT_MARKER not in entries:
        raise ValueError('R14 height profile marker missing')
    height=json.loads(entries[HEIGHT_MARKER].decode('utf-8'))
    if height.get('profile')!=R14_PROFILE or height.get('bedrock_roof_y')!=512:
        raise ValueError('source is not the accepted R14 roof512 profile')

    entries[NATIVE_MARKER]=encoded({
        'schema':1,
        'profile':NATIVE_PROFILE,
        'requires_height_profile':R14_PROFILE,
        'new_world_required':True,
    })
    entries[REQUIRED_PROCESSOR]=encoded({
        'processors':[{'processor_type':'neverfolia:field_r15_required'}]
    })

    manifest='nevernether-core-manifest.json'
    if manifest in entries:
        value=json.loads(entries[manifest].decode('utf-8'))
        value['native_field_cleanup_revision']=NATIVE_PROFILE
        entries[manifest]=encoded(value)

    doc=fp.fingerprint_document(entries)
    payload=encoded(doc)
    entries[fp.ROOT_FINGERPRINT_ENTRY]=payload
    entries[fp.RESOURCE_FINGERPRINT_ENTRY]=payload
    deterministic_zip(output,entries)
    verified=fp.verify(output)
    if verified['content_sha256']==source_doc['content_sha256']:
        raise ValueError('R15 pack fingerprint did not change')
    return {
        'schema':1,
        'profile':NATIVE_PROFILE,
        'source_content_sha256':source_doc['content_sha256'],
        'content_sha256':verified['content_sha256'],
        'native_marker':NATIVE_MARKER,
        'required_processor':REQUIRED_PROCESSOR,
    }


def self_test()->None:
    fp=load_fp()
    with tempfile.TemporaryDirectory(prefix='nn-r15-pack-') as raw:
        root=Path(raw);source=root/'r14.zip';output=root/'r15.zip'
        entries={
            'pack.mcmeta':encoded({'pack':{'description':'test','pack_format':1}}),
            HEIGHT_MARKER:encoded({
                'schema':1,'profile':R14_PROFILE,'bedrock_roof_y':512,
                'technical_height':656,'technical_max_y':527,'sections':41,
                'min_y':-128,'building_max_y':512,'bedrock_envelope':5,
                'dimension':'minecraft:the_nether','roof_building_allowed':False,
                'new_world_required':True,
            }),
            'nevernether-core-manifest.json':encoded({'id':'test'}),
        }
        fp.write_zip(source,entries);fp.inject(source)
        result=transform(source,output)
        out=fp.read_entries(output)
        marker=json.loads(out[NATIVE_MARKER])
        processor=json.loads(out[REQUIRED_PROCESSOR])
        assert marker['profile']==NATIVE_PROFILE and marker['new_world_required'] is True
        assert processor=={'processors':[{'processor_type':'neverfolia:field_r15_required'}]}
        assert json.loads(out['nevernether-core-manifest.json'])['native_field_cleanup_revision']==NATIVE_PROFILE
        assert result['source_content_sha256']!=result['content_sha256']
        try:transform(output,root/'twice.zip')
        except ValueError:pass
        else:raise AssertionError('R15 pack accepted as its own R14 source')
    print('[NeverFolia][NN-R15 pack] SELF-TEST OK')


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--self-test',action='store_true')
    a=p.parse_args()
    if a.self_test:self_test();return
    if a.input is None or a.output is None:p.error('--input and --output are required')
    print(json.dumps(transform(a.input,a.output),indent=2))

if __name__=='__main__':main()
