package net.minecraft.world.level.chunk;

import java.lang.reflect.Method;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.tags.BlockTags;
import net.minecraft.tags.TagKey;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.lighting.LevelLightEngine;

/** Real ProtoChunk regressions for the installed production flood methods.
 * Registry tags below are bound only in this standalone test JVM, not in-game.
 */
public final class TreePreservationSmoke {
    private static int checks;
    private static final int WATER_Y = 128;
    private static BlockState WATER; // Initialized only after Minecraft bootstrap.

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
        ++checks;
    }

    private static void tag(Block block, TagKey<Block> key) throws Exception {
        var holder = block.builtInRegistryHolder();
        Method bind = java.util.Arrays.stream(holder.getClass().getDeclaredMethods())
            .filter(m -> m.getName().equals("bindTags") && m.getParameterCount() == 1
                && m.getParameterTypes()[0].isInstance(Set.of(key)))
            .findFirst().orElseThrow(() -> new IllegalStateException("holder tag binding method missing"));
        bind.setAccessible(true);
        bind.invoke(holder, Set.of(key));
        check(block.defaultBlockState().is(key), "test tag binding: " + block);
    }

    private static ProtoChunk fixture(ChunkPos position, int groundY) {
        var biome = new Biome.BiomeBuilder().hasPrecipitation(true).temperature(0.7f).downfall(0.5f)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder = Holder.direct(biome);
        var ids = new IdMapper<Holder<Biome>>(); ids.add(holder);
        var factory = new PalettedContainerFactory(
            Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY), Blocks.AIR.defaultBlockState(), null,
            Strategy.createForBiomes(ids), holder, null, null);
        var chunk = new ProtoChunk(position, UpgradeData.EMPTY, LevelHeightAccessor.create(-512, 1024), factory, null);
        chunk.setLightEngine(LevelLightEngine.EMPTY);
        for (int z = 0; z < 16; z++) for (int x = 0; x < 16; x++) {
            put(chunk, x, groundY, z, Blocks.DIRT.defaultBlockState());
        }
        return chunk;
    }

    private static BlockPos world(ProtoChunk chunk, int x, int y, int z) {
        return new BlockPos(chunk.getPos().getMinBlockX() + x, y, chunk.getPos().getMinBlockZ() + z);
    }

    private static void put(ProtoChunk chunk, int x, int y, int z, BlockState state) {
        // Fixture population is independent of runtime write guards/heightmaps.
        var section = chunk.getSection(chunk.getSectionIndex(y));
        section.getStates().set(x & 15, y & 15, z & 15, state);
        section.recalcBlockCounts();
    }

    private static void tree(ProtoChunk chunk, Map<BlockPos, BlockState> expected,
                             int x, int y, int z, BlockState state) {
        put(chunk, x, y, z, state);
        expected.put(world(chunk, x, y, z), state);
    }

    private static void prime(ProtoChunk chunk) {
        Heightmap.primeHeightmaps(chunk, EnumSet.of(Heightmap.Types.OCEAN_FLOOR_WG, Heightmap.Types.WORLD_SURFACE_WG));
    }

    private static void mainFlood(ProtoChunk chunk, String methodName) throws Exception {
        Method method = NeverOverworldFlood.class.getDeclaredMethod(
            methodName, ChunkAccess.class, int.class, int.class, BlockState.class);
        method.setAccessible(true);
        method.invoke(null, chunk, chunk.getMinY() + 1, WATER_Y, WATER);
    }

    private static void intact(ProtoChunk chunk, Map<BlockPos, BlockState> expected, String phase) {
        for (var entry : expected.entrySet()) {
            check(chunk.getBlockState(entry.getKey()).equals(entry.getValue()),
                phase + " changed tree at " + entry.getKey() + ": " + chunk.getBlockState(entry.getKey()));
        }
    }

    private static void allFloods(ProtoChunk chunk, Map<BlockPos, BlockState> expected, String label) throws Exception {
        prime(chunk);
        mainFlood(chunk, "floodSurfaceConnectedVolume");
        intact(chunk, expected, label + " surface");
        mainFlood(chunk, "floodLargeBoundaryConnectedCaverns");
        intact(chunk, expected, label + " R8");
        NeverOverworldFloodBoundaryR11.floodBoundaryComponents(chunk);
        intact(chunk, expected, label + " R11");
        NeverOverworldSubmergedRemnants.clean(chunk);
        intact(chunk, expected, label + " remnants");
    }

    private static void fullySubmerged() throws Exception {
        var chunk = fixture(new ChunkPos(0, 0), 99);
        var expected = new LinkedHashMap<BlockPos, BlockState>();
        for (int y = 100; y <= 105; y++) tree(chunk, expected, 8, y, 8, Blocks.OAK_LOG.defaultBlockState());
        for (int x = 6; x <= 10; x++) for (int z = 6; z <= 10; z++) {
            if (x == 8 && z == 8) continue;
            tree(chunk, expected, x, 105, z, Blocks.OAK_LEAVES.defaultBlockState());
        }
        tree(chunk, expected, 8, 106, 8, Blocks.OAK_LEAVES.defaultBlockState());
        allFloods(chunk, expected, "fully submerged standing tree");
        check(chunk.getBlockState(world(chunk, 5, 104, 8)).is(Blocks.WATER), "water must surround submerged tree");
        check(chunk.getBlockState(world(chunk, 7, 104, 8)).is(Blocks.WATER), "water must reach below canopy");
    }

    private static void fallen() throws Exception {
        var chunk = fixture(new ChunkPos(-3, 2), 90);
        var expected = new LinkedHashMap<BlockPos, BlockState>();
        var horizontal = Blocks.BIRCH_LOG.defaultBlockState().setValue(BlockStateProperties.AXIS, Direction.Axis.X);
        for (int x = 3; x <= 11; x++) tree(chunk, expected, x, 91, 8, horizontal);
        tree(chunk, expected, 12, 91, 8, Blocks.BIRCH_LEAVES.defaultBlockState());
        tree(chunk, expected, 11, 92, 8, Blocks.BIRCH_LEAVES.defaultBlockState()
            .setValue(BlockStateProperties.WATERLOGGED, true));
        allFloods(chunk, expected, "underwater fallen tree");
        check(chunk.getBlockState(world(chunk, 7, 91, 7)).is(Blocks.WATER), "fallen trunk must not suppress nearby water");
    }

    private static void partial(int submergedBlocks) throws Exception {
        var chunk = fixture(new ChunkPos(2, -4), 126);
        var expected = new LinkedHashMap<BlockPos, BlockState>();
        int firstLogY = submergedBlocks == 3 ? 127 : 128;
        for (int y = firstLogY; y <= 134; y++) tree(chunk, expected, 8, y, 8, Blocks.OAK_LOG.defaultBlockState());
        tree(chunk, expected, 9, 128, 8, Blocks.OAK_LEAVES.defaultBlockState());
        tree(chunk, expected, 9, 134, 8, Blocks.OAK_LEAVES.defaultBlockState());
        tree(chunk, expected, 8, 135, 8, Blocks.OAK_LEAVES.defaultBlockState());
        check(expected.keySet().stream().filter(p -> p.getY() <= WATER_Y).count() == submergedBlocks,
            "partial fixture exact submerged count");
        allFloods(chunk, expected, "only " + submergedBlocks + " wood/leaf blocks submerged");
        check(chunk.getBlockState(world(chunk, 7, 128, 8)).is(Blocks.WATER), "partial tree waterline");
        check(chunk.getBlockState(world(chunk, 7, 129, 8)).isAir(), "do not raise ocean above Y128");
    }

    private static ProtoChunk edgeHalf(ChunkPos position, boolean left, Map<BlockPos, BlockState> expected) {
        var chunk = fixture(position, 99);
        var horizontal = Blocks.STRIPPED_OAK_LOG.defaultBlockState().setValue(BlockStateProperties.AXIS, Direction.Axis.X);
        for (int x = left ? 14 : 0; x <= (left ? 15 : 1); x++) tree(chunk, expected, x, 100, 8, horizontal);
        tree(chunk, expected, left ? 15 : 0, 101, 8, Blocks.OAK_LEAVES.defaultBlockState());
        return chunk;
    }

    private static void borderOrder() throws Exception {
        var a = new LinkedHashMap<BlockPos, BlockState>();
        var b = new LinkedHashMap<BlockPos, BlockState>();
        var left = edgeHalf(new ChunkPos(-1, 0), true, a);
        var right = edgeHalf(new ChunkPos(0, 0), false, b);
        allFloods(left, a, "border left first");
        intact(right, b, "neighbour unchanged before its own flood");
        allFloods(right, b, "border right second");
        var ar = new LinkedHashMap<BlockPos, BlockState>();
        var br = new LinkedHashMap<BlockPos, BlockState>();
        var leftReverse = edgeHalf(new ChunkPos(-1, 0), true, ar);
        var rightReverse = edgeHalf(new ChunkPos(0, 0), false, br);
        allFloods(rightReverse, br, "border right first");
        allFloods(leftReverse, ar, "border left second");
        for (int y = 90; y <= 130; y++) for (int z = 0; z < 16; z++) for (int x = 0; x < 16; x++) {
            check(left.getBlockState(world(left, x, y, z)).equals(leftReverse.getBlockState(world(leftReverse, x, y, z))),
                "left flood order");
            check(right.getBlockState(world(right, x, y, z)).equals(rightReverse.getBlockState(world(rightReverse, x, y, z))),
                "right flood order");
        }
    }

    private static void independentBoundary() throws Exception {
        var chunk = fixture(new ChunkPos(0, 0), 99);
        var expected = new LinkedHashMap<BlockPos, BlockState>();
        tree(chunk, expected, 0, 100, 7, Blocks.OAK_LOG.defaultBlockState());
        tree(chunk, expected, 0, 101, 7, Blocks.OAK_LEAVES.defaultBlockState());
        NeverOverworldFloodBoundaryR11.floodBoundaryComponents(chunk);
        intact(chunk, expected, "R11 independently");
        check(chunk.getBlockState(world(chunk, 0, 100, 8)).is(Blocks.WATER), "R11 still fills air");
    }

    private static void ordinaryFloraStillCleaned() throws Exception {
        var chunk = fixture(new ChunkPos(0, 0), 99);
        put(chunk, 3, 100, 3, Blocks.POPPY.defaultBlockState());
        put(chunk, 4, 100, 3, Blocks.SHORT_GRASS.defaultBlockState());
        put(chunk, 5, 100, 3, Blocks.SNOW.defaultBlockState());
        allFloods(chunk, Map.of(), "non-tree regressions");
        for (int x = 3; x <= 5; x++) check(chunk.getBlockState(world(chunk, x, 100, 3)).is(Blocks.WATER),
            "submerged flower/grass/snow cleanup must remain enabled");
    }

    public static void main(String[] args) throws Exception {
        var out = System.out;
        SharedConstants.tryDetectVersion(); Bootstrap.bootStrap();
        WATER = Blocks.WATER.defaultBlockState();
        for (Block block : new Block[]{Blocks.OAK_LOG, Blocks.BIRCH_LOG, Blocks.STRIPPED_OAK_LOG}) tag(block, BlockTags.LOGS);
        for (Block block : new Block[]{Blocks.OAK_LEAVES, Blocks.BIRCH_LEAVES}) tag(block, BlockTags.LEAVES);
        Method predicate = NeverOverworldFlood.class.getDeclaredMethod("isFloodable", BlockState.class);
        predicate.setAccessible(true);
        for (Block block : new Block[]{Blocks.OAK_LOG, Blocks.BIRCH_LOG, Blocks.STRIPPED_OAK_LOG, Blocks.OAK_LEAVES, Blocks.BIRCH_LEAVES}) {
            check(!(Boolean)predicate.invoke(null, block.defaultBlockState()), "main tree predicate: " + block);
            check(!NeverOverworldFloodBoundaryR11.isFloodable(block.defaultBlockState()), "R11 tree predicate: " + block);
        }
        fullySubmerged(); fallen(); partial(2); partial(3); borderOrder(); independentBoundary(); ordinaryFloraStillCleaned();
        out.println("PASS TreePreservationSmoke checks=" + checks + " fully-submerged/fallen/2-block/3-block/border/flora");
    }
}
