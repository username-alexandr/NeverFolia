#!/usr/bin/env python3
"""Late exact-source R399 transform. Only a Java source file is changed.
Run after historical R38/R396 materialization. Never reads or edits saved worlds.
"""
from pathlib import Path
import argparse
import hashlib
import os
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REL = Path('net/minecraft/world/level/chunk/NeverOverworldDryMinesR12.java')
SOURCE = ROOT/'native/neveroverworld/field-r12/java'/REL
EXPECTED_BLOB = '119af8898ba1edbd654ae6edf43ea5f67c043b23'
OLD = '''    public static boolean protectedCell(ChunkAccess chunk, BlockPos pos) {
        Mask mask = chunk.neverOverworldDryMineMaskR12;
        if (mask == null) return false;
        int x = pos.getX()-chunk.getPos().getMinBlockX(), z = pos.getZ()-chunk.getPos().getMinBlockZ();
        return x>=0 && x<16 && z>=0 && z<16 && pos.getY()>=chunk.getMinY() && pos.getY()<chunk.getMaxY()
            && mask.interior.get(index(x,pos.getY(),z,chunk));
    }'''
NEW = '''    public static boolean protectedCell(ChunkAccess chunk, BlockPos pos) {
        // R399: releasing a transient LIGHT cache does not remove persisted protection.
        if (chunk.getMinY() != -512 || chunk.getHeight() != 1024) return false;
        final int worldX = pos.getX(), worldY = pos.getY(), worldZ = pos.getZ();
        final int localX = worldX - chunk.getPos().getMinBlockX();
        final int localZ = worldZ - chunk.getPos().getMinBlockZ();
        // Keep the exact vertical clipping used by paint(): bottom bedrock excluded.
        if (localX < 0 || localX >= 16 || localZ < 0 || localZ >= 16
            || worldY <= chunk.getMinY() || worldY > 128) return false;
        final Mask cached = chunk.neverOverworldDryMineMaskR12;
        if (cached != null) return cached.interior.get(index(localX, worldY, localZ, chunk));
        // No neighbour lookup, block write or persistent/cache mutation here.
        // readBoxes validates ALL recorded pieces before any positive answer.
        for (BoundingBox box : readBoxes(chunk)) {
            if (worldX >= box.minX() && worldX <= box.maxX()
                && worldY >= box.minY() && worldY <= box.maxY()
                && worldZ >= box.minZ() && worldZ <= box.maxZ()) return true;
        }
        return false;
    }'''

def blob(raw):
    return hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()

def transform(raw):
    text = raw.decode('utf-8')
    if text.count(NEW) == 1:
        restored = text.replace(NEW, OLD, 1).encode('utf-8')
        if blob(restored) == EXPECTED_BLOB:
            return raw
    if blob(raw) != EXPECTED_BLOB or text.count(OLD) != 1:
        raise ValueError('Uninspected dry-mine source; refusing to change it')
    return text.replace(OLD, NEW, 1).encode('utf-8')

class Tests(unittest.TestCase):
    def setUp(self): self.raw = SOURCE.read_bytes()
    def test_exact_input(self): self.assertEqual(blob(self.raw), EXPECTED_BLOB)
    def test_only_method_changed(self):
        out = transform(self.raw)
        self.assertEqual(out.replace(NEW.encode(), OLD.encode(), 1), self.raw)
    def test_idempotent(self): self.assertEqual(transform(transform(self.raw)), transform(self.raw))
    def test_unknown_source(self):
        with self.assertRaises(ValueError): transform(self.raw+b'// drift\n')
    def test_partial_new_source(self):
        with self.assertRaises(ValueError): transform(transform(self.raw).replace(b'worldY > 128', b'worldY > 129'))
    def test_no_new_writes(self):
        for word in ('setBlockState', '.getChunk(', 'persistentDataContainer.set', 'neverOverworldDryMineMaskR12 ='):
            self.assertNotIn(word, NEW)
    def test_read_validation_retained(self):
        before = self.raw.decode().split('    private static List<BoundingBox> readBoxes(', 1)[1].split('    public static final class Mask', 1)[0]
        after = transform(self.raw).decode().split('    private static List<BoundingBox> readBoxes(', 1)[1].split('    public static final class Mask', 1)[0]
        self.assertEqual(before, after)
    def test_piece_interiors_not_aggregate(self):
        self.assertIn('for (BoundingBox box : readBoxes(chunk))', NEW)
        self.assertNotIn('inflatedBy', NEW)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folia', nargs='?', type=Path)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    if args.folia is None: parser.error('materialized Folia checkout required')
    target = args.folia/'folia-server/src/minecraft/java'/REL
    raw = target.read_bytes(); updated = transform(raw)
    if args.check_only:
        if raw != updated: raise SystemExit('R399 is not installed; no file changed')
        print('R399 exact-source verification passed'); return
    if raw == updated: print('R399 already installed'); return
    backup = target.with_name(target.name+'.before-r399')
    with backup.open('xb') as out: out.write(raw)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.r399-', delete=False) as out:
            temporary = Path(out.name); out.write(updated); out.flush(); os.fsync(out.fileno())
        os.chmod(temporary, target.stat().st_mode & 0o777)
        if target.read_bytes() != raw: raise RuntimeError('Source changed during preparation')
        os.replace(temporary, target)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    print('R399 installed; backup:', backup)

if __name__ == '__main__': main()
