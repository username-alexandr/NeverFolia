#!/usr/bin/env python3
"""Convert a verified R13 Core/full pack to the exact Y=512 roof profile.

Writes a NEW pack. Original source archives and existing worlds are not edited.
41 technical sections (-128..527) are required to include the block at Y=512;
513..527 are empty storage padding, never buildable with the matching runtime.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PROFILE='NN-R14-SUBSTRATE-1-ROOF512'
MIN_Y=-128
ROOF_Y=512
HEIGHT=656
MAX_Y=527
SECTIONS=41
SHAPES={
 'dimension':'data/minecraft/dimension_type/the_nether.json',
 'noise':'data/minecraft/worldgen/noise_settings/nether.json',
 'density':'data/neverfolia/worldgen/density_function/never_nether/final_density.json',
 'core':'nevernether-core-manifest.json',
}
FINGERPRINTS=('nevernether-worldgen-fingerprint.json','data/neverfolia/nevernether/worldgen_fingerprint.json')
PROFILE_PATH='data/neverfolia/nevernether/height_profile.json'
REQUIRED_PROCESSOR='data/neverfolia/worldgen/processor_list/never_nether/height_r14_required.json'


def load_fingerprint():
    spec=importlib.util.spec_from_file_location('r14_fingerprint',ROOT/'scripts/fingerprint-never-nether-pack.py')
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj


def encoded(value):return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode()


def convert(entries:dict[str,bytes])->dict[str,bytes]:
    expected=json.loads((ROOT/'worldgen-spec/never-nether-height-r14.json').read_text())
    for name,sha in expected['source_contract_sha256'].items():
        if name not in entries or hashlib.sha256(entries[name]).hexdigest()!=sha:
            raise ValueError('R13 height source contract differs: '+name)
    if PROFILE_PATH in entries or REQUIRED_PROCESSOR in entries:
        raise ValueError('Pack already has a height profile; no implicit reapplication/migration')
    out=dict(entries)
    dim=json.loads(entries[SHAPES['dimension']]);noise=json.loads(entries[SHAPES['noise']])
    density=json.loads(entries[SHAPES['density']]);core=json.loads(entries[SHAPES['core']])
    if dim['min_y']!=-128 or dim['height']!=1024 or noise['noise']['height']!=512:
        raise ValueError('Expected original R13 geometry')
    dim['height']=HEIGHT;dim['logical_height']=ROOF_Y-MIN_Y+1
    noise['noise']['height']=HEIGHT
    roofs=[r for r in noise['surface_rule']['sequence'] if r.get('if_true',{}).get('type')=='minecraft:not' and r.get('if_true',{}).get('invert',{}).get('random_name')=='neverfolia:bedrock_roof']
    if len(roofs)!=1:raise ValueError('Expected one original upper bedrock rule')
    gradient=roofs[0]['if_true']['invert']
    if gradient['true_at_and_below']!={'absolute':378} or gradient['false_at_and_above']!={'absolute':383}:
        raise ValueError('Original bedrock envelope differs')
    gradient['true_at_and_below']={'absolute':507};gradient['false_at_and_above']={'absolute':512}
    # Extend only the two previously roof-relative density ramps; retain lower
    # lava plane and all other noise parameters and feature attempt counts.
    changes=[]
    def visit(o):
        if isinstance(o,dict):
            if o.get('type')=='minecraft:y_clamped_gradient' and o.get('to_y')==384:
                if o.get('from_y')==344 and o.get('from_value')==0 and o.get('to_value')==1:
                    o['from_y']=473;o['to_y']=513;changes.append('ceiling')
                elif o.get('from_y')==336 and o.get('from_value')==1 and o.get('to_value')==0:
                    o['from_y']=465;o['to_y']=513;changes.append('upper_weight')
                else:raise ValueError('Unexpected roof density ramp')
            for v in o.values():visit(v)
        elif isinstance(o,list):
            for v in o:visit(v)
    visit(density)
    if sorted(changes)!=['ceiling','upper_weight']:raise ValueError('Roof density ramp coverage differs')
    density={'type':'minecraft:range_choice','input':{'type':'minecraft:y_clamped_gradient','from_y':512,'to_y':513,'from_value':0.0,'to_value':1.0},'min_inclusive':0.0,'max_exclusive':1.0,'when_in_range':density,'when_out_of_range':-1.0}
    # Do not interpret technical padding as another surface: the cutoff is
    # OUTSIDE interpolation and remains exactly negative at every Y>=513.
    core.update(id='NN-R14-core-roof512',dimension_height=HEIGHT,dimension_max_y=MAX_Y,
        generated_height=641,generated_max_y=ROOF_Y,noise_storage_height=HEIGHT,
        upper_bedrock_anchor=ROOF_Y,roof_building_allowed=False,logical_max_y=ROOF_Y,
        technical_padding_y=[513,527],required_native_profile=PROFILE)
    core.pop('roof_build_min_y',None);core.pop('roof_build_max_y',None)
    for key,value in [('dimension',dim),('noise',noise),('density',density),('core',core)]:out[SHAPES[key]]=encoded(value)
    out[PROFILE_PATH]=encoded({'schema':1,'profile':PROFILE,'dimension':'minecraft:the_nether','min_y':MIN_Y,
        'technical_height':HEIGHT,'technical_max_y':MAX_Y,'sections':SECTIONS,'bedrock_roof_y':ROOF_Y,
        'bedrock_envelope':5,'roof_building_allowed':False,'building_max_y':ROOF_Y,
        'new_world_required':True})
    out[REQUIRED_PROCESSOR]=encoded({'processors':[{'processor_type':'neverfolia:height_r14_required'}]})
    manifest_path='nevernether-structure-integration-manifest.json'
    if manifest_path in out:
        manifest=json.loads(out[manifest_path]);approved=manifest['approved_structures']
        if len(approved)!=20 or len({s['id'] for s in approved})!=20:raise ValueError('Expected all twenty structures')
        for item in approved:
            ns,name=item['id'].split(':',1);path=f'data/{ns}/worldgen/structure/{name}.json'
            value=json.loads(out[path])
            if value.get('dimension_padding')!={'bottom':5,'top':517}:raise ValueError('Unexpected R13 dimension padding '+path)
            value['dimension_padding']={'bottom':5,'top':20};out[path]=encoded(value)
        manifest['neverfolia_hardening']['dimension_padding']={'bottom':5,'top':20}
        manifest['neverfolia_hardening']['effective_bounding_box_y']=[-123,507]
        manifest['required_native_profile']=PROFILE;out[manifest_path]=encoded(manifest)
    for path in FINGERPRINTS:out.pop(path,None)
    return out


def build(source:Path,output:Path)->dict:
    if output.exists() or source.resolve()==output.resolve():raise ValueError('Output must be a new file')
    fp=load_fingerprint();entries=fp.read_entries(source)
    actual=fp.content_digest(entries)
    for path in FINGERPRINTS:
        if path not in entries or json.loads(entries[path]).get('content_sha256')!=actual:raise ValueError('R13 fingerprint not verified')
    out=convert(entries)
    fingerprint={'schema':1,'worldgen_id':'NN-DEV-1','algorithm':fp.ALGORITHM,'content_sha256':fp.content_digest(out),'entry_count_excluding_fingerprint':len(out)}
    for path in FINGERPRINTS:out[path]=encoded(fingerprint)
    output.parent.mkdir(parents=True,exist_ok=True)
    # All parsing and transformations finish before creating an output. ZIP
    # payload order/timestamps are deterministic for reproducible checksums.
    with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.zip') as temp:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for path,payload in sorted(out.items()):
                info=zipfile.ZipInfo(path,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,payload)
        temp.flush()
        with zipfile.ZipFile(temp.name) as z:
            if z.testzip() is not None:raise ValueError('Output archive corrupt')
        # Do not replace a concurrently created destination.
        import os
        os.link(temp.name,output)
    return {'profile':PROFILE,'bedrock_roof_y':ROOF_Y,'technical_height':HEIGHT,'technical_max_y':MAX_Y,
        'building_above_roof':False,'old_world_migration':False,'pack_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'content_sha256':fingerprint['content_sha256'],'source_pack_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    try:print(json.dumps(build(a.input,a.output),indent=2))
    except (OSError,ValueError,KeyError,TypeError) as e:p.exit(2,f'R14 height pack rejected: {e}\n')
if __name__=='__main__':main()
