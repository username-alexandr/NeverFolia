#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

VILLAGE_RADIUS = '''        if (id.startsWith("minecraft:village_")) {
            return 48;
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
            // R4 field QA proved that the old majority gate could accept a
            // materially flooded village envelope. R5 keeps the representative
            // 3x3 footprint fully above Y=128 and restores availability through
            // placement policy instead of weakening terrain safety.
            return 9;
        }
        if ("minecraft:pillager_outpost".equals(id)) {
            // Outposts remain shoreline-tolerant but require a strong majority.
            return 7;
        }
        // Compact monuments and mansions stay fully above the Y=128 flood plane.
        return 9;
    }
'''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][TEST1 R5 village safety] {message}')


def tune(text: str, label: str) -> str:
    if text.count(VILLAGE_RADIUS) != 1:
        fail(f'{label}: expected village radius=48 exactly once, got {text.count(VILLAGE_RADIUS)}')

    dry_new = text.count(NEW_DRY_SAMPLES)
    dry_old = text.count(OLD_DRY_SAMPLES)
    if dry_new == 1 and dry_old == 0:
        validate(text, label)
        return text
    if dry_old != 1 or dry_new != 0:
        fail(f'{label}: expected one pre-R5 dry-sample block; old={dry_old}, new={dry_new}')

    text = text.replace(OLD_DRY_SAMPLES, NEW_DRY_SAMPLES, 1)
    validate(text, label)
    return text


def validate(text: str, label: str) -> None:
    required = (
        VILLAGE_RADIUS,
        NEW_DRY_SAMPLES,
        'if ("minecraft:pillager_outpost".equals(id))',
        'return 7;',
        'return 9;',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'{label}: missing R5 markers: {missing}')
    if OLD_DRY_SAMPLES in text:
        fail(f'{label}: pre-R5 village dry gate survived transformation')
    if 'return 32;' in text:
        fail(f'{label}: obsolete R3 village radius=32 survived')
    if 'return 5;' in text:
        fail(f'{label}: obsolete R3 village dry gate=5 survived')


def apply(root: Path) -> None:
    for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
        path = root / rel
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        path.write_text(tune(path.read_text(encoding='utf-8'), label), encoding='utf-8')

    print('[NeverFolia][TEST1 R5 village safety] flooded village policy applied')
    print('  village footprint radius: 48 blocks')
    print('  village dry gate: dry centre + 9/9 dry samples')
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
    with tempfile.TemporaryDirectory(prefix='nr-r5-village-safety-') as tmp:
        root = Path(tmp)
        for rel, class_name in ((FAST_REL, 'NeverOverworldVanillaFastLocate'), (POLICY_REL, 'NeverOverworldVanillaStructurePolicy')):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture(class_name), encoding='utf-8')
        apply(root)
        for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
            text = (root / rel).read_text(encoding='utf-8')
            validate(text, label)
            if tune(text, label) != text:
                fail(f'SELF-TEST {label}: idempotent reapply changed output')
    print('[NeverFolia][TEST1 R5 village safety] SELF-TEST OK')


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
