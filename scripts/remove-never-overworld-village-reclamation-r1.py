#!/usr/bin/env python3
"""Remove only the custom post-placement village sea-level reclamation hook.

Historical V17/FIELD-R10 stages still validate before this final override.
Vanilla/Jigsaw placement and structure.afterPlace remain unchanged. No new
foundation inference is made from arbitrary terrain/trees inside a piece bbox.
Saved regions are never opened or rewritten by this source transformer.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile
import unittest

TARGET = Path('folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/StructureStart.java')
AFTER_PLACE = '            this.structure.afterPlace(level, structureManager, generator, random, chunkBB, chunkPos, this.pieceContainer);\n'
CALL = '            NeverOverworldVillageReclamation.apply(level, this, chunkPos);\n'
MARKER = ('            // VILLAGE-NOFILL-R1: keep vanilla placement; never reclaim the surrounding ocean to Y=128.\n')
CALL_PATTERN = re.compile(r'NeverOverworldVillageReclamation\s*\.\s*apply\s*\(')


def require(ok: bool, message: str) -> None:
    if not ok: raise ValueError('[NeverFolia][VILLAGE-NOFILL-R1] ' + message)


def patch(source: str) -> str:
    require(source.count(AFTER_PLACE) == 1, 'expected exactly one vanilla afterPlace call')
    if MARKER in source:
        require(source.count(MARKER) == 1 and AFTER_PLACE + MARKER in source,
                'partial/duplicate no-reclamation installation')
        require(not CALL_PATTERN.search(source), 'reclamation call survived no-fill override')
        return source
    require(source.count(AFTER_PLACE + CALL) == 1 and len(CALL_PATTERN.findall(source)) == 1,
            'expected one inspected custom reclamation call immediately after vanilla placement')
    result = source.replace(AFTER_PLACE + CALL, AFTER_PLACE + MARKER, 1)
    require(not CALL_PATTERN.search(result), 'custom reclamation call was not removed')
    require(result.replace(MARKER, '', 1) == source.replace(CALL, '', 1),
            'unexpected changes outside the custom call')
    return result


def prepare(folia: Path) -> tuple[Path, str]:
    path = folia / TARGET
    require(path.is_file(), 'materialized StructureStart source missing: ' + str(path))
    return path, patch(path.read_text(encoding='utf-8'))


def fixture() -> str:
    return ('class StructureStart {\n'
            '    void placeInChunk() {\n'
            '        for (var piece : pieces) { piece.postProcess(level); }\n'
            + AFTER_PLACE + CALL + '    }\n'
            '    boolean isValid() { return !pieces.isEmpty(); }\n}\n')


class NoReclamationTests(unittest.TestCase):
    def test_removes_only_custom_fill(self):
        before = fixture(); after = patch(before)
        self.assertNotRegex(after, CALL_PATTERN)
        self.assertEqual(before.replace(CALL, ''), after.replace(MARKER, ''))

    def test_vanilla_piece_and_after_place_preserved(self):
        after = patch(fixture())
        self.assertEqual(after.count('piece.postProcess(level);'), 1)
        self.assertEqual(after.count(AFTER_PLACE), 1)
        self.assertIn('boolean isValid() { return !pieces.isEmpty(); }', after)

    def test_never_adds_world_reads_writes_or_height_queries(self):
        difference = patch(fixture()).replace(fixture().replace(CALL, ''), '')
        for forbidden in ('setBlock', 'getChunk(', 'getHeight(', 'getBaseHeight(', 'for (int y'):
            self.assertNotIn(forbidden, MARKER)
        self.assertIn(MARKER, difference)

    def test_idempotent(self):
        once = patch(fixture()); self.assertEqual(patch(once), once)

    def test_missing_hook_is_not_silently_accepted(self):
        with self.assertRaises(ValueError): patch(fixture().replace(CALL, ''))

    def test_duplicate_hook_rejected(self):
        with self.assertRaises(ValueError): patch(fixture() + CALL)

    def test_duplicate_vanilla_call_rejected(self):
        with self.assertRaises(ValueError): patch(fixture() + AFTER_PLACE)

    def test_reordered_hook_rejected(self):
        with self.assertRaises(ValueError): patch(fixture().replace(AFTER_PLACE + CALL, CALL + AFTER_PLACE))

    def test_reenabled_hook_rejected(self):
        with self.assertRaises(ValueError): patch(patch(fixture()) + CALL)

    def test_spaced_duplicate_hook_rejected(self):
        with self.assertRaises(ValueError): patch(fixture() + 'NeverOverworldVillageReclamation . apply(level, start, cp);')

    def test_invalid_input_does_not_modify_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); path = root / TARGET; path.parent.mkdir(parents=True)
            path.write_text(fixture().replace(CALL, ''))
            before = path.read_bytes()
            with self.assertRaises(ValueError): prepare(root)
            self.assertEqual(path.read_bytes(), before)

    def test_preflight_read_only(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); path = root / TARGET; path.parent.mkdir(parents=True)
            path.write_text(fixture()); before = path.read_bytes()
            target, result = prepare(root)
            self.assertEqual(target, path); self.assertIn(MARKER, result)
            self.assertEqual(path.read_bytes(), before)


def self_test() -> None:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(NoReclamationTests))
    if not result.wasSuccessful(): raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folia', nargs='?', type=Path)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.self_test: self_test(); return
    if args.folia is None: parser.error('folia worktree required unless --self-test is used')
    path, result = prepare(args.folia.resolve())
    if args.check_only:
        print('[NeverFolia][VILLAGE-NOFILL-R1] source preflight OK; no writes'); return
    path.write_text(result, encoding='utf-8')
    print('[NeverFolia][VILLAGE-NOFILL-R1] custom Y=128 reclamation removed; vanilla placement retained')


if __name__ == '__main__': main()
