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

/** R40 combines the existing bounded R395 graph with the exact R399 kernel.
 * It is not a global ocean solver or a repair operation for saved FULL chunks.
 * The compatibility property remains neverfolia.r395OceanClosure; OFF by default.
 * Input witnesses are optional diagnostic data, never read back by worldgen.
 */
public final class NeverOverworldOceanClosureR40 {
    public static final String REVISION="R40-combined-bounded-ocean-v1";
    private static final boolean ENABLED=Boolean.getBoolean("neverfolia.r395OceanClosure");
    private static final String REPORT=System.getProperty("neverfolia.r395ReportDirectory","");
    private static final boolean WITNESS=Boolean.getBoolean("neverfolia.r40ExportWitness");
    private static final AtomicLong IDS=new AtomicLong();
    private static final int LOW=-511,HIGH=128,HEIGHT=640,WIDTH=48,AREA=2304;
    private NeverOverworldOceanClosureR40() {}

    public static int apply(WorldGenLevel world,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner) {
        if(!ENABLED || !world.getLevel().dimension().equals(Level.OVERWORLD)
            || owner.getMinY()!=-512 || owner.getHeight()!=1024
            || owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return 0;
        ChunkAccess[] chunks=new ChunkAccess[9];chunks[4]=owner;
        int cx=owner.getPos().x(),cz=owner.getPos().z();
        for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++) {
            if(dx==0&&dz==0)continue;
            if(cache!=null&&cache.contains(cx+dx,cz+dz)) {
                GenerationChunkHolder holder=cache.get(cx+dx,cz+dz);
                if(holder!=null)chunks[(dz+1)*3+dx+1]=holder.getChunkIfPresent(ChunkStatus.FEATURES);
            }
        }
        return close(chunks);
    }

    // The same implementation is exercised by an isolated, region-owned CI fixture.
    // Only apply() is a production entry: it enforces dimension, flag and FULL guard.
    private static int close(ChunkAccess[] chunks) {
        if(chunks.length!=9||chunks[4]==null)throw new IllegalArgumentException("R40 owner missing");
        long started=System.nanoTime();ChunkAccess owner=chunks[4];
        int cx=owner.getPos().x(),cz=owner.getPos().z(),missing=0;
        byte[] cells=new byte[AREA*HEIGHT];boolean[] sky=new boolean[AREA];
        BitSet extraLava=new BitSet(cells.length);
        BlockState[] original=new BlockState[256*HEIGHT];
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int tile=0;tile<9;tile++) {
            ChunkAccess chunk=chunks[tile];if(chunk==null){missing++;continue;}
            if(chunk.getMinY()!=-512||chunk.getHeight()!=1024
                ||chunk.getPos().x()!=cx+tile%3-1||chunk.getPos().z()!=cz+tile/3-1)
                throw new IllegalArgumentException("R40 inconsistent witness chunk");
            BitSet protectedCells=NeverOverworldDryMinesR12.mask(chunk).envelope;
            int bx=chunk.getPos().getMinBlockX(),bz=chunk.getPos().getMinBlockZ();
            int ox=tile%3*16,oz=tile/3*16;
            for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
                int plane=(oz+z)*WIDTH+ox+x;boolean open=true;
                for(int y=chunk.getMaxY()-1;y>HIGH;y--) {
                    p.set(bx+x,y,bz+z);
                    if(!conduit(chunk.getBlockState(p))){open=false;break;}
                }
                sky[plane]=open;
                p.set(bx+x,HIGH+1,bz+z);
                if(chunk.getBlockState(p).is(Blocks.LAVA))extraLava.set((HEIGHT-1)*AREA+plane);
                p.set(bx+x,LOW-1,bz+z);
                if(chunk.getBlockState(p).is(Blocks.LAVA))extraLava.set(plane);
                for(int y=LOW;y<=HIGH;y++) {
                    p.set(bx+x,y,bz+z);BlockState state=chunk.getBlockState(p);
                    int layer=y-LOW,index=layer*AREA+plane,local=(layer<<8)|(z<<4)|x;
                    if(tile==4)original[local]=state;
                    if(protectedCells.get(((y-chunk.getMinY())<<8)|(z<<4)|x))cells[index]=OceanConnectivityR395.PROTECTED;
                    else if(state.isAir())cells[index]=OceanConnectivityR395.AIR;
                    else if(aquatic(state))cells[index]=OceanConnectivityR395.WATER;
                    else if(state.is(Blocks.LAVA))cells[index]=OceanConnectivityR395.LAVA;
                    else cells[index]=OceanConnectivityR395.SOLID;
                }
            }
        }
        OceanConnectivityR395.Proof proof=OceanConnectivityR395.solve(WIDTH,WIDTH,HEIGHT,cells,sky,extraLava);
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        // Validate the entire owner's snapshot before the first write. A conflict
        // aborts, instead of publishing a partially applied proof as a success.
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x;p.set(bx+x,y,bz+z);
            if(owner.getBlockState(p)!=original[local])throw new IllegalStateException("R40 owner changed during witness capture");
        }
        BitSet added=new BitSet(original.length);
        int unproven=0,beforeWater=0,preservedWater=0;
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x,index=(y-LOW)*AREA+(z+16)*WIDTH+x+16;
            p.set(bx+x,y,bz+z);BlockState before=original[local];
            if(cells[index]==OceanConnectivityR395.AIR) {
                if(proof.connected().get(index)) {
                    owner.setBlockState(p,Blocks.WATER.defaultBlockState(),0);added.set(local);
                } else unproven++;
            }
            if(aquatic(before)){beforeWater++;if(owner.getBlockState(p)==before)preservedWater++;}
            if(!added.get(local)&&owner.getBlockState(p)!=before)throw new IllegalStateException("R40 non-target state changed");
        }
        if(beforeWater!=preservedWater)throw new IllegalStateException("R40 existing aquatic state changed");
        if(!REPORT.isEmpty()) {
            JsonObject report=new JsonObject();report.addProperty("revision",REVISION);
            report.addProperty("chunk_x",cx);report.addProperty("chunk_z",cz);
            report.addProperty("added_air_to_water",added.cardinality());report.addProperty("unproven_owner_air",unproven);
            report.addProperty("missing_cache_chunks",missing);report.addProperty("snapshot_write_conflicts",0);
            report.addProperty("native_aquatic_cells",beforeWater);report.addProperty("preserved_aquatic_cells",preservedWater);
            report.addProperty("visited_witness_cells",proof.visited());report.addProperty("min_y",LOW);report.addProperty("max_y",HIGH);
            report.addProperty("elapsed_ms",(System.nanoTime()-started)/1_000_000L);
            report.addProperty("global_closure_proven",false);
            try {
                Path dir=Path.of(REPORT);Files.createDirectories(dir);String id=cx+"_"+cz+"_"+IDS.incrementAndGet();
                if(WITNESS) {
                    String file=id+".witness.gz";
                    try(DataOutputStream out=new DataOutputStream(new GZIPOutputStream(Files.newOutputStream(dir.resolve(file),StandardOpenOption.CREATE_NEW)))) {
                        out.writeBytes("NF40W001");out.writeInt(WIDTH);out.writeInt(WIDTH);out.writeInt(HEIGHT);out.writeInt(LOW);
                        out.writeInt(cx);out.writeInt(cz);out.write(cells);
                        for(boolean value:sky)out.writeBoolean(value);
                        byte[] lava=extraLava.toByteArray(),writes=added.toByteArray();
                        out.writeInt(lava.length);out.write(lava);out.writeInt(writes.length);out.write(writes);
                    }
                    report.addProperty("witness_file",file);
                }
                Files.writeString(dir.resolve(id+".json"),report.toString()+"\n",StandardOpenOption.CREATE_NEW);
            }catch(java.io.IOException error){throw new IllegalStateException("Cannot retain R40 proof diagnostics",error);}
        }
        return added.cardinality();
    }
    private static boolean conduit(BlockState s){return s.isAir()||aquatic(s);}
    private static boolean aquatic(BlockState s){return s.is(Blocks.WATER)||s.is(Blocks.BUBBLE_COLUMN)||s.is(Blocks.KELP)||s.is(Blocks.KELP_PLANT)||s.is(Blocks.SEAGRASS)||s.is(Blocks.TALL_SEAGRASS);}
}
