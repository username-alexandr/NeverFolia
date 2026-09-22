#!/usr/bin/env python3
"""Convert exact R15 pack to R16 and add an R16-only processor marker."""
from __future__ import annotations
import argparse,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];FP=ROOT/'scripts/fingerprint-never-nether-pack.py'
OLD='NN-R15-FIELD-CLEANUP-1';NEW='NN-R16-LAVA-OCEAN-CLEANUP-1'
MARK='data/neverfolia/nevernether/native_profile.json';MANIFEST='nevernether-core-manifest.json'
R16='data/neverfolia/worldgen/processor_list/never_nether/field_r16_required.json'
def load():
 s=importlib.util.spec_from_file_location('fp',FP);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def enc(v):return (json.dumps(v,indent=2)+'\n').encode()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 fp=load();fp.verify(a.input);entries=fp.read_entries(a.input)
 for n in fp.FINGERPRINT_ENTRIES:entries.pop(n,None)
 doc=json.loads(entries[MARK])
 if doc.get('profile')!=OLD or R16 in entries:raise ValueError('R16 requires exact R15 source pack')
 doc['profile']=NEW;doc['new_world_required']=True;entries[MARK]=enc(doc)
 entries[R16]=enc({'processors':[{'processor_type':'neverfolia:field_r16_required'}]})
 if MANIFEST in entries:
  m=json.loads(entries[MANIFEST]);m['native_field_cleanup_revision']=NEW;entries[MANIFEST]=enc(m)
 fp.write_zip(a.output,entries);fp.inject(a.output);v=fp.verify(a.output)
 print(json.dumps({'profile':NEW,'content_sha256':v['content_sha256'],'required_processor':R16},indent=2))
if __name__=='__main__':main()
