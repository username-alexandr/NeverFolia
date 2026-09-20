#!/usr/bin/env python3
"""Synthetic bundle-integrity regressions; never distributed as world evidence."""
from copy import deepcopy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('bundle',Path(__file__).with_name('package-never-overworld-tree-village-r1.py'))
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
SHA='a'*40


def fixture(root):
    plan={'schema':2,'source_sha':SHA,'seed':P.SEED,'normal_stop':True,'process_exit_code':0,
          'final_village_geometry_verified':True,'areas':[],
          'phases':[{'name':'locate-and-initial-chunks','normal_stop':True,'process_exit_code':0,
                     'saved_initial_full_verified':True},
                    {'name':'complete-village-footprints','normal_stop':True,'process_exit_code':0,
                     'saved_all_full_verified':True}]}
    report={'schema':2,'source_sha':SHA,'seed':P.SEED,'areas':[],
            'natural_observation_pass':True,'saved_evidence_after_normal_stops':True,
            'final_village_geometry_verified':True,'production_ready':False,
            'village_visual_review_required':True,'underwater_wood_leaf_components':3}
    geometry={'schema':1,'source_sha':SHA,'final_saved_geometry_covered':True,
              'visual_shape_accepted':False,'villages':[]}
    for index,target in enumerate(P.FORESTS):
        x=index*1000;cx=x//16
        chunks=[[a,b] for a in range(cx-2,cx+3) for b in range(-2,3)]
        plan['areas'].append({'kind':'forest','target':target,'located_xz':[x,0],'chunks':chunks})
        report['areas'].append({'kind':'forest','target':target,'chunks_full':25,
                                'counts':{'wholly_submerged_components':1,'wood_leaf_components':1}})
    for index,target in enumerate(P.VILLAGES):
        x=4000+index*1024;cx=x//16
        boxes=[[x+3,130,3,x+5,138,5],[x+8,130,3,x+10,138,5]]
        chunks=[[cx,0]]
        plan['areas'].append({'kind':'village','target':target,'piece_boxes':boxes,'chunks':chunks,
            'start_chunk':[cx,0],'planning_piece_boxes':deepcopy(boxes),'planning_chunks':deepcopy(chunks)})
        name=target.split(':')[1]+'-y128.csv'
        out=io.StringIO();writer=csv.writer(out)
        writer.writerow(['x','z','y128_block','within_piece_xz_bbox'])
        for z in range(3,6):
            for a in range(x+3,x+11):
                inside=any(b[0]<=a<=b[3] for b in boxes)
                writer.writerow([a,z,'minecraft:water',int(inside)])
        (root/name).write_text(out.getvalue())
        report['areas'].append({'kind':'village','target':target,'chunks_full':1,'piece_count':2,
            'xz_bounds':[x+3,3,x+10,5],'plane_csv':name,'visual_shape_accepted':False,
            'counts':{'columns':24,'outside_piece_bbox_columns':6,'outside_piece_bbox_water':6}})
        geometry['villages'].append({'target':target,'initial_piece_boxes':deepcopy(boxes),
            'final_piece_boxes':deepcopy(boxes),'verified_chunks':deepcopy(chunks),
            'final_required_chunks':deepcopy(chunks),'unverified_required_chunks':[]})
    report['unique_full_chunks']=len({tuple(c) for a in plan['areas'] for c in a['chunks']})
    for filename,key in [('server.jar','jar_sha256'),('NeverOverworld.zip','pack_sha256')]:
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as z:z.writestr('SYNTHETIC-TEST-ONLY.txt',filename)
        raw=output.getvalue();(root/filename).write_bytes(raw)
        plan[key]=report[key]=P.digest(raw)
    initial=deepcopy(plan);initial.pop('final_village_geometry_verified')
    for area in initial['areas']:
        area.pop('planning_chunks',None);area.pop('planning_piece_boxes',None)
    for name,value in [('tree-village-plan.json',plan),('tree-village-natural.json',report),
                        ('tree-village-initial-plan.json',initial),('tree-village-geometry.json',geometry)]:
        (root/name).write_bytes(P.json_bytes(value))
    (root/'build-smoke.log').write_text('\n'.join(f'PASS {name} checks=1' for name in P.SMOKES)+'\nBUILD SUCCESSFUL\n')


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.artifacts=self.root/'artifacts';self.artifacts.mkdir();fixture(self.artifacts)
        self.out=self.root/'test.zip'
    def tearDown(self):self.tmp.cleanup()
    def change(self,name,action):
        path=self.artifacts/name;d=json.loads(path.read_text());action(d);path.write_bytes(P.json_bytes(d))
    def build(self):return P.build(self.artifacts,self.out,SHA,123)
    def fail_build(self):
        with self.assertRaises((ValueError,FileNotFoundError,zipfile.BadZipFile)):self.build()
        self.assertFalse(self.out.exists())
    def test_good_bundle_hashes_and_manual_scope(self):
        result=self.build();self.assertFalse(result['production_ready'])
        with zipfile.ZipFile(self.out) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read('server.jar'),(self.artifacts/'server.jar').read_bytes())
            self.assertEqual(z.read('datapacks/NeverOverworld.zip'),(self.artifacts/'NeverOverworld.zip').read_bytes())
            for line in z.read('SHA256SUMS.txt').decode().splitlines():
                digest,name=line.split('  ',1);self.assertEqual(digest,P.digest(z.read(name)))
            info=json.loads(z.read('BUILD-INFO.json'))
            self.assertFalse(info['production_ready']);self.assertTrue(info['village_visual_review_required'])
            self.assertNotIn('eula.txt',z.namelist())
    def test_existing_output_is_not_replaced(self):
        self.out.write_bytes(b'keep')
        with self.assertRaises(ValueError):self.build()
        self.assertEqual(self.out.read_bytes(),b'keep')
    def test_binary_mutation_rejected(self):
        (self.artifacts/'server.jar').write_bytes(b'changed');self.fail_build()
    def test_old_sha_rejected(self):
        self.change('tree-village-natural.json',lambda d:d.update(source_sha='b'*40));self.fail_build()
    def test_failed_or_string_success_rejected(self):
        self.change('tree-village-natural.json',lambda d:d.update(natural_observation_pass='true'));self.fail_build()
    def test_missing_stop_verification_rejected(self):
        self.change('tree-village-plan.json',lambda d:d['phases'][1].pop('saved_all_full_verified'));self.fail_build()
    def test_production_claim_rejected(self):
        self.change('tree-village-natural.json',lambda d:d.update(production_ready=True));self.fail_build()
    def test_missing_native_smoke_rejected(self):
        p=self.artifacts/'build-smoke.log';p.write_text(p.read_text().replace('PASS TreePreservationSmoke','FAIL TreePreservationSmoke'));self.fail_build()
    def test_truncated_csv_rejected(self):
        p=self.artifacts/'village_plains-y128.csv';p.write_text('\n'.join(p.read_text().splitlines()[:-1]));self.fail_build()
    def test_wrong_csv_counter_rejected(self):
        self.change('tree-village-natural.json',lambda d:d['areas'][3]['counts'].update(columns=999));self.fail_build()
    def test_false_csv_membership_rejected(self):
        p=self.artifacts/'village_plains-y128.csv';p.write_text(p.read_text().replace('minecraft:water,1','minecraft:water,0',1));self.fail_build()
    def test_extra_chunk_rejected(self):
        self.change('tree-village-plan.json',lambda d:d['areas'][0]['chunks'].append([999,999]));self.fail_build()
    def test_unverified_geometry_rejected(self):
        self.change('tree-village-geometry.json',lambda d:d['villages'][0]['unverified_required_chunks'].append([1,1]));self.fail_build()
    def test_original_snapshot_mismatch_rejected(self):
        self.change('tree-village-initial-plan.json',lambda d:d['areas'][3]['piece_boxes'][0].__setitem__(1,140));self.fail_build()
    def test_underwater_total_disagreement_rejected(self):
        self.change('tree-village-natural.json',lambda d:d.update(underwater_wood_leaf_components=7));self.fail_build()
    def test_duplicate_json_keys_rejected(self):
        p=self.artifacts/'tree-village-plan.json';p.write_text('{"schema":2,"schema":2}');self.fail_build()


if __name__=='__main__':unittest.main(verbosity=2)
