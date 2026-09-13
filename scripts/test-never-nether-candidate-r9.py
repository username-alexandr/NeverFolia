#!/usr/bin/env python3
"""Exact-source and atomic-validation regressions for the opt-in R9 transformer.

Uses synthetic hook fixtures, not a simulated world or a substitute native API.
The dedicated workflow compiles against the pinned real Folia source afterwards.
"""
from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('nn_r9_patcher', ROOT / 'scripts/apply-never-nether-experiment-r9.py')
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


class TransformationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folia = self.root / 'Folia'
        self.expected = copy.deepcopy(P.CONTRACTS)
        self.originals = {}
        for name, (_, replacements) in self.expected.items():
            text = 'synthetic class\n' + '\n'.join((old + '\n') * count for old, _, count in replacements)
            self.expected[name] = (P.sha(text), replacements)
            target = self.folia / P.JAVA / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            self.originals[name] = text
        self.helper_dir = self.root / 'qa/nevernether-r9/candidate' / P.PLACEMENT
        self.helper_dir.mkdir(parents=True)
        for name in P.HELPERS:
            (self.helper_dir / name).write_text('// synthetic fixture ' + name + '\n')
        self.patches = [patch.object(P, 'ROOT', self.root), patch.object(P, 'CONTRACTS', self.expected)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def snapshot(self):
        return {str(p.relative_to(self.folia)): p.read_bytes() for p in self.folia.rglob('*') if p.is_file()}

    def assert_atomic_rejection(self):
        before = self.snapshot()
        with self.assertRaises((ValueError, OSError)):
            P.apply(self.folia)
        self.assertEqual(self.snapshot(), before)

    def test_expected_inventory_six_files(self):
        self.assertEqual(len(P.prepare(self.folia)), 6)

    def test_prepare_does_not_write(self):
        before = self.snapshot()
        P.prepare(self.folia)
        self.assertEqual(before, self.snapshot())

    def test_each_exact_occurrence_transformed(self):
        for name, original in self.originals.items():
            out = P.transform(name, original)
            for _, new, count in self.expected[name][1]:
                self.assertEqual(out.count(new), count)

    def test_apply_is_idempotent(self):
        P.apply(self.folia)
        before = self.snapshot()
        P.apply(self.folia)
        self.assertEqual(before, self.snapshot())

    def test_original_bytes_invert_exactly(self):
        for name, original in self.originals.items():
            out = P.transform(name, original)
            for old, new, count in reversed(self.expected[name][1]):
                self.assertEqual(out.count(new), count)
                out = out.replace(new, old)
            self.assertEqual(out, original)

    def test_unrelated_input_change_rejected(self):
        name = next(iter(self.originals))
        (self.folia / P.JAVA / name).write_text(self.originals[name] + '// changed')
        self.assert_atomic_rejection()

    def test_changed_last_source_does_not_modify_first(self):
        name = list(self.originals)[-1]
        (self.folia / P.JAVA / name).write_text('wrong source')
        self.assert_atomic_rejection()

    def test_missing_source_rejected(self):
        (self.folia / P.JAVA / P.FUNGUS).unlink()
        self.assert_atomic_rejection()

    def test_installed_unrelated_edit_rejected(self):
        P.apply(self.folia)
        path = self.folia / P.JAVA / P.FUNGUS
        path.write_text(path.read_text() + '// unexpected')
        self.assert_atomic_rejection()

    def test_mixed_installed_hook_rejected(self):
        P.apply(self.folia)
        path = self.folia / P.JAVA / P.FUNGUS
        old, new, _ = self.expected[P.FUNGUS][1][-1]
        path.write_text(path.read_text().replace(new, old, 1))
        self.assert_atomic_rejection()

    def test_duplicate_hook_rejected(self):
        name = next(iter(self.originals))
        old, _, _ = self.expected[name][1][0]
        text = self.originals[name] + old
        self.expected[name] = (P.sha(text), self.expected[name][1])
        (self.folia / P.JAVA / name).write_text(text)
        self.assert_atomic_rejection()

    def test_missing_hook_rejected_even_with_matched_fixture_hash(self):
        name = next(iter(self.originals))
        old, _, _ = self.expected[name][1][0]
        text = self.originals[name].replace(old, '', 1)
        self.expected[name] = (P.sha(text), self.expected[name][1])
        (self.folia / P.JAVA / name).write_text(text)
        self.assert_atomic_rejection()

    def test_preexisting_replacement_in_original_rejected(self):
        name = next(iter(self.originals))
        _, new, _ = self.expected[name][1][0]
        text = self.originals[name] + new
        self.expected[name] = (P.sha(text), self.expected[name][1])
        (self.folia / P.JAVA / name).write_text(text)
        self.assert_atomic_rejection()

    def test_extra_helper_rejected(self):
        (self.helper_dir / 'Unexpected.java').write_text('unexpected')
        self.assert_atomic_rejection()

    def test_missing_helper_rejected(self):
        (self.helper_dir / P.HELPERS[0]).unlink()
        self.assert_atomic_rejection()

    def test_empty_helper_rejected(self):
        (self.helper_dir / P.HELPERS[-1]).write_text('  \n')
        self.assert_atomic_rejection()

    def test_conflicting_installed_helper_rejected(self):
        path = self.folia / P.JAVA / P.PLACEMENT / P.HELPERS[-1]
        path.write_text('another experiment')
        self.assert_atomic_rejection()

    def test_matching_installed_helper_accepted(self):
        path = self.folia / P.JAVA / P.PLACEMENT / P.HELPERS[0]
        path.write_bytes((self.helper_dir / P.HELPERS[0]).read_bytes())
        self.assertEqual(len(P.prepare(self.folia)), 6)

    def test_same_tree_repeatable(self):
        self.assertEqual(P.prepare(self.folia), P.prepare(self.folia))

    def test_opt_in_required(self):
        run = subprocess.run([sys.executable, str(ROOT / 'scripts/apply-never-nether-experiment-r9.py'),
                              str(self.folia)], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 2)
        self.assertIn('explicit opt-in', run.stderr)

    def test_production_chain_does_not_install_candidate(self):
        text = (ROOT / 'scripts/apply-neverfolia-post-patches.sh').read_text()
        self.assertNotIn('apply-never-nether-experiment-r9.py', text)
        self.assertNotIn('apply-never-nether-experiment-r8.py', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
