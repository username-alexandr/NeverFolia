#!/usr/bin/env python3
"""R37: floor-bounded ocean columns, cache write barriers and attachment relocation.

Runs after R33/R34/R35. It never edits saved worlds and never loads neighbours.
The primary LIGHT pass fills only the open part of each owning column. Native
cave WATER and flowing states are retained, including below the old Y96 cutoff.
"""
from __future__ import annotations
import argparse
from pathlib import Path

JAVA = Path('folia-server/src/minecraft/java')
OWNER = JAVA/'net/minecraft/world/level/chunk/NeverOverworldFlood.java'
CACHE = JAVA/'net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java'
NOISE = JAVA/'net/minecraft/world/level/levelgen/NoiseBasedChunkGenerator.java'
TEMPLATE = JAVA/'net/minecraft/world/level/levelgen/structure/templatesystem/StructureTemplate.java'

COLUMN_METHOD = '''    private static void floodSurfaceConnectedVolume(
        final ChunkAccess chunk,
        final int minY,
        final int maxY,
        final BlockState water
    ) {
        // R37_COLUMN_OCEAN: the column's solid surface, not an arbitrary Y96
        // plane, is the lower bound. No neighbour reads and no cave BFS.
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        for (int z = 0; z < 16; ++z) {
            for (int x = 0; x < 16; ++x) {
                // ChunkAccess#getHeight returns the highest occupied Y.
                final int floor = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, x, z);
                if (floor >= maxY) continue;
                final int bottom = Math.max(minY, floor + 1);
                for (int y = bottom; y <= maxY; ++y) {
                    pos.set(baseX + x, y, baseZ + z);
                    final BlockState previous = chunk.getBlockState(pos);
                    // Retain source/flow level and waterlogging verbatim.
                    if (!previous.getFluidState().isEmpty()) continue;
                    if (!customOceanColumnOpen(chunk, pos, y)
                        || !isFloodableAt(chunk, pos)
                        || NeverOverworldDryMinesR12.protectedCell(chunk, pos)) continue;
                    chunk.setBlockState(pos, water, 0);
                }
            }
        }
    }'''

TRACE_METHOD = '''    public static void traceNativeWaterR37(final String phase, final ChunkAccess chunk) {
        // Read-only, opt-in regression evidence at the reported coordinates.
        // No random draws, neighbour access, block writes or persistent state.
        if (!Boolean.getBoolean("neverfolia.debugFloodSeams")
            || chunk.getMinY() != EXPECTED_MIN_Y || chunk.getHeight() != EXPECTED_HEIGHT) return;
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final int[][] samples;
        if (baseX == 0 && baseZ == 0) samples = new int[][]{{14,52,11},{8,52,14}};
        else if (baseX == -64 && baseZ == 48) samples = new int[][]{{-53,23,50}};
        else return;
        for (final int[] sample : samples) {
            final BlockPos pos = new BlockPos(sample[0], sample[1], sample[2]);
            final BlockState state = chunk.getBlockState(pos);
            final String name = net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();
            LOGGER.info("[R37-WATER-ORIGIN] phase={} pos={},{},{} state={} floor={}",
                phase, sample[0], sample[1], sample[2], name,
                chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, sample[0] & 15, sample[2] & 15));
        }
    }
'''

ATTACHMENT_FIX = '''                // R37_ATTACHMENT: saved entity block_pos is in the author's
                // world, unlike entityInfo.blockPos, which is template-local.
                // Relocate BEFORE decoding; do not suppress the validation log
                // or delete every frame/painting from the imported datapack.
                final String attachmentId = tag.getString("id").orElse("");
                if (attachmentId.equals("minecraft:item_frame")
                    || attachmentId.equals("minecraft:glow_item_frame")
                    || attachmentId.equals("minecraft:painting")
                    || attachmentId.equals("minecraft:leash_knot")) {
                    tag.putIntArray("block_pos", new int[]{blockPos.getX(), blockPos.getY(), blockPos.getZ()});
                }
'''

CACHE_WRITE_OLD = '''                    if (!state.is(Blocks.WATER)
                        && traversableCache(chunks, localX + CACHE_OWNER_OFFSET, y, localZ + CACHE_OWNER_OFFSET, pos, adjacent)) {'''
CACHE_WRITE_NEW = '''                    if (!state.is(Blocks.WATER)
                        && customOceanColumnOpen(owner, pos, y) // R37_CACHE_WRITE
                        && traversableCache(chunks, localX + CACHE_OWNER_OFFSET, y, localZ + CACHE_OWNER_OFFSET, pos, adjacent)) {'''
CACHE_TRAVERSE_OLD = '        if (!traversable(chunk, pos)) return false;'
CACHE_TRAVERSE_NEW = '''        if (!traversable(chunk, pos)) return false;
        // R37_CACHE_TRAVERSAL: native WATER may be read, but roofed AIR is
        // never a custom-ocean conduit, including in adjacent chunks.
        if (!chunk.getBlockState(pos).is(Blocks.WATER)
            && !customOceanColumnOpen(chunk, pos, y)) return false;'''

def require(ok: bool, message: str) -> None:
    if not ok: raise ValueError('[FIELD-R37] ' + message)

def method_bounds(text: str, signature: str) -> tuple[int, int]:
    require(text.count(signature) == 1, 'missing/ambiguous method: ' + signature)
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    for i in range(opening + 1, len(text)):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0: return start, i + 1
    raise ValueError('Unterminated Java method: ' + signature)

def patch_owner(text: str) -> str:
    a, b = method_bounds(text, '    private static void floodSurfaceConnectedVolume(')
    text = text[:a] + COLUMN_METHOD + text[b:]
    if 'R37_NATIVE_WATER_TRACE' not in text:
        anchors = {
            '        // ORE-LIGHT-R12: prune only the complete neighbour-decorated substrate.':
                '        traceNativeWaterR37("PRE_LIGHT", chunk); // R37_NATIVE_WATER_TRACE\n',
            '        restoreFloodShorelineFlora(level, chunk, shorelineFlora);':
                '        traceNativeWaterR37("POST_OWNER", chunk);\n',
            '        chunk.neverOverworldDryMineMaskR12 = null;':
                '        traceNativeWaterR37("POST_LIGHT", chunk);\n',
        }
        for anchor, before in anchors.items():
            require(text.count(anchor) == 1, 'native trace anchor drift: ' + anchor)
            text = text.replace(anchor, before + anchor, 1)
        text = text.rstrip()[:-1] + '\n' + TRACE_METHOD + '}\n'
    require(TRACE_METHOD in text, 'partial native trace helper')
    return text

def patch_noise(text: str) -> str:
    anchor = '        noiseChunk.stopInterpolation();\n        return centerChunk;'
    replacement = '        noiseChunk.stopInterpolation();\n        net.minecraft.world.level.chunk.NeverOverworldFlood.traceNativeWaterR37("NOISE", centerChunk);\n        return centerChunk;'
    if replacement not in text:
        require(text.count(anchor) == 1, 'noise trace anchor drift')
        text = text.replace(anchor, replacement, 1)
    return text

def patch_cache(text: str) -> str:
    if 'R37_CACHE_WRITE' not in text:
        require(text.count(CACHE_WRITE_OLD) == 1, 'cache final write anchor drift')
        text = text.replace(CACHE_WRITE_OLD, CACHE_WRITE_NEW, 1)
    a, b = method_bounds(text, '    private static boolean traversableCache(')
    method = text[a:b]
    if 'R37_CACHE_TRAVERSAL' not in method:
        require(method.count(CACHE_TRAVERSE_OLD) == 1, 'cache traversal anchor drift')
        method = method.replace(CACHE_TRAVERSE_OLD, CACHE_TRAVERSE_NEW, 1)
        text = text[:a] + method + text[b:]
    return text

def patch_template(text: str) -> str:
    anchor = '                createEntityIgnoreException(problemReporter, level, tag).ifPresent(entity -> {'
    require(text.count(anchor) == 1, 'entity placement anchor drift')
    if ATTACHMENT_FIX not in text:
        require('R37_ATTACHMENT' not in text, 'partial attachment fix')
        text = text.replace(anchor, ATTACHMENT_FIX + anchor, 1)
    return text

def verify(owner: str, cache: str, template: str) -> None:
    a, b = method_bounds(owner, '    private static void floodSurfaceConnectedVolume(')
    require(owner[a:b] == COLUMN_METHOD, 'primary column contract changed')
    require(CACHE_WRITE_NEW in cache and CACHE_TRAVERSE_NEW in cache, 'cache barriers missing')
    require(CACHE_WRITE_OLD not in cache, 'unguarded cache final write survived')
    require(ATTACHMENT_FIX in template, 'attachment relocation missing')
    require(template.index(ATTACHMENT_FIX) < template.index('                createEntityIgnoreException(problemReporter, level, tag)'), 'relocation must precede decoding')
    require('LOGGER.error("Block-attached entity' not in template, 'do not suppress entity validation')

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia', type=Path)
    p.add_argument('--check-only', action='store_true')
    args = p.parse_args()
    paths = [args.folia/OWNER, args.folia/CACHE, args.folia/TEMPLATE, args.folia/NOISE]
    values = [path.read_text(encoding='utf-8') for path in paths]
    if not args.check_only:
        values = [patch_owner(values[0]), patch_cache(values[1]), patch_template(values[2]), patch_noise(values[3])]
    verify(*values[:3])
    require(TRACE_METHOD in values[0] and patch_noise(values[3]) == values[3], "native water provenance hooks missing")
    if not args.check_only:
        for path, value in zip(paths, values): path.write_text(value, encoding='utf-8')
    print('[FIELD-R37] open-column ocean, cache barriers and attachment relocation OK')

if __name__ == '__main__': main()
