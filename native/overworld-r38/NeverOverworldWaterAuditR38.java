package net.minecraft.world.level.chunk;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.BitSet;
import net.minecraft.core.BlockPos;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.Heightmap;

/** Read-only, opt-in evidence for the complete LIGHT mutation chain. */
public final class NeverOverworldWaterAuditR38 {
    private static final String DIRECTORY = System.getProperty("neverfolia.waterAuditDirectory", "");
    private NeverOverworldWaterAuditR38() {}

    public record Snapshot(int minY, int maxY, BlockState[] before, int[] floors, BitSet mineEnvelope) {}

    public static Snapshot begin(WorldGenLevel world, ChunkAccess chunk) {
        if (DIRECTORY.isEmpty() || !world.getLevel().dimension().equals(Level.OVERWORLD)
            || chunk.getMinY() != -512 || chunk.getHeight() != 1024
            || chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) return null;
        // Bound QA overhead. These rectangles cover the six reported target areas
        // plus their boundary neighbours, not an unbounded production world.
        int cx = chunk.getPos().x(), cz = chunk.getPos().z();
        boolean target = (cx >= -5 && cx <= 4 && cz >= -2 && cz <= 4)
            || (cx >= 11 && cx <= 13 && cz >= 3 && cz <= 5);
        if (!target) return null;
        final int low = chunk.getMinY() + 1, high = 128;
        BlockState[] before = new BlockState[(high - low + 1) * 256];
        int[] floors = new int[256];
        BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
        int bx = chunk.getPos().getMinBlockX(), bz = chunk.getPos().getMinBlockZ();
        for (int z=0; z<16; ++z) for (int x=0; x<16; ++x) {
            floors[(z<<4)|x] = chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG, x, z);
            for (int y=low; y<=high; ++y) {
                p.set(bx+x,y,bz+z);
                before[((y-low)<<8)|(z<<4)|x] = chunk.getBlockState(p);
            }
        }
        BitSet mine = (BitSet)NeverOverworldDryMinesR12.mask(chunk).envelope.clone();
        return new Snapshot(low, high, before, floors, mine);
    }

    public static void end(WorldGenLevel world, ChunkAccess chunk, Snapshot snapshot) {
        if (snapshot == null) return;
        int nativeWater=0, preserved=0, removed=0, changed=0, additions=0, forbiddenAdditions=0, mineChanges=0;
        JsonArray examples = new JsonArray();
        byte[] beforeMask = new byte[snapshot.before.length], afterMask = new byte[snapshot.before.length];
        BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
        int bx=chunk.getPos().getMinBlockX(), bz=chunk.getPos().getMinBlockZ();
        for (int y=snapshot.minY; y<=snapshot.maxY; ++y) for(int z=0;z<16;++z) for(int x=0;x<16;++x) {
            int index=((y-snapshot.minY)<<8)|(z<<4)|x;
            BlockState before=snapshot.before[index];
            p.set(bx+x,y,bz+z);
            BlockState after=chunk.getBlockState(p);
            beforeMask[index]=waterCode(before);afterMask[index]=waterCode(after);
            boolean hadWater=before.getFluidState().is(FluidTags.WATER);
            boolean hasWater=after.getFluidState().is(FluidTags.WATER);
            boolean mine=snapshot.mineEnvelope.get(((y-chunk.getMinY())<<8)|(z<<4)|x);
            String violation=null;
            if(hadWater) {
                ++nativeWater;
                if(before.getFluidState()==after.getFluidState()) ++preserved;
                else if(mine) ++mineChanges;
                else if(!hasWater) {++removed;violation="native_water_removed";}
                else {++changed;violation="native_water_state_changed";}
            } else if(hasWater) {
                ++additions;
                int floor=snapshot.floors[(z<<4)|x];
                if(y<=floor || floor>=128) {++forbiddenAdditions;violation="new_water_below_native_surface";}
            }
            if(violation!=null && examples.size()<32) {
                JsonObject row=new JsonObject();row.addProperty("kind",violation);
                row.addProperty("x",bx+x);row.addProperty("y",y);row.addProperty("z",bz+z);
                row.addProperty("floor",snapshot.floors[(z<<4)|x]);
                int originalFloor=snapshot.floors[(z<<4)|x];
                row.addProperty("final_floor",chunk.getHeight(Heightmap.Types.OCEAN_FLOOR_WG,x,z));
                if(originalFloor>=snapshot.minY && originalFloor<=snapshot.maxY) {
                    row.addProperty("before_floor_block",snapshot.before[((originalFloor-snapshot.minY)<<8)|(z<<4)|x].toString());
                    row.addProperty("after_floor_block",chunk.getBlockState(new BlockPos(bx+x,originalFloor,bz+z)).toString());
                }
                row.addProperty("before",before.toString());row.addProperty("after",after.toString());
                examples.add(row);
            }
        }
        JsonObject report=new JsonObject();
        report.addProperty("schema",1);report.addProperty("scope","PRE_LIGHT to final post-seam cleanup; read-only observer");
        report.addProperty("chunk_x",chunk.getPos().x());report.addProperty("chunk_z",chunk.getPos().z());
        report.addProperty("native_water",nativeWater);report.addProperty("preserved_native_water",preserved);
        report.addProperty("removed_native_water",removed);report.addProperty("changed_native_water_state",changed);
        report.addProperty("explicit_dry_mine_changes",mineChanges);report.addProperty("new_water",additions);
        report.addProperty("below_native_surface_additions",forbiddenAdditions);
        report.addProperty("before_water_sha256", digest(beforeMask));report.addProperty("after_water_sha256", digest(afterMask));
        report.add("violations",examples);report.addProperty("pass",removed==0 && changed==0 && forbiddenAdditions==0);
        try {
            Path dir=Path.of(DIRECTORY);Files.createDirectories(dir);
            Files.writeString(dir.resolve(chunk.getPos().x()+"_"+chunk.getPos().z()+".json"),
                new GsonBuilder().setPrettyPrinting().create().toJson(report));
        } catch(java.io.IOException error) {
            throw new IllegalStateException("Cannot write requested water audit evidence",error);
        }
    }
    private static byte waterCode(BlockState state) {
        if (!state.getFluidState().is(FluidTags.WATER)) return 0;
        return (byte)(1 + state.getFluidState().createLegacyBlock().getValue(net.minecraft.world.level.block.LiquidBlock.LEVEL));
    }
    private static String digest(byte[] value) {
        try { return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(value)); }
        catch (java.security.NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); }
    }

}
