import com.google.gson.*;
import java.nio.file.Files;
import java.util.EnumSet;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.core.BlockPos;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.chunk.ChunkAccess;
import net.minecraft.world.level.chunk.NeverOverworldDryMinesR12;
import net.minecraft.world.level.chunk.NeverOverworldWaterPolicyR38;
import net.minecraft.world.level.levelgen.Heightmap;

/** Synthetic regression ONLY in a fresh CI world. Never installed in a user kit.
 * Calls the actual kernel policy with real blocks, fluids and heightmaps.
 * This is not a natural-world, full cleanup-chain or dry-mine acceptance test.
 */
public final class R396RemovalQa extends JavaPlugin implements Listener {
    private final JsonArray cases = new JsonArray();
    private boolean started, finished;
    private final boolean fixed = Boolean.getBoolean("neverfolia.qaExpectFixedRemoval");
    private static final BlockPos POS = new BlockPos(8, 64, 8);

    @Override public void onEnable() { Bukkit.getPluginManager().registerEvents(this, this); }
    @EventHandler public void loaded(ServerLoadEvent event) {
        if (started) return;
        started = true;
        try {
            World world = Bukkit.getWorlds().stream().filter(w -> w.getEnvironment() == World.Environment.NORMAL).findFirst().orElseThrow();
            require(world.getSeed() == -4651369264513492755L, "unexpected real seed");
            world.getChunkAtAsync(0, 0, true).whenComplete((loaded, error) -> {
                if (error != null) { finish(error); return; }
                Bukkit.getRegionScheduler().execute(this, world, 0, 0, () -> {
                    try {
                        ChunkAccess chunk = ((CraftWorld) world).getHandle().getChunkAt(POS);
                        require(chunk.getMinY() == -512 && chunk.getHeight() == 1024, "wrong world envelope");
                        require(!NeverOverworldDryMinesR12.protectedCell(chunk, POS), "fixture intersects protected dry geometry");
                        test(chunk, "topmost_snow_with_water_contact", Blocks.SNOW_BLOCK.defaultBlockState(), 64, false, true, fixed);
                        test(chunk, "topmost_snow_no_water_contact", Blocks.SNOW_BLOCK.defaultBlockState(), 64, false, false, false);
                        test(chunk, "higher_stone_roof", Blocks.SNOW_BLOCK.defaultBlockState(), 64, true, true, false);
                        test(chunk, "nonsolid_fern_above_floor", Blocks.FERN.defaultBlockState(), 64, false, true, true);
                        test(chunk, "removed_snow_at_sea_bound", Blocks.SNOW_BLOCK.defaultBlockState(), 128, false, true, false);
                        test(chunk, "removed_snow_above_sea_bound", Blocks.SNOW_BLOCK.defaultBlockState(), 129, false, true, false);
                        test(chunk, "native_source_no_contact", Blocks.WATER.defaultBlockState(), 64, true, false, true);
                        test(chunk, "native_flowing_level_5", Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL, 5), 64, true, false, true);
                        test(chunk, "native_falling_level_8", Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL, 8), 64, true, false, true);
                        test(chunk, "waterlogged_slab_under_roof", Blocks.OAK_SLAB.defaultBlockState().setValue(BlockStateProperties.WATERLOGGED, true), 64, true, false, true);
                        require(cases.size() == 10, "incomplete fixture coverage");
                        finish(null);
                    } catch (Throwable failure) { finish(failure); }
                });
            });
        } catch (Throwable failure) { finish(failure); }
    }

    private void test(ChunkAccess chunk, String name, BlockState previous, int y, boolean roof, boolean contact, boolean waterExpected) {
        // All positions are inside the one region-owned chunk. No neighbour writes.
        for (int by = chunk.getMinY() + 1; by < chunk.getMaxY(); by++) {
            chunk.setBlockState(new BlockPos(8, by, 8), Blocks.AIR.defaultBlockState(), 0);
            chunk.setBlockState(new BlockPos(9, by, 8), Blocks.AIR.defaultBlockState(), 0);
        }
        BlockPos pos = new BlockPos(8, y, 8);
        chunk.setBlockState(new BlockPos(8, 60, 8), Blocks.STONE.defaultBlockState(), 0);
        chunk.setBlockState(pos, previous, 0);
        if (roof) chunk.setBlockState(pos.above(), Blocks.STONE.defaultBlockState(), 0);
        if (contact) chunk.setBlockState(pos.east(), Blocks.WATER.defaultBlockState(), 0);
        Heightmap.primeHeightmaps(chunk, EnumSet.of(Heightmap.Types.OCEAN_FLOOR_WG));
        int floor = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, 8, 8);
        boolean actualContact = chunk.getBlockState(pos.east()).getFluidState().is(FluidTags.WATER);
        require(actualContact == contact, "wrong water-contact fixture: " + name);
        require(!NeverOverworldDryMinesR12.protectedCell(chunk, pos), "protected fixture: " + name);
        if (previous.is(Blocks.SNOW_BLOCK) && !roof) require(floor == y, "snow is not the sampled top block: " + floor + "/" + y);
        if (roof) require(floor == y + 1, "roof height not sampled: " + name);
        BlockState expected = previous.getFluidState().is(FluidTags.WATER)
            ? previous.getFluidState().createLegacyBlock()
            : (waterExpected ? Blocks.WATER.defaultBlockState() : Blocks.AIR.defaultBlockState());
        BlockState actual = NeverOverworldWaterPolicyR38.afterPlantRemoval(chunk, pos, previous, actualContact);
        JsonObject row = new JsonObject();
        row.addProperty("name", name); row.addProperty("y", y); row.addProperty("sampled_floor", floor);
        row.addProperty("water_contact", actualContact); row.addProperty("previous", previous.toString());
        row.addProperty("expected", expected.toString()); row.addProperty("actual", actual.toString());
        row.addProperty("pass", actual.equals(expected)); cases.add(row);
        require(actual.equals(expected), "wrong replacement: " + name + " expected " + expected + " got " + actual);
        chunk.setBlockState(pos, actual, 0);
        require(chunk.getBlockState(pos).equals(expected), "replacement not stored: " + name);
    }
    private static void require(boolean ok, String message) { if (!ok) throw new AssertionError(message); }
    private synchronized void finish(Throwable failure) {
        if (finished) return;
        finished = true;
        JsonObject result = new JsonObject();
        result.addProperty("pass", failure == null); result.addProperty("expect_fixed", fixed);
        result.addProperty("scope", "10 synthetic fixtures in a real Folia region-owned chunk; actual policy, heightmap and fluid states; not natural generation or complete cleanup pipeline");
        result.add("cases", cases);
        if (failure != null) { result.addProperty("error", failure.toString()); failure.printStackTrace(); }
        try {
            getDataFolder().mkdirs();
            Files.writeString(getDataFolder().toPath().resolve("result.json"), new GsonBuilder().setPrettyPrinting().create().toJson(result));
        } catch (Exception e) { e.printStackTrace(); failure = e; }
        getLogger().info("R396 REMOVAL QA " + (failure == null ? "PASS" : "FAIL"));
    }
}
