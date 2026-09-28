#!/usr/bin/env python3
"""Real engine marker regression and the unchanged original graph contract."""
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import never_resource_stack as s

class MarkerTests(unittest.TestCase):
    def test_engine_marker_is_recorded_not_indexed(self):
        stack=s.ResourceStack()
        stack.add('vanilla', {'data/.mcassetsroot': b''})
        self.assertEqual(stack.files, {})
        self.assertEqual(stack.non_resource_markers, [{'path':'data/.mcassetsroot','pack':'vanilla','sha256':s.digest(b'')}])

    def test_unrecognized_data_root_file_still_fails(self):
        with self.assertRaises(ValueError):
            s.ResourceStack().add('vanilla', {'data/unknown-root-file':b''})

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(MarkerTests)
    original=s.module(ROOT/'scripts/tests/test_r39_resource_audit.py','r3919_original_alias_tests')
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(original))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
