#!/usr/bin/env python3
"""Source-transformer regressions; native Minecraft checks are a separate task."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as override

S=Path(__file__).with_name('defer-upper-pruning.py')
spec=importlib.util.spec_from_file_location('light_prune',S)
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)

class Tests(unittest.TestCase):
    def fixtures(self):
        old={};new={};contracts={}
        for name,rules in M.RULES.items():
            before='\n'.join(a for a,b,n in rules)
            after=before
            for a,b,n in rules:
                self.assertEqual(after.count(a),n)
                after=after.replace(a,b)
            old[name]=before;new[name]=after
            contracts[name]={'before':M.digest(before),'after':M.digest(after)}
        return old,new,contracts
    def test_patch_and_idempotence(self):
        old,new,contracts=self.fixtures()
        with override.object(M,'CONTRACTS',contracts):
            for name in old:
                self.assertEqual(M.patch(name,old[name]),new[name])
                self.assertEqual(M.patch(name,new[name]),new[name])
    def test_changed_original_rejected(self):
        old,new,contracts=self.fixtures()
        with override.object(M,'CONTRACTS',contracts):
            for name in old:
                with self.assertRaises(ValueError):M.patch(name,old[name]+'\n//changed')
    def test_changed_installed_output_rejected(self):
        old,new,contracts=self.fixtures()
        with override.object(M,'CONTRACTS',contracts):
            for name in new:
                with self.assertRaises(ValueError):M.patch(name,new[name]+'\n//changed')
    def test_bad_output_hash_rejected(self):
        old,new,contracts=self.fixtures()
        for c in contracts.values():c['after']='0'*64
        with override.object(M,'CONTRACTS',contracts):
            for name in old:
                with self.assertRaisesRegex(ValueError,'output contract'):M.patch(name,old[name])
    def test_missing_anchor_rejected_even_for_matching_input_digest(self):
        old,new,contracts=self.fixtures()
        for name in old:
            bad=old[name].replace(M.RULES[name][0][0],'/* missing */',1)
            specific={name:{'before':M.digest(bad),'after':contracts[name]['after']}}
            with override.object(M,'CONTRACTS',specific):
                with self.assertRaisesRegex(ValueError,'anchor'):M.patch(name,bad)
    def test_prepare_is_read_only_and_checks_both_files(self):
        old,new,contracts=self.fixtures()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);folder=root/M.JAVA;folder.mkdir(parents=True)
            for name,value in old.items():(folder/name).write_text(value)
            with override.object(M,'CONTRACTS',contracts):
                staged=M.prepare(root)
            self.assertEqual(len(staged),2)
            for name,value in old.items():self.assertEqual((folder/name).read_text(),value)
            for path,value in staged.items():self.assertEqual(value,new[path.name])
    def test_partial_failure_never_writes_first_file(self):
        old,new,contracts=self.fixtures()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);folder=root/M.JAVA;folder.mkdir(parents=True)
            for name,value in old.items():(folder/name).write_text(value)
            names=list(old);(folder/names[1]).write_text('unexpected')
            with override.object(M,'CONTRACTS',contracts):
                with self.assertRaises(ValueError):M.prepare(root)
            self.assertEqual((folder/names[0]).read_text(),old[names[0]])
            self.assertEqual((folder/names[1]).read_text(),'unexpected')
    def test_only_two_sources_change_and_nether_hooks_are_untouched(self):
        self.assertEqual(set(M.RULES),{'NeverOverworldFlood.java','NeverOverworldOreExposurePruner.java'})
        self.assertNotIn('ChunkStatusTasks.java',M.RULES)
        self.assertFalse(any('Nether' in name for name in M.RULES))
    def test_old_feature_entrypoint_is_inert(self):
        rules=M.RULES['NeverOverworldOreExposurePruner.java']
        body=next(b for a,b,n in rules if a.startswith('    public static void applyAfterFeatures'))
        inert=body.split('public static void applyAfterFeatures',1)[1].split('    }',1)[0]
        self.assertNotIn('prune(',inert)
        self.assertNotIn('getSeed()',inert)
        self.assertIn('ChunkStatus.INITIALIZE_LIGHT',body)
        self.assertIn('ChunkStatus.FULL',body)
    def test_light_call_precedes_final_cleanup(self):
        before,after,count=M.RULES['NeverOverworldFlood.java'][0]
        self.assertEqual(count,1)
        self.assertLess(after.index('applyAtLight'),after.index('removeUpperLapisDiamond'))
        self.assertEqual(after.count('applyAtLight'),1)
    def test_salts_percentages_and_deep_policy_are_not_recalibrated(self):
        rules=M.RULES['NeverOverworldOreExposurePruner.java']
        for old,new,count in rules:
            self.assertNotIn('SALT =',new)
            self.assertNotIn('COAL(',new)
            self.assertNotIn('KEEP_PERCENT',new)
        self.assertIn(('        prune(level, chunk, DEEP_MIN_Y, DEEP_MAX_Y, true);',
                       '        prune(level.getSeed(), chunk, DEEP_MIN_Y, DEEP_MAX_Y, true);',1),[tuple(r) for r in rules])

if __name__=='__main__':unittest.main(verbosity=2)
