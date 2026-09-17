#!/usr/bin/env python3
"""Synthetic exact-source transformer tests; not Minecraft world evidence."""
from __future__ import annotations
import hashlib,importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('field_r11',ROOT/'scripts/apply-never-overworld-field-r11.py');P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folia=self.root/'Folia';self.java=self.folia/P.JAVA
        original='class X {\n void apply(){\n'+P.ANCHOR+' }\n}\n';self.expected=hashlib.sha256(original.encode()).hexdigest()
        f=self.java/P.FLOOD;f.parent.mkdir(parents=True);f.write_text(original)
        h=self.root/'native/neveroverworld/field-r11/java'/P.HELPER;h.parent.mkdir(parents=True);h.write_text('package net.minecraft.world.level.chunk; final class NeverOverworldFloodBoundaryR11 {}\n')
        self.patches=[patch.object(P,'ROOT',self.root),patch.object(P,'SOURCE_ROOT',self.root/'native/neveroverworld/field-r11/java'),patch.object(P,'EXPECTED_FLOOD_SHA',self.expected)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def snap(self):return {str(p.relative_to(self.folia)):p.read_bytes() for p in self.folia.rglob('*') if p.is_file()}
    def test_prepare_is_read_only_two_files(self):
        before=self.snap();staged=P.prepare(self.folia);self.assertEqual(len(staged),2);self.assertEqual(before,self.snap())
    def test_apply_and_idempotence(self):
        P.apply(self.folia);before=self.snap();P.apply(self.folia);self.assertEqual(before,self.snap())
    def test_call_before_weather(self):
        out=P.patch_flood((self.java/P.FLOOD).read_text());self.assertEqual(out.count('NeverOverworldFloodBoundaryR11.apply(level, chunk);'),1);self.assertLess(out.index('NeverOverworldFloodBoundaryR11.apply'),out.index('weatherSubmergedSurface'))
    def test_changed_input_rejected(self):
        p=self.java/P.FLOOD;p.write_text(p.read_text()+'changed')
        with self.assertRaises(ValueError):P.prepare(self.folia)
    def test_duplicate_anchor_rejected(self):
        p=self.java/P.FLOOD;text=p.read_text()+P.ANCHOR;p.write_text(text)
        with patch.object(P,'EXPECTED_FLOOD_SHA',hashlib.sha256(text.encode()).hexdigest()),self.assertRaises(ValueError):P.prepare(self.folia)
    def test_conflicting_helper_rejected(self):
        p=self.java/P.HELPER;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('other')
        with self.assertRaises(ValueError):P.prepare(self.folia)

if __name__=='__main__':unittest.main(verbosity=2)
