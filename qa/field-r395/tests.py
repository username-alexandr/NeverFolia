#!/usr/bin/env python3
import copy
import gzip
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import prepare
import run_water as water


class PlanTests(unittest.TestCase):
    def test_negative_coordinate_floor(self):
        self.assertEqual(water.REMOTE_CENTER, (-202, -213))
        self.assertEqual((-3259 // 16, -3397 // 16), (-204, -213))
    def test_coverage(self):
        self.assertEqual((len(water.OLD), len(water.REMOTE), len(water.CHUNKS)), (48, 81, 129))
        self.assertFalse(water.OLD & water.REMOTE)
    def test_java_halo_covers_all_targets(self):
        self.assertTrue(all(-207 <= x <= -197 and -218 <= z <= -208 for x, z in water.REMOTE))
    def test_exact_delta(self):
        raw = (prepare.ROOT / prepare.SOURCE).read_bytes()
        self.assertEqual(prepare.blob(raw), prepare.SOURCE_BLOB)
        original = raw.decode()
        changed = prepare.transform(original)
        restored = changed.replace(prepare.NEW_SELECTION, prepare.OLD_SELECTION, 1).replace(prepare.MASK_WRITE, '', 1)
        self.assertEqual(restored, original)
    def test_missing_anchor(self):
        with self.assertRaises(ValueError):
            prepare.transform('not the expected source')
    def test_duplicate_anchor(self):
        with self.assertRaises(ValueError):
            prepare.once('foo foo', 'foo', 'bar')
    def test_empty_audit_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            summary, _, _ = water.audit_folder(Path(directory), 'this-run')
            self.assertFalse(summary['pass'])
            self.assertEqual(len(summary['missing_target_chunks']), 129)


class MaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.size = (water.HIGH - water.LOW + 1) * 256
        self.before, self.after = bytearray(self.size), bytearray(self.size)
        self.floors = [-512] * 256
        self.path = self.folder / '-202_-213.json'
    def tearDown(self):
        self.temp.cleanup()
    def write(self, **overrides):
        payload = gzip.compress(struct.pack('>iii256ii', 0x57415431, water.LOW, water.HIGH, *self.floors, self.size) + self.before + self.after, mtime=0)
        mask = self.folder / '-202_-213.water.gz'
        mask.write_bytes(payload)
        row = {'chunk_x': -202, 'chunk_z': -213, 'audit_revision': 'R395', 'run_id': 'this-run',
               'mask_file': mask.name, 'mask_sha256': hashlib.sha256(payload).hexdigest(),
               'before_water_sha256': hashlib.sha256(self.before).hexdigest(),
               'after_water_sha256': hashlib.sha256(self.after).hexdigest(),
               **{key: 0 for key in water.COUNTERS}, 'pass': True}
        row.update(overrides)
        self.path.write_text(json.dumps(row))
        return row
    def check(self):
        return water.verify_row(self.folder, self.path, 'this-run')
    def test_valid_empty_water_record_is_not_global_coverage(self):
        self.write()
        self.assertTrue(self.check()[1]['pass'])
        self.assertFalse(water.audit_folder(self.folder, 'this-run')[0]['pass'])
    def test_preserved_water(self):
        self.before[10] = self.after[10] = 1
        self.write(native_water=1, preserved_native_water=1)
        self.assertTrue(self.check()[1]['pass'])
    def test_removed_water_remains_failure(self):
        self.before[10] = 1
        self.write(native_water=1, removed_native_water=1, **{'pass': False})
        self.assertFalse(self.check()[1]['pass'])
    def test_new_water_below_floor_remains_failure(self):
        self.floors[10] = -511
        self.after[10] = 1
        self.write(new_water=1, below_native_surface_additions=1, **{'pass': False})
        self.assertFalse(self.check()[1]['pass'])
    def test_stale_run(self):
        self.write(run_id='earlier-run')
        with self.assertRaises(ValueError): self.check()
    def test_wrong_revision(self):
        self.write(audit_revision='R38')
        with self.assertRaises(ValueError): self.check()
    def test_wrong_coordinate(self):
        self.write(chunk_x=-201)
        with self.assertRaises(ValueError): self.check()
    def test_path_escape(self):
        self.write(mask_file='../other.gz')
        with self.assertRaises(ValueError): self.check()
    def test_bad_digest(self):
        self.write(mask_sha256='0' * 64)
        with self.assertRaises(ValueError): self.check()
    def test_bad_counter(self):
        self.write(native_water=10)
        with self.assertRaises(ValueError): self.check()
    def test_contradictory_pass(self):
        self.write(**{'pass': False})
        with self.assertRaises(ValueError): self.check()
    def test_changed_state_accounting(self):
        self.before[10] = 1
        self.after[10] = 2
        self.write(native_water=1, changed_native_water_state=1, **{'pass': False})
        self.assertFalse(self.check()[1]['pass'])
    def test_truncated_mask(self):
        self.write()
        mask = self.folder / '-202_-213.water.gz'
        with self.assertRaises((ValueError, EOFError, gzip.BadGzipFile)):
            water.mask_data(mask.read_bytes()[:-8])
    def test_trailing_data(self):
        self.write()
        mask = self.folder / '-202_-213.water.gz'
        raw = gzip.decompress(mask.read_bytes())
        with self.assertRaises(ValueError): water.mask_data(gzip.compress(raw + b'x'))
    def test_invalid_fluid_code(self):
        self.after[0] = 255
        self.write()
        with self.assertRaises(ValueError): self.check()


if __name__ == '__main__':
    unittest.main(verbosity=2)
