#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

HELPER_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java')
OLD = '''    private static boolean isSugarCaneGround(final BlockState state) {
        return state.is(net.minecraft.tags.BlockTags.DIRT)
            || state.is(net.minecraft.tags.BlockTags.SAND);
    }
'''
NEW = '''    private static boolean isSugarCaneGround(final BlockState state) {
        // Use Minecraft 26.2's canonical sugar-cane substrate tag. Besides dirt
        // and sand it includes grass, mud and moss substrates that commonly form
        // NeverOverworld's new Y=128 flood shoreline.
        return state.is(net.minecraft.tags.BlockTags.SUPPORTS_SUGAR_CANE);
    }
'''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][shoreline sugar cane] {message}')


def patch(text: str) -> str:
    if 'BlockTags.SUPPORTS_SUGAR_CANE' in text:
        return text
    if text.count(OLD) != 1:
        fail(f'expected one legacy sugar-cane ground helper, got {text.count(OLD)}')
    text = text.replace(OLD, NEW, 1)
    if 'BlockTags.DIRT' in text or 'BlockTags.SAND' in text:
        fail('legacy narrowed substrate tags survived')
    return text


def apply(root: Path) -> None:
    helper = root / HELPER_REL
    if not helper.is_file():
        fail(f'NeverOverworldFlood helper not found: {helper}')
    helper.write_text(patch(helper.read_text(encoding='utf-8')), encoding='utf-8')
    print('[NeverFolia][shoreline sugar cane] canonical 26.2 substrate support applied')
    print('  substrate tag: minecraft:supports_sugar_cane')
    print('  includes dirt/sand plus grass, mud and moss shoreline substrates')


def self_test() -> None:
    fixture = '''final class NeverOverworldFlood {
    private static boolean isSugarCaneGround(final BlockState state) {
        return state.is(net.minecraft.tags.BlockTags.DIRT)
            || state.is(net.minecraft.tags.BlockTags.SAND);
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='nr-shoreline-sugar-cane-') as tmp:
        root = Path(tmp)
        helper = root / HELPER_REL
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(fixture, encoding='utf-8')
        apply(root)
        out = helper.read_text(encoding='utf-8')
        if 'BlockTags.SUPPORTS_SUGAR_CANE' not in out:
            fail('SELF-TEST: canonical substrate tag missing')
    print('[NeverFolia][shoreline sugar cane] SELF-TEST OK')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('folia_root', nargs='?', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia_root is None:
        parser.error('folia_root is required unless --self-test is used')
    apply(args.folia_root.resolve())


if __name__ == '__main__':
    main()
