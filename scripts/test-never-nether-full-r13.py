#!/usr/bin/env python3
"""Independent FULL-only evidence contracts; synthetic fixtures, not game worlds."""
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

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('full_r13_compare',ROOT/'qa/nevernether-r13/compare-full1599.py')
F=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(F)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


def fixture(directory,reverse=False):
    root=directory/'plugins/NN-STAGE-R8-QA';root.mkdir(parents=True)
    coords=[[64,0],[65,0]]
    if reverse:coords.reverse()
    states={'0':'minecraft:air','1':'minecraft:lava[level=1]','2':'minecraft:cave_air','3':'minecraft:crimson_stem[axis=y]'}
    write(root/'states.json',states)
    rows=[{'entry':0,'file':'fixture.class','sha256':'a'*64}]
    payload=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    write(directory/'runtime-inventory.json',{'files':rows,'payload_sha256':payload,'manifest_sha256':'b'*64})
    evidence={'schema':2,'stage':'completed','seed':7270913,'process_exit_code':0,'forced_stop':False,
        'runtime_unchanged':True,'inputs_unchanged':True,'runtime_payload_sha256':payload,'classpath_manifest_sha256':'b'*64,
        'pack_sha256':'c'*64,'qa_plugin_sha256':'d'*64,'java_executable_sha256':'e'*64,'jvm_flags':['fixture'],
        'release_ready':False}
    write(directory/'run-evidence.json',evidence)
    report={'schema':1,'probe':'NN-FULL-R13','stage':'completed','seed':7270913,
        'plan':{'seed':7270913,'chunks':coords},'exact_r7_coverage_sha256':F.B.PLAN_SHA,
        'simulation_frozen_before_probe':True,'target_FULL_requests':4,
        'state_dictionary_sha256':F.C.digest(root/'states.json'),'observations':[]}
    for phase in F.PHASES:
        for x,z in coords:
            p=root/phase/f'{x}_{z}.bin.gz';p.parent.mkdir(exist_ok=True)
            raw=struct.pack('>6i',0x4e4e5238,1,x,z,-128,1024)+bytes(F.C.CELLS*4)
            p.write_bytes(gzip.compress(raw,mtime=0))
            meta=root/phase/f'{x}_{z}.substrate.nbt';meta.write_bytes(b'synthetic metadata: native contents validated elsewhere')
            report['observations'].append({'phase':phase,'x':x,'z':z,'status':'minecraft:full',
                'simulation_frozen':True,'capture_protocol':'immutable-section-copy-r11',
                'capture_status_before':'minecraft:full','capture_status_after':'minecraft:full',
                'file':phase+'/'+p.name,'bytes':p.stat().st_size,'sha256':F.C.digest(p),
                'metadata_file':phase+'/'+meta.name,'metadata_sections':64,'metadata_sha256':F.C.digest(meta)})
    write(root/'report.json',report)
    return report


class FullEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.a=self.root/'a';self.b=self.root/'b';self.ra=fixture(self.a);self.rb=fixture(self.b,True)
        # Coverage validation itself is exercised without patches below; reduce
        # only fixture size here to test independent FULL protocol contracts.
        def validate(plan,seed):
            if seed!=7270913 or plan.get('seed')!=seed or sorted(plan.get('chunks',[]))!=[[64,0],[65,0]]:
                raise ValueError('Synthetic coverage mismatch')
            return plan
        self.patches=[patch.object(F.B,'COUNT',2),patch.object(F.B,'validate',validate)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def save(self):write(self.a/'plugins/NN-STAGE-R8-QA/report.json',self.ra)
    def reject(self):
        with self.assertRaises((ValueError,KeyError,OSError,TypeError)):F.compare(self.a,self.b)
    def evidence(self,key,val):
        p=self.a/'run-evidence.json';o=json.loads(p.read_text());o[key]=val;write(p,o)
    def change(self,phase,index,state):
        row=next(r for r in self.ra['observations'] if r['phase']==phase and r['x']==64)
        path=self.a/'plugins/NN-STAGE-R8-QA'/row['file'];raw=bytearray(gzip.decompress(path.read_bytes()))
        struct.pack_into('>I',raw,24+index*4,state);path.write_bytes(gzip.compress(raw,mtime=0))
        row.update(bytes=path.stat().st_size,sha256=F.C.digest(path));self.save()
    def test_matching_full_only_does_not_claim_pre_full_gate_or_release(self):
        r=F.compare(self.a,self.b);self.assertTrue(r['full_and_settled_equal']);self.assertTrue(r['late_changes_absent'])
        self.assertEqual(r['carvers_light_stage_gate'],'NOT_EVALUATED_BY_THIS_PROTOCOL');self.assertFalse(r['release_ready'])
    def test_ordinary_comparator_rejects_full_protocol(self):
        with self.assertRaises(ValueError):F.C.load(self.a)
    def test_old_protocol_cannot_be_relabeled_success(self):
        self.ra['probe']='NN-STAGE-R8';self.save();self.reject()
    def test_incomplete_phase_coverage_rejected(self):
        self.ra['observations'].pop();self.save();self.reject()
    def test_duplicate_observation_rejected(self):
        self.ra['observations'].append(copy.deepcopy(self.ra['observations'][0]));self.save();self.reject()
    def test_non_full_capture_rejected(self):
        self.ra['observations'][0]['status']='minecraft:spawn';self.save();self.reject()
    def test_changed_capture_status_rejected(self):
        self.ra['observations'][0]['capture_status_before']='minecraft:spawn';self.save();self.reject()
    def test_unfrozen_capture_rejected(self):
        self.ra['observations'][0]['simulation_frozen']=False;self.save();self.reject()
    def test_wrong_full_request_count_rejected(self):
        self.ra['target_FULL_requests']=0;self.save();self.reject()
    def test_wrong_order_rejected(self):
        self.ra['plan']['chunks'].reverse();self.save();self.reject()
    def test_runtime_identity_difference_rejected(self):
        self.evidence('qa_plugin_sha256','f'*64);self.reject()
    def test_abnormal_stop_rejected(self):
        self.evidence('process_exit_code',-9);self.reject()
    def test_forced_stop_not_accepted_even_at_exit_zero(self):
        self.evidence('forced_stop',True);self.reject()
    def test_runtime_inventory_change_rejected(self):
        p=self.a/'runtime-inventory.json';o=json.loads(p.read_text());o['files'][0]['sha256']='f'*64;write(p,o);self.reject()
    def test_metadata_corruption_rejected(self):
        (self.a/'plugins/NN-STAGE-R8-QA/full/64_0.substrate.nbt').write_bytes(b'changed');self.reject()
    def test_block_snapshot_corruption_rejected(self):
        (self.a/'plugins/NN-STAGE-R8-QA/full/64_0.bin.gz').write_bytes(b'changed');self.reject()
    def test_fluids_and_air_variants_remain_in_comparison(self):
        self.change('settled',1,1);self.change('settled',2,2)
        r=F.compare(self.a,self.b);self.assertEqual(r['cross_order']['settled']['different_blocks'],2)
    def test_flora_and_roof_remain_in_comparison(self):
        self.change('settled',F.C.CELLS-1,3);r=F.compare(self.a,self.b)
        self.assertEqual(r['cross_order']['settled']['samples'][0]['position'][1],895)
    def test_late_changes_remain_explicit(self):
        self.change('settled',1,3);r=F.compare(self.a,self.b)
        self.assertEqual(r['late_changes']['forward']['different_blocks'],1);self.assertFalse(r['late_changes_absent'])
    def test_path_escape_rejected(self):
        self.ra['observations'][0]['file']='../../outside';self.save();self.reject()


class OriginalCoverageTests(unittest.TestCase):
    def test_real_pinned_coverage_contract_is_not_relaxed(self):
        plan=F.B.original_plan();self.assertEqual(len(F.B.validate(plan,7270913)['chunks']),1599)
        plan['chunks'].pop()
        with self.assertRaises(ValueError):F.B.validate(plan,7270913)
    def test_java_source_keeps_owning_thread_and_capture_checks(self):
        text=(ROOT/'qa/nevernether-r13/NeverNetherFullProbeR13.java').read_text()
        for marker in ('status!=ChunkStatus.FULL','TickThread.isTickThreadFor(level,x,z)',
                       'chunk.getPersistedStatus()!=status','runsNormally()','isSteppingForward()',F.B.PLAN_SHA):
            self.assertIn(marker,text)
        self.assertIn('"NN-FULL-R13"',text)
        self.assertNotIn('ChunkStatus.CARVERS,',text)

if __name__=='__main__':unittest.main(verbosity=2)
