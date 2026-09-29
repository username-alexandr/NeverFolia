package net.minecraft.world.level.chunk;

import com.google.gson.JsonObject;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.BitSet;
import java.util.zip.GZIPOutputStream;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/** A 5x5 positive witness, with a completed FEATURES writer halo (7x7).
 * Only the new owning chunk is written. No load, tick, repair, or neighbour write.
 * The matching ChunkPyramid change is mandatory; an incomplete halo fails closed.
 * Finite reachability is not global closure and is not worldgen-order determinism.
 */
public final class NeverOverworldOceanClosureR399 {
    public static final String REVISION="R399-5x5-completed-feature-halo-v2-surface-gate";
    private static final boolean ENABLED=Boolean.getBoolean("neverfolia.r399OceanClosure");
    private static final String REPORT=System.getProperty("neverfolia.r399ReportDirectory","");
    private static final int LOW=-511,HIGH=128,WATER_SURFACE_Y=128,HEIGHT=640,RADIUS=2,SIDE=5,WIDTH=80,AREA=6400;
    private NeverOverworldOceanClosureR399() {}

    public static int apply(WorldGenLevel world,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner) {
        if(!ENABLED || !world.getLevel().dimension().equals(Level.OVERWORLD)
            || owner.getMinY()!=-512 || owner.getHeight()!=1024
            || owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return 0;
        long started=System.nanoTime();
        int cx=owner.getPos().x(),cz=owner.getPos().z();
        // A feature at distance 3 may write into the radius-2 witness.
        // Never synchronously request these chunks here; the generation pyramid owns the dependency.
        for(int dz=-3;dz<=3;dz++)for(int dx=-3;dx<=3;dx++) {
            if(dx==0&&dz==0)continue;
            if(cache==null||!cache.contains(cx+dx,cz+dz)
                ||cache.get(cx+dx,cz+dz)==null
                ||cache.get(cx+dx,cz+dz).getChunkIfPresent(ChunkStatus.FEATURES)==null)
                throw new IllegalStateException("R399 requires completed FEATURES radius 3 before LIGHT");
        }
        ChunkAccess[] chunks=new ChunkAccess[SIDE*SIDE];chunks[12]=owner;
        for(int dz=-RADIUS;dz<=RADIUS;dz++)for(int dx=-RADIUS;dx<=RADIUS;dx++) {
            if(dx==0&&dz==0)continue;
            chunks[(dz+RADIUS)*SIDE+dx+RADIUS]=cache.get(cx+dx,cz+dz).getChunkIfPresent(ChunkStatus.FEATURES);
        }
        byte[] cells=new byte[AREA*HEIGHT];boolean[] sky=new boolean[AREA];BitSet extraLava=new BitSet(cells.length);
        BlockState[] originalOwner=new BlockState[256*HEIGHT];
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int tile=0;tile<chunks.length;tile++) {
            ChunkAccess chunk=chunks[tile];
            if(chunk.getMinY()!=-512||chunk.getHeight()!=1024)throw new IllegalStateException("R399 mixed world envelope");
            BitSet protectedCells=NeverOverworldDryMinesR12.mask(chunk).envelope;
            int bx=chunk.getPos().getMinBlockX(),bz=chunk.getPos().getMinBlockZ();
            int ox=(tile%SIDE)*16,oz=(tile/SIDE)*16;
            for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
                int plane=(oz+z)*WIDTH+ox+x;boolean open=true;
                for(int y=chunk.getMaxY()-1;y>HIGH;y--) {
                    p.set(bx+x,y,bz+z);if(!conduit(chunk.getBlockState(p))){open=false;break;}
                }
                sky[plane]=open;
                p.set(bx+x,HIGH+1,bz+z);
                if(chunk.getBlockState(p).is(Blocks.LAVA))extraLava.set((HEIGHT-1)*AREA+plane);
                p.set(bx+x,LOW-1,bz+z);
                if(chunk.getBlockState(p).is(Blocks.LAVA))extraLava.set(plane);
                for(int y=LOW;y<=HIGH;y++) {
                    p.set(bx+x,y,bz+z);BlockState state=chunk.getBlockState(p);
                    int layer=y-LOW,index=layer*AREA+plane,local=(layer<<8)|(z<<4)|x;
                    if(tile==12)originalOwner[local]=state;
                    if(protectedCells.get(((y-chunk.getMinY())<<8)|(z<<4)|x))cells[index]=OceanConnectivityR399.PROTECTED;
                    else if(state.isAir())cells[index]=OceanConnectivityR399.AIR;
                    else if(aquatic(state))cells[index]=OceanConnectivityR399.WATER;
                    else if(state.is(Blocks.LAVA))cells[index]=OceanConnectivityR399.LAVA;
                    else cells[index]=OceanConnectivityR399.SOLID;
                }
            }
        }
        OceanConnectivityR399.Proof proof=OceanConnectivityR399.solve(WIDTH,WIDTH,HEIGHT,cells,sky,extraLava);
        int changed=0,unproven=0,conflicts=0,beforeWater=0,preservedWater=0,protectedAir=0,skippedSurfaceAir=0;
        BitSet changedOwner=new BitSet(256*HEIGHT);
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        // Validate the entire owning snapshot before the first write, avoiding partial writes on conflict.
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x;p.set(bx+x,y,bz+z);
            if(originalOwner[local]!=owner.getBlockState(p))conflicts++;
        }
        if(conflicts!=0)throw new IllegalStateException("R399 owning snapshot changed before commit: "+conflicts);
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x,index=(y-LOW)*AREA+(z+32)*WIDTH+x+32;
            BlockState before=originalOwner[local];p.set(bx+x,y,bz+z);
            // R39.24: Y=128 is the water surface plane, not a water block target.
            // Never synthesize WATER at the surface plane or above. Connectivity may still
            // traverse the witness there so below-surface ocean cells retain the same proof.
            if(y>=WATER_SURFACE_Y) {
                if(cells[index]==OceanConnectivityR399.AIR&&proof.connected().get(index))skippedSurfaceAir++;
            } else if(cells[index]==OceanConnectivityR399.AIR) {
                if(proof.connected().get(index)) {owner.setBlockState(p,Blocks.WATER.defaultBlockState(),0);changedOwner.set(local);changed++;}
                else unproven++;
            } else if(cells[index]==OceanConnectivityR399.PROTECTED&&before.isAir())protectedAir++;
            if(aquatic(before)) {beforeWater++;if(owner.getBlockState(p)==before)preservedWater++;}
        }
        if(beforeWater!=preservedWater)throw new IllegalStateException("R399 native water changed");
        if(!REPORT.isEmpty() && auditTarget(cx,cz)) {
            JsonObject r=new JsonObject();r.addProperty("revision",REVISION);r.addProperty("chunk_x",cx);r.addProperty("chunk_z",cz);
            r.addProperty("added_air_to_water",changed);r.addProperty("unproven_owner_air",unproven);r.addProperty("water_surface_y",WATER_SURFACE_Y);r.addProperty("skipped_at_or_above_surface_air",skippedSurfaceAir);
            r.addProperty("protected_owner_air",protectedAir);r.addProperty("snapshot_write_conflicts",conflicts);
            r.addProperty("native_aquatic_cells",beforeWater);r.addProperty("preserved_aquatic_cells",preservedWater);
            r.addProperty("visited_witness_cells",proof.visited());r.addProperty("elapsed_ms",(System.nanoTime()-started)/1_000_000L);
            r.addProperty("witness_radius",2);r.addProperty("completed_feature_radius",3);r.addProperty("global_closure_proven",false);
            try {
                Path dir=Path.of(REPORT);Files.createDirectories(dir);String stem=cx+"_"+cz;
                try(var out=new DataOutputStream(new GZIPOutputStream(Files.newOutputStream(dir.resolve(stem+".witness.gz"),StandardOpenOption.CREATE_NEW)))) {
                    out.writeInt(0x52333939);out.writeInt(WIDTH);out.writeInt(WIDTH);out.writeInt(HEIGHT);out.writeInt(cx);out.writeInt(cz);
                    out.write(cells);for(boolean value:sky)out.writeBoolean(value);
                    byte[] lava=extraLava.toByteArray();out.writeInt(lava.length);out.write(lava);
                    byte[] delta=changedOwner.toByteArray();out.writeInt(delta.length);out.write(delta);
                }
                Files.writeString(dir.resolve(stem+".json"),r+"\n",StandardOpenOption.CREATE_NEW);
            }catch(IOException error){throw new IllegalStateException("Cannot retain R399 diagnostics",error);}
        }
        return changed;
    }
    // Evidence only. Generation always applies to every eligible new Overworld chunk.
    private static boolean auditTarget(int cx,int cz) {
        int[][] centers={{7,1},{1,-4},{-197,-217},{-169,-250},{-189,-223},{-1699,-769}};
        for(int[] c:centers)if(Math.abs(cx-c[0])<=1&&Math.abs(cz-c[1])<=1)return true;
        return false;
    }
    private static boolean conduit(BlockState s){return s.isAir()||aquatic(s);}
    private static boolean aquatic(BlockState s) {
        return s.is(Blocks.WATER)||s.is(Blocks.BUBBLE_COLUMN)||s.is(Blocks.KELP)||s.is(Blocks.KELP_PLANT)
            ||s.is(Blocks.SEAGRASS)||s.is(Blocks.TALL_SEAGRASS);
    }
}
