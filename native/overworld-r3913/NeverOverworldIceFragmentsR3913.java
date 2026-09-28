package net.minecraft.world.level.chunk;

import com.google.gson.JsonObject;
import java.nio.file.*;
import java.util.BitSet;
import java.util.concurrent.atomic.AtomicLong;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.StructureStart;

/** Generation-only, bounded ice cleanup. Resolve existing structure references
 * from the supplied cache; never load neighbours. Protect individual piece
 * envelopes. Incomplete reference data retains the whole owner conservatively.
 * This is not global ice removal and does not repair saved LIGHT/FULL chunks.
 */
public final class NeverOverworldIceFragmentsR3913 {
    public static final String REVISION = "R3914-piece-aware-deep-ice-v1";
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
    private static void paint(BitSet target, BoundingBox box, ChunkAccess owner) {
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        int x0=Math.max(bx,box.minX()),x1=Math.min(bx+15,box.maxX());
        int z0=Math.max(bz,box.minZ()),z1=Math.min(bz+15,box.maxZ());
        int y0=Math.max(LOW,box.minY()),y1=Math.min(HIGH,box.maxY());
        if(x0>x1||z0>z1||y0>y1)return;
        for(int y=y0;y<=y1;y++)for(int z=z0;z<=z1;z++) {
            int row=((y-LOW)<<8)|((z-bz)<<4);
            target.set(row+x0-bx,row+x1-bx+1);
        }
    }
    private static boolean include(BitSet mask, StructureStart start, ChunkAccess owner) {
        if(start==null||!start.isValid()||start.getPieces().isEmpty())return false;
        for(var piece:start.getPieces())paint(mask,piece.getBoundingBox().inflatedBy(1),owner);
        return true;
    }
    /** null means unproven protection, not an empty structure mask. */
    private static BitSet protection(StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner) {
        BitSet mask=new BitSet(COUNT);
        // The persisted dry mask indexes from -512, whereas this scan starts -511.
        BitSet dry=NeverOverworldDryMinesR12.mask(owner).envelope;
        for(int i=dry.nextSetBit(256);i>=256&&i<COUNT+256;i=dry.nextSetBit(i+1))mask.set(i-256);
        for(var start:owner.getAllStarts().values()) {
            if(start!=null&&start.isValid()&&!include(mask,start,owner))return null;
        }
        for(var entry:owner.getAllReferences().entrySet()) {
            if(entry.getValue()==null||entry.getValue().isEmpty())continue;
            for(long packed:entry.getValue()) {
                ChunkPos at=new ChunkPos((int)packed,(int)(packed >>> 32));ChunkAccess source=null;
                if(at.equals(owner.getPos()))source=owner;
                else if(cache!=null&&cache.contains(at.x(),at.z())) {
                    GenerationChunkHolder holder=cache.get(at.x(),at.z());
                    if(holder!=null)source=holder.getChunkIfPresent(ChunkStatus.STRUCTURE_STARTS);
                }
                if(source==null)return null;
                StructureStart start=source.getAllStarts().get(entry.getKey());
                if(!include(mask,start,owner))return null;
            }
        }
        return mask;
    }
    public static int apply(WorldGenLevel level,ChunkAccess owner) { return apply(level,null,owner); }
    public static int apply(WorldGenLevel level,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner) {
        if(!ENABLED||!level.getLevel().dimension().equals(Level.OVERWORLD)
            ||owner.getMinY()!=-512||owner.getHeight()!=1024
            ||owner.getPersistedStatus().isOrAfter(ChunkStatus.LIGHT))return 0;
        boolean contains=false;
        for(LevelChunkSection section:owner.getSections())if(section.maybeHas(NeverOverworldIceFragmentsR3913::ice)){contains=true;break;}
        if(!contains)return 0;
        BitSet protectedCells=protection(cache,owner);
        if(protectedCells==null){record(owner,0,0,0,0,true,0);return 0;}
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
                if(y>=HIGH-SURFACE_BUFFER||protectedCells.get(i))safe=false;
                for(int face=0;face<6;face++) {
                    int nx=x+(face==0?-1:face==1?1:0),nz=z+(face==2?-1:face==3?1:0);
                    int ny=y+(face==4?-1:face==5?1:0);
                    if(nx<0||nx>=16||nz<0||nz>=16||ny<LOW||ny>HIGH){safe=false;touchesBoundary=true;continue;}
                    int n=((ny-LOW)<<8)|(nz<<4)|nx;BlockState next=snapshot[n];
                    if(protectedCells.get(n))safe=false;
                    if(ice(next)){if(!seen.get(n)){seen.set(n);queue[tail++]=n;}continue;}
                    if(!aquatic(next)&&!(face==5&&next.is(Blocks.MAGMA_BLOCK)))safe=false;
                }
            }
            if(tail>MAX_COMPONENT)safe=false;
            if(safe){for(int j=0;j<tail;j++)melt.set(queue[j]);}
            else{retained++;if(touchesBoundary)boundary++;}
        }
        if(!melt.isEmpty()) {
            BitSet currentProtection=protection(cache,owner);
            if(currentProtection==null||!currentProtection.equals(protectedCells))
                throw new IllegalStateException("R3914 structure protection changed before commit");
            for(int i=0;i<COUNT;i++) {
                pos.set(bx+(i&15),LOW+(i>>>8),bz+((i>>>4)&15));
                if(owner.getBlockState(pos)!=snapshot[i])throw new IllegalStateException("R3914 owner snapshot changed before commit");
            }
            for(int i=melt.nextSetBit(0);i>=0;i=melt.nextSetBit(i+1)) {
                pos.set(bx+(i&15),LOW+(i>>>8),bz+((i>>>4)&15));
                owner.setBlockState(pos,Blocks.WATER.defaultBlockState(),0);
            }
        }
        record(owner,iceCount,melt.cardinality(),retained,boundary,false,protectedCells.cardinality());
        return melt.cardinality();
    }
    private static void record(ChunkAccess chunk,int before,int changed,int retained,int boundary,boolean unresolved,int protectedCells) {
        if(REPORT.isEmpty())return;
        JsonObject r=new JsonObject();r.addProperty("revision",REVISION);
        r.addProperty("chunk_x",chunk.getPos().x());r.addProperty("chunk_z",chunk.getPos().z());
        r.addProperty("ice_before",before);r.addProperty("ice_to_source_water",changed);
        r.addProperty("retained_components",retained);r.addProperty("unknown_boundary_components",boundary);
        r.addProperty("structure_chunk_skipped",unresolved);r.addProperty("protection_unresolved",unresolved);
        r.addProperty("protected_cells",protectedCells);r.addProperty("max_component",MAX_COMPONENT);
        r.addProperty("surface_buffer",SURFACE_BUFFER);r.addProperty("all_ice_fixed",false);
        try{Path dir=Path.of(REPORT);Files.createDirectories(dir);Files.writeString(dir.resolve(chunk.getPos().x()+"_"+chunk.getPos().z()+"_"+IDS.incrementAndGet()+".json"),r+"\n",StandardOpenOption.CREATE_NEW);}
        catch(java.io.IOException e){throw new IllegalStateException("R3914 evidence write failed",e);}
    }
}
