#!/usr/bin/env python3
"""R12 source-contract tests use synthetic fixtures; native/world checks are separate."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('r12_transform',ROOT/'scripts/apply-never-nether-experiment-r12.py')
P=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(P)

class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folia=self.root/'Folia'
        self.name='net/minecraft/Test.java';self.text='class Test {\n  OLD();\n}\n'
        self.rule={'sha256':hashlib.sha256(self.text.encode()).hexdigest(),'replacements':[{'old':'OLD()','new':'NEW()','count':1}]}
        self.profile={'schema':1,'files':{self.name:self.rule}}
        self.profile_path=self.root/'profile.json';self.write_profile()
        self.target=self.folia/P.JAVA/self.name;self.target.parent.mkdir(parents=True);self.target.write_text(self.text)
        self.helpers=self.root/'qa/nevernether-r12/candidate'
        for name in P.HELPERS:
            p=self.helpers/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic helper\n')
        self.patches=[patch.object(P,'ROOT',self.root),patch.object(P,'PROFILE',self.profile_path)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def write_profile(self):self.profile_path.write_text(json.dumps(self.profile))
    def snapshot(self):return {str(p.relative_to(self.folia)):p.read_bytes() for p in self.folia.rglob('*') if p.is_file()}
    def apply(self):
        staged=P.prepare(self.folia)
        for p,text in staged.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    def reject(self):
        before=self.snapshot()
        with self.assertRaises((OSError,ValueError)):self.apply()
        self.assertEqual(before,self.snapshot())
    def test_exact_source_transforms(self):self.assertIn('NEW()',P.transform(self.text,self.rule))
    def test_source_is_not_modified_by_prepare(self):
        before=self.snapshot();P.prepare(self.folia);self.assertEqual(before,self.snapshot())
    def test_idempotent_application(self):
        self.apply();before=self.snapshot();self.apply();self.assertEqual(before,self.snapshot())
    def test_exact_inverse(self):self.assertEqual(P.transform(self.text,self.rule).replace('NEW()','OLD()'),self.text)
    def test_unknown_input_rejected(self):self.target.write_text('different source');self.reject()
    def test_missing_input_rejected(self):self.target.unlink();self.reject()
    def test_duplicate_anchor_rejected(self):
        text=self.text+'OLD()';self.rule['sha256']=hashlib.sha256(text.encode()).hexdigest();self.write_profile();self.target.write_text(text);self.reject()
    def test_missing_anchor_with_matching_hash_rejected(self):
        text=self.text.replace('OLD()','removed()');self.rule['sha256']=hashlib.sha256(text.encode()).hexdigest();self.write_profile();self.target.write_text(text);self.reject()
    def test_preexisting_new_anchor_rejected(self):
        text=self.text+'NEW()';self.rule['sha256']=hashlib.sha256(text.encode()).hexdigest();self.write_profile();self.target.write_text(text);self.reject()
    def test_patched_file_tampering_rejected(self):self.apply();self.target.write_text(self.target.read_text()+'tampered');self.reject()
    def test_duplicate_installed_anchor_rejected(self):self.apply();self.target.write_text(self.target.read_text()+'NEW()');self.reject()
    def test_missing_helper_rejected(self):(self.helpers/P.HELPERS[0]).unlink();self.reject()
    def test_empty_helper_rejected(self):(self.helpers/P.HELPERS[0]).write_text(' \n');self.reject()
    def test_extra_helper_rejected(self):(self.helpers/'Unexpected.java').write_text('unexpected');self.reject()
    def test_conflicting_installed_helper_rejected(self):
        p=self.folia/P.JAVA/P.HELPERS[0];p.parent.mkdir(parents=True,exist_ok=True);p.write_text('other version');self.reject()
    def test_identical_installed_helper_accepted(self):
        p=self.folia/P.JAVA/P.HELPERS[0];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((self.helpers/P.HELPERS[0]).read_bytes());self.apply()
    def test_schema_rejected(self):self.profile['schema']=2;self.write_profile();self.reject()
    def test_last_bad_source_does_not_modify_first(self):
        self.profile['files']['net/minecraft/Last.java']=copy.deepcopy(self.rule);self.write_profile();p=self.folia/P.JAVA/'net/minecraft/Last.java';p.write_text('invalid');self.reject()
    def test_preparation_repeatable(self):self.assertEqual(P.prepare(self.folia),P.prepare(self.folia))
    def test_cli_requires_opt_in(self):
        run=subprocess.run([sys.executable,str(ROOT/'scripts/apply-never-nether-experiment-r12.py'),str(self.folia)],capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,2);self.assertIn('Explicit opt-in',run.stderr)
    def test_production_chain_unchanged(self):self.assertNotIn('experiment-r12',(ROOT/'scripts/apply-neverfolia-post-patches.sh').read_text())
    def test_real_profile_updates_storage_policy(self):
        profile=json.loads((ROOT/'worldgen-spec/never-nether-r12-hooks.json').read_text())
        changes=profile['files']['net/minecraft/world/level/levelgen/placement/NeverNetherStorageR11.java']['replacements']
        self.assertTrue(any('NN-R12-' in r['new'] and 'NN-R11-' in r['old'] for r in changes))

if __name__=='__main__':unittest.main(verbosity=2)
