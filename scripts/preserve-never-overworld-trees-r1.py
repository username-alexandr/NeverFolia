#!/usr/bin/env python3
"""Explicitly protect logs/leaves in the inspected FINAL R9/R11 flood predicates.

R9 already removes R8's positive LOGS/LEAVES clauses. This final stage must
recognize that real input, not require the obsolete R8 clauses to survive.
Never edits saved worlds, tree distribution, or neighbouring chunks.
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
R9_MARKER = '// NeverFolia R9: interpolated drowned sediment'
R9_POWDER = '        removeDeepPowderSnow(chunk, minY, FLOOD_LEVEL - 1, air);\n'
R8_CALL = '        floodLargeBoundaryConnectedCaverns(chunk, minY, FLOOD_LEVEL, water);\n'
MARKER = '        // TREE-R1: submersion alone never authorizes removal of a log or leaf.\n'
GUARD = (MARKER
         + '        if (state.is(net.minecraft.tags.BlockTags.LOGS)\n'
         + '            || state.is(net.minecraft.tags.BlockTags.LEAVES)) return false;\n')


def expected_body(name: str) -> str:
    # Both methods have the same semantics, but the historical main helper
    # uses qualified class names for the ecology clauses.
    main = name == 'NeverOverworldFlood.java'
    tags = 'net.minecraft.tags.BlockTags' if main else 'BlockTags'
    blocks = 'net.minecraft.world.level.block.Blocks' if main else 'Blocks'
    return ('        return state.isAir()\n'
            '            || state.is(Blocks.WATER)\n'
            '            || (state.getFluidState().isEmpty() && state.canBeReplaced())\n'
            f'            || state.is({tags}.RAILS)\n'
            f'            || state.is({blocks}.SUGAR_CANE)\n'
            f'            || state.is({blocks}.LILY_PAD)\n'
            f'            || state.is({blocks}.MUSHROOM_STEM)\n'
            f'            || state.is({blocks}.RED_MUSHROOM_BLOCK)\n'
            f'            || state.is({blocks}.BROWN_MUSHROOM_BLOCK);')


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError('[NeverFolia][TREE-R1] ' + message)


def patch(source: str, name: str) -> str:
    """Accept only the complete inspected final predicate, or our exact output."""
    signature = TARGETS[name]
    require(source.count(signature) == 1, name + ': expected exactly one flood predicate')
    start = source.index(signature) + len(signature)
    end = source.find('\n    }', start)
    require(end >= start, name + ': predicate end missing')
    body = source[start:end]
    if name == 'NeverOverworldFlood.java':
        require(R9_MARKER in source and source.count(R9_POWDER) == 1,
                name + ': final R9 stabilization must be installed first')
        require(R8_CALL not in source, name + ': obsolete R8 fallback is still active')
    expected = expected_body(name)
    if MARKER in source:
        require(source.count(MARKER) == 1 and body == GUARD + expected,
                name + ': partial, duplicate or changed TREE-R1 predicate')
        return source
    require(body == expected,
            name + ': final R9/R11 predicate differs from inspected input; refusing partial rewrite')
    return source[:start] + GUARD + body + source[end:]


def prepare(folia: Path) -> dict[Path, str]:
    staged = {}
    for name in TARGETS:
        path = folia / JAVA / name
        require(path.is_file(), 'materialized production source missing: ' + str(path))
        staged[path] = patch(path.read_text(encoding='utf-8'), name)
    return staged


def fixture(name: str) -> str:
    prefix = 'class Fixture {\n'
    if name == 'NeverOverworldFlood.java':
        prefix += '    ' + R9_MARKER + '\n    void apply() {\n' + R9_POWDER + '    }\n'
    return prefix + TARGETS[name] + expected_body(name) + '\n    }\n}\n'


class TransformerTests(unittest.TestCase):
    def test_real_r9_input_has_no_positive_log_leaf_clauses(self):
        name = 'NeverOverworldFlood.java'
        original = fixture(name)
        self.assertNotIn('BlockTags.LOGS', original)
        self.assertNotIn('BlockTags.LEAVES', original)
        out = patch(original, name)
        self.assertIn(GUARD, out)
        self.assertLess(out.index(GUARD), out.index('return state.isAir()'))
        self.assertEqual(out.replace(GUARD, '', 1), original)

    def test_boundary_protection_before_generic_replaceable(self):
        name = 'NeverOverworldFloodBoundaryR11.java'
        out = patch(fixture(name), name)
        self.assertLess(out.index(GUARD), out.index('state.canBeReplaced()'))

    def test_water_and_non_tree_ecology_unchanged(self):
        for name in TARGETS:
            out = patch(fixture(name), name)
            self.assertIn(expected_body(name), out)
            self.assertIn('|| state.is(Blocks.WATER)', out)

    def test_idempotent_both_targets(self):
        for name in TARGETS:
            first = patch(fixture(name), name)
            self.assertEqual(patch(first, name), first)

    def test_missing_or_duplicate_predicate_rejected(self):
        for name in TARGETS:
            for bad in ('class Empty {}', fixture(name) + fixture(name)):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    patch(bad, name)

    def test_obsolete_r8_pair_rejected_not_required(self):
        name = 'NeverOverworldFlood.java'
        for tag in ('LOGS', 'LEAVES'):
            old = fixture(name).replace('return state.isAir()',
                'return state.isAir()\n            || state.is(net.minecraft.tags.BlockTags.' + tag + ')')
            with self.assertRaises(ValueError): patch(old, name)

    def test_unknown_clause_rejected(self):
        for name in TARGETS:
            bad = fixture(name).replace('return state.isAir()', 'return state.isAir() || state.is(Blocks.STONE)')
            with self.assertRaises(ValueError): patch(bad, name)

    def test_missing_r9_markers_rejected(self):
        name = 'NeverOverworldFlood.java'
        for marker in (R9_MARKER, R9_POWDER):
            with self.assertRaises(ValueError): patch(fixture(name).replace(marker, ''), name)

    def test_r8_runtime_call_cannot_be_reenabled(self):
        name = 'NeverOverworldFlood.java'
        with self.assertRaises(ValueError): patch(fixture(name) + R8_CALL, name)

    def test_marker_cannot_hide_wrong_guard(self):
        for name in TARGETS:
            good = patch(fixture(name), name)
            with self.assertRaises(ValueError): patch(good.replace('return false;', 'return true;'), name)

    def test_changed_installed_return_rejected(self):
        name = 'NeverOverworldFlood.java'
        with self.assertRaises(ValueError):
            patch(patch(fixture(name), name).replace('state.canBeReplaced()', 'true'), name)

    def test_unrelated_methods_unchanged(self):
        name = 'NeverOverworldFlood.java'
        extra = '\nvoid unrelated() { chunk.setBlockState(pos, water, 0); }\n'
        self.assertTrue(patch(fixture(name) + extra, name).endswith(extra))

    def test_prepare_failure_writes_neither_file(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); directory = root / JAVA; directory.mkdir(parents=True)
            first = directory / 'NeverOverworldFlood.java'
            first.write_text(fixture(first.name))
            before = first.read_bytes()
            with self.assertRaises(ValueError): prepare(root)
            self.assertEqual(first.read_bytes(), before)


def self_test() -> None:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TransformerTests))
    if not result.wasSuccessful(): raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folia', nargs='?', type=Path)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.self_test: self_test(); return
    if args.folia is None: parser.error('folia worktree is required unless --self-test is used')
    staged = prepare(args.folia.resolve())
    if args.check_only:
        print('[NeverFolia][TREE-R1] preflight OK; no files changed'); return
    for path, content in staged.items(): path.write_text(content, encoding='utf-8')
    print('[NeverFolia][TREE-R1] explicit log/leaf exclusion installed on final R9/R11 predicates')


if __name__ == '__main__': main()
