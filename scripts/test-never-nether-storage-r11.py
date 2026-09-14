#!/usr/bin/env python3
"""Synthetic exact API hook contracts; actual section/NBT tests run in Java."""
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
spec=importlib.util.spec_from_file_location('r11',ROOT/'scripts/apply-never-nether-experiment-r11.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)

class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folia=self.root/'Folia'
        self.text='head\nold1\nold2\nold2\n'
        self.rule={'sha256':hashlib.sha256(self.text.encode()).hexdigest(),'replacements':[{'old':'old1','new':'new1','count':1},{'old':'old2','new':'new2','count':2}]}
        self.profile={'schema':1,'files':{'pkg/First.java':copy.deepcopy(self.rule),'pkg/Second.java':copy.deepcopy(self.rule)}}
        self.profile_path=self.root/'hooks.json';self.save()
        self.loader_path=self.root/'loader.json';self.loader_path.write_text(json.dumps({'schema':1,'files':{}}))
        for rel in self.profile['files']:
            p=self.folia/P.JAVA/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(self.text)
        helper=self.root/'qa/nevernether-r11/candidate'/P.HELPER;helper.parent.mkdir(parents=True);helper.write_text('synthetic helper')
        (self.root/'qa/nevernether-r11/candidate'/P.HELPERS[1]).write_text('synthetic guard')
        self.patches=[patch.object(P,'ROOT',self.root),patch.object(P,'PROFILE',self.profile_path),patch.object(P,'LOADER_PROFILE',self.loader_path)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def save(self):self.profile_path.write_text(json.dumps(self.profile))
    def snapshot(self):return {p.relative_to(self.folia).as_posix():p.read_bytes() for p in self.folia.rglob('*') if p.is_file()}
    def reject(self):
        before=self.snapshot()
        with self.assertRaises((ValueError,OSError)):P.prepare(self.folia)
        self.assertEqual(before,self.snapshot())
    def test_exact_transform(self):self.assertEqual(P.transform(self.text,self.rule),'head\nnew1\nnew2\nnew2\n')
    def test_idempotent(self):
        out=P.transform(self.text,self.rule);self.assertEqual(P.transform(out,self.rule),out)
    def test_unrelated_input_change(self):
        with self.assertRaises(ValueError):P.transform(self.text+'extra',self.rule)
    def test_unrelated_installed_change(self):
        with self.assertRaises(ValueError):P.transform(P.transform(self.text,self.rule)+'extra',self.rule)
    def test_mixed_hook(self):
        with self.assertRaises(ValueError):P.transform(P.transform(self.text,self.rule).replace('new1','old1'),self.rule)
    def test_bad_count(self):
        self.rule['replacements'][0]['count']=2
        with self.assertRaises(ValueError):P.transform(self.text,self.rule)
    def test_existing_replacement_in_input(self):
        text=self.text+'new1';self.rule['sha256']=hashlib.sha256(text.encode()).hexdigest()
        with self.assertRaises(ValueError):P.transform(text,self.rule)
    def test_prepare_readonly(self):
        before=self.snapshot();self.assertEqual(len(P.prepare(self.folia)),4);self.assertEqual(before,self.snapshot())
    def test_last_input_failure_atomic(self):
        (self.folia/P.JAVA/'pkg/Second.java').write_text('bad');self.reject()
    def test_missing_source_atomic(self):
        (self.folia/P.JAVA/'pkg/Second.java').unlink();self.reject()
    def test_missing_helper_atomic(self):
        (self.root/'qa/nevernether-r11/candidate'/P.HELPER).unlink();self.reject()
    def test_empty_helper_atomic(self):
        (self.root/'qa/nevernether-r11/candidate'/P.HELPER).write_text(' \n');self.reject()
    def test_extra_helper_atomic(self):
        (self.root/'qa/nevernether-r11/candidate/extra.java').write_text('extra');self.reject()
    def test_conflicting_installed_helper(self):
        p=self.folia/P.JAVA/P.HELPER;p.parent.mkdir(parents=True);p.write_text('other');self.reject()
    def test_equal_installed_helper(self):
        p=self.folia/P.JAVA/P.HELPER;p.parent.mkdir(parents=True);p.write_text('synthetic helper');self.assertEqual(len(P.prepare(self.folia)),4)
    def test_unknown_schema(self):self.profile['schema']=2;self.save();self.reject()
    def test_repeat_preparation(self):self.assertEqual(P.prepare(self.folia),P.prepare(self.folia))
    def test_explicit_optin(self):
        r=subprocess.run([sys.executable,str(ROOT/'scripts/apply-never-nether-experiment-r11.py'),str(self.folia)],capture_output=True,text=True)
        self.assertEqual(r.returncode,2);self.assertIn('explicit opt-in',r.stderr)
    def test_production_does_not_apply_r11(self):
        self.assertNotIn('apply-never-nether-experiment-r11.py',(ROOT/'scripts/apply-neverfolia-post-patches.sh').read_text())
    def test_real_profile_covers_serializer_and_copy(self):
        real=json.loads((ROOT/'worldgen-spec/never-nether-r11-hooks.json').read_text())
        self.assertIn('net/minecraft/world/level/chunk/storage/SerializableChunkData.java',real['files'])
        self.assertIn('net/minecraft/world/level/chunk/LevelChunkSection.java',real['files'])
    def test_loader_duplicate_rejected(self):
        self.loader_path.write_text(json.dumps({'schema':1,'files':{'pkg/First.java':self.rule}}));self.reject()
    def test_helper_is_separate_from_normal_native_sources(self):
        self.assertFalse((ROOT/'native/nevernether/java'/P.HELPER).exists())

if __name__=='__main__':unittest.main(verbosity=2)
