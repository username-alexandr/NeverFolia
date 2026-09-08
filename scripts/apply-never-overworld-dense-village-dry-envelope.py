#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

FAST_3X3 = '''        final int radius = sampleRadius(id);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        if (preliminarySurfaceY(state, centerX, centerZ) < MIN_DRY_BASE_HEIGHT) {
            return false;
        }

        int drySamples = 1;
        final int[] offsets = {-radius, 0, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                if (dx == 0 && dz == 0) {
                    continue;
                }
                if (preliminarySurfaceY(state, centerX + dx, centerZ + dz) >= MIN_DRY_BASE_HEIGHT) {
                    ++drySamples;
                }
            }
        }
        return drySamples >= minDrySamples(id);
'''

FAST_DENSE = '''        final int radius = sampleRadius(id);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();

        if (id.startsWith("minecraft:village_")) {
            // R7 flooded villages use a dense 5x5 predictive envelope instead
            // of the old sparse 3x3 corners/centre check. The 25 probes span
            // the full representative radius and reject narrow shore channels
            // that can pass between sparse samples.
            final int halfRadius = Math.max(1, radius / 2);
            final int[] villageOffsets = {-radius, -halfRadius, 0, halfRadius, radius};
            for (final int dx : villageOffsets) {
                for (final int dz : villageOffsets) {
                    if (preliminarySurfaceY(state, centerX + dx, centerZ + dz) < MIN_DRY_BASE_HEIGHT) {
                        return false;
                    }
                }
            }
            return true;
        }

        if (preliminarySurfaceY(state, centerX, centerZ) < MIN_DRY_BASE_HEIGHT) {
            return false;
        }
        int drySamples = 1;
        final int[] offsets = {-radius, 0, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                if (dx == 0 && dz == 0) {
                    continue;
                }
                if (preliminarySurfaceY(state, centerX + dx, centerZ + dz) >= MIN_DRY_BASE_HEIGHT) {
                    ++drySamples;
                }
            }
        }
        return drySamples >= minDrySamples(id);
'''

POLICY_3X3 = '''        final int radius = sampleRadius(id);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        if (generator.getBaseHeight(
            centerX,
            centerZ,
            Heightmap.Types.WORLD_SURFACE_WG,
            heightAccessor,
            randomState
        ) < MIN_DRY_BASE_HEIGHT) {
            return false;
        }

        int drySamples = 1;
        final int[] offsets = {-radius, 0, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                if (dx == 0 && dz == 0) {
                    continue;
                }
                final int base = generator.getBaseHeight(
                    centerX + dx,
                    centerZ + dz,
                    Heightmap.Types.WORLD_SURFACE_WG,
                    heightAccessor,
                    randomState
                );
                if (base >= MIN_DRY_BASE_HEIGHT) {
                    ++drySamples;
                }
            }
        }
        return drySamples >= minDrySamples(id);
'''

POLICY_DENSE = '''        final int radius = sampleRadius(id);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();

        if (id.startsWith("minecraft:village_")) {
            // Keep generation policy byte-for-byte equivalent in semantics to
            // predictive fast locate: every point in a 5x5 envelope must be
            // above the Y=128 flood plane before a village start is accepted.
            final int halfRadius = Math.max(1, radius / 2);
            final int[] villageOffsets = {-radius, -halfRadius, 0, halfRadius, radius};
            for (final int dx : villageOffsets) {
                for (final int dz : villageOffsets) {
                    final int base = generator.getBaseHeight(
                        centerX + dx,
                        centerZ + dz,
                        Heightmap.Types.WORLD_SURFACE_WG,
                        heightAccessor,
                        randomState
                    );
                    if (base < MIN_DRY_BASE_HEIGHT) {
                        return false;
                    }
                }
            }
            return true;
        }

        if (generator.getBaseHeight(
            centerX,
            centerZ,
            Heightmap.Types.WORLD_SURFACE_WG,
            heightAccessor,
            randomState
        ) < MIN_DRY_BASE_HEIGHT) {
            return false;
        }
        int drySamples = 1;
        final int[] offsets = {-radius, 0, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                if (dx == 0 && dz == 0) {
                    continue;
                }
                final int base = generator.getBaseHeight(
                    centerX + dx,
                    centerZ + dz,
                    Heightmap.Types.WORLD_SURFACE_WG,
                    heightAccessor,
                    randomState
                );
                if (base >= MIN_DRY_BASE_HEIGHT) {
                    ++drySamples;
                }
            }
        }
        return drySamples >= minDrySamples(id);
'''


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][R7 dense village envelope] {message}')


def tune(text: str, *, fast: bool, label: str) -> str:
    old = FAST_3X3 if fast else POLICY_3X3
    new = FAST_DENSE if fast else POLICY_DENSE
    if text.count(new) == 1 and text.count(old) == 0:
        validate(text, fast=fast, label=label)
        return text
    if text.count(old) != 1 or text.count(new) != 0:
        fail(f'{label}: expected one sparse 3x3 footprint; old={text.count(old)} new={text.count(new)}')
    text = text.replace(old, new, 1)
    validate(text, fast=fast, label=label)
    return text


def validate(text: str, *, fast: bool, label: str) -> None:
    required = (
        'if (id.startsWith("minecraft:village_"))',
        'final int halfRadius = Math.max(1, radius / 2);',
        'final int[] villageOffsets = {-radius, -halfRadius, 0, halfRadius, radius};',
        'for (final int dx : villageOffsets)',
        'for (final int dz : villageOffsets)',
        'return drySamples >= minDrySamples(id);',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'{label}: dense village markers missing: {missing}')
    if fast:
        if 'preliminarySurfaceY(state, centerX + dx, centerZ + dz) < MIN_DRY_BASE_HEIGHT' not in text:
            fail(f'{label}: predictive 5x5 surface probe missing')
    else:
        if 'Heightmap.Types.WORLD_SURFACE_WG' not in text:
            fail(f'{label}: generation 5x5 WORLD_SURFACE_WG probe missing')
        if 'if (base < MIN_DRY_BASE_HEIGHT)' not in text:
            fail(f'{label}: generation 5x5 rejection branch missing')


def apply(root: Path) -> None:
    for label, rel, fast in (
        ('fast-locate', FAST_REL, True),
        ('generation-policy', POLICY_REL, False),
    ):
        path = root / rel
        if not path.is_file():
            fail(f'{label}: helper not found: {path}')
        text = path.read_text(encoding='utf-8')
        path.write_text(tune(text, fast=fast, label=label), encoding='utf-8')
    print('[NeverFolia][R7 dense village envelope] DENSE 5x5 DRY VILLAGE PREFILTER APPLIED')
    print('  village samples: 25/25 dry')
    print('  village radius: inherited from sampleRadius (R7 candidate: 48)')
    print('  non-village dry-land structures keep their existing 3x3 policy')
    print('  persisted Jigsaw bbox zero-water audit remains final authority')


def fast_fixture() -> str:
    return f'''final class NeverOverworldVanillaFastLocate {{
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    boolean test(Object state, Object chunkPos, String id) {{
{FAST_3X3.rstrip()}
    }}
    private static int sampleRadius(String id) {{ return 48; }}
    private static int minDrySamples(String id) {{ return 9; }}
    private static int preliminarySurfaceY(Object state, int x, int z) {{ return 140; }}
}}
'''


def policy_fixture() -> str:
    return f'''final class NeverOverworldVanillaStructurePolicy {{
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    boolean test(Object generator, Object randomState, Object heightAccessor, Object chunkPos, String id) {{
{POLICY_3X3.rstrip()}
    }}
    private static int sampleRadius(String id) {{ return 48; }}
    private static int minDrySamples(String id) {{ return 9; }}
}}
'''


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='nr-r7-dense-village-') as tmp:
        root = Path(tmp)
        pairs = (
            (FAST_REL, fast_fixture(), True, 'fast-locate'),
            (POLICY_REL, policy_fixture(), False, 'generation-policy'),
        )
        for rel, fixture, _, _ in pairs:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fixture, encoding='utf-8')
        for rel, _, fast, label in pairs:
            path = root / rel
            tuned = tune(path.read_text(encoding='utf-8'), fast=fast, label=label)
            validate(tuned, fast=fast, label=label)
            if tune(tuned, fast=fast, label=label) != tuned:
                fail(f'SELF-TEST {label}: reapply changed output')
    print('[NeverFolia][R7 dense village envelope] SELF-TEST OK')


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
