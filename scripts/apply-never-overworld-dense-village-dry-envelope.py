#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

FAST_OPT_3X3 = '''        final int radius = sampleRadius(id);
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

FAST_OPT_DENSE = '''        final int radius = sampleRadius(id);
        if (id.startsWith("minecraft:village_")) {
            // The center was already proven dry above and reused for the biome
            // check. Probe the remaining 24 points in a 5x5 envelope so fast
            // locate and real generation reject the same shoreline gaps.
            final int halfRadius = Math.max(1, radius / 2);
            final int[] villageOffsets = {-radius, -halfRadius, 0, halfRadius, radius};
            for (final int dx : villageOffsets) {
                for (final int dz : villageOffsets) {
                    if (dx == 0 && dz == 0) {
                        continue;
                    }
                    if (preliminarySurfaceY(state, centerX + dx, centerZ + dz) < MIN_DRY_BASE_HEIGHT) {
                        return false;
                    }
                }
            }
            return true;
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
            // Dense generation-side contract: all 25 points across the village
            // representative footprint must remain above the Y=128 flood plane.
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


def tune_fast(text: str) -> str:
    if text.count(FAST_OPT_DENSE) == 1 and text.count(FAST_OPT_3X3) == 0:
        validate_fast(text)
        return text
    if text.count(FAST_OPT_3X3) != 1 or text.count(FAST_OPT_DENSE) != 0:
        fail(
            'fast-locate: expected the post-optimization sparse 3x3 footprint exactly once; '
            f'sparse={text.count(FAST_OPT_3X3)} dense={text.count(FAST_OPT_DENSE)}'
        )
    text = text.replace(FAST_OPT_3X3, FAST_OPT_DENSE, 1)
    validate_fast(text)
    return text


def tune_policy(text: str) -> str:
    if text.count(POLICY_DENSE) == 1 and text.count(POLICY_3X3) == 0:
        validate_policy(text)
        return text
    if text.count(POLICY_3X3) != 1 or text.count(POLICY_DENSE) != 0:
        fail(
            'generation-policy: expected sparse 3x3 footprint exactly once; '
            f'sparse={text.count(POLICY_3X3)} dense={text.count(POLICY_DENSE)}'
        )
    text = text.replace(POLICY_3X3, POLICY_DENSE, 1)
    validate_policy(text)
    return text


def validate_fast(text: str) -> None:
    required = (
        'final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);',
        'if (id.startsWith("minecraft:village_"))',
        'final int halfRadius = Math.max(1, radius / 2);',
        'final int[] villageOffsets = {-radius, -halfRadius, 0, halfRadius, radius};',
        'preliminarySurfaceY(state, centerX + dx, centerZ + dz) < MIN_DRY_BASE_HEIGHT',
        'return drySamples >= minDrySamples(id);',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'fast-locate: dense markers missing: {missing}')
    if text.count(FAST_OPT_DENSE) != 1:
        fail('fast-locate: dense footprint block count mismatch')


def validate_policy(text: str) -> None:
    required = (
        'if (id.startsWith("minecraft:village_"))',
        'final int halfRadius = Math.max(1, radius / 2);',
        'final int[] villageOffsets = {-radius, -halfRadius, 0, halfRadius, radius};',
        'Heightmap.Types.WORLD_SURFACE_WG',
        'if (base < MIN_DRY_BASE_HEIGHT)',
        'return drySamples >= minDrySamples(id);',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'generation-policy: dense markers missing: {missing}')
    if text.count(POLICY_DENSE) != 1:
        fail('generation-policy: dense footprint block count mismatch')


def apply(root: Path) -> None:
    fast = root / FAST_REL
    policy = root / POLICY_REL
    if not fast.is_file():
        fail(f'fast-locate helper not found: {fast}')
    if not policy.is_file():
        fail(f'generation-policy helper not found: {policy}')
    fast.write_text(tune_fast(fast.read_text(encoding='utf-8')), encoding='utf-8')
    policy.write_text(tune_policy(policy.read_text(encoding='utf-8')), encoding='utf-8')
    print('[NeverFolia][R7 dense village envelope] DENSE 5x5 DRY VILLAGE PREFILTER APPLIED')
    print('  fast locate: dry center reused + 24 additional probes')
    print('  generation policy: 25/25 probes dry')
    print('  representative radius: inherited from sampleRadius (R7: 48)')
    print('  non-village structures retain existing 3x3 policy')
    print('  persisted Jigsaw bbox zero-water audit remains final authority')


def fast_fixture() -> str:
    return f'''final class NeverOverworldVanillaFastLocate {{
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    boolean test(Object state, Object chunkPos, String id) {{
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int centerSurfaceY = preliminarySurfaceY(state, centerX, centerZ);
        if (centerSurfaceY < MIN_DRY_BASE_HEIGHT) return false;
{FAST_OPT_3X3.rstrip()}
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
        fast = root / FAST_REL
        policy = root / POLICY_REL
        fast.parent.mkdir(parents=True, exist_ok=True)
        policy.parent.mkdir(parents=True, exist_ok=True)
        fast.write_text(fast_fixture(), encoding='utf-8')
        policy.write_text(policy_fixture(), encoding='utf-8')
        fast_out = tune_fast(fast.read_text(encoding='utf-8'))
        policy_out = tune_policy(policy.read_text(encoding='utf-8'))
        validate_fast(fast_out)
        validate_policy(policy_out)
        if tune_fast(fast_out) != fast_out:
            fail('SELF-TEST fast-locate: idempotent reapply changed output')
        if tune_policy(policy_out) != policy_out:
            fail('SELF-TEST generation-policy: idempotent reapply changed output')
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
