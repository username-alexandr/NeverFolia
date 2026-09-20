#!/usr/bin/env python3
"""Preserve logs/leaves in the FINAL NeverOverworld LIGHT flood predicates.

Run after FIELD-R10, FIELD-R11 and DESERT-R1: the earlier exact-source stages
still validate their historic inputs, then this stage replaces the obsolete
block-wise tree erasure policy. It does not inspect/mutate saved worlds, add a
submersion quota, change tree frequency, or read neighbouring chunks.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import unittest

JAVA = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk')
TARGETS = {
    'NeverOverworldFlood.java': '    private static boolean isFloodable(final BlockState state) {\n',
    'NeverOverworldFloodBoundaryR11.java': '    static boolean isFloodable(final BlockState state) {\n',
}
LEGACY_LOGS = '            || state.is(net.minecraft.tags.BlockTags.LOGS)\n'
LEGACY_LEAVES = '            || state.is(net.minecraft.tags.BlockTags.LEAVES)\n'
MARKER = '        // TREE-R1: submersion alone never authorizes removal of a log or leaf.\n'
GUARD = (MARKER
         + '        if (state.is(net.minecraft.tags.BlockTags.LOGS)\n'
         + '            || state.is(net.minecraft.tags.BlockTags.LEAVES)) return false;\n')


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError('[NeverFolia][TREE-R1] ' + message)


def patch(source: str, name: str) -> str:
    """Fail closed on duplicate, partial or unrecognized predicate installation."""
    signature = TARGETS[name]
    require(source.count(signature) == 1, name + ': expected exactly one flood predicate')
    start = source.index(signature) + len(signature)
    end = source.find('\n    }', start)
    require(end >= start, name + ': predicate end missing')
    body = source[start:end]
    require('state.isAir()' in body and 'state.canBeReplaced()' in body,
            name + ': base flood semantics missing')
    if MARKER in source:
        require(source.count(MARKER) == 1 and body.startswith(GUARD),
                name + ': partial/duplicate tree protection')
        require(LEGACY_LOGS not in body and LEGACY_LEAVES not in body,
                name + ': legacy tree erasure still present')
        return source
    require('BlockTags.LOGS' not in body.replace(LEGACY_LOGS, '')
            and 'BlockTags.LEAVES' not in body.replace(LEGACY_LEAVES, ''),
            name + ': unknown pre-existing tree predicate')
    if name == 'NeverOverworldFlood.java':
        require(body.count(LEGACY_LOGS) == body.count(LEGACY_LEAVES) == 1,
                name + ': expected the historic LOGS/LEAVES erasure pair')
        body = body.replace(LEGACY_LOGS, '', 1).replace(LEGACY_LEAVES, '', 1)
    else:
        require(LEGACY_LOGS not in body and LEGACY_LEAVES not in body,
                name + ': unexpected boundary tree erasure pair')
    return source[:start] + GUARD + body + source[end:]


def prepare(folia: Path) -> dict[Path, str]:
    staged = {}
    for name in TARGETS:
        path = folia / JAVA / name
        require(path.is_file(), 'materialized production source missing: ' + str(path))
        staged[path] = patch(path.read_text(encoding='utf-8'), name)
    return staged


def fixture(name: str) -> str:
    legacy = LEGACY_LOGS + LEGACY_LEAVES if name == 'NeverOverworldFlood.java' else ''
    return ('class Fixture {\n' + TARGETS[name]
            + '        return state.isAir()\n'
            + '            || (state.getFluidState().isEmpty() && state.canBeReplaced())\n'
            + legacy + '            || state.is(Blocks.SUGAR_CANE);\n'
            + '    }\n}\n')


class TransformerTests(unittest.TestCase):
    def test_main_removes_legacy_pair_and_protects_before_replaceable(self):
        out = patch(fixture('NeverOverworldFlood.java'), 'NeverOverworldFlood.java')
        self.assertNotIn(LEGACY_LOGS, out)
        self.assertNotIn(LEGACY_LEAVES, out)
        self.assertLess(out.index(GUARD), out.index('return state.isAir()'))
        self.assertIn('state.canBeReplaced()', out)
        self.assertIn('state.is(Blocks.SUGAR_CANE)', out)

    def test_boundary_protection_before_generic_replaceable(self):
        name = 'NeverOverworldFloodBoundaryR11.java'
        out = patch(fixture(name), name)
        self.assertLess(out.index(GUARD), out.index('state.canBeReplaced()'))

    def test_idempotent_both_targets(self):
        for name in TARGETS:
            first = patch(fixture(name), name)
            self.assertEqual(patch(first, name), first)

    def test_missing_or_duplicate_predicate_rejected(self):
        for name in TARGETS:
            for bad in ('class Empty {}', fixture(name) + fixture(name)):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    patch(bad, name)

    def test_partial_legacy_pair_rejected(self):
        name = 'NeverOverworldFlood.java'
        for old in (LEGACY_LOGS, LEGACY_LEAVES):
            with self.assertRaises(ValueError):
                patch(fixture(name).replace(old, ''), name)

    def test_marker_cannot_hide_missing_guard(self):
        name = 'NeverOverworldFlood.java'
        good = patch(fixture(name), name)
        with self.assertRaises(ValueError):
            patch(good.replace(')) return false;', ')) return true;'), name)

    def test_unrelated_methods_unchanged(self):
        name = 'NeverOverworldFlood.java'
        extra = '\nvoid unrelated() { chunk.setBlockState(pos, water, 0); }\n'
        out = patch(fixture(name) + extra, name)
        self.assertTrue(out.endswith(extra))

    def test_prepare_failure_writes_neither_file(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); directory = root / JAVA; directory.mkdir(parents=True)
            first = directory / 'NeverOverworldFlood.java'
            first.write_text(fixture(first.name))
            before = first.read_bytes()
            with self.assertRaises(ValueError):
                prepare(root)
            self.assertEqual(first.read_bytes(), before)


def self_test() -> None:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TransformerTests))
    if not result.wasSuccessful():
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folia', nargs='?', type=Path)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None:
        parser.error('folia worktree is required unless --self-test is used')
    staged = prepare(args.folia.resolve())
    if args.check_only:
        print('[NeverFolia][TREE-R1] preflight OK; no files changed')
        return
    for path, content in staged.items():
        path.write_text(content, encoding='utf-8')
    print('[NeverFolia][TREE-R1] logs/leaves preserved in surface, R8 and FIELD-R11 floods')


if __name__ == '__main__':
    main()
