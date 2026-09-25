#!/usr/bin/env python3
"""Synthetic exact-source/atomic contracts for NeverOverworld field-R10."""
from __future__ import annotations
import importlib.util, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fieldr10',ROOT/'scripts/apply-never-overworld-field-r10.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folia=self.root/'Folia';self.src=self.root/'native/neveroverworld/field-r10/java'
        for rel in (P.VILLAGE,P.SUBMERGED,P.ORE):
            p=self.src/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('// canonical '+str(rel)+'\n')
        village_old='// old village\n'
        flood_old='class F {\n'+P.SCOPE_ANCHOR+P.ORE_ANCHOR+P.CLEAN_ANCHOR+'}\n'
        vp=self.folia/P.JAVA/P.VILLAGE;vp.parent.mkdir(parents=True,exist_ok=True);vp.write_text(village_old)
        fp=self.folia/P.JAVA/P.FLOOD;fp.parent.mkdir(parents=True,exist_ok=True);fp.write_text(flood_old)
        self.patches=[patch.object(P,'ROOT',self.root),patch.object(P,'SOURCE_ROOT',self.src),patch.object(P,'OLD_VILLAGE_SHA',P.sha(village_old)),patch.object(P,'OLD_FLOOD_SHA',P.sha(flood_old))]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def snap(self):return {str(p.relative_to(self.folia)):p.read_bytes() for p in self.folia.rglob('*') if p.is_file()}
    def test_prepare_is_read_only_and_four_files(self):
        before=self.snap();staged=P.prepare(self.folia);self.assertEqual(len(staged),4);self.assertEqual(before,self.snap())
    def test_apply_and_idempotence(self):
        P.apply(self.folia);before=self.snap();P.apply(self.folia);self.assertEqual(before,self.snap())
    def test_flood_calls_and_full_guard_exactly_once(self):
        P.apply(self.folia);s=(self.folia/P.JAVA/P.FLOOD).read_text()
        self.assertEqual(s.count('NeverOverworldOreScarcityFieldR10.apply'),1)
        self.assertEqual(s.count('NeverOverworldSubmergedRemnants.apply'),1)
        self.assertEqual(s.count('chunk.getPersistedStatus().isOrAfter(net.minecraft.world.level.chunk.status.ChunkStatus.FULL)'),1)
        self.assertLess(s.index('ChunkStatus.FULL'),s.index('NeverOverworldOreScarcityFieldR10.apply'))
        self.assertLess(s.index('ChunkStatus.FULL'),s.index('NeverOverworldSubmergedRemnants.apply'))
    def test_unrelated_village_edit_rejected_atomically(self):
        (self.folia/P.JAVA/P.VILLAGE).write_text('changed');before=self.snap()
        with self.assertRaises(ValueError):P.apply(self.folia)
        self.assertEqual(before,self.snap())
    def test_unrelated_flood_edit_rejected_atomically(self):
        p=self.folia/P.JAVA/P.FLOOD;p.write_text(p.read_text()+'changed');before=self.snap()
        with self.assertRaises(ValueError):P.apply(self.folia)
        self.assertEqual(before,self.snap())
    def test_partial_install_rejected(self):
        p=self.folia/P.JAVA/P.FLOOD;p.write_text(p.read_text().replace(P.ORE_ANCHOR,P.ORE_CALL,1));before=self.snap()
        with self.assertRaises(ValueError):P.apply(self.folia)
        self.assertEqual(before,self.snap())
    def test_guard_only_partial_install_rejected(self):
        p=self.folia/P.JAVA/P.FLOOD;p.write_text(p.read_text().replace(P.SCOPE_ANCHOR,P.FULL_GUARD,1));before=self.snap()
        with self.assertRaises(ValueError):P.apply(self.folia)
        self.assertEqual(before,self.snap())
    def test_conflicting_helper_rejected(self):
        p=self.folia/P.JAVA/P.SUBMERGED;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('other');before=self.snap()
        with self.assertRaises(ValueError):P.apply(self.folia)
        self.assertEqual(before,self.snap())

if __name__=='__main__':unittest.main(verbosity=2)
