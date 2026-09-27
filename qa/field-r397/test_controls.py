#!/usr/bin/env python3
"""Unit tests only: these fixtures do not simulate a running Minecraft server."""
from pathlib import Path
import copy,hashlib,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_controls as runner
from control_contract import SEED,TARGETS,validate_observation,success_marker

class ReportTests(unittest.TestCase):
    def doc(self,reverse=False):
        points=sorted(TARGETS,key=lambda p:str(p[0])+','+str(p[1]),reverse=reverse)
        return {'pass':True,'seed':SEED,'reverse_order':reverse,'completed_chunks':54,'chunks':[{'chunk_x':x,'chunk_z':z,'min_y':-511,'max_y':128,'water_sha256':'a'*64,'block_counts':{'minecraft:air':640*256}} for x,z in points]}
    def reject(self,change):
        d=self.doc();change(d)
        with self.assertRaises(ValueError):validate_observation(d,False)
    def test_target_count(self):self.assertEqual(len(TARGETS),54)
    def test_forward(self):validate_observation(self.doc(),False)
    def test_reverse(self):validate_observation(self.doc(True),True)
    def test_failed(self):self.reject(lambda d:d.update({'pass':False}))
    def test_wrong_seed(self):self.reject(lambda d:d.update({'seed':1}))
    def test_string_seed(self):self.reject(lambda d:d.update({'seed':str(SEED)}))
    def test_wrong_direction(self):self.reject(lambda d:d.update({'reverse_order':True}))
    def test_integer_direction(self):self.reject(lambda d:d.update({'reverse_order':0}))
    def test_missing_row(self):self.reject(lambda d:d['chunks'].pop())
    def test_extra_row(self):self.reject(lambda d:d['chunks'].append(d['chunks'][0]))
    def test_duplicate_row(self):self.reject(lambda d:d['chunks'].__setitem__(1,d['chunks'][0]))
    def test_bad_coordinate(self):self.reject(lambda d:d['chunks'][0].update({'chunk_x':100000}))
    def test_bad_scope(self):self.reject(lambda d:d['chunks'][0].update({'min_y':-64}))
    def test_bad_digest(self):self.reject(lambda d:d['chunks'][0].update({'water_sha256':'abc'}))
    def test_bad_census(self):self.reject(lambda d:d['chunks'][0].update({'block_counts':{'minecraft:air':1}}))
    def test_negative_census(self):self.reject(lambda d:d['chunks'][0].update({'block_counts':{'minecraft:air':-1,'minecraft:water':640*256+1}}))
    def test_wrong_count(self):self.reject(lambda d:d.update({'completed_chunks':53}))
    def test_bool_count(self):self.reject(lambda d:d.update({'completed_chunks':True}))
    def test_pass_marker(self):self.assertTrue(success_marker('[INFO] R395 NATURAL QA PASS\n'))
    def test_fail_marker(self):
        with self.assertRaises(ValueError):success_marker('[INFO] R395 NATURAL QA FAIL')
    def test_fake_pass_suffix(self):
        with self.assertRaises(ValueError):success_marker('R395 NATURAL QA PASS stale')
    def test_unrelated_line(self):self.assertFalse(success_marker('[INFO] Done'))

class StateTests(unittest.TestCase):
    def test_property_order(self):
        a={'Name':'minecraft:water','Properties':{'level':'1','test':'x'}}
        b={'Name':'minecraft:water','Properties':{'test':'x','level':'1'}}
        self.assertEqual(runner.encode_state(a,{}),runner.encode_state(b,{}))
    def test_level_change(self):
        a={'Name':'minecraft:water','Properties':{'level':'1'}};b={'Name':'minecraft:water','Properties':{'level':'2'}}
        self.assertNotEqual(runner.encode_state(a,{}),runner.encode_state(b,{}))
    def test_equal_count_different_positions(self):
        a=runner.encode_state({'Name':'minecraft:stone'},{});b=runner.encode_state({'Name':'minecraft:air'},{})
        self.assertNotEqual(hashlib.sha256(a+b).digest(),hashlib.sha256(b+a).digest())
    def test_absent_properties_equal_empty(self):self.assertEqual(runner.encode_state({'Name':'minecraft:air'},{}),runner.encode_state({'Name':'minecraft:air','Properties':{}},{}))
    def test_missing_state(self):
        with self.assertRaises(ValueError):runner.encode_state({}, {})
    def test_bad_properties(self):
        with self.assertRaises(ValueError):runner.encode_state({'Name':'minecraft:stone','Properties':{'a':1}}, {})

class MatrixTests(unittest.TestCase):
    def matrix(self):
        doc=ReportTests().doc();keys={f'{x},{z}' for x,z in TARGETS}
        saved={field:{key:'a'*64 for key in keys} for field in runner.FIELDS}
        saved['chunk_block_counts']={key:{'minecraft:air':640*256} for key in keys}
        return {name:{'pass':True,'observed':copy.deepcopy(doc),'saved':copy.deepcopy(saved)} for name in runner.REQUIRED}
    def test_identical(self):self.assertTrue(runner.compare(self.matrix())['pass'])
    def test_missing_phase(self):
        p=self.matrix();p.pop('baseline_reverse');self.assertFalse(runner.compare(p)['pass'])
    def test_failed_phase(self):
        p=self.matrix();p['reverse']['pass']=False;self.assertFalse(runner.compare(p)['diagnostic_complete'])
    def test_geometry_diff_even_with_equal_water(self):
        p=self.matrix();k=next(iter(p['reverse']['saved']['full_state_hashes']));p['reverse']['saved']['full_state_hashes'][k]='b'*64
        result=runner.compare(p);self.assertFalse(result['pass']);self.assertTrue(result['diagnostic_complete'])
        self.assertEqual(result['comparisons']['candidate_reverse']['water_hashes'],[])
    def test_snapshot_drift(self):
        p=self.matrix();p['candidate']['observed']['chunks'][0]['water_sha256']='b'*64;self.assertFalse(runner.compare(p)['pass'])
    def test_incomplete_saved_hashes(self):
        p=self.matrix();p['baseline']['saved']['water_hashes'].pop(next(iter(p['baseline']['saved']['water_hashes'])))
        with self.assertRaises(ValueError):runner.compare(p)
    def test_baseline_reverse_diagnostic(self):
        p=self.matrix();k=next(iter(p['baseline_reverse']['saved']['block_state_hashes']));p['baseline_reverse']['saved']['block_state_hashes'][k]='b'*64
        result=runner.compare(p);self.assertFalse(result['pass']);self.assertEqual(result['comparisons']['baseline_reverse']['block_state_hashes'],[k])
    def test_disabled_candidate_difference(self):
        p=self.matrix();k=next(iter(p['candidate_off']['saved']['water_hashes']));p['candidate_off']['saved']['water_hashes'][k]='b'*64
        self.assertFalse(runner.compare(p)['pass'])

if __name__=='__main__':unittest.main(verbosity=2)
