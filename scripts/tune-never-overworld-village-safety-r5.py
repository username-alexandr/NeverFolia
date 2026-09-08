#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

R5_RADIUS = '''        if (id.startsWith("minecraft:village_")) {
            return 48;
        }
'''
R6_RADIUS = '''        if (id.startsWith("minecraft:village_")) {
            return 8;
        }
'''

# Keep the strict 9/9 dry contract. Runtime QA showed radius=32 was
# pathologically sparse and radius=16 recovered desert/savanna/snowy villages,
# but plains and taiga still had no candidate in the bounded predictive scan.
# R6 radius8 therefore narrows only the cheap representative prefilter footprint
# to +/-8 blocks. This is NOT the final flood-safety decision: persisted-
# structure QA remains authoritative and rejects any generated village whose
# real bbox contains water at Y=128.
VILLAGE_DRY_9 = re.compile(
    r'if\s*\(id\.startsWith\("minecraft:village_"\)\)\s*\{[\s\S]{0,900}?return\s+9;\s*\}'
)


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][TEST1 R6 village safety] {message}')


def validate(text: str, label: str) -> None:
    if text.count(R6_RADIUS) != 1:
        fail(f'{label}: expected exactly one village radius=8 block, got {text.count(R6_RADIUS)}')
    if R5_RADIUS in text:
        fail(f'{label}: obsolete R5 village radius=48 survived R6 tuning')
    for obsolete in ('return 32;', 'return 16;'):
        if obsolete in text:
            fail(f'{label}: obsolete village scarcity profile survived radius8 tuning: {obsolete}')
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
    radius32 = '''        if (id.startsWith("minecraft:village_")) {
            return 32;
        }
'''
    radius16 = '''        if (id.startsWith("minecraft:village_")) {
            return 16;
        }
'''
    if text.count(R6_RADIUS) == 1 and all(source not in text for source in (R5_RADIUS, radius32, radius16)):
        validate(text, label)
        return text

    sources = [source for source in (R5_RADIUS, radius32, radius16) if text.count(source) == 1]
    if len(sources) != 1 or text.count(R6_RADIUS) != 0:
        fail(
            f'{label}: expected one radius=48/32/16 source or one already tuned radius=8 block; '
            f'r48={text.count(R5_RADIUS)} r32={text.count(radius32)} '
            f'r16={text.count(radius16)} r8={text.count(R6_RADIUS)}'
        )
    if VILLAGE_DRY_9.search(text) is None:
        fail(f'{label}: refusing to narrow the footprint unless the strict 9/9 dry gate is present')
    text = text.replace(sources[0], R6_RADIUS, 1)
    validate(text, label)
    return text


def apply(root: Path) -> None:
    for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
        path = root / rel
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        path.write_text(tune(path.read_text(encoding='utf-8'), label), encoding='utf-8')
    print('[NeverFolia][TEST1 R6 village safety] compact radius8 dry village contract applied/verified')
    print('  village representative radius: 8 blocks')
    print('  village dry gate: dry centre + 9/9 dry samples')
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
        return 12;
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
    with tempfile.TemporaryDirectory(prefix='nr-r6-village-safety-') as tmp:
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

        # Regression coverage for rejected intermediate scarcity profiles.
        for source_radius in (32, 16):
            for rel, cls in pairs:
                path = root / rel
                path.write_text(fixture(cls, source_radius), encoding='utf-8')
                compacted = tune(path.read_text(encoding='utf-8'), rel.name)
                validate(compacted, rel.name)
    print('[NeverFolia][TEST1 R6 village safety] SELF-TEST OK')


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
