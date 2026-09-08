#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

OLD_RADIUS = '''            final int halfRadius = Math.max(1, radius / 2);
            final int[] villageOffsets = {-radius, -halfRadius, 0, halfRadius, radius};
'''
NEW_RADIUS = '''            final int villageRadius = 32;
            final int halfRadius = 16;
            final int[] villageOffsets = {-villageRadius, -halfRadius, 0, halfRadius, villageRadius};
'''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][dense village radius32] {message}')


def tune(text: str, label: str) -> str:
    old_count = text.count(OLD_RADIUS)
    new_count = text.count(NEW_RADIUS)

    if new_count == 1 and old_count == 0:
        validate(text, label)
        return text

    if old_count != 1 or new_count != 0:
        fail(
            f'{label}: expected exactly one inherited dense-radius block; '
            f'old={old_count} new={new_count}'
        )

    text = text.replace(OLD_RADIUS, NEW_RADIUS, 1)
    validate(text, label)
    return text


def validate(text: str, label: str) -> None:
    required = (
        'if (id.startsWith("minecraft:village_"))',
        'final int villageRadius = 32;',
        'final int halfRadius = 16;',
        'final int[] villageOffsets = {-villageRadius, -halfRadius, 0, halfRadius, villageRadius};',
        'MIN_DRY_BASE_HEIGHT',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'{label}: radius32 dense markers missing: {missing}')
    if text.count(NEW_RADIUS) != 1:
        fail(f'{label}: radius32 block count mismatch')
    if OLD_RADIUS in text:
        fail(f'{label}: inherited sampleRadius village envelope survived')


def apply(root: Path) -> None:
    for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
        path = root / rel
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        text = path.read_text(encoding='utf-8')
        path.write_text(tune(text, label), encoding='utf-8')

    print('[NeverFolia][dense village radius32] FIXED DENSE 5x5 ENVELOPE APPLIED')
    print('  village radius: 32 blocks')
    print('  village offsets: -32, -16, 0, 16, 32')
    print('  fast-locate and generation policy remain geometry-identical')
    print('  all 25 village samples must remain above the Y=128 flood plane')
    print('  persisted Jigsaw bbox zero-water audit remains final authority')


def fixture(class_name: str) -> str:
    return f'''final class {class_name} {{
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    boolean test(String id) {{
        final int radius = sampleRadius(id);
        if (id.startsWith("minecraft:village_")) {{
{OLD_RADIUS.rstrip()}
            for (final int dx : villageOffsets) {{
                for (final int dz : villageOffsets) {{
                    if (dx == 0 && dz == 0) continue;
                    if (MIN_DRY_BASE_HEIGHT < 0) return false;
                }}
            }}
            return true;
        }}
        return radius > 0;
    }}
    private static int sampleRadius(String id) {{ return 48; }}
}}
'''


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='nr-dense-radius32-') as tmp:
        root = Path(tmp)
        for label, rel, class_name in (
            ('fast-locate', FAST_REL, 'NeverOverworldVanillaFastLocate'),
            ('generation-policy', POLICY_REL, 'NeverOverworldVanillaStructurePolicy'),
        ):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture(class_name), encoding='utf-8')
            out = tune(path.read_text(encoding='utf-8'), label)
            validate(out, label)
            if tune(out, label) != out:
                fail(f'SELF-TEST {label}: idempotent reapply changed output')
    print('[NeverFolia][dense village radius32] SELF-TEST OK')


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

    self_test()
    apply(args.folia_root.resolve())


if __name__ == '__main__':
    main()
