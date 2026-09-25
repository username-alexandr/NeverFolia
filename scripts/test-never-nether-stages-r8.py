#!/usr/bin/env python3
"""Synthetic isolation/byte identity/coverage contracts, not real worldgen tests."""
from __future__ import annotations
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
C=module('nn_stage_compare',ROOT/'scripts/compare-never-nether-stages-r8.py')
R=module('nn_stage_runner',ROOT/'qa/nevernether-r8/run-stage-probe.py')
P=module('nn_stage_patcher',ROOT/'scripts/apply-never-nether-experiment-r8.py')

def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

def fixture(root,reverse=False):
    chunks=[[64,0],[65,0]]
    if reverse:chunks.reverse()
    sample=root/'plugins/NN-STAGE-R8-QA';sample.mkdir(parents=True)
    write(sample/'states.json',{'0':'minecraft:air','1':'minecraft:lava[level=1]','2':'minecraft:crimson_stem[axis=y]','3':'minecraft:cave_air'})
    rows=[{'entry':0,'file':'example.class','sha256':'a'*64}]
    payload=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    write(root/'runtime-inventory.json',{'schema':1,'files':rows,'payload_sha256':payload,'manifest_sha256':'c'*64})
    run={'schema':2,'stage':'completed','seed':1,'process_exit_code':0,'forced_stop':False,
         'runtime_unchanged':True,'inputs_unchanged':True,'runtime_payload_sha256':payload,
         'classpath_manifest_sha256':'c'*64,'pack_sha256':'d'*64,'qa_plugin_sha256':'e'*64,'java_executable_sha256':'f'*64,'jvm_flags':['-ea']}
    write(root/'run-evidence.json',run)
    report={'schema':1,'probe':'NN-STAGE-R8','stage':'completed','seed':1,'plan':{'seed':1,'chunks':chunks},
            'simulation_frozen_before_probe':True,'target_FULL_requests':0,'state_dictionary_sha256':C.digest(sample/'states.json'),'observations':[]}
    for phase in C.PHASES:
        for x,z in chunks:
            raw=struct.pack('>6i',0x4e4e5238,1,x,z,-128,1024)+bytes(C.CELLS*4)
            path=sample/phase/f'{x}_{z}.bin.gz';path.parent.mkdir(exist_ok=True);path.write_bytes(gzip.compress(raw,mtime=0))
            report['observations'].append({'phase':phase,'x':x,'z':z,'simulation_frozen':True,
                'status':'minecraft:carvers' if phase=='carvers' else 'minecraft:spawn',
                'class':'net.minecraft.world.level.chunk.ProtoChunk','file':phase+'/'+path.name,
                'sha256':C.digest(path),'bytes':path.stat().st_size})
    write(sample/'report.json',report)
    return report

class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.a=self.root/'a';self.b=self.root/'b';self.ra=fixture(self.a);self.rb=fixture(self.b,True)
    def tearDown(self):self.tmp.cleanup()
    def report(self,which,value):write(which/'plugins/NN-STAGE-R8-QA/report.json',value)
    def run_change(self,key,value):
        p=self.a/'run-evidence.json';o=json.loads(p.read_text());o[key]=value;write(p,o)
    def reject(self):
        with self.assertRaises((ValueError,OSError)):C.compare(self.a,self.b)
    def change_voxel(self,phase,index,value):
        row=next(r for r in self.rb['observations'] if r['phase']==phase and r['x']==64)
        p=self.b/'plugins/NN-STAGE-R8-QA'/row['file'];raw=bytearray(gzip.decompress(p.read_bytes()));struct.pack_into('>I',raw,24+index*4,value)
        p.write_bytes(gzip.compress(raw,mtime=0));row['sha256']=C.digest(p);row['bytes']=p.stat().st_size;self.report(self.b,self.rb)
    def test_exact_reverse_all_three_stages_pass(self):self.assertTrue(C.compare(self.a,self.b)['generation_stage_equal'])
    def test_same_order_control_supported(self):
        self.rb['plan']['chunks'].reverse();self.report(self.b,self.rb);self.assertTrue(C.compare(self.a,self.b,'same')['generation_stage_equal'])
    def test_wrong_order_rejected(self):
        self.rb['plan']['chunks'].reverse();self.report(self.b,self.rb);self.reject()
    def test_flowing_lava_not_normalized(self):
        self.change_voxel('light',10,1);o=C.compare(self.a,self.b);self.assertEqual(o['cross_order']['light']['different_blocks'],1);self.assertFalse(o['generation_stage_equal'])
    def test_plants_not_ignored(self):
        self.change_voxel('light',800,2);self.assertEqual(C.compare(self.a,self.b)['cross_order']['light']['different_blocks'],1)
    def test_air_variants_not_normalized(self):
        self.change_voxel('light',1,3);self.assertFalse(C.compare(self.a,self.b)['generation_stage_equal'])
    def test_roof_zone_not_excluded(self):
        self.change_voxel('light',C.CELLS-1,2);o=C.compare(self.a,self.b);self.assertEqual(o['cross_order']['light']['samples'][0]['position'][1],895)
    def test_late_neighbor_writes_reported(self):
        self.change_voxel('settled',5,2);o=C.compare(self.a,self.b);self.assertEqual(o['late_changes']['right']['different_blocks'],1)
    def test_changed_input_file_hash_rejected(self):self.run_change('pack_sha256','b'*64);self.reject()
    def test_runtime_changed_during_run_rejected(self):self.run_change('runtime_unchanged',False);self.reject()
    def test_missing_binary_provenance_rejected(self):self.run_change('runtime_payload_sha256',None);self.reject()
    def test_inventory_tampering_rejected(self):
        p=self.a/'runtime-inventory.json';o=json.loads(p.read_text());o['files'][0]['sha256']='1'*64;write(p,o);self.reject()
    def test_same_classpath_names_different_bytes_rejected(self):
        p=self.a/'runtime-inventory.json';o=json.loads(p.read_text());o['files'][0]['sha256']='1'*64;o['payload_sha256']=hashlib.sha256(json.dumps(o['files'],sort_keys=True,separators=(',',':')).encode()).hexdigest();write(p,o);self.run_change('runtime_payload_sha256',o['payload_sha256']);self.reject()
    def test_forced_stop_rejected(self):self.run_change('forced_stop',True);self.reject()
    def test_nonzero_exit_rejected(self):self.run_change('process_exit_code',1);self.reject()
    def test_failed_probe_rejected(self):self.ra['stage']='failed';self.report(self.a,self.ra);self.reject()
    def test_unfrozen_run_rejected(self):self.ra['simulation_frozen_before_probe']=False;self.report(self.a,self.ra);self.reject()
    def test_unfrozen_observation_rejected(self):self.ra['observations'][0]['simulation_frozen']=False;self.report(self.a,self.ra);self.reject()
    def test_later_carvers_status_rejected(self):self.ra['observations'][0]['status']='minecraft:features';self.report(self.a,self.ra);self.reject()
    def test_first_light_full_rejected(self):self.ra['observations'][2]['status']='minecraft:full';self.report(self.a,self.ra);self.reject()
    def test_first_observation_must_be_protochunk(self):self.ra['observations'][0]['class']='net.minecraft.world.level.chunk.LevelChunk';self.report(self.a,self.ra);self.reject()
    def test_partial_coverage_rejected(self):self.ra['observations'].pop();self.report(self.a,self.ra);self.reject()
    def test_duplicate_observation_rejected(self):self.ra['observations'].append(copy.deepcopy(self.ra['observations'][0]));self.report(self.a,self.ra);self.reject()
    def test_empty_plan_rejected(self):self.ra['plan']['chunks']=[];self.report(self.a,self.ra);self.reject()
    def test_dictionary_change_rejected(self):write(self.a/'plugins/NN-STAGE-R8-QA/states.json',{'0':'minecraft:air'});self.reject()
    def test_unregistered_state_index_rejected(self):self.change_voxel('light',1,999);self.reject()
    def test_snapshot_wrong_header_rejected(self):
        p=self.root/'wrong.gz';p.write_bytes(gzip.compress(bytes(24+C.CELLS*4),mtime=0))
        with self.assertRaises(ValueError):C.read_snapshot(p,(64,0))
    def test_snapshot_truncated_rejected(self):
        p=self.root/'wrong.gz';p.write_bytes(gzip.compress(b'NNR8',mtime=0))
        with self.assertRaises(ValueError):C.read_snapshot(p,(64,0))
    def test_snapshot_trailing_bytes_rejected(self):
        p=self.root/'wrong.gz';p.write_bytes(gzip.compress(struct.pack('>6i',0x4e4e5238,1,64,0,-128,1024)+bytes(C.CELLS*4)+b'x',mtime=0))
        with self.assertRaises(ValueError):C.read_snapshot(p,(64,0))
    def test_traversal_not_a_snapshot(self):self.ra['observations'][0]['file']='../../elsewhere';self.report(self.a,self.ra);self.reject()
    def test_no_release_acceptance_even_when_equal(self):self.assertFalse(C.compare(self.a,self.b)['release_ready'])

class InputTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_plan_validation_rejects_float_bool_duplicate_and_near_spawn(self):
        for chunks in [[[64.5,0]],[[True,64]],[[64,0],[64,0]],[[0,0]],[],[[100001,0]]]:
            p=self.root/'plan.json';write(p,{'seed':1,'chunks':chunks})
            with self.subTest(chunks=chunks),self.assertRaises(ValueError):R.checked_plan(p,1,False)
    def test_reverse_plan_preserves_input(self):
        p=self.root/'plan.json';write(p,{'seed':1,'chunks':[[-64,0],[65,0]]});before=p.read_bytes()
        self.assertEqual(R.checked_plan(p,1,True)['chunks'],[[65,0],[-64,0]]);self.assertEqual(p.read_bytes(),before)
    def test_runtime_hash_detects_class_changes(self):
        r=self.root/'runtime';r.mkdir();(r/'classpath.txt').write_text('classes\n');(r/'classes').mkdir();(r/'classes/A.class').write_bytes(b'a')
        _,a=R.runtime_inventory(r);(r/'classes/A.class').write_bytes(b'b');_,b=R.runtime_inventory(r)
        self.assertEqual(a['manifest_sha256'],b['manifest_sha256']);self.assertNotEqual(a['payload_sha256'],b['payload_sha256'])
    def test_runtime_rejects_external_paths(self):
        r=self.root/'runtime';r.mkdir();(r/'classpath.txt').write_text('../other\n')
        with self.assertRaises(ValueError):R.runtime_inventory(r)
    def test_candidate_patcher_exact_hash_and_idempotence(self):
        fixture=P.OLD_CALL+'\n'+P.OLD_START+'\n'
        with patch.object(P,'EXPECTED',hashlib.sha256(fixture.encode()).hexdigest()):
            out=P.transform(fixture);self.assertEqual(P.transform(out),out)
            with self.assertRaises(ValueError):P.transform(fixture+'changed')
    def test_candidate_patcher_refuses_changed_installed_code(self):
        fixture=P.OLD_CALL+'\n'+P.OLD_START+'\n'
        with patch.object(P,'EXPECTED',hashlib.sha256(fixture.encode()).hexdigest()):
            out=P.transform(fixture)
            with self.assertRaises(ValueError):P.transform(out+'unrelated edit')

if __name__=='__main__':unittest.main(verbosity=2)
