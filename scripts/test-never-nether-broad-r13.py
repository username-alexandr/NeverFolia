#!/usr/bin/env python3
"""Pinned coverage expansion tests; never relax stage/ownership/hash checks."""
import copy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
B=load('broad_r13',ROOT/'qa/nevernether-r13/broad1599.py')
C=load('stage_compare',ROOT/'scripts/compare-never-nether-stages-r8.py')

class CoverageTests(unittest.TestCase):
    def setUp(self):self.plan=B.original_plan()
    def test_exact_original_full_coverage(self):self.assertEqual(len(B.validate(self.plan,7270913)['chunks']),1599)
    def test_unique_original_coordinate_set(self):self.assertEqual(len(set(map(tuple,self.plan['chunks']))),1599)
    def test_order_independent_identity(self):self.assertEqual(B.plan_hash(self.plan['chunks']),B.plan_hash(list(reversed(self.plan['chunks']))))
    def test_minimum_distance_is_real_original_sample(self):self.assertEqual(min(max(map(abs,p)) for p in self.plan['chunks']),7)
    def test_subset_rejected(self):
        self.plan['chunks'].pop()
        with self.assertRaises(ValueError):B.validate(self.plan,7270913)
    def test_substituted_coordinate_rejected(self):
        self.plan['chunks'][0][0]+=10000
        with self.assertRaises(ValueError):B.validate(self.plan,7270913)
    def test_duplicate_rejected(self):
        self.plan['chunks'][0]=self.plan['chunks'][1]
        with self.assertRaises(ValueError):B.validate(self.plan,7270913)
    def test_noninteger_coordinates_rejected(self):
        for value in (True,1.5,'1'):
            p=copy.deepcopy(self.plan);p['chunks'][0][0]=value
            with self.subTest(value=value),self.assertRaises(ValueError):B.validate(p,7270913)
    def test_wrong_seed_rejected(self):
        for seed in (1,123456789):
            with self.assertRaises(ValueError):B.validate(self.plan,seed)
    def test_other_report_seed_rejected(self):
        self.plan['seed']=123456789
        with self.assertRaises(ValueError):B.validate(self.plan,7270913)
    def test_no_incomplete_checkpoint_mode(self):
        for key in ('stop_after_carvers','verify_saved_only'):
            p={**self.plan,key:True}
            with self.assertRaises(ValueError):B.validate(p,7270913)
    def test_reverse_does_not_modify_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'plan.json';p.write_text(json.dumps(self.plan));raw=p.read_bytes();r=B.checked_plan(p,7270913,True)
            self.assertEqual(r['chunks'],list(reversed(self.plan['chunks'])));self.assertEqual(p.read_bytes(),raw)
    def test_regular_runner_still_rejects_broad_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'plan.json';p.write_text(json.dumps(self.plan))
            with self.assertRaises(ValueError):B.RUNNER.checked_plan(p,7270913,False)
    def test_regular_comparator_bound_unchanged(self):
        for fun in (C.load,C.compare):self.assertEqual(inspect.signature(fun).parameters['max_chunks'].default,512)
    def test_regular_runner_default_validator_unchanged(self):self.assertIs(inspect.signature(B.RUNNER.main).parameters['plan_validator'].default,B.RUNNER.checked_plan)
    def test_capture_checks_unchanged(self):
        original=(ROOT/'qa/nevernether-r11/NeverNetherLifecycleProbeR11.java').read_text();out=B.probe_source()
        self.assertEqual(out[out.index('    private void load('):],original[original.index('    private void load('):])
        self.assertIn(B.PLAN_SHA,out);self.assertIn('raw.size()!=1599',out)
    def test_source_identity_change_rejected(self):
        with patch.object(B,'PROBE_SHA','0'*64),self.assertRaises(ValueError):B.probe_source()
    def test_production_unchanged(self):self.assertNotIn('broad1599',(ROOT/'scripts/apply-neverfolia-post-patches.sh').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
