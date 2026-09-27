package net.minecraft.world.level.chunk;

import com.google.gson.JsonObject;
import java.io.DataOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.BitSet;
import java.util.concurrent.atomic.AtomicLong;
import java.util.zip.GZIPOutputStream;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/** Explicit opt-in integration on R399. Positive 3x3 ocean witnesses only.
 * Never repairs FULL chunks or loads/writes neighbours. All input reads precede
 * the first write. An unproved cell is NOT asserted to be a correct dry cave.
 * This finite witness does not prove global closure or arbitrary scheduling safety.
 */
public final class NeverOverworldOceanClosureR3910 {
    public static final String REVISION = "R3910-R399-positive-ocean-integration";
    private static final boolean ENABLED = Boolean.getBoolean("neverfolia.r3910OceanClosure");
    private static final String REPORT = System.getProperty("neverfolia.r3910ReportDirectory", "");
    private static final boolean WITNESSES = Boolean.getBoolean("neverfolia.r3910SaveWitnesses");
    private static final AtomicLong IDS = new AtomicLong();
    private static final int LOW=-511, HIGH=128, HEIGHT=640, WIDTH=48, AREA=2304;
    private NeverOverworldOceanClosureR3910() {}

    public static int apply(WorldGenLevel world, StaticCache2D<GenerationChunkHolder> cache, ChunkAccess owner) {
        if (!ENABLED || !world.getLevel().dimension().equals(Level.OVERWORLD)
            || owner.getMinY()!=-512 || owner.getHeight()!=1024
            || owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) return 0;
        ChunkAccess[] chunks=new ChunkAccess[9]; chunks[4]=owner;
        int cx=owner.getPos().x(), cz=owner.getPos().z();
        for (int dz=-1;dz<=1;dz++) for (int dx=-1;dx<=1;dx++) {
            if (dx==0 && dz==0) continue;
            if (cache!=null && cache.contains(cx+dx,cz+dz)) {
                GenerationChunkHolder holder=cache.get(cx+dx,cz+dz);
                if (holder!=null) chunks[(dz+1)*3+dx+1]=holder.getChunkIfPresent(ChunkStatus.FEATURES);
            }
        }
        return closePrepared(owner,chunks);
    }

    /** The caller supplies exclusively owned or generation-stage input chunks.
     * Public for real detached-ProtoChunk regression tests; never a FULL-world repair API.
     */
    public static int closePrepared(ChunkAccess owner, ChunkAccess[] chunks) {
        if (owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) return 0;
        if (owner.getMinY()!=-512 || owner.getHeight()!=1024 || chunks.length!=9 || chunks[4]!=owner)
            throw new IllegalArgumentException("R3910 invalid owner or supplied window");
        long started=System.nanoTime();
        int cx=owner.getPos().x(),cz=owner.getPos().z(),missing=0;
        byte[] cells=new byte[AREA*HEIGHT];
        boolean[] sky=new boolean[AREA];
        BitSet extraLava=new BitSet(cells.length);
        BlockState[] beforeOwner=new BlockState[HEIGHT*256];
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for (int tile=0;tile<9;tile++) {
            ChunkAccess chunk=chunks[tile];
            if (chunk==null) {missing++;continue;}
            if (chunk.getPos().x()!=cx+tile%3-1 || chunk.getPos().z()!=cz+tile/3-1
                || chunk.getMinY()!=-512 || chunk.getHeight()!=1024
                || chunk.getPersistedStatus().isBefore(ChunkStatus.FEATURES))
                throw new IllegalArgumentException("R3910 wrong cached chunk identity/status");
            // Read authoritative persisted per-piece geometry, never a released cache.
            BitSet protectedCells=NeverOverworldDryMinesR12.mask(chunk).envelope;
            int bx=chunk.getPos().getMinBlockX(),bz=chunk.getPos().getMinBlockZ();
            int ox=(tile%3)*16,oz=(tile/3)*16;
            for (int z=0;z<16;z++) for (int x=0;x<16;x++) {
                int plane=(oz+z)*WIDTH+ox+x; boolean open=true;
                for (int y=chunk.getMaxY()-1;y>HIGH;y--) {
                    p.set(bx+x,y,bz+z);
                    if (!conduit(chunk.getBlockState(p))) {open=false;break;}
                }
                sky[plane]=open;
                p.set(bx+x,HIGH+1,bz+z);
                if (chunk.getBlockState(p).is(Blocks.LAVA)) extraLava.set((HEIGHT-1)*AREA+plane);
                p.set(bx+x,LOW-1,bz+z);
                if (chunk.getBlockState(p).is(Blocks.LAVA)) extraLava.set(plane);
                for (int y=LOW;y<=HIGH;y++) {
                    p.set(bx+x,y,bz+z); BlockState state=chunk.getBlockState(p);
                    int layer=y-LOW,index=layer*AREA+plane,local=(layer<<8)|(z<<4)|x;
                    if (tile==4) beforeOwner[local]=state;
                    // Lava is already impassable. Keep its identity even inside
                    // a protected envelope so its neighbours remain excluded too.
                    cells[index]=state.is(Blocks.LAVA) ? OceanConnectivityR395.LAVA
                        : protectedCells.get(((y-chunk.getMinY())<<8)|(z<<4)|x) ? OceanConnectivityR395.PROTECTED
                        : state.isAir() ? OceanConnectivityR395.AIR
                        : aquatic(state) ? OceanConnectivityR395.WATER
                        : OceanConnectivityR395.SOLID;
                }
            }
        }
        OceanConnectivityR395.Proof proof=OceanConnectivityR395.solve(WIDTH,WIDTH,HEIGHT,cells,sky,extraLava);
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        // Validate the whole owner BEFORE any writes, not partly after filling it.
        // This detects owner mutation, not an arbitrary race in another chunk.
        for (int y=LOW;y<=HIGH;y++) for (int z=0;z<16;z++) for (int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x; p.set(bx+x,y,bz+z);
            if (owner.getBlockState(p)!=beforeOwner[local])
                throw new IllegalStateException("R3910 owner changed while calculating ocean witness");
        }
        BitSet changed=new BitSet(HEIGHT*256);
        int unproven=0,protectedAir=0,preservedNonAir=0;
        for (int y=LOW;y<=HIGH;y++) for (int z=0;z<16;z++) for (int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x,index=(y-LOW)*AREA+(z+16)*WIDTH+x+16;
            BlockState before=beforeOwner[local]; p.set(bx+x,y,bz+z);
            if (before.isAir()) {
                if (cells[index]==OceanConnectivityR395.PROTECTED) protectedAir++;
                else if (cells[index]==OceanConnectivityR395.AIR && proof.connected().get(index)) {
                    owner.setBlockState(p,Blocks.WATER.defaultBlockState(),0); changed.set(local);
                } else unproven++;
            } else {
                if (owner.getBlockState(p)!=before) throw new IllegalStateException("R3910 changed a non-air block");
                preservedNonAir++;
            }
        }
        if (!REPORT.isEmpty()) {
            String stem=cx+"_"+cz+"_"+IDS.incrementAndGet();
            JsonObject report=new JsonObject();
            report.addProperty("revision",REVISION);report.addProperty("chunk_x",cx);report.addProperty("chunk_z",cz);
            report.addProperty("added_air_to_water",changed.cardinality());report.addProperty("unproven_owner_air",unproven);
            report.addProperty("protected_owner_air",protectedAir);report.addProperty("preserved_owner_non_air",preservedNonAir);
            report.addProperty("missing_cache_chunks",missing);report.addProperty("snapshot_write_conflicts",0);
            report.addProperty("visited_witness_cells",proof.visited());report.addProperty("min_y",LOW);report.addProperty("max_y",HIGH);
            report.addProperty("global_closure_proven",false);report.addProperty("elapsed_ms",(System.nanoTime()-started)/1_000_000L);
            try {
                Path directory=Path.of(REPORT);Files.createDirectories(directory);
                if (WITNESSES) {
                    String file=stem+".witness.gz";
                    try (DataOutputStream out=new DataOutputStream(new GZIPOutputStream(Files.newOutputStream(directory.resolve(file),StandardOpenOption.CREATE_NEW)))) {
                        out.writeInt(0x4e4c3130);out.writeInt(1);out.writeInt(cx);out.writeInt(cz);
                        out.writeInt(WIDTH);out.writeInt(WIDTH);out.writeInt(HEIGHT);out.writeInt(LOW);
                        out.writeInt(cells.length);out.write(cells);
                        out.writeInt(sky.length);for(boolean value:sky)out.writeBoolean(value);
                        byte[] lava=extraLava.toByteArray(),writes=changed.toByteArray();
                        out.writeInt(lava.length);out.write(lava);out.writeInt(writes.length);out.write(writes);
                    }
                    report.addProperty("witness_file",file);
                }
                Files.writeString(directory.resolve(stem+".json"),report.toString()+"\n",StandardOpenOption.CREATE_NEW);
            } catch (java.io.IOException error) {throw new IllegalStateException("Cannot retain R3910 proof diagnostics",error);}
        }
        return changed.cardinality();
    }
    private static boolean conduit(BlockState state) {return state.isAir()||aquatic(state);}
    private static boolean aquatic(BlockState state) {
        return state.is(Blocks.WATER)||state.is(Blocks.BUBBLE_COLUMN)||state.is(Blocks.KELP)||state.is(Blocks.KELP_PLANT)
            ||state.is(Blocks.SEAGRASS)||state.is(Blocks.TALL_SEAGRASS);
    }
}
