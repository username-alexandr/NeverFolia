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
            return 16;
        }
'''

# Keep R5's strict 9/9 dry contract. Runtime QA on radius=32 proved that the
# candidate acceptance rate was still pathological: four village variants were
# absent inside the bounded locate scan and the only variant found was ~32 km
# away. R6 therefore narrows only the representative prefilter footprint to
# +/-16 blocks. This is NOT the final flood-safety decision: persisted-structure
# QA remains authoritative and rejects any generated village whose real bbox
# contains water at Y=128.
VILLAGE_DRY_9 = re.compile(
    r'if\s*\(id\.startsWith\("minecraft:village_"\)\)\s*\{[\s\S]{0,900}?return\s+9;\s*\}'
)


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][TEST1 R6 village safety] {message}')


def validate(text: str, label: str) -> None:
    if text.count(R6_RADIUS) != 1:
        fail(f'{label}: expected exactly one village radius=16 block, got {text.count(R6_RADIUS)}')
    if R5_RADIUS in text:
        fail(f'{label}: obsolete R5 village radius=48 survived R6 tuning')
    if 'return 32;' in text:
        fail(f'{label}: obsolete radius=32 scarcity profile survived compact R6 tuning')
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
    # The immediately preceding legacy R3 transformer emits radius=48 + 9/9 in
    # the current pipeline. Accept radius=32 too so the transformer is safe to
    # reapply to a partially transformed developer worktree.
    radius32 = '''        if (id.startsWith("minecraft:village_")) {
            return 32;
        }
'''
    if text.count(R6_RADIUS) == 1 and R5_RADIUS not in text and radius32 not in text:
        validate(text, label)
        return text
    source = None
    if text.count(R5_RADIUS) == 1 and radius32 not in text:
        source = R5_RADIUS
    elif text.count(radius32) == 1 and R5_RADIUS not in text:
        source = radius32
    else:
        fail(
            f'{label}: expected one radius=48/32 source or one already tuned radius=16 block; '
            f'r48={text.count(R5_RADIUS)} r32={text.count(radius32)} r16={text.count(R6_RADIUS)}'
        )
    if VILLAGE_DRY_9.search(text) is None:
        fail(f'{label}: refusing to narrow the footprint unless the strict 9/9 dry gate is present')
    text = text.replace(source, R6_RADIUS, 1)
    validate(text, label)
    return text


def apply(root: Path) -> None:
    for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
        path = root / rel
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        path.write_text(tune(path.read_text(encoding='utf-8'), label), encoding='utf-8')
    print('[NeverFolia][TEST1 R6 village safety] compact dry village contract applied/verified')
    print('  village representative radius: 16 blocks')
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

        # Regression: a developer worktree may already contain the rejected
        # radius=32 experiment. Compacting it to radius=16 must be deterministic.
        for rel, cls in ((FAST_REL, 'NeverOverworldVanillaFastLocate'), (POLICY_REL, 'NeverOverworldVanillaStructurePolicy')):
            path = root / rel
            path.write_text(fixture(cls, 32), encoding='utf-8')
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
