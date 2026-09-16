package net.minecraft.world.level.chunk;

import java.util.ArrayList;
import java.util.List;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.StructureStart;

/**
 * Additional field-requested 50% deterministic thinning over final generated
 * Overworld resource blocks. It runs only at the existing pre-FULL LIGHT barrier.
 */
public final class NeverOverworldOreScarcityFieldR10 {
    public static final int KEEP_PERCENT = 50;
    private static final long SALT = 0x4E524F5245463130L;
    private NeverOverworldOreScarcityFieldR10() {}

    public static int apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024) return 0;
        return thin(level.getSeed(), chunk);
    }

    static int kind(final BlockState state) {
        if (state.is(Blocks.COAL_ORE) || state.is(Blocks.DEEPSLATE_COAL_ORE)) return 1;
        if (state.is(Blocks.IRON_ORE) || state.is(Blocks.DEEPSLATE_IRON_ORE) || state.is(Blocks.RAW_IRON_BLOCK)) return 2;
        if (state.is(Blocks.COPPER_ORE) || state.is(Blocks.DEEPSLATE_COPPER_ORE) || state.is(Blocks.RAW_COPPER_BLOCK)) return 3;
        if (state.is(Blocks.GOLD_ORE) || state.is(Blocks.DEEPSLATE_GOLD_ORE)) return 4;
        if (state.is(Blocks.REDSTONE_ORE) || state.is(Blocks.DEEPSLATE_REDSTONE_ORE)) return 5;
        if (state.is(Blocks.LAPIS_ORE) || state.is(Blocks.DEEPSLATE_LAPIS_ORE)) return 6;
        if (state.is(Blocks.DIAMOND_ORE) || state.is(Blocks.DEEPSLATE_DIAMOND_ORE)) return 7;
        if (state.is(Blocks.EMERALD_ORE) || state.is(Blocks.DEEPSLATE_EMERALD_ORE)) return 8;
        return 0;
    }

    static BlockState host(final BlockState state) {
        if (state.is(Blocks.RAW_IRON_BLOCK)) return Blocks.TUFF.defaultBlockState();
        if (state.is(Blocks.RAW_COPPER_BLOCK)) return Blocks.GRANITE.defaultBlockState();
        if (state.is(Blocks.DEEPSLATE_COAL_ORE) || state.is(Blocks.DEEPSLATE_IRON_ORE)
            || state.is(Blocks.DEEPSLATE_COPPER_ORE) || state.is(Blocks.DEEPSLATE_GOLD_ORE)
            || state.is(Blocks.DEEPSLATE_REDSTONE_ORE) || state.is(Blocks.DEEPSLATE_LAPIS_ORE)
            || state.is(Blocks.DEEPSLATE_DIAMOND_ORE) || state.is(Blocks.DEEPSLATE_EMERALD_ORE)) {
            return Blocks.DEEPSLATE.defaultBlockState();
        }
        if (kind(state) != 0) return Blocks.STONE.defaultBlockState();
        throw new IllegalArgumentException("Not a generated Overworld resource block: " + state);
    }

    static boolean retain(final long seed, final int x, final int y, final int z, final int resource, final int keepPercent) {
        if (resource < 1 || resource > 8 || keepPercent < 0 || keepPercent > 100) {
            throw new IllegalArgumentException("Invalid ore scarcity key/profile");
        }
        if (keepPercent == 0) return false;
        if (keepPercent == 100) return true;
        long h = mix(seed ^ SALT ^ ((long)resource * 0x632BE59BD9B4E019L));
        h = mix(h ^ ((long)x * 0x9E3779B97F4A7C15L));
        h = mix(h ^ ((long)y * 0xC2B2AE3D27D4EB4FL));
        h = mix(h ^ ((long)z * 0x165667B19E3779F9L));
        return Math.floorMod(h, 100L) < keepPercent;
    }

    static int thin(final long seed, final ChunkAccess chunk) {
        final var status = chunk.getPersistedStatus();
        if (status.isBefore(ChunkStatus.INITIALIZE_LIGHT) || status.isOrAfter(ChunkStatus.FULL)) {
            throw new IllegalStateException("Ore scarcity requires pre-FULL LIGHT barrier");
        }
        if (chunk.getMinY() != -512 || chunk.getHeight() != 1024) {
            throw new IllegalStateException("Mismatched NeverOverworld chunk envelope");
        }
        final List<BoundingBox> protectedBoxes = protectionBoxes(chunk);
        final int minX = chunk.getPos().getMinBlockX();
        final int minZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;
        final LevelChunkSection[] sections = chunk.getSections();
        for (int i = 0; i < sections.length; ++i) {
            final LevelChunkSection section = sections[i];
            if (!section.maybeHas(state -> kind(state) != 0)) continue;
            final int baseY = chunk.getMinY() + (i << 4);
            for (int ly = 0; ly < 16; ++ly) for (int lz = 0; lz < 16; ++lz) for (int lx = 0; lx < 16; ++lx) {
                final BlockState state = section.getBlockState(lx, ly, lz);
                final int resource = kind(state);
                if (resource == 0) continue;
                final int x = minX + lx, y = baseY + ly, z = minZ + lz;
                if (isProtected(protectedBoxes, x, y, z) || retain(seed, x, y, z, resource, KEEP_PERCENT)) continue;
                chunk.setBlockState(pos.set(x, y, z), host(state), 0);
                ++changed;
            }
        }
        return changed;
    }

    private static long mix(long n) {
        n = (n ^ (n >>> 30)) * 0xBF58476D1CE4E5B9L;
        n = (n ^ (n >>> 27)) * 0x94D049BB133111EBL;
        return n ^ (n >>> 31);
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
            if (x >= box.minX() && x <= box.maxX()
                && y >= box.minY() && y <= box.maxY()
                && z >= box.minZ() && z <= box.maxZ()) return true;
        }
        return false;
    }
}
