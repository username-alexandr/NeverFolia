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

/** R39.27: AIR is never treated as evidence by itself.
 * Vanilla CarvingMask and CAVE_AIR are exact cave provenance.
 * Y>128 is never read. Only owner AIR/CAVE_AIR becomes source WATER.
 */
public final class NeverOverworldOceanClassifierR3927 {
    public static final String REVISION="R3927-carving-provenance-v1";
    private static final boolean ENABLED=Boolean.getBoolean("neverfolia.r3927OceanClassifier");
    private static final String REPORT=System.getProperty("neverfolia.r3927ReportDirectory","");
    private static final AtomicLong IDS=new AtomicLong();
    private static final int LOW=-511,HIGH=128,HEIGHT=640,WIDTH=48,AREA=2304;
    private NeverOverworldOceanClassifierR3927(){}

    public static int apply(WorldGenLevel world,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner){
        if(!ENABLED||!world.getLevel().dimension().equals(Level.OVERWORLD)||owner.getMinY()!=-512||owner.getHeight()!=1024
            ||owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return 0;
        ChunkAccess[] chunks=new ChunkAccess[9];chunks[4]=owner;int cx=owner.getPos().x(),cz=owner.getPos().z(),missing=0;
        for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++){
            if(dx==0&&dz==0)continue;int tile=(dz+1)*3+dx+1;
            if(cache!=null&&cache.contains(cx+dx,cz+dz)){
                GenerationChunkHolder h=cache.get(cx+dx,cz+dz);
                if(h!=null)chunks[tile]=h.getChunkIfPresent(ChunkStatus.FEATURES);
            }
            if(chunks[tile]==null)missing++;
        }
        return close(chunks,missing);
    }

    static int close(ChunkAccess[] chunks,int missing){
        if(chunks.length!=9||chunks[4]==null)throw new IllegalArgumentException("R3927 owner missing");
        ChunkAccess owner=chunks[4];int cx=owner.getPos().x(),cz=owner.getPos().z();
        byte[] cells=new byte[AREA*HEIGHT];BlockState[] original=new BlockState[256*HEIGHT];
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();int carvedEvidence=0,caveAirEvidence=0;

        for(int tile=0;tile<9;tile++){
            ChunkAccess chunk=chunks[tile];if(chunk==null)continue;
            if(chunk.getMinY()!=-512||chunk.getHeight()!=1024||chunk.getPos().x()!=cx+tile%3-1||chunk.getPos().z()!=cz+tile/3-1)
                throw new IllegalArgumentException("R3927 inconsistent witness chunk");
            BitSet protectedCells=NeverOverworldDryMinesR12.mask(chunk).envelope;
            CarvingMask carving=(chunk instanceof ProtoChunk proto)?proto.getCarvingMask():null;
            int bx=chunk.getPos().getMinBlockX(),bz=chunk.getPos().getMinBlockZ(),ox=tile%3*16,oz=tile/3*16;
            for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
                p.set(bx+x,y,bz+z);BlockState state=chunk.getBlockState(p);
                int layer=y-LOW,plane=(oz+z)*WIDTH+ox+x,index=layer*AREA+plane,local=(layer<<8)|(z<<4)|x;
                if(tile==4)original[local]=state;
                int maskIndex=((y-chunk.getMinY())<<8)|(z<<4)|x;
                if(protectedCells.get(maskIndex))cells[index]=OceanConnectivityR3927.PROTECTED;
                else if(state.is(Blocks.LAVA))cells[index]=OceanConnectivityR3927.LAVA;
                else if(aquatic(state))cells[index]=OceanConnectivityR3927.WATER;
                else if(state.isAir()){
                    boolean carved=carving!=null&&carving.get(bx+x,y,bz+z);
                    boolean caveAir=state.is(Blocks.CAVE_AIR);
                    if(carved||caveAir){cells[index]=OceanConnectivityR3927.CAVE;if(carved)carvedEvidence++;if(caveAir)caveAirEvidence++;}
                    else cells[index]=OceanConnectivityR3927.AIR;
                } else cells[index]=OceanConnectivityR3927.SOLID;
            }
        }

        OceanConnectivityR3927.Proof proof=OceanConnectivityR3927.solve(WIDTH,WIDTH,HEIGHT,cells);
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            int local=((y-LOW)<<8)|(z<<4)|x;p.set(bx+x,y,bz+z);
            if(owner.getBlockState(p)!=original[local])throw new IllegalStateException("R3927 owner changed during capture");
        }
        int changed=0,beforeAquatic=0,preservedAquatic=0;
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            int local=((y-LOW)<<8)|(z<<4)|x,index=(y-LOW)*AREA+(z+16)*WIDTH+x+16;
            p.set(bx+x,y,bz+z);BlockState before=original[local];
            if((cells[index]==OceanConnectivityR3927.AIR||cells[index]==OceanConnectivityR3927.CAVE)&&proof.flood().get(index)){
                owner.setBlockState(p,Blocks.WATER.defaultBlockState(),0);changed++;
            }
            if(aquatic(before)){beforeAquatic++;if(owner.getBlockState(p)==before)preservedAquatic++;}
        }
        if(beforeAquatic!=preservedAquatic)throw new IllegalStateException("R3927 existing aquatic state changed");
        if(!REPORT.isEmpty()){
            JsonObject r=new JsonObject();r.addProperty("revision",REVISION);r.addProperty("chunk_x",cx);r.addProperty("chunk_z",cz);
            r.addProperty("added_air_to_water",changed);r.addProperty("ocean_connected_air",proof.oceanConnected());
            r.addProperty("inferred_ocean_air",proof.inferredOcean());r.addProperty("dry_cave_air",proof.dryCave());
            r.addProperty("unresolved_air",proof.unresolvedAir());r.addProperty("carving_mask_evidence",carvedEvidence);
            r.addProperty("cave_air_evidence",caveAirEvidence);r.addProperty("missing_cache_chunks",missing);
            r.addProperty("read_max_y",HIGH);r.addProperty("reads_above_sea_level",0);
            try{Path d=Path.of(REPORT);Files.createDirectories(d);Files.writeString(d.resolve(cx+"_"+cz+"_"+IDS.incrementAndGet()+".json"),r+"\n",StandardOpenOption.CREATE_NEW);}
            catch(java.io.IOException e){throw new IllegalStateException("Cannot retain R3927 diagnostics",e);}
        }
        return changed;
    }

    private static boolean aquatic(BlockState s){
        return s.is(Blocks.WATER)||s.is(Blocks.BUBBLE_COLUMN)||s.is(Blocks.KELP)||s.is(Blocks.KELP_PLANT)||s.is(Blocks.SEAGRASS)||s.is(Blocks.TALL_SEAGRASS);
    }
}
