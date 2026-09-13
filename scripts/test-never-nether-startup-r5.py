#!/usr/bin/env python3
"""Synthetic gate regressions; supplied logs are inspected separately."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('startup_gate', Path(__file__).with_name('validate-never-nether-startup-r5.py'))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
CLEAN = '[INFO]: Done (2.000s)! For help, type "help"\nAll dimensions are saved\n'

class GateTests(unittest.TestCase):
    def test_clean_start_and_stop(self): self.assertTrue(mod.analyze(CLEAN, 0)['smoke_passed'])
    def test_empty_log_not_success(self): self.assertFalse(mod.analyze('', 0)['smoke_passed'])
    def test_missing_save_not_success(self): self.assertFalse(mod.analyze('Done (2.0s)! For help', 0)['smoke_passed'])
    def test_nonzero_exit_not_success(self): self.assertFalse(mod.analyze(CLEAN, 1)['smoke_passed'])
    def test_function_failure_despite_done(self):
        result = mod.analyze('[ERROR]: Failed to load function test:bad\n'+CLEAN, 0)
        self.assertFalse(result['smoke_passed']); self.assertEqual(result['failed_functions'], ['test:bad'])
    def test_data_failure_despite_done(self): self.assertFalse(mod.analyze("[ERROR]: Couldn't parse data file 'test:loot'\n"+CLEAN, 0)['smoke_passed'])
    def test_loot_warning_is_blocker(self): self.assertFalse(mod.analyze('Missing element test:loot of type minecraft:loot_table\n'+CLEAN, 0)['smoke_passed'])
    def test_offline_auth_recorded_separately(self):
        result = mod.analyze('[ERROR]: Failed to request yggdrasil public key\n'+CLEAN, 0)
        self.assertTrue(result['content_clean']); self.assertEqual(len(result['offline_auth_error_lines']), 1)
    def test_unknown_error_is_blocker(self): self.assertFalse(mod.analyze('[ERROR]: Unexpected failure\n'+CLEAN, 0)['smoke_passed'])
    def test_missing_pool_unknown_not_empty(self): self.assertFalse(mod.analyze('Empty or non-existent pool: test:missing\n'+CLEAN, 0)['smoke_passed'])
    def test_declared_empty_pool_is_observation(self):
        result = mod.analyze('Empty or non-existent pool: test:empty\n'+CLEAN, 0, {'data/test/worldgen/template_pool/empty.json': b'{"elements":[]}'})
        self.assertTrue(result['smoke_passed']); self.assertEqual(result['intentional_empty_pool_warnings'], ['test:empty'])
    def test_readiness_never_means_release_ready(self): self.assertFalse(mod.analyze(CLEAN, 0)['release_ready'])

if __name__ == '__main__': unittest.main(verbosity=2)
