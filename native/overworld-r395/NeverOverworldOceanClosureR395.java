package net.minecraft.world.level.chunk;

import com.google.gson.JsonObject;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.BitSet;
import java.util.concurrent.atomic.AtomicLong;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/** Experimental candidate: positive 3D proof, never a blanket underground fill.
 * Uses only supplied FEATURES holders; never loads or writes a neighbouring chunk.
 * All reads precede all writes. Only AIR becomes water; native fluids and solid
 * ice, vegetation, structure blocks and lava are not replaced by this pass.
 * Unproven connections beyond the cache remain unresolved and are reported.
 */
public final class NeverOverworldOceanClosureR395 {
    public static final String REVISION="R395-positive-ocean-proof-v1";
    private static final boolean ENABLED=Boolean.getBoolean("neverfolia.r395OceanClosure");
    private static final String REPORT=System.getProperty("neverfolia.r395ReportDirectory","");
    private static final AtomicLong IDS=new AtomicLong();
    private static final int LOW=-511,HIGH=128,HEIGHT=HIGH-LOW+1,WIDTH=48,AREA=WIDTH*WIDTH;
    private NeverOverworldOceanClosureR395() {}

    public static int apply(WorldGenLevel world,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner) {
        if(!ENABLED || !world.getLevel().dimension().equals(Level.OVERWORLD)
            || owner.getMinY()!=-512 || owner.getHeight()!=1024
            || owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return 0;
        long started=System.nanoTime();
        ChunkAccess[] chunks=new ChunkAccess[9];chunks[4]=owner;
        int missing=0,cx=owner.getPos().x(),cz=owner.getPos().z();
        for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++) {
            if(dx==0&&dz==0)continue;
            if(cache!=null&&cache.contains(cx+dx,cz+dz)) {
                GenerationChunkHolder holder=cache.get(cx+dx,cz+dz);
                if(holder!=null)chunks[(dz+1)*3+dx+1]=holder.getChunkIfPresent(ChunkStatus.FEATURES);
            }
            if(chunks[(dz+1)*3+dx+1]==null)missing++;
        }
        byte[] cells=new byte[AREA*HEIGHT];boolean[] sky=new boolean[AREA];BitSet extraLava=new BitSet(cells.length);
        BlockState[] originalOwner=new BlockState[256*HEIGHT];
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int tile=0;tile<9;tile++) {
            ChunkAccess chunk=chunks[tile];if(chunk==null)continue;
            if(chunk.getMinY()!=-512||chunk.getHeight()!=1024)throw new IllegalStateException("R395 mixed world envelope");
            // Read persisted geometry rather than a transient mask that another LIGHT
            // pass may have released. This is a fresh local immutable BitSet.
            BitSet protectedCells=NeverOverworldDryMinesR12.mask(chunk).envelope;
            int bx=chunk.getPos().getMinBlockX(),bz=chunk.getPos().getMinBlockZ();
            int ox=(tile%3)*16,oz=(tile/3)*16;
            for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
                int plane=(oz+z)*WIDTH+ox+x;boolean open=true;
                // A raised roof is not a sea-surface seed. The obsolete WG heightmap
                // is deliberately not used to classify anything below that roof.
                for(int y=chunk.getMaxY()-1;y>HIGH;y--) {
                    p.set(bx+x,y,bz+z);BlockState state=chunk.getBlockState(p);
                    if(!conduit(state)){open=false;break;}
                }
                sky[plane]=open;
                p.set(bx+x,HIGH+1,bz+z);
                if(chunk.getBlockState(p).is(Blocks.LAVA))extraLava.set((HEIGHT-1)*AREA+plane);
                p.set(bx+x,LOW-1,bz+z);
                if(chunk.getBlockState(p).is(Blocks.LAVA))extraLava.set(plane);
                for(int y=LOW;y<=HIGH;y++) {
                    p.set(bx+x,y,bz+z);BlockState state=chunk.getBlockState(p);
                    int layer=y-LOW,index=layer*AREA+plane,local=(layer<<8)|(z<<4)|x;
                    if(tile==4)originalOwner[local]=state;
                    if(protectedCells.get(((y-chunk.getMinY())<<8)|(z<<4)|x))cells[index]=OceanConnectivityR395.PROTECTED;
                    else if(state.isAir())cells[index]=OceanConnectivityR395.AIR;
                    else if(aquatic(state))cells[index]=OceanConnectivityR395.WATER;
                    else if(state.is(Blocks.LAVA))cells[index]=OceanConnectivityR395.LAVA;
                    else cells[index]=OceanConnectivityR395.SOLID;
                }
            }
        }
        OceanConnectivityR395.Proof proof=OceanConnectivityR395.solve(WIDTH,WIDTH,HEIGHT,cells,sky,extraLava);
        int changed=0,unproven=0,conflicts=0,beforeWater=0,preservedWater=0;
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x,index=(y-LOW)*AREA+(z+16)*WIDTH+x+16;
            BlockState before=originalOwner[local];p.set(bx+x,y,bz+z);
            BlockState current=owner.getBlockState(p);
            if(before!=current){conflicts++;continue;}
            if(cells[index]==OceanConnectivityR395.AIR) {
                if(proof.connected().get(index)) {owner.setBlockState(p,Blocks.WATER.defaultBlockState(),0);changed++;}
                else unproven++;
            }
            if(aquatic(before)) {beforeWater++;if(owner.getBlockState(p)==before)preservedWater++;}
        }
        if(beforeWater!=preservedWater)throw new IllegalStateException("R395 native water changed");
        if(!REPORT.isEmpty()) {
            JsonObject report=new JsonObject();report.addProperty("revision",REVISION);
            report.addProperty("chunk_x",cx);report.addProperty("chunk_z",cz);
            report.addProperty("added_air_to_water",changed);report.addProperty("unproven_owner_air",unproven);
            report.addProperty("missing_cache_chunks",missing);report.addProperty("snapshot_write_conflicts",conflicts);
            report.addProperty("native_aquatic_cells",beforeWater);report.addProperty("preserved_aquatic_cells",preservedWater);
            report.addProperty("visited_witness_cells",proof.visited());report.addProperty("min_y",LOW);report.addProperty("max_y",HIGH);
            report.addProperty("elapsed_ms",(System.nanoTime()-started)/1_000_000L);
            report.addProperty("global_closure_proven",false);
            try {
                Path dir=Path.of(REPORT);Files.createDirectories(dir);
                Files.writeString(dir.resolve(cx+"_"+cz+"_"+IDS.incrementAndGet()+".json"),report.toString()+"\n",StandardOpenOption.CREATE_NEW);
            }catch(java.io.IOException error){throw new IllegalStateException("Cannot retain R395 proof diagnostics",error);}
        }
        return changed;
    }
    private static boolean conduit(BlockState s){return s.isAir()||aquatic(s);}
    private static boolean aquatic(BlockState s) {
        return s.is(Blocks.WATER)||s.is(Blocks.BUBBLE_COLUMN)||s.is(Blocks.KELP)||s.is(Blocks.KELP_PLANT)
            ||s.is(Blocks.SEAGRASS)||s.is(Blocks.TALL_SEAGRASS);
    }
}
