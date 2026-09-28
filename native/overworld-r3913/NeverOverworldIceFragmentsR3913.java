package net.minecraft.world.level.chunk;

import com.google.gson.JsonObject;
import java.nio.file.*;
import java.util.BitSet;
import java.util.concurrent.atomic.AtomicLong;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/** Conservative generation-only removal of small deeply submerged ice remnants.
 * A whole component must be known inside the owner. Unknown chunk faces, air,
 * rock, structures, surface ice and large components are retained. No neighbour
 * access, no modification of magma, existing fluids or already generated chunks.
 * This is a bounded cleanup policy, NOT an assertion that all ice is erroneous.
 */
public final class NeverOverworldIceFragmentsR3913 {
    public static final String REVISION = "R3913-bounded-deep-ice-v1";
    private static final int LOW=-511, HIGH=128, COUNT=(HIGH-LOW+1)*256;
    private static final int SURFACE_BUFFER=16, MAX_COMPONENT=64;
    private static final boolean ENABLED=Boolean.getBoolean("neverfolia.r3913IceFragments");
    private static final String REPORT=System.getProperty("neverfolia.r3913IceReport","");
    private static final AtomicLong IDS=new AtomicLong();
    private NeverOverworldIceFragmentsR3913() {}
    public static boolean ice(BlockState s) {
        return s.is(Blocks.ICE)||s.is(Blocks.PACKED_ICE)||s.is(Blocks.BLUE_ICE);
    }
    private static boolean aquatic(BlockState s) {
        return s.is(Blocks.WATER)||s.is(Blocks.BUBBLE_COLUMN)||s.is(Blocks.KELP)
            ||s.is(Blocks.KELP_PLANT)||s.is(Blocks.SEAGRASS)||s.is(Blocks.TALL_SEAGRASS);
    }
    private static boolean structure(ChunkAccess chunk) {
        if(chunk.getAllStarts().values().stream().anyMatch(s->s!=null&&s.isValid()))return true;
        if(chunk.getAllReferences().values().stream().anyMatch(s->s!=null&&!s.isEmpty()))return true;
        // Preserve even persisted mines whose temporary mask has been released.
        return !NeverOverworldDryMinesR12.mask(chunk).envelope.isEmpty();
    }
    public static int apply(WorldGenLevel level, ChunkAccess owner) {
        if(!ENABLED||!level.getLevel().dimension().equals(Level.OVERWORLD)
            ||owner.getMinY()!=-512||owner.getHeight()!=1024
            ||owner.getPersistedStatus().isOrAfter(ChunkStatus.LIGHT))return 0;
        boolean contains=false;
        for(LevelChunkSection section:owner.getSections())if(section.maybeHas(NeverOverworldIceFragmentsR3913::ice)){contains=true;break;}
        if(!contains)return 0;
        if(structure(owner)){record(owner,0,0,0,0,true);return 0;}
        BlockState[] snapshot=new BlockState[COUNT];
        BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ(),iceCount=0;
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int i=((y-LOW)<<8)|(z<<4)|x;
            snapshot[i]=owner.getBlockState(pos.set(bx+x,y,bz+z));
            if(ice(snapshot[i]))iceCount++;
        }
        if(iceCount==0)return 0;
        BitSet seen=new BitSet(COUNT),melt=new BitSet(COUNT);
        int[] queue=new int[iceCount];int retained=0,boundary=0;
        for(int first=0;first<COUNT;first++) {
            if(seen.get(first)||!ice(snapshot[first]))continue;
            int head=0,tail=1;queue[0]=first;seen.set(first);boolean safe=true,touchesBoundary=false;
            while(head<tail) {
                int i=queue[head++],x=i&15,z=(i>>>4)&15,y=LOW+(i>>>8);
                if(y>=HIGH-SURFACE_BUFFER)safe=false;
                for(int face=0;face<6;face++) {
                    int nx=x+(face==0?-1:face==1?1:0),nz=z+(face==2?-1:face==3?1:0);
                    int ny=y+(face==4?-1:face==5?1:0);
                    if(nx<0||nx>=16||nz<0||nz>=16||ny<LOW||ny>HIGH){safe=false;touchesBoundary=true;continue;}
                    int n=((ny-LOW)<<8)|(nz<<4)|nx;BlockState next=snapshot[n];
                    if(ice(next)){if(!seen.get(n)){seen.set(n);queue[tail++]=n;}continue;}
                    // A magma cap does not make the ice beneath it inaccessible.
                    // Lava is NOT magma and is never accepted as an immersion face.
                    if(!aquatic(next)&&!(face==5&&next.is(Blocks.MAGMA_BLOCK)))safe=false;
                }
            }
            if(tail>MAX_COMPONENT)safe=false;
            if(safe){for(int j=0;j<tail;j++)melt.set(queue[j]);}
            else{retained++;if(touchesBoundary)boundary++;}
        }
        // No partial commit if any owner state changed during the calculation.
        if(!melt.isEmpty()) {
            if(structure(owner))throw new IllegalStateException("R3913 structure protection changed before commit");
            for(int i=0;i<COUNT;i++) {
                pos.set(bx+(i&15),LOW+(i>>>8),bz+((i>>>4)&15));
                if(owner.getBlockState(pos)!=snapshot[i])throw new IllegalStateException("R3913 owner snapshot changed before commit");
            }
            for(int i=melt.nextSetBit(0);i>=0;i=melt.nextSetBit(i+1)) {
                pos.set(bx+(i&15),LOW+(i>>>8),bz+((i>>>4)&15));
                owner.setBlockState(pos,Blocks.WATER.defaultBlockState(),0);
            }
        }
        record(owner,iceCount,melt.cardinality(),retained,boundary,false);
        return melt.cardinality();
    }
    private static void record(ChunkAccess chunk,int before,int changed,int retained,int boundary,boolean protectedChunk) {
        if(REPORT.isEmpty())return;
        JsonObject r=new JsonObject();r.addProperty("revision",REVISION);
        r.addProperty("chunk_x",chunk.getPos().x());r.addProperty("chunk_z",chunk.getPos().z());
        r.addProperty("ice_before",before);r.addProperty("ice_to_source_water",changed);
        r.addProperty("retained_components",retained);r.addProperty("unknown_boundary_components",boundary);
        r.addProperty("structure_chunk_skipped",protectedChunk);r.addProperty("max_component",MAX_COMPONENT);
        r.addProperty("surface_buffer",SURFACE_BUFFER);r.addProperty("all_ice_fixed",false);
        try{Path dir=Path.of(REPORT);Files.createDirectories(dir);Files.writeString(dir.resolve(chunk.getPos().x()+"_"+chunk.getPos().z()+"_"+IDS.incrementAndGet()+".json"),r+"\n",StandardOpenOption.CREATE_NEW);}
        catch(java.io.IOException e){throw new IllegalStateException("R3913 evidence write failed",e);}
    }
}
