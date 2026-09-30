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

/**
 * R39.26 ocean/cave pass on top of the accepted R39.9 kernel.
 *
 * It reads only Y=-511..128 from the supplied radius-1 FEATURES cache.
 * Y>128 is deliberately never inspected. This is the core rollback-safe rule:
 * upper island branches cannot suppress flooding below sea level.
 *
 * Only owner AIR is replaced with source WATER after a positive bounded
 * connection proof. Existing water, ice, vegetation, structures and lava are
 * never overwritten. Persisted dry-mine envelopes remain hard barriers.
 */
public final class NeverOverworldOceanClassifierR3926 {
    public static final String REVISION="R3926-sea-plane-ocean-cave-v1";
    private static final boolean ENABLED=Boolean.getBoolean("neverfolia.r3926OceanClassifier");
    private static final String REPORT=System.getProperty("neverfolia.r3926ReportDirectory","");
    private static final AtomicLong IDS=new AtomicLong();
    private static final int LOW=-511,HIGH=128,HEIGHT=HIGH-LOW+1,WIDTH=48,AREA=WIDTH*WIDTH;

    private NeverOverworldOceanClassifierR3926() {}

    public static int apply(WorldGenLevel world,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner) {
        if(!ENABLED || !world.getLevel().dimension().equals(Level.OVERWORLD)
            || owner.getMinY()!=-512 || owner.getHeight()!=1024
            || owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return 0;

        ChunkAccess[] chunks=new ChunkAccess[9];
        chunks[4]=owner;
        int cx=owner.getPos().x(),cz=owner.getPos().z(),missing=0;
        for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++) {
            if(dx==0&&dz==0)continue;
            int tile=(dz+1)*3+dx+1;
            if(cache!=null&&cache.contains(cx+dx,cz+dz)) {
                GenerationChunkHolder holder=cache.get(cx+dx,cz+dz);
                if(holder!=null)chunks[tile]=holder.getChunkIfPresent(ChunkStatus.FEATURES);
            }
            if(chunks[tile]==null)missing++;
        }
        return close(chunks,missing);
    }

    // Package-private production implementation is intentionally deterministic
    // over an already supplied snapshot. It never performs neighbour lookups.
    static int close(ChunkAccess[] chunks,int missing) {
        if(chunks.length!=9||chunks[4]==null)throw new IllegalArgumentException("R3926 owner missing");
        ChunkAccess owner=chunks[4];
        int cx=owner.getPos().x(),cz=owner.getPos().z();
        byte[] cells=new byte[AREA*HEIGHT];
        BlockState[] originalOwner=new BlockState[256*HEIGHT];
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();

        for(int tile=0;tile<9;tile++) {
            ChunkAccess chunk=chunks[tile];
            if(chunk==null)continue;
            if(chunk.getMinY()!=-512||chunk.getHeight()!=1024
                ||chunk.getPos().x()!=cx+tile%3-1||chunk.getPos().z()!=cz+tile/3-1)
                throw new IllegalArgumentException("R3926 inconsistent witness chunk");

            BitSet protectedCells=NeverOverworldDryMinesR12.mask(chunk).envelope;
            int bx=chunk.getPos().getMinBlockX(),bz=chunk.getPos().getMinBlockZ();
            int ox=(tile%3)*16,oz=(tile/3)*16;

            // IMPORTANT: this loop ends at HIGH=128. There is no read at 129+
            // anywhere in this class.
            for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
                p.set(bx+x,y,bz+z);
                BlockState state=chunk.getBlockState(p);
                int layer=y-LOW;
                int plane=(oz+z)*WIDTH+ox+x;
                int index=layer*AREA+plane;
                int local=(layer<<8)|(z<<4)|x;
                if(tile==4)originalOwner[local]=state;

                int maskIndex=((y-chunk.getMinY())<<8)|(z<<4)|x;
                if(protectedCells.get(maskIndex))cells[index]=OceanConnectivityR3926.PROTECTED;
                else if(state.isAir())cells[index]=OceanConnectivityR3926.AIR;
                else if(aquatic(state))cells[index]=OceanConnectivityR3926.WATER;
                else if(state.is(Blocks.LAVA))cells[index]=OceanConnectivityR3926.LAVA;
                else cells[index]=OceanConnectivityR3926.SOLID;
            }
        }

        OceanConnectivityR3926.Proof proof=OceanConnectivityR3926.solve(WIDTH,WIDTH,HEIGHT,cells);

        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        // Fail before the first write if owner state changed after capture.
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x;
            p.set(bx+x,y,bz+z);
            if(owner.getBlockState(p)!=originalOwner[local])
                throw new IllegalStateException("R3926 owner changed during capture");
        }

        int changed=0,unproven=0,beforeAquatic=0,preservedAquatic=0;
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x;
            int index=(y-LOW)*AREA+(z+16)*WIDTH+x+16;
            BlockState before=originalOwner[local];
            p.set(bx+x,y,bz+z);

            if(cells[index]==OceanConnectivityR3926.AIR) {
                if(proof.connected().get(index)) {
                    owner.setBlockState(p,Blocks.WATER.defaultBlockState(),0);
                    changed++;
                } else {
                    unproven++;
                }
            }

            if(aquatic(before)) {
                beforeAquatic++;
                if(owner.getBlockState(p)==before)preservedAquatic++;
            }
        }
        if(beforeAquatic!=preservedAquatic)
            throw new IllegalStateException("R3926 existing aquatic state changed");

        if(!REPORT.isEmpty()) {
            JsonObject report=new JsonObject();
            report.addProperty("revision",REVISION);
            report.addProperty("chunk_x",cx);
            report.addProperty("chunk_z",cz);
            report.addProperty("added_air_to_water",changed);
            report.addProperty("unproven_owner_air",unproven);
            report.addProperty("missing_cache_chunks",missing);
            report.addProperty("visited_witness_cells",proof.visited());
            report.addProperty("read_min_y",LOW);
            report.addProperty("read_max_y",HIGH);
            report.addProperty("reads_above_sea_level",0);
            report.addProperty("native_aquatic_cells",beforeAquatic);
            report.addProperty("preserved_aquatic_cells",preservedAquatic);
            try {
                Path dir=Path.of(REPORT);
                Files.createDirectories(dir);
                Files.writeString(dir.resolve(cx+"_"+cz+"_"+IDS.incrementAndGet()+".json"),
                    report.toString()+"\n",StandardOpenOption.CREATE_NEW);
            } catch(java.io.IOException error) {
                throw new IllegalStateException("Cannot retain R3926 diagnostics",error);
            }
        }
        return changed;
    }

    private static boolean aquatic(BlockState s) {
        return s.is(Blocks.WATER)||s.is(Blocks.BUBBLE_COLUMN)||s.is(Blocks.KELP)||s.is(Blocks.KELP_PLANT)
            ||s.is(Blocks.SEAGRASS)||s.is(Blocks.TALL_SEAGRASS);
    }
}
