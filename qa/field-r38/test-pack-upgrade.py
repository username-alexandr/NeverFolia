#!/usr/bin/env python3
"""Regression tests for the actual CI pack upgrader, not a replacement algorithm."""
from pathlib import Path
import importlib.util
import io
import json
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('upgrade_r38', ROOT / 'scripts/upgrade-neveroverworld-r38-pack.py')
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


class RewriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / 'pack.zip'

    def pack(self, function=None, duplicate=False):
        if function is None:
            function = sorted(upgrade.KNOWN)[0].encode()
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.comment = b'archive metadata remains intact'
            archive.writestr('data/', b'')
            archive.writestr('data/before.nbt', b'NBT-before' * 731, compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr(upgrade.FUNCTION, function, compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr('data/after.nbt', bytes(range(256)) * 111, compress_type=zipfile.ZIP_STORED)
            if duplicate:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    archive.writestr('data/after.nbt', b'duplicate')

    def snapshot(self):
        with zipfile.ZipFile(self.path) as archive:
            return archive.namelist(), archive.comment, {i.filename: archive.read(i) for i in archive.infolist()}

    def test_changed_length_does_not_corrupt_source_reader(self):
        self.pack()
        names, comment, before = self.snapshot()
        result = upgrade.upgrade(self.path)
        new_names, new_comment, after = self.snapshot()
        self.assertTrue(result['modified'])
        self.assertEqual(names, new_names)
        self.assertEqual(comment, new_comment)
        self.assertEqual(after.pop(upgrade.FUNCTION), upgrade.OUTPUT)
        before.pop(upgrade.FUNCTION)
        self.assertEqual(before, after)
        with zipfile.ZipFile(self.path) as archive:
            self.assertIsNone(archive.testzip())
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_both_known_source_contracts(self):
        for text in sorted(upgrade.KNOWN):
            with self.subTest(text=text):
                self.pack(text.encode())
                self.assertTrue(upgrade.upgrade(self.path)['modified'])
                self.assertEqual(self.snapshot()[2][upgrade.FUNCTION], upgrade.OUTPUT)

    def test_idempotent_byte_for_byte(self):
        self.pack()
        upgrade.upgrade(self.path)
        before = self.path.read_bytes()
        self.assertFalse(upgrade.upgrade(self.path)['modified'])
        self.assertEqual(before, self.path.read_bytes())

    def test_unknown_function_keeps_original(self):
        self.pack(b'unknown controller')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            upgrade.upgrade(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_missing_function_is_noop(self):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('pack.mcmeta', b'{}')
        before = self.path.read_bytes()
        self.assertFalse(upgrade.upgrade(self.path)['function_present'])
        self.assertEqual(before, self.path.read_bytes())

    def test_duplicate_is_rejected(self):
        self.pack(duplicate=True)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            upgrade.upgrade(self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_write_failure_cleans_temporary_without_replacing(self):
        self.pack()
        before = self.path.read_bytes()
        with mock.patch.object(zipfile.ZipFile, 'writestr', side_effect=OSError('simulated write failure')):
            with self.assertRaises(OSError):
                upgrade.upgrade(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_replace_failure_cleans_temporary_without_replacing(self):
        self.pack()
        before = self.path.read_bytes()
        with mock.patch.object(upgrade.os, 'replace', side_effect=OSError('simulated rename failure')):
            with self.assertRaises(OSError):
                upgrade.upgrade(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.folder.iterdir()), [self.path])

    def test_unrelated_payload_mutation_fails_validation(self):
        self.pack()
        before = self.path.read_bytes()
        original = zipfile.ZipFile.writestr
        def changed(archive, info, data, *args, **kwargs):
            if getattr(info, 'filename', info) == 'data/after.nbt':
                data = b'unexpected change'
            return original(archive, info, data, *args, **kwargs)
        with mock.patch.object(zipfile.ZipFile, 'writestr', changed):
            with self.assertRaisesRegex(ValueError, 'Unexpected file mutation'):
                upgrade.upgrade(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.folder.iterdir()), [self.path])


if __name__ == '__main__':
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RewriteTests))
    print(stream.getvalue(), end='')
    out = ROOT / 'artifacts/r38-pack-upgrader-tests.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'pass': result.wasSuccessful()}, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
