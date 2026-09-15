#!/usr/bin/env python3
"""Exact-source hotfix contracts. Synthetic source fixtures, not a world test."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bug01', ROOT/'scripts/apply-never-nether-bug01-bounds.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)

class BoundsHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rules = copy.deepcopy(P.CONTRACTS)
        self.originals = {}
        for name,rule in self.rules.items():
            text = 'synthetic fixture\n' + '\n'.join((r['old']+'\n')*r['count'] for r in rule['replacements'])
            rule['sha256'] = P.sha(text)
            self.originals[name] = text
            path = self.root/P.JAVA/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text)
        self.override = patch.object(P,'CONTRACTS',self.rules)
        self.override.start()
    def tearDown(self):
        self.override.stop()
        self.tmp.cleanup()
    def snapshot(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def rejects(self):
        before = self.snapshot()
        with self.assertRaises((ValueError,OSError)): P.apply(self.root)
        self.assertEqual(before,self.snapshot())
    def test_prepare_is_read_only(self):
        before=self.snapshot();self.assertEqual(len(P.prepare(self.root)),3);self.assertEqual(before,self.snapshot())
    def test_repeat_application_is_identical(self):
        P.apply(self.root);once=self.snapshot();P.apply(self.root);self.assertEqual(once,self.snapshot())
    def test_exact_inverse(self):
        for name,original in self.originals.items():
            out=P.transform(name,original)
            for item in reversed(self.rules[name]['replacements']):out=out.replace(item['new'],item['old'])
            self.assertEqual(out,original)
    def test_changed_first_input_rejects_atomically(self):
        p=self.root/P.JAVA/next(iter(self.rules));p.write_text(p.read_text()+'changed');self.rejects()
    def test_changed_last_input_does_not_write_earlier_files(self):
        p=self.root/P.JAVA/list(self.rules)[-1];p.write_text('different');self.rejects()
    def test_missing_input_rejects_atomically(self):
        (self.root/P.JAVA/list(self.rules)[-1]).unlink();self.rejects()
    def test_installed_unrelated_edit_rejects(self):
        P.apply(self.root);p=self.root/P.JAVA/next(iter(self.rules));p.write_text(p.read_text()+'different');self.rejects()
    def test_partial_install_rejects(self):
        P.apply(self.root);name=next(iter(self.rules));p=self.root/P.JAVA/name;r=self.rules[name]['replacements'][0]
        p.write_text(p.read_text().replace(r['new'],r['old']));self.rejects()
    def test_wrong_anchor_count_rejects_even_for_matching_hash(self):
        name=next(iter(self.rules));p=self.root/P.JAVA/name
        text=p.read_text()+self.rules[name]['replacements'][0]['old'];p.write_text(text);self.rules[name]['sha256']=P.sha(text);self.rejects()
    def test_no_exception_suppression_or_index_clamping(self):
        additions='\n'.join(r['new'] for v in self.rules.values() for r in v['replacements'])
        self.assertNotIn('catch',additions);self.assertNotIn('Math.min',additions);self.assertNotIn('Math.max',additions)
        self.assertIn('sectionIndex >= chunk.getSections().length',additions)
    def test_bound_check_precedes_world_query(self):
        additions='\n'.join(r['new'] for v in self.rules.values() for r in v['replacements'])
        self.assertIn('!isProposalHeight(p.getY()) || !level.ensureCanWrite(p)',additions)
        self.assertIn('!NeverNetherSubstrateR10.isProposalHeight(pos.getY()) || !actual.ensureCanWrite(pos)',additions)
    def test_only_three_nether_sources_changed(self):
        self.assertEqual(len(self.rules),3)
        for name in self.rules:self.assertTrue(name.startswith('net/minecraft/world/level/levelgen/placement/NeverNether'))

if __name__=='__main__':unittest.main(verbosity=2)
