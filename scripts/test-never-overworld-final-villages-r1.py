#!/usr/bin/env python3
"""Synthetic final-snapshot regressions; no generated-world claims."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('final_villages',Path(__file__).with_name('probe-never-overworld-final-villages-r1.py'))
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)


def fixture():
    areas=[]; roots={}
    for x,target in ((0,'minecraft:village_plains'),(64,'minecraft:village_desert')):
        boxes=[[x+3,130,3,x+5,138,5],[x+8,130,3,x+10,136,5]]
        cx=x//16; chunks=[list(p) for p in sorted(P.coverage(boxes))]
        areas.append({'kind':'village','target':target,'start_chunk':[cx,0],
                      'piece_boxes':boxes,'chunks':chunks})
        roots[(cx,0)]={'Status':'minecraft:full','xPos':cx,'zPos':0,'structures':{'starts':{
            target:{'id':target,'Children':[{'BB':{'$int_array':deepcopy(b)}} for b in boxes]}}}}
    plan={'schema':2,'source_sha':'a'*40,'normal_stop':True,'process_exit_code':0,'areas':areas,
          'phases':[{'name':'locate-and-initial-chunks','normal_stop':True,'process_exit_code':0,
                     'saved_initial_full_verified':True},
                    {'name':'complete-village-footprints','normal_stop':True,'process_exit_code':0,
                     'saved_all_full_verified':True}]}
    return plan,roots


def children(roots):
    return roots[(0,0)]['structures']['starts']['minecraft:village_plains']['Children']


class FinalSnapshotTests(unittest.TestCase):
    def run_case(self,plan,roots):
        before=deepcopy((plan,roots)); diagnostic={}
        result=P.reconcile(plan,lambda x,z: roots[(x,z)],diagnostic)
        self.assertEqual((plan,roots),before)
        self.assertTrue(diagnostic['final_saved_geometry_covered'])
        self.assertFalse(diagnostic['visual_shape_accepted'])
        return result,diagnostic

    def test_unchanged_retains_original_plan(self):
        plan,roots=fixture(); result,d=self.run_case(plan,roots)
        self.assertTrue(d['villages'][0]['ordered_boxes_equal'])
        self.assertEqual(result['areas'][0]['planning_piece_boxes'],plan['areas'][0]['piece_boxes'])

    def test_reordering_keeps_multiplicity(self):
        plan,roots=fixture(); children(roots).reverse(); result,d=self.run_case(plan,roots)
        self.assertFalse(d['villages'][0]['ordered_boxes_equal'])
        self.assertTrue(d['villages'][0]['box_multisets_equal'])
        self.assertEqual(result['areas'][0]['piece_boxes'],list(reversed(plan['areas'][0]['piece_boxes'])))

    def test_final_y_change_preserved_not_discarded(self):
        plan,roots=fixture(); b=children(roots)[0]['BB']['$int_array']; b[1]+=7;b[4]+=7
        result,d=self.run_case(plan,roots)
        self.assertTrue(d['villages'][0]['xz_multisets_equal'])
        self.assertFalse(d['villages'][0]['box_multisets_equal'])
        self.assertEqual(result['areas'][0]['piece_boxes'][0][1],137)
        self.assertEqual(result['areas'][0]['planning_piece_boxes'][0][1],130)

    def test_changed_xz_inside_verified_chunks_is_reported(self):
        plan,roots=fixture();children(roots)[0]['BB']['$int_array'][3]+=1
        result,d=self.run_case(plan,roots)
        self.assertFalse(d['villages'][0]['xz_multisets_equal'])
        self.assertEqual(len(d['villages'][0]['added_box_instances']),1)

    def test_added_piece_in_verified_area_remains_observation(self):
        plan,roots=fixture();children(roots).append({'BB':[7,140,7,8,143,8]})
        result,d=self.run_case(plan,roots)
        self.assertEqual(d['villages'][0]['final_piece_count'],3)
        self.assertFalse(d['visual_shape_accepted'])

    def test_expansion_fails_before_reading_unverified_chunk(self):
        plan,roots=fixture();children(roots)[0]['BB']['$int_array'][3]=18
        read=[];d={}
        def get(x,z):read.append((x,z));return roots[(x,z)]
        with self.assertRaisesRegex(ValueError,'expands beyond'):
            P.reconcile(plan,get,d)
        self.assertEqual(read,[(0,0)])
        self.assertEqual(d['villages'][0]['unverified_required_chunks'],[[1,0]])
        self.assertIn('final_piece_boxes',d['villages'][0])

    def test_no_reads_after_abnormal_or_unverified_stop(self):
        for key,value in (('normal_stop',False),('normal_stop','true'),('process_exit_code',True),('process_exit_code',1)):
            plan,roots=fixture();plan[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                P.reconcile(plan,lambda *p:self.fail('unexpected NBT read'),{})
        plan,roots=fixture();plan['phases'][1]['saved_all_full_verified']=False
        with self.assertRaises(ValueError):P.reconcile(plan,lambda *p:self.fail('unexpected read'),{})

    def test_bad_status_coordinate_or_missing_start_fails(self):
        for key,value in (('Status','minecraft:features'),('xPos',1),('structures',{})):
            plan,roots=fixture();roots[(0,0)][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):P.reconcile(plan,lambda x,z:roots[(x,z)],{})

    def test_inverted_out_of_height_and_boolean_box_rejected(self):
        for bad in ([3,130,3,2,138,5],[3,130,3,5,600,5],[True,130,3,5,138,5]):
            plan,roots=fixture();children(roots)[0]['BB']['$int_array']=bad
            with self.subTest(box=bad),self.assertRaises(ValueError):P.reconcile(plan,lambda x,z:roots[(x,z)],{})

    def test_duplicate_and_missing_target_rejected(self):
        plan,roots=fixture();plan['areas'][1]['target']=plan['areas'][0]['target']
        with self.assertRaises(ValueError):P.reconcile(plan,lambda *p:self.fail('unexpected read'),{})

    def test_planning_coverage_cannot_be_silently_enlarged(self):
        plan,roots=fixture();plan['areas'][0]['chunks'].append([1,0])
        with self.assertRaisesRegex(ValueError,'planning coverage'):
            P.reconcile(plan,lambda *p:self.fail('unexpected read'),{})

    def test_duplicate_chunks_rejected(self):
        plan,roots=fixture();plan['areas'][0]['chunks']*=2
        with self.assertRaises(ValueError):P.reconcile(plan,lambda *p:self.fail('unexpected read'),{})

    def test_partial_failure_does_not_mutate_plan(self):
        plan,roots=fixture();before=deepcopy(plan)
        roots[(4,0)]['Status']='minecraft:features'
        with self.assertRaises(ValueError):P.reconcile(plan,lambda x,z:roots[(x,z)],{})
        self.assertEqual(plan,before)

    def test_negative_chunk_coverage(self):
        self.assertEqual(P.coverage([[-15,130,-15,-3,140,-3]]),{(-1,-1)})
        self.assertEqual(P.coverage([[-2,130,-2,2,140,2]]),{(-1,-1),(-1,0),(0,-1),(0,0)})


if __name__=='__main__':unittest.main(verbosity=2)
