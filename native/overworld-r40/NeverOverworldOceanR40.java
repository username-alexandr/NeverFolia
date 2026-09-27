package net.minecraft.world.level.chunk;

import com.google.gson.JsonObject;
import java.nio.file.*;
import java.io.IOException;
import java.util.BitSet;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import org.bukkit.NamespacedKey;
import org.bukkit.persistence.PersistentDataType;

/** Generation-only staged closure. INITIALIZE_LIGHT snapshots the owning chunk
 * after all neighbouring FEATURES writers complete. LIGHT reads only persisted
 * immutable snapshots, never the neighbours' mutable block states. */
public final class NeverOverworldOceanR40 {
    public static final boolean ENABLED=Boolean.getBoolean("neverfolia.r40Ocean");
    public static final int RADIUS=4,LOW=-511,HIGH=128,HEIGHT=640;
    private static final NamespacedKey SNAPSHOT=new NamespacedKey("neverfolia","ocean_snapshot_r40_v1");
    private static final NamespacedKey DONE=new NamespacedKey("neverfolia","ocean_done_r40_v1");
    private static final String REPORT=System.getProperty("neverfolia.r40ReportDirectory","");
    private NeverOverworldOceanR40() {}
    public static boolean scope(WorldGenLevel world,ChunkAccess chunk) {
        return ENABLED&&world.getLevel().dimension().equals(Level.OVERWORLD)&&chunk.getMinY()==-512&&chunk.getHeight()==1024;
    }
    public static boolean envelope(ChunkAccess chunk) {return ENABLED&&chunk.getMinY()==-512&&chunk.getHeight()==1024;}
    public static void prepare(WorldGenLevel world,ChunkAccess owner) {
        if(!scope(world,owner)||owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return;
        byte[] existing=owner.persistentDataContainer.get(SNAPSHOT,PersistentDataType.BYTE_ARRAY);
        if(existing!=null) {OceanSnapshotR40.decode(existing,world.getSeed(),owner.getPos().x(),owner.getPos().z());return;}
        if(owner.getPersistedStatus().isBefore(ChunkStatus.FEATURES))throw new IllegalStateException("R40 snapshot before FEATURES");
        // These routines operate only on the owner. The old neighbour seam BFS is
        // intentionally not used: all new cross-column reachability uses snapshots.
        NeverOverworldFlood.apply(world,owner);
        NeverOverworldFlood.reweatherSubmergedSurface(world,owner);
        NeverOverworldEcologyR13.cleanup(world,owner);
        NeverOverworldEcologyR15.cleanup(world,owner);
        byte[] cells=new byte[256*HEIGHT];boolean[] sky=new boolean[256];BitSet edgeLava=new BitSet(cells.length);
        BitSet protectedCells=NeverOverworldDryMinesR12.mask(owner).envelope;
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int c=z*16+x;boolean open=true;
            for(int y=owner.getMaxY()-1;y>HIGH;y--) {
                p.set(bx+x,y,bz+z);BlockState state=owner.getBlockState(p);
                if(!state.isAir()&&!aquatic(state)){open=false;break;}
            }
            sky[c]=open;
            p.set(bx+x,LOW-1,bz+z);if(owner.getBlockState(p).is(Blocks.LAVA))edgeLava.set(c*HEIGHT);
            p.set(bx+x,HIGH+1,bz+z);if(owner.getBlockState(p).is(Blocks.LAVA))edgeLava.set(c*HEIGHT+HEIGHT-1);
            for(int y=LOW;y<=HIGH;y++) {
                p.set(bx+x,y,bz+z);BlockState state=owner.getBlockState(p);int i=c*HEIGHT+y-LOW;
                if(protectedCells.get(((y+512)<<8)|(z<<4)|x))cells[i]=SpanOceanR40.PROTECTED;
                else cells[i]=classify(state);
            }
        }
        byte[] encoded=OceanSnapshotR40.encode(world.getSeed(),owner.getPos().x(),owner.getPos().z(),cells,sky,edgeLava);
        // Verify the exact serialized representation before exposing the completed stage.
        OceanSnapshotR40.decode(encoded,world.getSeed(),owner.getPos().x(),owner.getPos().z());
        owner.persistentDataContainer.set(SNAPSHOT,PersistentDataType.BYTE_ARRAY,encoded);
    }
    public static int close(WorldGenLevel world,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner) {
        if(!scope(world,owner)||owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return 0;
        if(owner.persistentDataContainer.has(DONE,PersistentDataType.BYTE))return 0;
        if(owner.persistentDataContainer.get(SNAPSHOT,PersistentDataType.BYTE_ARRAY)==null) {
            // A pre-existing partially generated world must be migrated separately.
            throw new IllegalStateException("R40 owner has no completed ocean snapshot; use an isolated new test world");
        }
        final long started=System.nanoTime();final int tiles=RADIUS*2+1,width=tiles*16,area=width*width;
        byte[] cells=new byte[area*HEIGHT];boolean[] sky=new boolean[area];BitSet edgeLava=new BitSet(cells.length);
        int missing=0,cx=owner.getPos().x(),cz=owner.getPos().z();
        for(int dz=-RADIUS;dz<=RADIUS;dz++)for(int dx=-RADIUS;dx<=RADIUS;dx++) {
            ChunkAccess neighbour=null;
            if(dx==0&&dz==0)neighbour=owner;
            else if(cache!=null&&cache.contains(cx+dx,cz+dz)) {
                GenerationChunkHolder holder=cache.get(cx+dx,cz+dz);
                if(holder!=null)neighbour=holder.getChunkIfPresent(ChunkStatus.INITIALIZE_LIGHT);
            }
            byte[] encoded=neighbour==null?null:neighbour.persistentDataContainer.get(SNAPSHOT,PersistentDataType.BYTE_ARRAY);
            if(encoded==null){missing++;continue;}
            OceanSnapshotR40.Data data=OceanSnapshotR40.decode(encoded,world.getSeed(),cx+dx,cz+dz);
            int ox=(dx+RADIUS)*16,oz=(dz+RADIUS)*16;
            for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
                int local=z*16+x,plane=(oz+z)*width+ox+x,base=plane*HEIGHT;
                System.arraycopy(data.cells(),local*HEIGHT,cells,base,HEIGHT);sky[plane]=data.sky()[local];
                if(data.boundaryLava().get(local*HEIGHT))edgeLava.set(base);
                if(data.boundaryLava().get(local*HEIGHT+HEIGHT-1))edgeLava.set(base+HEIGHT-1);
            }
        }
        SpanOceanR40.Proof proof=SpanOceanR40.solve(width,width,HEIGHT,cells,sky,edgeLava);
        BitSet protection=NeverOverworldDryMinesR12.mask(owner).envelope;
        int added=0,plants=0,unproven=0,conflicts=0,bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int z=0;z<16;z++)for(int x=0;x<16;x++)for(int y=LOW;y<=HIGH;y++) {
            int i=((z+RADIUS*16)*width+x+RADIUS*16)*HEIGHT+y-LOW;byte original=cells[i];
            if(original!=SpanOceanR40.AIR&&original!=SpanOceanR40.REMOVABLE)continue;
            if(!proof.connected().get(i)){if(original==SpanOceanR40.AIR)unproven++;continue;}
            if(protection.get(((y+512)<<8)|(z<<4)|x))throw new IllegalStateException("R40 protected volume reached");
            p.set(bx+x,y,bz+z);BlockState state=owner.getBlockState(p);
            if(!state.getFluidState().isEmpty())continue;
            if((original==SpanOceanR40.AIR&&!state.isAir())||(original==SpanOceanR40.REMOVABLE&&!removable(state))) {conflicts++;continue;}
            owner.setBlockState(p,Blocks.WATER.defaultBlockState(),0);
            if(original==SpanOceanR40.AIR)added++;else plants++;
        }
        owner.persistentDataContainer.set(DONE,PersistentDataType.BYTE,(byte)1);
        if(!REPORT.isEmpty()) {
            JsonObject r=new JsonObject();r.addProperty("revision","R40-immutable-span-v1");r.addProperty("chunk_x",cx);r.addProperty("chunk_z",cz);
            r.addProperty("seed",world.getSeed());r.addProperty("radius",RADIUS);r.addProperty("missing_snapshots",missing);r.addProperty("owner_conflicts",conflicts);
            r.addProperty("air_to_water",added);r.addProperty("plants_to_water",plants);r.addProperty("unproven_air",unproven);
            r.addProperty("visited",proof.visitedCells());r.addProperty("spans",proof.spans());r.addProperty("elapsed_ms",(System.nanoTime()-started)/1_000_000L);
            r.addProperty("global_closure_proven",false);
            try {Path dir=Path.of(REPORT);Files.createDirectories(dir);Files.writeString(dir.resolve(cx+"_"+cz+".json"),r+"\n",StandardOpenOption.CREATE_NEW);}
            catch(IOException failure){throw new IllegalStateException("Cannot retain R40 proof",failure);}
        }
        return added+plants;
    }
    private static byte classify(BlockState state) {
        if(state.isAir())return SpanOceanR40.AIR;
        if(aquatic(state))return SpanOceanR40.WATER;
        if(state.is(Blocks.LAVA))return SpanOceanR40.LAVA;
        if(state.is(Blocks.ICE)||state.is(Blocks.PACKED_ICE)||state.is(Blocks.BLUE_ICE)||state.is(Blocks.FROSTED_ICE))return SpanOceanR40.ICE;
        if(removable(state))return SpanOceanR40.REMOVABLE;
        return SpanOceanR40.SOLID;
    }
    private static boolean removable(BlockState state) {return state.getFluidState().isEmpty()&&NeverOverworldEcologyR15.floodedCavePlant(state);}
    private static boolean aquatic(BlockState state) {return state.is(Blocks.WATER)||state.is(Blocks.BUBBLE_COLUMN)||state.is(Blocks.KELP)||state.is(Blocks.KELP_PLANT)||state.is(Blocks.SEAGRASS)||state.is(Blocks.TALL_SEAGRASS);}
}
