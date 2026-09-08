#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

OLD_RADIUS = '''        if (id.startsWith("minecraft:village_")) {
            return 32;
        }
'''
NEW_RADIUS = '''        if (id.startsWith("minecraft:village_")) {
            return 48;
        }
'''

OLD_DRY = '''        if (id.startsWith("minecraft:village_")) {
            // Villages are common gameplay anchors. Keep the centre dry, but a
            // simple majority of the 3x3 footprint is enough for broad shores and
            // practical islands in the flooded world.
            return 5;
        }
'''
NEW_DRY = '''        if (id.startsWith("minecraft:village_")) {
            // R4 field QA proved that the 5/9 gate can still accept materially
            // flooded village envelopes. R5 requires all representative samples
            // to be above the Y=128 flood plane; candidate density is solved by
            // placement policy instead of weakening terrain safety.
            return 9;
        }
'''

# The historical tune-never-overworld-village-availability-r3.py was promoted in
# place to the R5 strict 9/9 policy. Its comments differ from NEW_DRY even though
# the generated Java contract is identical. Match the contract semantically so
# this hardening pass can safely re-validate either representation.
VILLAGE_DRY_9 = re.compile(
    r'if\s*\(id\.startsWith\("minecraft:village_"\)\)\s*\{[\s\S]{0,900}?return\s+9;\s*\}'
)


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][TEST1 R5 village safety] {message}')


def has_strict_village_contract(text: str) -> bool:
    return text.count(NEW_RADIUS) == 1 and VILLAGE_DRY_9.search(text) is not None


def tune(text: str, label: str) -> str:
    if has_strict_village_contract(text) and OLD_RADIUS not in text and OLD_DRY not in text:
        validate(text, label)
        return text
    if text.count(OLD_RADIUS) != 1:
        fail(f'{label}: expected one R3 village radius block or an existing strict radius=48 block; old={text.count(OLD_RADIUS)} new={text.count(NEW_RADIUS)}')
    if text.count(OLD_DRY) != 1:
        fail(f'{label}: expected one R3 village dry gate or an existing strict 9/9 gate; old={text.count(OLD_DRY)} strict={int(VILLAGE_DRY_9.search(text) is not None)}')
    text = text.replace(OLD_RADIUS, NEW_RADIUS, 1)
    text = text.replace(OLD_DRY, NEW_DRY, 1)
    validate(text, label)
    return text


def validate(text: str, label: str) -> None:
    if text.count(NEW_RADIUS) != 1:
        fail(f'{label}: expected exactly one strict village radius=48 block, got {text.count(NEW_RADIUS)}')
    if VILLAGE_DRY_9.search(text) is None:
        fail(f'{label}: village dry gate is not strict 9/9')
    required = (
        'if ("minecraft:pillager_outpost".equals(id))',
        'return 7;',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'{label}: missing R5 markers: {missing}')
    if OLD_RADIUS in text or OLD_DRY in text:
        fail(f'{label}: R3 village availability markers survived R5 hardening')


def apply(root: Path) -> None:
    for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
        path = root / rel
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        path.write_text(tune(path.read_text(encoding='utf-8'), label), encoding='utf-8')
    print('[NeverFolia][TEST1 R5 village safety] dry village contract applied/verified')
    print('  village sample radius: 48 blocks')
    print('  village dry gate: dry centre + 9/9 dry samples')
    print('  availability restored by highland biome placement, not wet starts')


def fixture(class_name: str) -> str:
    return f'''final class {class_name} {{
    private static int sampleRadius(final String id) {{
        if ("minecraft:mansion".equals(id)) {{
            return 40;
        }}
        if (id.startsWith("minecraft:village_")) {{
            return 32;
        }}
        if ("minecraft:pillager_outpost".equals(id)) {{
            return 24;
        }}
        return 16;
    }}

    private static int minDrySamples(final String id) {{
        if (id.startsWith("minecraft:village_")) {{
            // Villages are common gameplay anchors. Keep the centre dry, but a
            // simple majority of the 3x3 footprint is enough for broad shores and
            // practical islands in the flooded world.
            return 5;
        }}
        if ("minecraft:pillager_outpost".equals(id)) {{
            return 7;
        }}
        return 9;
    }}
}}
'''


def already_strict_fixture(class_name: str) -> str:
    return f'''final class {class_name} {{
    private static int sampleRadius(final String id) {{
        if (id.startsWith("minecraft:village_")) {{
            return 48;
        }}
        if ("minecraft:pillager_outpost".equals(id)) {{
            return 24;
        }}
        return 16;
    }}

    private static int minDrySamples(final String id) {{
        if (id.startsWith("minecraft:village_")) {{
            // Alternate strict-policy wording from the promoted legacy tuner.
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
    with tempfile.TemporaryDirectory(prefix='nr-r5-village-safety-') as tmp:
        root = Path(tmp)
        for rel, cls in ((FAST_REL, 'NeverOverworldVanillaFastLocate'), (POLICY_REL, 'NeverOverworldVanillaStructurePolicy')):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture(cls), encoding='utf-8')
        apply(root)
        for label, rel in (('fast-locate', FAST_REL), ('generation-policy', POLICY_REL)):
            text = (root / rel).read_text(encoding='utf-8')
            validate(text, label)
            if tune(text, label) != text:
                fail(f'SELF-TEST {label}: idempotent reapply changed output')

        # Regression: the promoted legacy tuner already emits radius=48 + 9/9,
        # but with different comments. Re-applying the dedicated safety pass must
        # validate and no-op instead of rejecting that equivalent source text.
        for rel, cls in ((FAST_REL, 'NeverOverworldVanillaFastLocate'), (POLICY_REL, 'NeverOverworldVanillaStructurePolicy')):
            path = root / rel
            strict = already_strict_fixture(cls)
            path.write_text(strict, encoding='utf-8')
            if tune(strict, rel.name) != strict:
                fail(f'SELF-TEST {rel.name}: semantic strict reapply changed output')
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
