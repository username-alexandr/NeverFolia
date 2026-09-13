#!/usr/bin/env python3
"""Synthetic contracts; not a substitute for saved-world or native parser QA."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/filename)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
F=load('r7_fixtures','test-never-nether-source-inputs.py')
A=load('r7_audit','audit-never-nether-worldgen-r7.py')
R=load('r7_repair','nevernether_jigsaw_states_r7.py')
OLD='minecraft:chisled_polished_blackstone';NEW='minecraft:chiseled_polished_blackstone'

def template(value=OLD,kind='minecraft:jigsaw',**extra):
    return F.template(blocks=[{'state':0,'pos':[1,2,3],'nbt':{'id':kind,'final_state':value,'pool':'minecraft:empty',**extra}}])
def discovery():
    sid='test:one';return {'status':'completed','mode':'discover','seed':1,'forced_structure_placement':False,'attempts':[{}],
        'first_natural_starts':{sid:{'id':sid,'ChunkX':-1,'ChunkZ':0,'observed_chunk_x':-1,'observed_chunk_z':0,
            'observed_status':'structure_starts','Children':[{'BB':[-16,10,0,-1,20,15],'pool_element':{'element_type':'minecraft:single_pool_element','location':'test:room'}}]}}}

class Repairs(unittest.TestCase):
    def test_only_expected_jigsaw_string_changes(self):
        source=template(name='keep',Items=[{'Slot':2,'id':'minecraft:diamond'}]);out=R.repair(source,OLD,NEW,1)
        original=R.parser()(gzip.decompress(source));expected=copy.deepcopy(original);expected['blocks'][0]['nbt']['final_state']=NEW
        self.assertEqual(R.parser()(gzip.decompress(out)),expected)
        self.assertEqual(gzip.decompress(out),gzip.decompress(source).replace(R.encoded_field(OLD),R.encoded_field(NEW)))
    def test_repeatable_gzip_bytes(self):self.assertEqual(R.repair(template(),OLD,NEW,1),R.repair(template(),OLD,NEW,1))
    def test_uncompressed_input_remains_uncompressed(self):
        out=R.repair(gzip.decompress(template()),OLD,NEW,1);self.assertFalse(out.startswith(b'\x1f\x8b'))
    def test_non_jigsaw_field_not_changed(self):
        with self.assertRaises(ValueError):R.repair(template(kind='minecraft:chest'),OLD,NEW,1)
    def test_missing_value_rejected(self):
        with self.assertRaises(ValueError):R.repair(template('minecraft:air'),OLD,NEW,1)
    def test_count_mismatch_rejected(self):
        with self.assertRaises(ValueError):R.repair(template(),OLD,NEW,2)
    def test_unrelated_same_named_field_causes_atomic_refusal(self):
        source=F.template(blocks=[{'nbt':{'id':'minecraft:jigsaw','final_state':OLD}}],metadata={'final_state':OLD})
        with self.assertRaises(ValueError):R.repair(source,OLD,NEW,1)
    def test_invalid_contract_rejected(self):
        for count in (0,-1,True,1.5):
            with self.subTest(count=count),self.assertRaises(ValueError):R.repair(template(),OLD,NEW,count)
        with self.assertRaises(ValueError):R.repair(template(),OLD,OLD,1)
    def test_corrupt_nbt_rejected(self):
        with self.assertRaises(ValueError):R.repair(b'invalid',OLD,NEW,1)
    def test_small_bounded_payload_limit(self):
        with patch.object(R,'MAX_NBT',10),self.assertRaises(ValueError):R.repair(template(),OLD,NEW,1)
    def test_all_files_verified_before_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'profile.json';raw=template();rule={'path':'data/test/structure/a.nbt','input_sha256':hashlib.sha256(raw).hexdigest(),'old':OLD,'new':NEW,'count':1}
            profile={'sources':{'test':{'source_sha256':'pinned','repairs':[rule,{**rule,'path':'data/test/structure/missing.nbt'}]}}};p.write_text(json.dumps(profile))
            obj=SimpleNamespace(sha256='pinned',entries={PurePosixPath(rule['path']):raw},decoded={},provenance={},compatibility_changes=[],dependency_cache={})
            before=copy.deepcopy(vars(obj))
            with patch.object(R,'PROFILE',p),self.assertRaises(ValueError):R.apply_states(obj,'test')
            self.assertEqual(vars(obj),before)
    def test_success_records_exact_output_and_clears_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'profile.json';raw=template();path=PurePosixPath('data/test/structure/a.nbt')
            rule={'path':str(path),'input_sha256':hashlib.sha256(raw).hexdigest(),'old':OLD,'new':NEW,'count':1}
            p.write_text(json.dumps({'sources':{'test':{'source_sha256':'pinned','repairs':[rule]}}}))
            obj=SimpleNamespace(sha256='pinned',entries={path:raw},decoded={path:{}},provenance={},compatibility_changes=[],dependency_cache={'old':1})
            with patch.object(R,'PROFILE',p):R.apply_states(obj,'test')
            self.assertEqual(obj.entries[path],R.repair(raw,OLD,NEW,1));self.assertFalse(obj.decoded);self.assertFalse(obj.dependency_cache)
            self.assertEqual(obj.compatibility_changes[0]['output_sha256'],hashlib.sha256(obj.entries[path]).hexdigest())
    def test_unrecognized_source_never_guessed(self):
        obj=SimpleNamespace(sha256='wrong',entries={});before=copy.deepcopy(vars(obj));R.apply_states(obj,'dungeons_and_taverns');self.assertEqual(vars(obj),before)

class Observations(unittest.TestCase):
    def test_start_is_not_claimed_full_or_walkable(self):
        with patch.object(A,'EXPECTED',{'test:one'}):r=A.summarize(discovery())
        self.assertTrue(r['natural_starts_complete']);self.assertFalse(r['all_blocks_generated_verified']);self.assertFalse(r['walkability_tested']);self.assertFalse(r['release_ready'])
    def test_partial_and_failed_rejected(self):
        for status in ('running','failed',None):
            d=discovery();d['status']=status
            with self.subTest(status=status),self.assertRaises(ValueError):A.summarize(d)
    def test_forced_not_called_natural(self):
        d=discovery();d['forced_structure_placement']=True
        with self.assertRaises(ValueError):A.summarize(d)
    def test_empty_not_pass(self):
        d=discovery();d['first_natural_starts']={}
        with self.assertRaises(ValueError):A.summarize(d)
    def test_identifier_mismatch_rejected(self):
        d=discovery();d['first_natural_starts']['test:one']['id']='test:other'
        with self.assertRaises(ValueError):A.summarize(d)
    def test_wrong_observed_chunk_rejected(self):
        d=discovery();d['first_natural_starts']['test:one']['observed_chunk_x']=0
        with self.assertRaises(ValueError):A.summarize(d)
    def test_invalid_bbox_rejected(self):
        for b in ([0,0,0,-1,1,1],[0,True,0,1,1,1],[0,1]):
            with self.subTest(b=b),self.assertRaises(ValueError):A.bbox([{'BB':b}])
    def test_empty_children_rejected(self):
        with self.assertRaises(ValueError):A.bbox([])
    def test_roof_out_of_bounds_fails_observation(self):
        d=discovery();d['first_natural_starts']['test:one']['Children'][0]['BB'][4]=384
        self.assertFalse(A.summarize(d)['structures']['test:one']['body_bounds_passed'])
    def test_bbox_overlap_is_not_labelled_solid_collision(self):
        d=discovery();other=copy.deepcopy(d['first_natural_starts']['test:one']);other['id']='test:two';d['first_natural_starts']['test:two']=other
        r=A.summarize(d);self.assertFalse(r['bbox_policy_passed']);self.assertIn('not_solid_collision',r['bbox_policy_findings'][0]['classification'])
    def test_separate_vertical_boxes_do_not_overlap(self):self.assertIsNone(A.intersection([0,0,0,10,10,10],[0,11,0,10,20,10]))
    def test_quota_count_shared_across_variants(self):
        a={'element_type':'neverfolia:limited_single_pool_element','name':'group','max_count':1}
        q=A.quotas([a,{**a,'location':'different'}]);self.assertFalse(q['group']['passed']);self.assertEqual(q['group']['used'],2)
    def test_nested_quota_and_stricter_cap(self):
        a={'element_type':'neverfolia:limited_single_pool_element','name':'group','max_count':4}
        q=A.quotas([{'element_type':'minecraft:list_pool_element','elements':[a,{**a,'max_count':1}]}]);self.assertFalse(q['group']['passed']);self.assertEqual(q['group']['limit'],1)
    def test_nbt_storage_wrappers_not_layout_changes(self):self.assertEqual(A.digest(A.layout({'BB':{'$int_array':[0,1,2,3,4,5]}})),A.digest(A.layout({'BB':[0,1,2,3,4,5]})))
    def test_observation_metadata_does_not_change_layout_hash(self):self.assertEqual(A.layout({'id':'test:a','observed_status':'full'}),{'id':'test:a'})

class SavedCoverage(unittest.TestCase):
    def inputs(self):
        d=discovery();d['first_natural_starts']['test:one']['Children'][0]['BB'][3]=15
        report=A.summarize(d);root={'xPos':-1,'zPos':0,'Status':'minecraft:full',
            'structures':{'starts':{'test:one':A.layout(d['first_natural_starts']['test:one'])}}}
        return d,report,root,{'seed':1,'chunks':[[-1,0]]}
    def test_partial_footprint_never_marked_complete(self):
        d,report,root,plan=self.inputs()
        with patch.object(A,'load_reader',return_value=SimpleNamespace(read_chunk_nbt=lambda *args:root)):
            out=A.verify_saved(report,d,Path('.'),plan,allow_partial=True)
        self.assertFalse(out['all_blocks_generated_verified']);self.assertEqual(out['complete_footprint_count'],0)
        self.assertTrue(out['all_saved_layouts_match_discovery'])
    def test_strict_footprint_mode_rejects_incomplete(self):
        d,report,root,plan=self.inputs()
        with patch.object(A,'load_reader',return_value=SimpleNamespace(read_chunk_nbt=lambda *args:root)),self.assertRaises(ValueError):
            A.verify_saved(report,d,Path('.'),plan)
    def test_non_full_saved_chunk_rejected(self):
        d,report,root,plan=self.inputs();root['Status']='minecraft:features'
        with patch.object(A,'load_reader',return_value=SimpleNamespace(read_chunk_nbt=lambda *args:root)),self.assertRaises(ValueError):
            A.verify_saved(report,d,Path('.'),plan,allow_partial=True)

C=load('r7_compare','compare-never-nether-persisted-r7.py')
class ExactSnapshots(unittest.TestCase):
    def test_palette_storage_order_does_not_change_blocks(self):
        palette=[{'Name':'minecraft:air'},{'Name':'minecraft:lava','Properties':{'level':'1'}}]
        pattern=[i%2 for i in range(4096)]
        a={'palette':palette,'data':{'$long_array':C.D.pack_indices(pattern,4)}}
        b={'palette':list(reversed(palette)),'data':{'$long_array':C.D.pack_indices([1-v for v in pattern],4)}}
        self.assertEqual(C.semantic_container(a,4096,4),C.semantic_container(b,4096,4))
    def test_flowing_lava_not_changed_to_air_or_source(self):
        h=lambda state:C.semantic_container({'palette':[state]},4096,4)
        air=h({'Name':'minecraft:air'});source=h({'Name':'minecraft:lava','Properties':{'level':'0'}})
        flowing=h({'Name':'minecraft:lava','Properties':{'level':'1'}})
        self.assertEqual(len({air,source,flowing}),3)
    def test_invalid_data_not_accepted_as_empty(self):
        with self.assertRaises(ValueError):C.semantic_container({'palette':[{'Name':'minecraft:air'},{'Name':'minecraft:stone'}],'data':{'$long_array':[]}},4096,4)
    def test_non_full_chunk_not_compared(self):
        root={'xPos':0,'zPos':0,'Status':'minecraft:features'}
        with self.assertRaises(ValueError):C.chunk_components(root,(0,0))
    def test_missing_biome_coverage_is_not_a_pass(self):
        with self.assertRaises(ValueError):C.chunk_components({'xPos':0,'zPos':0,'Status':'minecraft:full','sections':[{'Y':0,'block_states':{'palette':[{'Name':'minecraft:air'}]}}]},(0,0))
    def test_empty_comparison_is_not_pass(self):
        with self.assertRaises(ValueError):C.compare(Path('.'),Path('.'),[])

if __name__=='__main__':unittest.main(verbosity=2)
