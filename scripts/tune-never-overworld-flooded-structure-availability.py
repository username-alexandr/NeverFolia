#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

FAST_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java')
POLICY_REL = Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java')

OLD_ID = 'minecraft:woodland_mansion'
NEW_ID = 'minecraft:mansion'

FAST_FOOTPRINT = '''        final int radius = sampleRadius(id);
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

POLICY_FOOTPRINT = '''        final int radius = sampleRadius(id);
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

NEW_RADIUS_METHOD = '''    private static int sampleRadius(final String id) {
        if ("minecraft:mansion".equals(id)) {
            return 40;
        }
        if (id.startsWith("minecraft:village_")) {
            return 48;
        }
        if ("minecraft:pillager_outpost".equals(id)) {
            return 24;
        }
        if ("minecraft:desert_pyramid".equals(id) || "minecraft:jungle_pyramid".equals(id)) {
            return 16;
        }
        if ("minecraft:igloo".equals(id)) {
            return 10;
        }
        return 16;
    }

    private static int minDrySamples(final String id) {
        if (id.startsWith("minecraft:village_") || "minecraft:pillager_outpost".equals(id)) {
            // Flooded-world settlements may touch the shoreline, but their core
            // and a strong majority of the sampled footprint must remain dry.
            return 7;
        }
        // Compact monuments and mansions stay fully above the Y=128 flood plane.
        return 9;
    }
'''

SAMPLE_RADIUS_SIGNATURE = '    private static int sampleRadius(final String id) {'


def fail(message: str) -> None:
    raise SystemExit(f'[NeverFolia][flooded structure availability] {message}')


def replace_footprint(text: str, replacement: str) -> str:
    # This block has a stable terminal return before the enclosing method closes.
    pattern = re.compile(
        r'        final int radius = sampleRadius\(id\);\n'
        r'.*?'
        r'        return true;\n',
        re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        fail(f'expected exactly one dry-footprint block, got {len(matches)}')
    return pattern.sub(replacement, text, count=1)


def replace_java_method(text: str, signature: str, replacement: str) -> str:
    """Replace one Java method by matching braces, not by regex.

    The previous transformer used a non-greedy regex ending at the first line
    containing four-space + '}'. sampleRadius contains nested if blocks, so that
    regex stopped at the first nested closing brace and left the rest of the old
    method in the source, producing an uncompilable helper. Brace matching makes
    the transformer insensitive to nested blocks.
    """
    if text.count(signature) != 1:
        fail(f'expected exactly one Java method signature {signature!r}, got {text.count(signature)}')

    start = text.find(signature)
    opening = text.find('{', start + len(signature) - 1)
    if opening < 0:
        fail(f'opening brace not found for Java method {signature!r}')

    depth = 0
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escaped = False
    i = opening
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ''

        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == '*' and nxt == '/':
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == "'":
                in_char = False
            i += 1
            continue

        if ch == '/' and nxt == '/':
            in_line_comment = True
            i += 2
            continue
        if ch == '/' and nxt == '*':
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            in_char = True
            i += 1
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == '\n':
                    end += 1
                return text[:start] + replacement + text[end:]
        i += 1

    fail(f'unterminated Java method {signature!r}')


def java_braces_balanced(text: str) -> bool:
    """Cheap structural guard that ignores Java comments and quoted literals."""
    depth = 0
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ''
        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == '*' and nxt == '/':
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == "'":
                in_char = False
            i += 1
            continue
        if ch == '/' and nxt == '/':
            in_line_comment = True
            i += 2
            continue
        if ch == '/' and nxt == '*':
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
        elif ch == "'":
            in_char = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0 and not in_string and not in_char and not in_block_comment


def replace_radius_method(text: str) -> str:
    return replace_java_method(text, SAMPLE_RADIUS_SIGNATURE, NEW_RADIUS_METHOD)


def tune(text: str, *, fast: bool) -> str:
    text = text.replace(OLD_ID, NEW_ID)
    if OLD_ID in text:
        fail('obsolete woodland_mansion id survived replacement')
    text = replace_footprint(text, FAST_FOOTPRINT if fast else POLICY_FOOTPRINT)
    text = replace_radius_method(text)

    required = (
        '"minecraft:mansion"',
        'return 48;',
        'return 40;',
        'return 24;',
        'return drySamples >= minDrySamples(id);',
        'return 7;',
        'return 9;',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        fail(f'missing tuned markers: {missing}')
    if fast and 'preliminarySurfaceY(state, centerX + dx, centerZ + dz)' not in text:
        fail('fast helper lost preliminary-surface footprint sampling')
    if not fast and 'Heightmap.Types.WORLD_SURFACE_WG' not in text:
        fail('generation policy lost WORLD_SURFACE_WG footprint sampling')

    if text.count(SAMPLE_RADIUS_SIGNATURE) != 1:
        fail('sampleRadius definition count is not exactly one after tuning')
    if text.count('    private static int minDrySamples(final String id) {') != 1:
        fail('minDrySamples definition count is not exactly one after tuning')
    if 'return 80;' in text or 'return 96;' in text or 'halfRadius' in text:
        fail('old 5x5 footprint/radius code survived tuning')
    if not java_braces_balanced(text):
        fail('tuned Java source has unbalanced structural braces')
    return text


def apply(root: Path) -> None:
    fast = root / FAST_REL
    policy = root / POLICY_REL
    for path in (fast, policy):
        if not path.is_file():
            fail(f'helper not found: {path}')
    fast.write_text(tune(fast.read_text(encoding='utf-8'), fast=True), encoding='utf-8')
    policy.write_text(tune(policy.read_text(encoding='utf-8'), fast=False), encoding='utf-8')
    print('[NeverFolia][flooded structure availability] shoreline-tolerant dry policy applied')
    print('  canonical mansion id: minecraft:mansion')
    print('  villages: radius=48, >=7/9 dry samples with dry center')
    print('  mansion: radius=40, 9/9 dry samples')
    print('  outpost: radius=24, >=7/9 dry samples with dry center')
    print('  pyramids: radius=16, 9/9 dry samples; igloo: radius=10, 9/9')


def self_test() -> None:
    fast_fixture = '''final class NeverOverworldVanillaFastLocate {
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    private static final Set<String> DRY_LAND_ONLY = Set.of("minecraft:woodland_mansion", "minecraft:village_plains");
    boolean test(Object state, Object chunkPos, String id) {
        final int radius = sampleRadius(id);
        final int halfRadius = Math.max(1, radius / 2);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int[] offsets = {-radius, -halfRadius, 0, halfRadius, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                final int base = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                if (base < MIN_DRY_BASE_HEIGHT) return false;
            }
        }
        return true;
    }
    private static int sampleRadius(final String id) {
        if ("minecraft:woodland_mansion".equals(id)) {
            return 80;
        }
        if (id.startsWith("minecraft:village_")) {
            return 96;
        }
        return 32;
    }
}
'''
    policy_fixture = '''final class NeverOverworldVanillaStructurePolicy {
    private static final int MIN_DRY_BASE_HEIGHT = 129;
    boolean test(Object generator, Object randomState, Object heightAccessor, Object chunkPos, String id) {
        final int radius = sampleRadius(id);
        final int halfRadius = Math.max(1, radius / 2);
        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int[] offsets = {-radius, -halfRadius, 0, halfRadius, radius};
        for (final int dx : offsets) {
            for (final int dz : offsets) {
                final int base = generator.getBaseHeight(centerX + dx, centerZ + dz, Heightmap.Types.WORLD_SURFACE_WG, heightAccessor, randomState);
                if (base < MIN_DRY_BASE_HEIGHT) return false;
            }
        }
        return true;
    }
    private static int sampleRadius(final String id) {
        if ("minecraft:woodland_mansion".equals(id)) {
            return 80;
        }
        if (id.startsWith("minecraft:village_")) {
            return 96;
        }
        return 32;
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='nr-flooded-structure-availability-') as tmp:
        root = Path(tmp)
        fp = root / FAST_REL
        pp = root / POLICY_REL
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(fast_fixture, encoding='utf-8')
        pp.write_text(policy_fixture, encoding='utf-8')
        apply(root)
        out_fast = fp.read_text(encoding='utf-8')
        out_policy = pp.read_text(encoding='utf-8')
        for label, output in (('fast', out_fast), ('policy', out_policy)):
            if OLD_ID in output:
                fail(f'SELF-TEST {label}: obsolete mansion id survived')
            if output.count(SAMPLE_RADIUS_SIGNATURE) != 1:
                fail(f'SELF-TEST {label}: sampleRadius definition count mismatch')
            if output.count('    private static int minDrySamples(final String id) {') != 1:
                fail(f'SELF-TEST {label}: minDrySamples definition count mismatch')
            if 'return 80;' in output or 'return 96;' in output or 'halfRadius' in output:
                fail(f'SELF-TEST {label}: old nested method tail survived')
            if not java_braces_balanced(output):
                fail(f'SELF-TEST {label}: Java braces are unbalanced')
        if 'preliminarySurfaceY(state, centerX, centerZ)' not in out_fast:
            fail('SELF-TEST: fast dry-center probe missing')
        if 'drySamples >= minDrySamples(id)' not in out_policy:
            fail('SELF-TEST: generation dry-sample gate missing')
    print('[NeverFolia][flooded structure availability] SELF-TEST OK')


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
