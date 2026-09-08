#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

RADIUS_48 = '''        if (id.startsWith("minecraft:village_")) {
            return 48;
        }
'''
RADIUS_32 = '''        if (id.startsWith("minecraft:village_")) {
            return 32;
        }
'''

# R6 keeps the strict R5 9/9 dry contract. Only the representative footprint
# radius is reduced. The persisted-structure QA remains the final safety gate:
# every generated village bbox must contain zero water samples at Y=128.
VILLAGE_DRY_9 = re.compile(
    r'if\s*\(id\.startsWith\("minecraft:village_"\)\)\s*\{[\s\S]{0,900}?return\s+9;\s*\}'
)


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][TEST1 R6 village availability] {message}')


def validate(text: str, label: str) -> None:
    if text.count(RADIUS_32) != 1:
        fail(f'{label}: expected exactly one village radius=32 block, got {text.count(RADIUS_32)}')
    if RADIUS_48 in text:
        fail(f'{label}: obsolete R5 village radius=48 survived R6 availability tuning')
    if VILLAGE_DRY_9.search(text) is None:
        fail(f'{label}: strict village dry gate drifted; expected 9/9')


def tune(text: str, label: str) -> str:
    if text.count(RADIUS_32) == 1 and RADIUS_48 not in text:
        validate(text, label)
        return text
    if text.count(RADIUS_48) != 1 or RADIUS_32 in text:
        fail(
            f'{label}: expected one strict R5 radius=48 block or an already tuned radius=32 block; '
            f'r48={text.count(RADIUS_48)} r32={text.count(RADIUS_32)}'
        )
    if VILLAGE_DRY_9.search(text) is None:
        fail(f'{label}: refusing to reduce radius unless the strict R5 9/9 dry gate is present')
    text = text.replace(RADIUS_48, RADIUS_32, 1)
    validate(text, label)
    return text


def apply(root: Path) -> None:
    for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
        path = root / rel
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        path.write_text(tune(path.read_text(encoding='utf-8'), label), encoding='utf-8')
    print('[NeverFolia][TEST1 R6 village availability] strict dry village availability applied')
    print('  representative village radius: 32 blocks')
    print('  village dry gate: 9/9 samples above Y=128')
    print('  persisted village bbox zero-water QA remains authoritative')


def fixture(class_name: str, radius: int) -> str:
    return f'''final class {class_name} {{
    private static int sampleRadius(final String id) {{
        if ("minecraft:woodland_mansion".equals(id)) {{
            return 40;
        }}
        if (id.startsWith("minecraft:village_")) {{
            return {radius};
        }}
        if ("minecraft:pillager_outpost".equals(id)) {{
            return 24;
        }}
        return 16;
    }}

    private static int minDrySamples(final String id) {{
        if (id.startsWith("minecraft:village_")) {{
            // Strict flooded-world village safety.
            return 9;
        }}
        if ("minecraft:pillager_outpost".equals(id)) {{
            return 7;
        }}
        return 9;
    }}
}}
'''


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='nr-r6-village-availability-') as tmp:
        root = Path(tmp)
        for rel, cls in ((FAST_REL, 'NeverOverworldVanillaFastLocate'), (POLICY_REL, 'NeverOverworldVanillaStructurePolicy')):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture(cls, 48), encoding='utf-8')
        apply(root)
        for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
            text = (root / rel).read_text(encoding='utf-8')
            validate(text, label)
            if tune(text, label) != text:
                fail(f'SELF-TEST {label}: idempotent reapply changed output')
    print('[NeverFolia][TEST1 R6 village availability] SELF-TEST OK')


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
