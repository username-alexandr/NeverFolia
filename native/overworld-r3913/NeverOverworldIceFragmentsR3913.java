package net.minecraft.world.level.chunk;

import com.google.gson.JsonObject;
import java.nio.file.*;
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
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.StructureStart;

/** Bounded generation-only ice-remnant policy. A whole ice component must be
 * known inside its owner. Real structure piece envelopes, not whole columns,
 * remain protected. Missing referenced geometry causes a conservative skip.
 * No neighbour loads/writes; only already supplied holder metadata is read.
 */
public final class NeverOverworldIceFragmentsR3913 {
    public static final String REVISION="R3924-piece-scoped-deep-ice-v3-flat-boundary";
    private static final int LOW=-511,HIGH=128,COUNT=(HIGH-LOW+1)*256;
    private static final int SURFACE_BUFFER=16,MAX_COMPONENT=64;
    private static final boolean ENABLED=Boolean.getBoolean("neverfolia.r3913IceFragments");
    private static final String REPORT=System.getProperty("neverfolia.r3913IceReport","");
    private static final AtomicLong IDS=new AtomicLong();
    private NeverOverworldIceFragmentsR3913() {}
    public static boolean ice(BlockState s){return s.is(Blocks.ICE)||s.is(Blocks.PACKED_ICE)||s.is(Blocks.BLUE_ICE);}
    private static boolean aquatic(BlockState s){
        return s.is(Blocks.WATER)||s.is(Blocks.BUBBLE_COLUMN)||s.is(Blocks.KELP)
            ||s.is(Blocks.KELP_PLANT)||s.is(Blocks.SEAGRASS)||s.is(Blocks.TALL_SEAGRASS);
    }
    private static void paint(BitSet mask,BoundingBox box,ChunkAccess owner){
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        int x0=Math.max(bx,box.minX()-1),x1=Math.min(bx+15,box.maxX()+1);
        int z0=Math.max(bz,box.minZ()-1),z1=Math.min(bz+15,box.maxZ()+1);
        int y0=Math.max(LOW,box.minY()-1),y1=Math.min(HIGH,box.maxY()+1);
        if(x0>x1||z0>z1||y0>y1)return;
        for(int y=y0;y<=y1;y++)for(int z=z0;z<=z1;z++){
            int row=((y-LOW)<<8)|((z-bz)<<4);mask.set(row+x0-bx,row+x1-bx+1);
        }
    }
    private static boolean addStart(BitSet mask,StructureStart start,ChunkAccess owner){
        if(start==null||!start.isValid()||start.getPieces().isEmpty()||start.getPieces().size()>4096)return false;
        for(var piece:start.getPieces())paint(mask,piece.getBoundingBox(),owner);
        return true;
    }
    /** null means geometry was not resolved. It never means unprotected. */
    private static BitSet protection(StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner){
        BitSet result=new BitSet(COUNT);
        // Persisted mine mask uses chunk-minY indexing, one layer below LOW.
        BitSet mines=NeverOverworldDryMinesR12.mask(owner).envelope;
        for(int i=mines.nextSetBit(256);i>=0&&i<COUNT+256;i=mines.nextSetBit(i+1))result.set(i-256);
        for(var start:owner.getAllStarts().values()){
            if(start!=null&&start.isValid()&&!addStart(result,start,owner))return null;
        }
        for(var entry:owner.getAllReferences().entrySet()){
            var refs=entry.getValue();if(refs==null||refs.isEmpty())continue;
            var iterator=refs.iterator();
            while(iterator.hasNext()){
                long packed=iterator.nextLong();int cx=(int)packed,cz=(int)(packed>>>32);
                ChunkAccess source=null;
                if(cx==owner.getPos().x()&&cz==owner.getPos().z())source=owner;
                else if(cache!=null&&cache.contains(cx,cz)){
                    GenerationChunkHolder holder=cache.get(cx,cz);
                    if(holder!=null)source=holder.getChunkIfPresent(ChunkStatus.STRUCTURE_STARTS);
                }
                if(source==null||source.getPos().x()!=cx||source.getPos().z()!=cz)return null;
                if(!addStart(result,source.getAllStarts().get(entry.getKey()),owner))return null;
            }
        }
        return result;
    }
    private static ChunkAccess availableFeaturesChunk(StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner,int cx,int cz){
        if(cx==owner.getPos().x()&&cz==owner.getPos().z())return owner;
        if(cache==null||!cache.contains(cx,cz))return null;
        GenerationChunkHolder holder=cache.get(cx,cz);
        return holder==null?null:holder.getChunkIfPresent(ChunkStatus.FEATURES);
    }
    /** Proves only the owner writes of a deep, flat ice sheet. Neighbour chunks
     * are read-only evidence and may contain either the same ice sheet or
     * aquatic blocks if their owner already ran this cleanup. */
    private static boolean flatBoundaryContinuation(StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner,
        int[] component,int count,BitSet protectedCells){
        if(cache==null||count<=MAX_COMPONENT)return false;
        int y0=LOW+(component[0]>>>8);
        if(y0>=HIGH-SURFACE_BUFFER)return false;
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
        boolean crossed=false;
        for(int j=0;j<count;j++){
            int i=component[j],x=i&15,z=(i>>>4)&15,y=LOW+(i>>>8);
            if(y!=y0||protectedCells.get(i))return false;
            if(x==0){crossed=true;if(!boundaryAquaticOrIce(cache,owner,bx-1,y,bz+z,pos))return false;}
            if(x==15){crossed=true;if(!boundaryAquaticOrIce(cache,owner,bx+16,y,bz+z,pos))return false;}
            if(z==0){crossed=true;if(!boundaryAquaticOrIce(cache,owner,bx+x,y,bz-1,pos))return false;}
            if(z==15){crossed=true;if(!boundaryAquaticOrIce(cache,owner,bx+x,y,bz+16,pos))return false;}
        }
        return crossed;
    }
    private static boolean boundaryAquaticOrIce(StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner,
        int x,int y,int z,BlockPos.MutableBlockPos pos){
        int cx=Math.floorDiv(x,16),cz=Math.floorDiv(z,16);
        ChunkAccess neighbour=availableFeaturesChunk(cache,owner,cx,cz);
        if(neighbour==null||neighbour.getMinY()!=owner.getMinY()||neighbour.getHeight()!=owner.getHeight())return false;
        BlockState state=neighbour.getBlockState(pos.set(x,y,z));
        return aquatic(state)||ice(state);
    }
    public static int apply(WorldGenLevel level,ChunkAccess owner){return apply(level,null,owner);}
    public static int apply(WorldGenLevel level,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner){
        if(!ENABLED||!level.getLevel().dimension().equals(Level.OVERWORLD)
            ||owner.getMinY()!=-512||owner.getHeight()!=1024
            ||owner.getPersistedStatus().isOrAfter(ChunkStatus.LIGHT))return 0;
        boolean contains=false;
        for(LevelChunkSection section:owner.getSections())if(section.maybeHas(NeverOverworldIceFragmentsR3913::ice)){contains=true;break;}
        if(!contains)return 0;
        BitSet protectedCells=protection(cache,owner);
        if(protectedCells==null){record(owner,-1,0,0,0,0,0,true);return 0;}
        BlockState[] snapshot=new BlockState[COUNT];BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ(),iceCount=0;
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            int i=((y-LOW)<<8)|(z<<4)|x;snapshot[i]=owner.getBlockState(pos.set(bx+x,y,bz+z));
            if(ice(snapshot[i]))iceCount++;
        }
        if(iceCount==0)return 0;
        BitSet seen=new BitSet(COUNT),melt=new BitSet(COUNT);int[] queue=new int[iceCount];int retained=0,boundary=0,flatBoundaryMelted=0;
        for(int first=0;first<COUNT;first++){
            if(seen.get(first)||!ice(snapshot[first]))continue;
            int head=0,tail=1;queue[0]=first;seen.set(first);boolean intrinsicSafe=true,touchesBoundary=false;
            while(head<tail){
                int i=queue[head++],x=i&15,z=(i>>>4)&15,y=LOW+(i>>>8);
                if(y>=HIGH-SURFACE_BUFFER||protectedCells.get(i))intrinsicSafe=false;
                for(int face=0;face<6;face++){
                    int nx=x+(face==0?-1:face==1?1:0),nz=z+(face==2?-1:face==3?1:0),ny=y+(face==4?-1:face==5?1:0);
                    if(nx<0||nx>=16||nz<0||nz>=16||ny<LOW||ny>HIGH){touchesBoundary=true;continue;}
                    int n=((ny-LOW)<<8)|(nz<<4)|nx;BlockState next=snapshot[n];
                    if(ice(next)){if(!seen.get(n)){seen.set(n);queue[tail++]=n;}continue;}
                    if(!aquatic(next)&&!(face==5&&next.is(Blocks.MAGMA_BLOCK)))intrinsicSafe=false;
                }
            }
            boolean localSafe=intrinsicSafe&&!touchesBoundary&&tail<=MAX_COMPONENT;
            boolean flatBoundarySafe=intrinsicSafe&&touchesBoundary&&flatBoundaryContinuation(cache,owner,queue,tail,protectedCells);
            boolean safe=localSafe||flatBoundarySafe;
            if(flatBoundarySafe)flatBoundaryMelted++;
            if(safe){for(int j=0;j<tail;j++)melt.set(queue[j]);}else{retained++;if(touchesBoundary)boundary++;}
        }
        if(!melt.isEmpty()){
            BitSet now=protection(cache,owner);
            if(now==null||!now.equals(protectedCells))throw new IllegalStateException("R3913 structure protection changed before commit");
            for(int i=0;i<COUNT;i++){
                pos.set(bx+(i&15),LOW+(i>>>8),bz+((i>>>4)&15));
                if(owner.getBlockState(pos)!=snapshot[i])throw new IllegalStateException("R3913 owner snapshot changed before commit");
            }
            for(int i=melt.nextSetBit(0);i>=0;i=melt.nextSetBit(i+1)){
                pos.set(bx+(i&15),LOW+(i>>>8),bz+((i>>>4)&15));owner.setBlockState(pos,Blocks.WATER.defaultBlockState(),0);
            }
        }
        record(owner,iceCount,melt.cardinality(),retained,boundary,flatBoundaryMelted,protectedCells.cardinality(),false);return melt.cardinality();
    }
    private static void record(ChunkAccess chunk,int before,int changed,int retained,int boundary,int flatBoundaryMelted,int protectedCount,boolean unknown){
        if(REPORT.isEmpty())return;JsonObject r=new JsonObject();r.addProperty("revision",REVISION);
        r.addProperty("chunk_x",chunk.getPos().x());r.addProperty("chunk_z",chunk.getPos().z());
        r.addProperty("ice_before",before);r.addProperty("ice_to_source_water",changed);r.addProperty("retained_components",retained);
        r.addProperty("unknown_boundary_components",boundary);r.addProperty("flat_boundary_components_melted",flatBoundaryMelted);r.addProperty("protected_cells",protectedCount);r.addProperty("unresolved_structure_geometry",unknown);
        r.addProperty("max_component",MAX_COMPONENT);r.addProperty("surface_buffer",SURFACE_BUFFER);r.addProperty("all_ice_fixed",false);
        try{Path dir=Path.of(REPORT);Files.createDirectories(dir);Files.writeString(dir.resolve(chunk.getPos().x()+"_"+chunk.getPos().z()+"_"+IDS.incrementAndGet()+".json"),r+"\n",StandardOpenOption.CREATE_NEW);}
        catch(java.io.IOException e){throw new IllegalStateException("R3913 evidence write failed",e);}
    }
}
