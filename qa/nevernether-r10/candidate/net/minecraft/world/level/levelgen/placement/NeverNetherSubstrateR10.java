package net.minecraft.world.level.levelgen.placement;

import java.util.BitSet;
import java.util.HashMap;
import java.util.Map;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;
import net.minecraft.world.level.chunk.LevelChunkSection;
import net.minecraft.world.level.chunk.PalettedContainer;
import net.minecraft.world.level.levelgen.feature.configurations.OreConfiguration;
import net.minecraft.world.level.levelgen.structure.templatesystem.BlockMatchTest;
import net.minecraft.world.level.levelgen.structure.templatesystem.TagMatchTest;

/** R10 opt-in prototype: immutable CARVERS substrate and explicit decoration provenance.
 * Section-owned state isolates worlds and survives normal ProtoChunk conversion.
 * Snapshots are NOT persisted. A resume needing a missing snapshot fails closed;
 * this experimental implementation is not an existing-world migration.
 */
public final class NeverNetherSubstrateR10 {
    private NeverNetherSubstrateR10() { }
    private static final ThreadLocal<Write> OWN_WRITE = new ThreadLocal<>();
    private record Write(LevelChunkSection section, int index) { }
    public static final class SectionData {
        final PalettedContainer<BlockState> original;
        final BitSet external = new BitSet(4096);
        final Map<Integer, BlockState> proposals = new HashMap<>();
        private SectionData(LevelChunkSection source) { original = source.getStates().copy(); }
    }
    public static boolean scope(ServerLevel level) {
        return level != null && level.dimension().equals(Level.NETHER) && level.getMinY() == -128 && level.getHeight() == 1024;
    }
    public static void capture(ServerLevel level, ChunkAccess chunk) {
        if (!scope(level)) return;
        // This method is called before publishing the CARVERS barrier; neighbor
        // FEATURES tasks cannot yet write this chunk. Validate before publishing.
        if (chunk.getPersistedStatus().isOrAfter(net.minecraft.world.level.chunk.status.ChunkStatus.FEATURES))
            throw new IllegalStateException("R10 cannot capture an already decorated chunk");
        LevelChunkSection[] sections = chunk.getSections();
        SectionData[] staged = new SectionData[sections.length];
        for (int i = 0; i < sections.length; i++) {
            if (sections[i].neverNetherR10Data != null) throw new IllegalStateException("R10 substrate captured twice");
            staged[i] = new SectionData(sections[i]);
        }
        for (int i = 0; i < sections.length; i++) sections[i].neverNetherR10Data = staged[i];
    }
    private static SectionData data(LevelChunkSection section) {
        SectionData result = section.neverNetherR10Data;
        if (result == null) throw new IllegalStateException("NN-R10 missing immutable CARVERS substrate; saved/reloaded intermediate chunks are not supported by this experiment");
        return result;
    }
    private static int index(BlockPos p) { return ((p.getY() & 15) << 8) | ((p.getZ() & 15) << 4) | (p.getX() & 15); }
    private static LevelChunkSection section(WorldGenLevel level, BlockPos p) {
        // WorldGenRegion/delegates enforce their existing cached dependency bounds.
        // No ServerLevel fallback or synchronous request for a new neighbor.
        ChunkAccess chunk = level.getChunk(p.getX() >> 4, p.getZ() >> 4, net.minecraft.world.level.chunk.status.ChunkStatus.CARVERS, false);
        if (chunk == null) throw new IllegalStateException("R10 substrate outside cached generation dependencies");
        return chunk.getSection(chunk.getSectionIndex(p.getY()));
    }
    public static BlockState original(LevelChunkSection section, BlockPos p) {
        return data(section).original.get(p.getX() & 15, p.getY() & 15, p.getZ() & 15);
    }
    public static BlockState original(WorldGenLevel level, BlockPos p) {
        if (p.getY() < -128 || p.getY() > 895) return Blocks.AIR.defaultBlockState();
        return original(section(level,p),p);
    }
    public static int floor(PlacementContext context, int x, int z, int ordinal) {
        if (ordinal < 0) throw new IllegalArgumentException("Negative floor ordinal");
        ChunkAccess chunk = context.getLevel().getChunk(x >> 4, z >> 4, net.minecraft.world.level.chunk.status.ChunkStatus.CARVERS, false);
        if (chunk == null) throw new IllegalStateException("R10 floor outside cached generation dependencies");
        SectionData[] slices = new SectionData[64];
        for (int i = 0; i < slices.length; i++) slices[i] = data(chunk.getSection(i));
        // Copy stable snapshot references once. No reflective world/chunk lookup
        // inside the vertical loop, and no reads of mutable decorated columns.
        BlockState upper = slices[63].original.get(x & 15,15,z & 15);
        int found = 0;
        // Scan the actual frozen substrate, not a material whitelist. Original
        // natural glowstone, if any, remains; only later features cannot add floors.
        for (int y = 894; y >= -128; y--) {
            BlockState below = slices[(y + 128) >> 4].original.get(x & 15, y & 15, z & 15);
            if (!empty(below) && empty(upper) && !below.is(Blocks.BEDROCK)) {
                if (found++ == ordinal) return y + 1;
            }
            upper = below;
        }
        return Integer.MAX_VALUE;
    }
    private static boolean empty(BlockState state) { return state.isAir() || state.is(Blocks.WATER) || state.is(Blocks.LAVA); }
    public static boolean oreScope(WorldGenLevel level, OreConfiguration config) {
        if (!NeverNetherDecorationR8.inWorld(level) || config.discardChanceOnAirExposure != 0.0f || config.targetStates.isEmpty()) return false;
        for (var target : config.targetStates) {
            if (priority(target.state) == 0 || !(target.target instanceof BlockMatchTest || target.target instanceof TagMatchTest)) return false;
        }
        return true;
    }
    public static boolean blobScope(WorldGenLevel level, BlockState target, BlockState result) {
        return NeverNetherDecorationR8.inWorld(level) && target.is(Blocks.NETHERRACK)
            && (result.is(Blocks.BASALT) || result.is(Blocks.BLACKSTONE));
    }
    /** Explicit output-priority policy: resources over inclusions; not vanilla order parity. */
    public static int priority(BlockState state) {
        if (state.is(Blocks.NETHER_GOLD_ORE)) return 5;
        if (state.is(Blocks.NETHER_QUARTZ_ORE)) return 4;
        if (state.is(Blocks.MAGMA_BLOCK)) return 3;
        if (state.is(Blocks.BLACKSTONE)) return 2;
        if (state.is(Blocks.BASALT)) return 1;
        return 0;
    }
    public static BlockState winner(BlockState a, BlockState b) {
        if (priority(a) == 0 || priority(b) == 0) throw new IllegalArgumentException("Non-proposal conflict");
        int pa = priority(a), pb = priority(b);
        return pa > pb || pa == pb && net.minecraft.world.level.block.Block.getId(a) >= net.minecraft.world.level.block.Block.getId(b) ? a : b;
    }
    /** A non-proposal worldgen write protects the cell even if the new material
     * equals an earlier ore output. Never infer provenance from block type alone. */
    public static void externalWrite(LevelChunkSection section, int x, int y, int z) {
        SectionData d = section.neverNetherR10Data;
        if (d == null) return; // this section has no captured experimental substrate
        Write own = OWN_WRITE.get(); int i = ((y & 15) << 8) | ((z & 15) << 4) | (x & 15);
        if (own != null && own.section() == section && own.index() == i) return;
        synchronized (d) { d.external.set(i); d.proposals.remove(i); }
    }
    public static boolean proposeSection(LevelChunkSection section, BlockPos p, BlockState proposed) {
        return propose(null, section, p, proposed);
    }
    public static boolean proposeBlock(WorldGenLevel level, BlockPos p, BlockState proposed) {
        if (!level.ensureCanWrite(p)) return false;
        return propose(level, section(level,p), p, proposed);
    }
    private static boolean propose(WorldGenLevel level, LevelChunkSection section, BlockPos p, BlockState proposed) {
        if (priority(proposed) == 0 || proposed.hasBlockEntity()) throw new IllegalArgumentException("Unknown R10 proposal material");
        SectionData d = data(section); int i = index(p);
        synchronized (d) {
            if (d.external.get(i)) return false;
            BlockState current = section.getBlockState(p.getX() & 15,p.getY() & 15,p.getZ() & 15);
            BlockState winner = d.proposals.get(i);
            BlockState expected = winner == null ? original(section,p) : winner;
            if (current != expected || current.hasBlockEntity()) {
                d.external.set(i); d.proposals.remove(i); return false;
            }
            if (winner != null && winner(winner,proposed) == winner) return true;
            Write previous = OWN_WRITE.get(); OWN_WRITE.set(new Write(section,i));
            try {
                if (level == null) section.setBlockState(p.getX() & 15,p.getY() & 15,p.getZ() & 15,proposed,false);
                else if (!level.setBlock(p,proposed,2)) return false;
            } finally { if (previous == null) OWN_WRITE.remove(); else OWN_WRITE.set(previous); }
            d.proposals.put(i,proposed); return true;
        }
    }
    public static WorldGenLevel originalView(WorldGenLevel level) {
        var view = new org.bukkit.craftbukkit.util.DelegatedLevelAccessor() {
            @Override public BlockState getBlockState(BlockPos p) { return original(level,p); }
            @Override public boolean isEmptyBlock(BlockPos p) { return getBlockState(p).isAir(); }
            @Override public boolean isStateAtPosition(BlockPos p, java.util.function.Predicate<BlockState> test) { return test.test(getBlockState(p)); }
            @Override public net.minecraft.world.level.material.FluidState getFluidState(BlockPos p) { return getBlockState(p).getFluidState(); }
        };
        view.setDelegate(level); return view;
    }
}
