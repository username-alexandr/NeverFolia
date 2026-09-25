#!/usr/bin/env python3
"""Real builder data contracts, not claims of generated world acceptance."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
M=load('heightpack',ROOT/'scripts/build-never-nether-height-r14.py')
BASE=load('heightbase',ROOT/'scripts/build-never-nether-core-test1-pack.py')

class PackTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(); cls.root=Path(cls.tmp.name); cls.src=cls.root/'core.zip';BASE.build(cls.src)
  cls.fp=M.load_fingerprint(); cls.entries=cls.fp.read_entries(cls.src)
  # The conversion takes the real legacy finalized builder output. Its exact
  # four payloads must match the inspected Core in the R13 integration pack.
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def convert(self,e=None):return M.convert(self.entries if e is None else e)
 def test_all_four_inspected_payloads_match_real_builder(self):self.convert()
 def test_dimension_exact_section_count(self):
  v=json.loads(self.convert()[M.SHAPES['dimension']]);self.assertEqual((v['min_y'],v['height']),(-128,656));self.assertEqual(v['height']//16,41)
 def test_logical_top_is512_not511(self):
  v=json.loads(self.convert()[M.SHAPES['dimension']]);self.assertEqual(v['min_y']+v['logical_height']-1,512)
 def test_roof_rule_is512_with_five_block_envelope(self):
  n=json.loads(self.convert()[M.SHAPES['noise']]);r=n['surface_rule']['sequence'][1]['if_true']['invert']
  self.assertEqual(r['true_at_and_below'],{'absolute':507});self.assertEqual(r['false_at_and_above'],{'absolute':512})
 def test_lower_bedrock_is_not_changed(self):
  old=json.loads(self.entries[M.SHAPES['noise']]);new=json.loads(self.convert()[M.SHAPES['noise']]);self.assertEqual(old['surface_rule']['sequence'][0],new['surface_rule']['sequence'][0])
 def test_noise_height_aligned(self):
  n=json.loads(self.convert()[M.SHAPES['noise']]);self.assertEqual(n['noise']['height'],656);self.assertEqual(n['noise']['height']%16,0)
 def test_padding_air_cutoff_is_outside_interpolation(self):
  d=json.loads(self.convert()[M.SHAPES['density']]);self.assertEqual(d['type'],'minecraft:range_choice');self.assertEqual(d['when_out_of_range'],-1.0)
  self.assertEqual(d['input']['from_y'],512);self.assertEqual(d['input']['to_y'],513)
  self.assertEqual(d['when_in_range']['type'],'minecraft:squeeze')
 def test_lower_noise_and_lava_parameters_unchanged(self):
  n=json.loads(self.convert()[M.SHAPES['noise']]);self.assertEqual(n['sea_level'],32)
  o=json.loads(self.entries[M.SHAPES['noise']]);self.assertEqual(n['noise_router'],o['noise_router'])
 def test_no_lava_floor_skins_reintroduced(self):
  n=json.loads(self.convert()[M.SHAPES['noise']]);d=n['surface_rule']['sequence'][2]
  self.assertNotIn('minecraft:lava',json.dumps(d));self.assertIn('minecraft:magma_block',json.dumps(d))
 def test_native_r14_required_codec_present(self):
  p=json.loads(self.convert()[M.REQUIRED_PROCESSOR]);self.assertEqual(p['processors'],[{'processor_type':'neverfolia:height_r14_required'}])
 def test_profile_marks_new_world_and_no_roof_building(self):
  p=json.loads(self.convert()[M.PROFILE_PATH]);self.assertTrue(p['new_world_required']);self.assertFalse(p['roof_building_allowed']);self.assertEqual(p['building_max_y'],512)
 def test_old_roof_build_fields_removed(self):
  m=json.loads(self.convert()[M.SHAPES['core']]);self.assertNotIn('roof_build_min_y',m);self.assertEqual(m['technical_padding_y'],[513,527])
 def test_unrelated_source_payloads_preserved(self):
  o=self.convert();changed=set(M.SHAPES.values())|set(M.FINGERPRINTS)
  for p,raw in self.entries.items():
   if p not in changed:self.assertEqual(o[p],raw)
 def test_source_not_mutated(self):
  old=copy.deepcopy(self.entries);self.convert();self.assertEqual(self.entries,old)
 def test_changed_source_contract_rejected(self):
  for p in M.SHAPES.values():
   e=dict(self.entries);e[p]+=b' '
   with self.subTest(path=p),self.assertRaises(ValueError):self.convert(e)
 def test_missing_contract_rejected(self):
  e=dict(self.entries);e.pop(M.SHAPES['density'])
  with self.assertRaises(ValueError):self.convert(e)
 def test_reapplication_rejected(self):
  with self.assertRaises(ValueError):self.convert(self.convert())
 def test_stale_fingerprint_rejected_without_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   src=Path(tmp)/'src.zip';out=Path(tmp)/'out.zip'
   with zipfile.ZipFile(src,'w') as z:
    for p,raw in self.entries.items():z.writestr(p,raw)
    for p in M.FINGERPRINTS:z.writestr(p,json.dumps({'content_sha256':'0'*64}))
   with self.assertRaises(ValueError):M.build(src,out)
   self.assertFalse(out.exists())
 def fingerprinted(self,path):
  e=dict(self.entries);f={'schema':1,'worldgen_id':'NN-DEV-1','algorithm':self.fp.ALGORITHM,'content_sha256':self.fp.content_digest(e),'entry_count_excluding_fingerprint':len(e)}
  with zipfile.ZipFile(path,'w') as z:
   for p,raw in e.items():z.writestr(p,raw)
   for p in M.FINGERPRINTS:z.writestr(p,M.encoded(f))
 def test_identical_inputs_have_reproducible_zip_bytes(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Path(tmp)/'s.zip';a=Path(tmp)/'a.zip';b=Path(tmp)/'b.zip';self.fingerprinted(s)
   M.build(s,a);M.build(s,b);self.assertEqual(a.read_bytes(),b.read_bytes())
 def test_new_fingerprint_matches_new_payloads(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Path(tmp)/'s.zip';a=Path(tmp)/'a.zip';self.fingerprinted(s);M.build(s,a)
   e=self.fp.read_entries(a);h=self.fp.content_digest(e)
   for p in M.FINGERPRINTS:self.assertEqual(json.loads(e[p])['content_sha256'],h)
 def test_output_refuses_existing_file(self):
  with self.assertRaises(ValueError):M.build(self.src,self.src)
 def test_twenty_structures_update_padding_not_layout(self):
  e=dict(self.entries);records=[]
  for i in range(20):
   sid='test:structure_'+str(i);records.append({'id':sid});e[f'data/test/worldgen/structure/structure_{i}.json']=M.encoded({'type':'minecraft:jigsaw','size':4,'dimension_padding':{'bottom':5,'top':517}})
  e['nevernether-structure-integration-manifest.json']=M.encoded({'approved_structures':records,'neverfolia_hardening':{}})
  o=self.convert(e)
  for i in range(20):
   v=json.loads(o[f'data/test/worldgen/structure/structure_{i}.json']);self.assertEqual(v['dimension_padding'],{'bottom':5,'top':20});self.assertEqual(v['size'],4)
 def test_incomplete_structure_set_rejected(self):
  e=dict(self.entries);e['nevernether-structure-integration-manifest.json']=M.encoded({'approved_structures':[]})
  with self.assertRaises(ValueError):self.convert(e)

if __name__=='__main__':unittest.main(verbosity=2)
