#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

R7_RADIUS = '''        if (id.startsWith("minecraft:village_")) {
            return 48;
        }
'''
RADIUS32 = '''        if (id.startsWith("minecraft:village_")) {
            return 32;
        }
'''
RADIUS16 = '''        if (id.startsWith("minecraft:village_")) {
            return 16;
        }
'''
RADIUS8 = '''        if (id.startsWith("minecraft:village_")) {
            return 8;
        }
'''

# R7 radius48 restores the earlier strict representative footprint now that
# village variants no longer compete in one weighted structure set. Keep the
# strict 9/9 dry gate and require persisted bbox zero-water QA as final authority.
VILLAGE_DRY_9 = re.compile(
    r'if\s*\(id\.startsWith\("minecraft:village_"\)\)\s*\{[\s\S]{0,900}?return\s+9;\s*\}'
)


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][TEST1 R7 radius48 village safety] {message}')


def validate(text: str, label: str) -> None:
    if text.count(R7_RADIUS) != 1:
        fail(f'{label}: expected exactly one village radius=48 block, got {text.count(R7_RADIUS)}')
    for obsolete_name, obsolete in (('32', RADIUS32), ('16', RADIUS16), ('8', RADIUS8)):
        if obsolete in text:
            fail(f'{label}: obsolete village radius={obsolete_name} block survived radius48 tuning')
    if VILLAGE_DRY_9.search(text) is None:
        fail(f'{label}: village dry gate is not strict 9/9')
    required = (
        'if ("minecraft:pillager_outpost".equals(id))',
        'return 7;',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'{label}: missing settlement safety markers: {missing}')


def tune(text: str, label: str) -> str:
    if text.count(R7_RADIUS) == 1 and all(source not in text for source in (RADIUS32, RADIUS16, RADIUS8)):
        validate(text, label)
        return text

    sources = [source for source in (RADIUS32, RADIUS16, RADIUS8) if text.count(source) == 1]
    if len(sources) != 1 or text.count(R7_RADIUS) != 0:
        fail(
            f'{label}: expected one radius=32/16/8 source or one already tuned radius=48 block; '
            f'r48={text.count(R7_RADIUS)} r32={text.count(RADIUS32)} '
            f'r16={text.count(RADIUS16)} r8={text.count(RADIUS8)}'
        )
    if VILLAGE_DRY_9.search(text) is None:
        fail(f'{label}: refusing radius48 tuning unless the strict 9/9 dry gate is present')
    text = text.replace(sources[0], R7_RADIUS, 1)
    validate(text, label)
    return text


def apply(root: Path) -> None:
    for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
        path = root / rel
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        path.write_text(tune(path.read_text(encoding='utf-8'), label), encoding='utf-8')
    print('[NeverFolia][TEST1 R7 radius48 village safety] strict radius48 dry village contract applied/verified')
    print('  village representative radius: 48 blocks')
    print('  village dry gate: dry centre + 9/9 dry samples')
    print('  independent village structure sets remove weighted-slot starvation')
    print('  actual persisted bbox must still pass zero-water QA at Y=128')


def fixture(class_name: str, radius: int) -> str:
    return f'''final class {class_name} {{
    private static int sampleRadius(final String id) {{
        if ("minecraft:mansion".equals(id)) {{
            return 40;
        }}
        if (id.startsWith("minecraft:village_")) {{
            return {radius};
        }}
        if ("minecraft:pillager_outpost".equals(id)) {{
            return 24;
        }}
        if ("minecraft:desert_pyramid".equals(id) || "minecraft:jungle_pyramid".equals(id)) {{
            return 16;
        }}
        return 16;
    }}

    private static int minDrySamples(final String id) {{
        if (id.startsWith("minecraft:village_")) {{
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
    with tempfile.TemporaryDirectory(prefix='nr-r7-radius48-village-safety-') as tmp:
        root = Path(tmp)
        pairs = ((FAST_REL, 'NeverOverworldVanillaFastLocate'), (POLICY_REL, 'NeverOverworldVanillaStructurePolicy'))
        for rel, cls in pairs:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture(cls, 48), encoding='utf-8')
        apply(root)
        for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
            text = (root / rel).read_text(encoding='utf-8')
            validate(text, label)
            if tune(text, label) != text:
                fail(f'SELF-TEST {label}: idempotent reapply changed output')

        for source_radius in (32, 16, 8):
            for rel, cls in pairs:
                path = root / rel
                path.write_text(fixture(cls, source_radius), encoding='utf-8')
                tuned = tune(path.read_text(encoding='utf-8'), rel.name)
                validate(tuned, rel.name)
    print('[NeverFolia][TEST1 R7 radius48 village safety] SELF-TEST OK')


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
