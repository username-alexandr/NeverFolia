#!/usr/bin/env python3
"""Synthetic exact-source/atomic-validation contracts, not a Minecraft test."""
from __future__ import annotations
import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('height_hooks',ROOT/'scripts/apply-never-nether-experiment-r14.py');P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folia=self.root/'Folia'
        self.config=json.loads(P.PROFILE.read_text());self.original={}
        for name,c in self.config['files'].items():
            text='synthetic source\n'+'\n'.join((i['old']+'\n')*i['count'] for i in c['replacements'])
            c['sha256']=P.sha(text);p=self.folia/P.JAVA/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);self.original[name]=text
        self.profile=self.root/'hooks.json';self.profile.write_text(json.dumps(self.config))
        helper=self.root/'qa/nevernether-r14/candidate'/P.HELPER;helper.parent.mkdir(parents=True);helper.write_text('// synthetic helper\n')
        self.patches=[patch.object(P,'ROOT',self.root),patch.object(P,'PROFILE',self.profile)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def snapshot(self):return {str(p.relative_to(self.folia)):p.read_bytes() for p in self.folia.rglob('*') if p.is_file()}
    def reject(self):
        before=self.snapshot()
        with self.assertRaises((OSError,ValueError)):P.prepare(self.folia)
        self.assertEqual(before,self.snapshot())
    def test_exact_inventory(self):self.assertEqual(len(P.prepare(self.folia)),16)
    def test_prepare_read_only(self):
        before=self.snapshot();P.prepare(self.folia);self.assertEqual(before,self.snapshot())
    def test_idempotence(self):
        staged=P.prepare(self.folia)
        for p,s in staged.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
        self.assertEqual(staged,P.prepare(self.folia))
    def test_inversion(self):
        for name,c in self.config['files'].items():
            s=P.transform(name,self.original[name],c)
            for i in reversed(c['replacements']):s=s.replace(i['new'],i['old'])
            self.assertEqual(s,self.original[name])
    def test_changed_original_rejected(self):
        p=self.folia/P.JAVA/next(iter(self.original));p.write_text(p.read_text()+'changed');self.reject()
    def test_missing_input_rejected(self):
        (self.folia/P.JAVA/next(iter(self.original))).unlink();self.reject()
    def test_missing_helper_rejected(self):
        (self.root/'qa/nevernether-r14/candidate'/P.HELPER).unlink();self.reject()
    def test_empty_helper_rejected(self):
        (self.root/'qa/nevernether-r14/candidate'/P.HELPER).write_text(' ');self.reject()
    def test_conflicting_helper_rejected(self):
        p=self.folia/P.JAVA/P.HELPER;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('other');self.reject()
    def test_changed_installed_hook_rejected(self):
        for p,s in P.prepare(self.folia).items():p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
        p=self.folia/P.JAVA/next(iter(self.original));p.write_text(p.read_text()+'unexpected');self.reject()
    def test_inside_outside_height_methods_remain_complementary(self):
        c=json.loads((ROOT/'worldgen-spec/never-nether-r14-hooks.json').read_text())['files']['net/minecraft/world/level/Level.java']
        self.assertTrue(any(r['new']=='return !this.isOutsideBuildHeight(blockY);' for r in c['replacements']))
    def test_thread_guards_remain_before_height_mutation_guard(self):
        cfg=json.loads((ROOT/'worldgen-spec/never-nether-r14-hooks.json').read_text())
        for c in cfg['files'].values():
            for i in c['replacements']:
                if 'TickThread.ensureTickThread' in i['old']:
                    self.assertTrue(i['new'].startswith(i['old']));self.assertIn('canSet',i['new'])
    def test_old_production_entrypoint_unchanged(self):
        self.assertNotIn('experiment-r14.py',(ROOT/'scripts/apply-neverfolia-post-patches.sh').read_text())
if __name__=='__main__':unittest.main(verbosity=2)
