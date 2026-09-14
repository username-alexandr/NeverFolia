#!/usr/bin/env python3
"""Synthetic source guards and explicit metadata lineage tests, no worldgen claims."""
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
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
P=load('r13_patch',ROOT/'scripts/apply-never-nether-experiment-r13.py')
M=load('r13_metadata',ROOT/'scripts/compare-never-nether-metadata-r11.py')

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.folia=self.root/'Folia'
        self.text='head\nold1\nold2\nold2\n'
        self.rule={'sha256':hashlib.sha256(self.text.encode()).hexdigest(),'replacements':[{'old':'old1','new':'new1','count':1},{'old':'old2','new':'new2','count':2}]}
        self.profile={'schema':1,'files':{'a.java':copy.deepcopy(self.rule),'b.java':copy.deepcopy(self.rule)}}
        self.profile_path=self.root/'hooks.json';self.save()
        for rel in self.profile['files']:
            p=self.folia/P.JAVA/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(self.text)
        self.helper=self.root/'qa/nevernether-r13/candidate'/P.HELPERS[0];self.helper.parent.mkdir(parents=True);self.helper.write_text('synthetic helper')
        self.patches=[patch.object(P,'ROOT',self.root),patch.object(P,'PROFILE',self.profile_path)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def save(self):self.profile_path.write_text(json.dumps(self.profile))
    def snapshot(self):return {p.relative_to(self.folia).as_posix():p.read_bytes() for p in self.folia.rglob('*') if p.is_file()}
    def reject(self):
        before=self.snapshot()
        with self.assertRaises((ValueError,OSError)):P.prepare(self.folia)
        self.assertEqual(before,self.snapshot())
    def test_exact_transform(self):self.assertEqual(P.transform(self.text,self.rule),'head\nnew1\nnew2\nnew2\n')
    def test_idempotent(self):
        out=P.transform(self.text,self.rule);self.assertEqual(P.transform(out,self.rule),out)
    def test_changed_input_rejected(self):
        with self.assertRaises(ValueError):P.transform(self.text+'unrelated',self.rule)
    def test_changed_installed_rejected(self):
        with self.assertRaises(ValueError):P.transform(P.transform(self.text,self.rule)+'unrelated',self.rule)
    def test_wrong_occurrence_count_rejected(self):
        self.rule['replacements'][0]['count']=2
        with self.assertRaises(ValueError):P.transform(self.text,self.rule)
    def test_mixed_install_rejected(self):
        out=P.transform(self.text,self.rule).replace('new2','old2',1)
        with self.assertRaises(ValueError):P.transform(out,self.rule)
    def test_prepare_readonly(self):
        old=self.snapshot();self.assertEqual(len(P.prepare(self.folia)),3);self.assertEqual(old,self.snapshot())
    def test_last_source_failure_atomic(self):(self.folia/P.JAVA/'b.java').write_text('wrong source');self.reject()
    def test_missing_source_atomic(self):(self.folia/P.JAVA/'b.java').unlink();self.reject()
    def test_missing_helper_atomic(self):self.helper.unlink();self.reject()
    def test_empty_helper_atomic(self):self.helper.write_text('  \n');self.reject()
    def test_extra_helper_atomic(self):(self.helper.parent/'Extra.java').write_text('extra');self.reject()
    def test_conflicting_helper_atomic(self):
        path=self.folia/P.JAVA/P.HELPERS[0];path.parent.mkdir(parents=True);path.write_text('different helper');self.reject()
    def test_matching_helper_allowed(self):
        path=self.folia/P.JAVA/P.HELPERS[0];path.parent.mkdir(parents=True);path.write_text('synthetic helper');self.assertEqual(len(P.prepare(self.folia)),3)
    def test_unknown_schema_rejected(self):self.profile['schema']=2;self.save();self.reject()
    def test_repeat_preparation(self):self.assertEqual(P.prepare(self.folia),P.prepare(self.folia))
    def test_explicit_opt_in_required(self):
        r=subprocess.run([sys.executable,str(ROOT/'scripts/apply-never-nether-experiment-r13.py'),str(self.folia)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,2);self.assertIn('Explicit opt-in',r.stderr)

class ReconciliationTests(unittest.TestCase):
    def test_r11_is_still_default(self):
        import inspect
        self.assertEqual(inspect.signature(M.compare).parameters['profile'].default,'r11')
        self.assertEqual(M.profile_id('r11'),'NN-R11-SUBSTRATE-1-REMOTE-R10-PRIORITY')
    def test_incompatible_r12_lineages_are_explicit(self):
        self.assertEqual(M.profile_id('r12-local'),'NN-R12-SUBSTRATE-1-NATURAL-PROPOSALS')
        self.assertEqual(M.profile_id('r12-remote'),'NN-R12-SUBSTRATE-1-DECORATION-PROPOSALS')
        self.assertEqual(len(M.PROFILES),len(set(M.PROFILES.values())))
    def test_unknown_profile_fails_before_file_io(self):
        with self.assertRaisesRegex(ValueError,'Unknown explicit metadata profile'):M.observations(Path('/no-such-file'),profile='latest')
    def test_r13_profile_matches_hook(self):
        data=json.loads((ROOT/'worldgen-spec/never-nether-r13-hooks.json').read_text())
        self.assertEqual(data['generator_profile'],M.profile_id('r13'))
        self.assertEqual(data['base_commit'],'6b1dbd4fb3b5e3a9e5c22e2f6a7ad9d1aef93af6')
    def test_historical_r12_not_replaced(self):
        data=json.loads((ROOT/'worldgen-spec/never-nether-r12-hooks.json').read_text())
        rules=data['files']['net/minecraft/world/level/levelgen/placement/NeverNetherStorageR11.java']['replacements']
        self.assertIn(M.profile_id('r12-remote'),[v['new'] for v in rules])
    def test_narrow_generated_inventory(self):
        data=json.loads((ROOT/'worldgen-spec/never-nether-r13-hooks.json').read_text())
        self.assertEqual({Path(v).name for v in data['files']},{'NeverNetherStorageR11.java','NeverNetherFloraCandidateR8.java','NeverNetherProposalR12.java'})
    def test_production_entry_unchanged(self):
        text=(ROOT/'scripts/apply-neverfolia-post-patches.sh').read_text()
        self.assertNotIn('experiment-r13',text)
    def test_no_priority_or_rng_rewrite(self):
        data=json.loads((ROOT/'worldgen-spec/never-nether-r13-hooks.json').read_text())
        for rule in data['files'].values():
            for item in rule['replacements']:
                self.assertNotIn('RandomSource',item['new']);self.assertNotIn('orePriority',item['new'])

if __name__=='__main__':unittest.main(verbosity=2)
