#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

# Minecraft 26.2 vanilla village_*.json: max_distance_from_center = 80.
# Persisted TEST1 plains QA measured a real Jigsaw bbox reaching ~83 blocks
# from the candidate chunk centre, so one full 16-block chunk of overhang
# margin is reserved. Step 16 keeps the envelope dense enough to detect
# shoreline corridors between the old sparse probes.
VILLAGE_REACH = 96
VILLAGE_STEP = 16
OFFSETS = (-96, 96, -80, 80, -64, 64, -48, 48, -32, 32, -16, 16, 0)
OFFSETS_JAVA = '{' + ', '.join(str(v) for v in OFFSETS) + '}'

FAST_OLD = '''            // The center was already proven dry above and reused for the biome
            // check. Probe the remaining 24 points in a 5x5 envelope so fast
            // locate and real generation reject the same shoreline gaps.
            final int villageRadius = 32;
            final int halfRadius = 16;
            final int[] villageOffsets = {-villageRadius, -halfRadius, 0, halfRadius, villageRadius};
'''
FAST_NEW = f'''            // Vanilla 26.2 villages allow Jigsaw anchors up to 80 blocks from
            // the centre. Persisted QA observed piece bboxes beyond that reach,
            // so reserve one chunk of overhang and sample every 16 blocks.
            // The offset order checks the outer envelope first for cheap rejection.
            final int villageReach = {VILLAGE_REACH};
            final int villageStep = {VILLAGE_STEP};
            final int[] villageOffsets = {OFFSETS_JAVA};
'''

POLICY_OLD = '''            // Dense generation-side contract: all 25 points across the village
            // representative footprint must remain above the Y=128 flood plane.
            final int villageRadius = 32;
            final int halfRadius = 16;
            final int[] villageOffsets = {-villageRadius, -halfRadius, 0, halfRadius, villageRadius};
'''
POLICY_NEW = f'''            // Generation-side contract matches fast locate: vanilla Jigsaw
            // reach 80 + one 16-block bbox-overhang margin, sampled every 16.
            // This is 13x13 / 169 exact WORLD_SURFACE_WG probes with early exit.
            final int villageReach = {VILLAGE_REACH};
            final int villageStep = {VILLAGE_STEP};
            final int[] villageOffsets = {OFFSETS_JAVA};
'''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][village reach96] {message}')


def tune(text: str, label: str, old: str, new: str) -> str:
    old_count = text.count(old)
    new_count = text.count(new)
    if new_count == 1 and old_count == 0:
        validate(text, label, new)
        return text
    if old_count != 1 or new_count != 0:
        fail(f'{label}: expected one radius32 block before reach96 transform; old={old_count} new={new_count}')
    text = text.replace(old, new, 1)
    validate(text, label, new)
    return text


def validate(text: str, label: str, new: str) -> None:
    required = (
        'if (id.startsWith("minecraft:village_"))',
        f'final int villageReach = {VILLAGE_REACH};',
        f'final int villageStep = {VILLAGE_STEP};',
        f'final int[] villageOffsets = {OFFSETS_JAVA};',
        'MIN_DRY_BASE_HEIGHT',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'{label}: reach96 markers missing: {missing}')
    if text.count(new) != 1:
        fail(f'{label}: reach96 block count mismatch')
    if 'final int villageRadius = 32;' in text:
        fail(f'{label}: radius32 village envelope survived')
    if len(OFFSETS) != 13 or set(OFFSETS) != set(range(-VILLAGE_REACH, VILLAGE_REACH + 1, VILLAGE_STEP)):
        fail('internal offset contract is not complete -96..96 step16')


def apply(root: Path) -> None:
    specs = (
        ('fast-locate', FAST_REL, FAST_OLD, FAST_NEW),
        ('generation-policy', POLICY_REL, POLICY_OLD, POLICY_NEW),
    )
    for label, rel, old, new in specs:
        path = root / rel
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        out = tune(path.read_text(encoding='utf-8'), label, old, new)
        path.write_text(out, encoding='utf-8')

    print('[NeverFolia][village reach96] BBOX-SIZED DENSE ENVELOPE APPLIED')
    print('  vanilla village max_distance_from_center: 80')
    print('  bbox overhang safety margin: 16')
    print('  final reach: 96 blocks')
    print('  grid: 13x13 / 169 points, step=16, outer-first order')
    print('  fast-locate: center + up to 168 preliminary-surface probes')
    print('  generation: up to 169 exact WORLD_SURFACE_WG probes')
    print('  both paths short-circuit on the first wet point')
    print('  persisted Jigsaw bbox zero-water audit remains authoritative')


def fixture(class_name: str, block: str) -> str:
    return f'''final class {class_name} {{
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    boolean test(String id) {{
        if (id.startsWith("minecraft:village_")) {{
{block.rstrip()}
            for (final int dx : villageOffsets) {{
                for (final int dz : villageOffsets) {{
                    if (dx == 0 && dz == 0) continue;
                    if (MIN_DRY_BASE_HEIGHT < 0) return false;
                }}
            }}
            return true;
        }}
        return false;
    }}
}}
'''


def self_test() -> None:
    if VILLAGE_REACH != 80 + 16:
        fail('SELF-TEST: reach is not vanilla 80 + one chunk margin')
    expected = set(range(-96, 97, 16))
    if len(OFFSETS) != 13 or set(OFFSETS) != expected or OFFSETS[-1] != 0:
        fail(f'SELF-TEST: offset coverage/order drifted: {OFFSETS}')

    with tempfile.TemporaryDirectory(prefix='nr-village-reach96-') as tmp:
        root = Path(tmp)
        cases = (
            ('fast-locate', FAST_REL, 'NeverOverworldVanillaFastLocate', FAST_OLD, FAST_NEW),
            ('generation-policy', POLICY_REL, 'NeverOverworldVanillaStructurePolicy', POLICY_OLD, POLICY_NEW),
        )
        for label, rel, class_name, old, new in cases:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture(class_name, old), encoding='utf-8')
            first = tune(path.read_text(encoding='utf-8'), label, old, new)
            validate(first, label, new)
            second = tune(first, label, old, new)
            if second != first:
                fail(f'SELF-TEST {label}: idempotent reapply changed output')
    print('[NeverFolia][village reach96] SELF-TEST OK')


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
