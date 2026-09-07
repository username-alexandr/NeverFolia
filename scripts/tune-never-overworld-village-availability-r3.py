#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

OLD_RADIUS = '''        if (id.startsWith("minecraft:village_")) {
            return 48;
        }
'''
NEW_RADIUS = '''        if (id.startsWith("minecraft:village_")) {
            return 32;
        }
'''

OLD_DRY_SAMPLES = '''    private static int minDrySamples(final String id) {
        if (id.startsWith("minecraft:village_") || "minecraft:pillager_outpost".equals(id)) {
            // Flooded-world settlements may touch the shoreline, but their core
            // and a strong majority of the sampled footprint must remain dry.
            return 7;
        }
        // Compact monuments and mansions stay fully above the Y=128 flood plane.
        return 9;
    }
'''
NEW_DRY_SAMPLES = '''    private static int minDrySamples(final String id) {
        if (id.startsWith("minecraft:village_")) {
            // Villages are common gameplay anchors. Keep the centre dry, but a
            // simple majority of the 3x3 footprint is enough for broad shores and
            // practical islands in the flooded world.
            return 5;
        }
        if ("minecraft:pillager_outpost".equals(id)) {
            // Outposts remain more selective than villages.
            return 7;
        }
        // Compact monuments and mansions stay fully above the Y=128 flood plane.
        return 9;
    }
'''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][TEST1 R3 village availability] {message}')


def tune(text: str, label: str) -> str:
    # Idempotence is useful when a local developer reapplies post-patches while
    # iterating in an existing worktree. A half-applied state is never accepted.
    radius_new = text.count(NEW_RADIUS)
    dry_new = text.count(NEW_DRY_SAMPLES)
    radius_old = text.count(OLD_RADIUS)
    dry_old = text.count(OLD_DRY_SAMPLES)

    if radius_new == 1 and dry_new == 1 and radius_old == 0 and dry_old == 0:
        validate(text, label)
        return text

    if radius_old != 1 or dry_old != 1:
        fail(
            f'{label}: expected exactly one pre-R3 village radius/dry-sample block; '
            f'old_radius={radius_old}, old_dry={dry_old}, '
            f'new_radius={radius_new}, new_dry={dry_new}'
        )

    text = text.replace(OLD_RADIUS, NEW_RADIUS, 1)
    text = text.replace(OLD_DRY_SAMPLES, NEW_DRY_SAMPLES, 1)
    validate(text, label)
    return text


def validate(text: str, label: str) -> None:
    required = (
        NEW_RADIUS,
        NEW_DRY_SAMPLES,
        'if ("minecraft:pillager_outpost".equals(id))',
        'return 5;',
        'return 7;',
        'return 9;',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'{label}: missing R3 markers: {missing}')
    if OLD_RADIUS in text or OLD_DRY_SAMPLES in text:
        fail(f'{label}: pre-R3 village policy survived transformation')


def apply(root: Path) -> None:
    paths = (
        ('fast-locate', root / FAST_REL),
        ('generation-policy', root / POLICY_REL),
    )
    for label, path in paths:
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        text = path.read_text(encoding='utf-8')
        path.write_text(tune(text, label), encoding='utf-8')

    print('[NeverFolia][TEST1 R3 village availability] flooded village policy applied')
    print('  village footprint radius: 32 blocks')
    print('  village dry gate: dry centre + >=5/9 dry samples')
    print('  pillager outpost remains: radius=24, >=7/9 dry samples')
    print('  mansion remains: radius=40, 9/9 dry samples')


def fixture(class_name: str) -> str:
    return f'''final class {class_name} {{
    private static int sampleRadius(final String id) {{
        if ("minecraft:mansion".equals(id)) {{
            return 40;
        }}
        if (id.startsWith("minecraft:village_")) {{
            return 48;
        }}
        if ("minecraft:pillager_outpost".equals(id)) {{
            return 24;
        }}
        if ("minecraft:desert_pyramid".equals(id) || "minecraft:jungle_pyramid".equals(id)) {{
            return 16;
        }}
        if ("minecraft:igloo".equals(id)) {{
            return 10;
        }}
        return 16;
    }}

    private static int minDrySamples(final String id) {{
        if (id.startsWith("minecraft:village_") || "minecraft:pillager_outpost".equals(id)) {{
            // Flooded-world settlements may touch the shoreline, but their core
            // and a strong majority of the sampled footprint must remain dry.
            return 7;
        }}
        // Compact monuments and mansions stay fully above the Y=128 flood plane.
        return 9;
    }}
}}
'''


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='nr-r3-village-availability-') as tmp:
        root = Path(tmp)
        for rel, class_name in (
            (FAST_REL, 'NeverOverworldVanillaFastLocate'),
            (POLICY_REL, 'NeverOverworldVanillaStructurePolicy'),
        ):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture(class_name), encoding='utf-8')

        apply(root)

        for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
            text = (root / rel).read_text(encoding='utf-8')
            validate(text, label)
            # Verify idempotence as part of the self-test.
            if tune(text, label) != text:
                fail(f'SELF-TEST {label}: idempotent reapply changed output')

    print('[NeverFolia][TEST1 R3 village availability] SELF-TEST OK')


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
