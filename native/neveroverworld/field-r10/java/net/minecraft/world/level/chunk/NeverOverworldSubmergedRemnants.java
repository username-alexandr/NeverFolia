package net.minecraft.world.level.chunk;

import java.util.ArrayList;
import java.util.List;
import net.minecraft.core.BlockPos;
import net.minecraft.core.SectionPos;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.StructureStart;

/**
 * Field cleanup for snow buried by post-flood sediment and terrestrial flora
 * that survives inside actual water. No neighbouring chunk is read or written.
 */
public final class NeverOverworldSubmergedRemnants {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int FLOOD_LEVEL = 128;
    private static final int[][] HORIZONTAL = {{-1,0},{1,0},{0,-1},{0,1}};

    private NeverOverworldSubmergedRemnants() {}

    public static int apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) return 0;
        return clean(chunk);
    }

    static int clean(final ChunkAccess chunk) {
        if (chunk.getMinY() != EXPECTED_MIN_Y || chunk.getHeight() != EXPECTED_HEIGHT) {
            throw new IllegalStateException("NeverOverworld submerged cleanup requires -512..511 chunk envelope");
        }
        final List<BoundingBox> protectedBoxes = protectionBoxes(chunk);
        final LevelChunkSection[] sections = chunk.getSections();
        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int minZ = chunkPos.getMinBlockZ();
        final int minSectionY = SectionPos.blockToSectionCoord(chunk.getMinY() + 1);
        final int maxSectionY = SectionPos.blockToSectionCoord(FLOOD_LEVEL - 1);
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;

        for (int sectionY = minSectionY; sectionY <= maxSectionY; ++sectionY) {
            final int sectionIndex = chunk.getSectionIndexFromSectionY(sectionY);
            if (sectionIndex < 0 || sectionIndex >= sections.length) continue;
            final LevelChunkSection section = sections[sectionIndex];
            if (!section.maybeHas(NeverOverworldSubmergedRemnants::isCandidate)) continue;
            final int sectionMinY = SectionPos.sectionToBlockCoord(sectionY);
            final int scanMinY = Math.max(chunk.getMinY() + 1, sectionMinY);
            final int scanMaxY = Math.min(FLOOD_LEVEL - 1, sectionMinY + 15);
            for (int y = scanMinY; y <= scanMaxY; ++y) {
                final int localY = SectionPos.sectionRelative(y);
                for (int localZ = 0; localZ < 16; ++localZ) {
                    for (int localX = 0; localX < 16; ++localX) {
                        final BlockState state = section.getBlockState(localX, localY, localZ);
                        if (!isCandidate(state)) continue;
                        final int x = minX + localX;
                        final int z = minZ + localZ;
                        if (isProtected(protectedBoxes, x, y, z)) continue;
                        pos.set(x, y, z);
                        if (isFrozenRemnant(state)) {
                            chunk.setBlockState(pos, frozenReplacement(chunk, pos), 0);
                            ++changed;
                        } else if (isTerrestrialFlora(state) && touchesWater(chunk, pos, minX, minZ)) {
                            chunk.setBlockState(pos, Blocks.WATER.defaultBlockState(), 0);
                            ++changed;
                        }
                    }
                }
            }
        }
        return changed;
    }

    static boolean isFrozenRemnant(final BlockState state) {
        return state.is(Blocks.SNOW)
            || state.is(Blocks.SNOW_BLOCK)
            || state.is(Blocks.POWDER_SNOW);
    }

    static boolean isTerrestrialFlora(final BlockState state) {
        return state.is(BlockTags.FLOWERS)
            || state.is(Blocks.DANDELION)
            || state.is(Blocks.GOLDEN_DANDELION)
            || state.is(Blocks.TORCHFLOWER)
            || state.is(Blocks.POPPY)
            || state.is(Blocks.BLUE_ORCHID)
            || state.is(Blocks.ALLIUM)
            || state.is(Blocks.AZURE_BLUET)
            || state.is(Blocks.RED_TULIP)
            || state.is(Blocks.ORANGE_TULIP)
            || state.is(Blocks.WHITE_TULIP)
            || state.is(Blocks.PINK_TULIP)
            || state.is(Blocks.OXEYE_DAISY)
            || state.is(Blocks.CORNFLOWER)
            || state.is(Blocks.LILY_OF_THE_VALLEY)
            || state.is(Blocks.WITHER_ROSE)
            || state.is(Blocks.CACTUS_FLOWER)
            || state.is(Blocks.SUNFLOWER)
            || state.is(Blocks.LILAC)
            || state.is(Blocks.ROSE_BUSH)
            || state.is(Blocks.PEONY)
            || state.is(Blocks.SHORT_GRASS)
            || state.is(Blocks.TALL_GRASS)
            || state.is(Blocks.FERN)
            || state.is(Blocks.LARGE_FERN)
            || state.is(Blocks.DEAD_BUSH)
            || state.is(Blocks.BUSH)
            || state.is(Blocks.PINK_PETALS)
            || state.is(Blocks.WILDFLOWERS)
            || state.is(Blocks.LEAF_LITTER)
            || state.is(Blocks.FIREFLY_BUSH);
    }

    private static boolean isCandidate(final BlockState state) {
        return isFrozenRemnant(state) || isTerrestrialFlora(state);
    }

    static BlockState frozenReplacement(final ChunkAccess chunk, final BlockPos pos) {
        final int minX = chunk.getPos().getMinBlockX();
        final int minZ = chunk.getPos().getMinBlockZ();
        if (touchesWater(chunk, pos, minX, minZ)) return Blocks.WATER.defaultBlockState();
        if (touchesAir(chunk, pos, minX, minZ)) return Blocks.AIR.defaultBlockState();
        final BlockState above = stateAtOwned(chunk, pos.getX(), pos.getY() + 1, pos.getZ(), minX, minZ);
        if (isNaturalHost(above)) return above;
        final BlockState below = stateAtOwned(chunk, pos.getX(), pos.getY() - 1, pos.getZ(), minX, minZ);
        if (isNaturalHost(below)) return below;
        for (int[] d : HORIZONTAL) {
            final BlockState side = stateAtOwned(chunk, pos.getX() + d[0], pos.getY(), pos.getZ() + d[1], minX, minZ);
            if (isNaturalHost(side)) return side;
        }
        return pos.getY() < 0 ? Blocks.DEEPSLATE.defaultBlockState() : Blocks.STONE.defaultBlockState();
    }

    private static boolean touchesWater(final ChunkAccess chunk, final BlockPos pos, final int minX, final int minZ) {
        if (stateAtOwned(chunk, pos.getX(), pos.getY() - 1, pos.getZ(), minX, minZ).is(Blocks.WATER)
            || stateAtOwned(chunk, pos.getX(), pos.getY() + 1, pos.getZ(), minX, minZ).is(Blocks.WATER)) return true;
        for (int[] d : HORIZONTAL) {
            if (stateAtOwned(chunk, pos.getX() + d[0], pos.getY(), pos.getZ() + d[1], minX, minZ).is(Blocks.WATER)) return true;
        }
        return false;
    }

    private static boolean touchesAir(final ChunkAccess chunk, final BlockPos pos, final int minX, final int minZ) {
        if (stateAtOwned(chunk, pos.getX(), pos.getY() - 1, pos.getZ(), minX, minZ).isAir()
            || stateAtOwned(chunk, pos.getX(), pos.getY() + 1, pos.getZ(), minX, minZ).isAir()) return true;
        for (int[] d : HORIZONTAL) {
            if (stateAtOwned(chunk, pos.getX() + d[0], pos.getY(), pos.getZ() + d[1], minX, minZ).isAir()) return true;
        }
        return false;
    }

    private static BlockState stateAtOwned(
        final ChunkAccess chunk, final int x, final int y, final int z, final int minX, final int minZ
    ) {
        if (x < minX || x > minX + 15 || z < minZ || z > minZ + 15 || y < chunk.getMinY() || y >= chunk.getMaxY()) {
            return Blocks.BEDROCK.defaultBlockState();
        }
        return chunk.getBlockState(new BlockPos(x, y, z));
    }

    private static boolean isNaturalHost(final BlockState state) {
        return state.is(Blocks.SAND)
            || state.is(Blocks.GRAVEL)
            || state.is(Blocks.CLAY)
            || state.is(Blocks.MUD)
            || state.is(Blocks.DIRT)
            || state.is(Blocks.COARSE_DIRT)
            || state.is(Blocks.ROOTED_DIRT)
            || state.is(Blocks.STONE)
            || state.is(Blocks.ANDESITE)
            || state.is(Blocks.DIORITE)
            || state.is(Blocks.GRANITE)
            || state.is(Blocks.DEEPSLATE)
            || state.is(Blocks.TUFF);
    }

    private static List<BoundingBox> protectionBoxes(final ChunkAccess chunk) {
        final ArrayList<BoundingBox> result = new ArrayList<>();
        for (StructureStart start : chunk.getAllStarts().values()) {
            if (start != null && start.isValid()) result.add(start.getBoundingBox());
        }
        return result;
    }

    private static boolean isProtected(final List<BoundingBox> boxes, final int x, final int y, final int z) {
        for (BoundingBox box : boxes) {
            if (x >= box.minX() - 1 && x <= box.maxX() + 1
                && y >= box.minY() - 1 && y <= box.maxY() + 1
                && z >= box.minZ() - 1 && z <= box.maxZ() + 1) return true;
        }
        return false;
    }
}
