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
    public static final String REVISION="R3913-piece-scoped-deep-ice-v2";
    private static final int LOW=-511,HIGH=128,COUNT=(HIGH-LOW+1)*256;
    private static final int SURFACE_BUFFER=16,MAX_COMPONENT=64;
    private static final int DIAG_X=-3022,DIAG_Y=62,DIAG_Z=-3564;
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
    public static int apply(WorldGenLevel level,ChunkAccess owner){return apply(level,null,owner);}
    public static int apply(WorldGenLevel level,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner){
        if(!ENABLED||!level.getLevel().dimension().equals(Level.OVERWORLD)
            ||owner.getMinY()!=-512||owner.getHeight()!=1024
            ||owner.getPersistedStatus().isOrAfter(ChunkStatus.LIGHT))return 0;
        boolean contains=false;
        for(LevelChunkSection section:owner.getSections())if(section.maybeHas(NeverOverworldIceFragmentsR3913::ice)){contains=true;break;}
        if(!contains)return 0;
        BitSet protectedCells=protection(cache,owner);
        if(protectedCells==null){record(owner,-1,0,0,0,0,true);return 0;}
        BlockState[] snapshot=new BlockState[COUNT];BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ(),iceCount=0;
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            int i=((y-LOW)<<8)|(z<<4)|x;snapshot[i]=owner.getBlockState(pos.set(bx+x,y,bz+z));
            if(ice(snapshot[i]))iceCount++;
        }
        if(iceCount==0)return 0;
        BitSet seen=new BitSet(COUNT),melt=new BitSet(COUNT);int[] queue=new int[iceCount];int retained=0,boundary=0;
        final boolean diagChunk=Math.floorDiv(DIAG_X,16)==owner.getPos().x()&&Math.floorDiv(DIAG_Z,16)==owner.getPos().z();
        final int diagIndex=diagChunk?((DIAG_Y-LOW)<<8)|(Math.floorMod(DIAG_Z,16)<<4)|Math.floorMod(DIAG_X,16):-1;
        for(int first=0;first<COUNT;first++){
            if(seen.get(first)||!ice(snapshot[first]))continue;
            int head=0,tail=1;queue[0]=first;seen.set(first);boolean safe=true,touchesBoundary=false,targetComponent=false;
            int protectedHits=0,nonAquaticFaces=0,boundaryFaces=0,minComponentY=Integer.MAX_VALUE,maxComponentY=Integer.MIN_VALUE;
            String firstBlocker="";
            while(head<tail){
                int i=queue[head++],x=i&15,z=(i>>>4)&15,y=LOW+(i>>>8);
                if(i==diagIndex)targetComponent=true;
                minComponentY=Math.min(minComponentY,y);maxComponentY=Math.max(maxComponentY,y);
                if(y>=HIGH-SURFACE_BUFFER)safe=false;
                if(protectedCells.get(i)){safe=false;protectedHits++;}
                for(int face=0;face<6;face++){
                    int nx=x+(face==0?-1:face==1?1:0),nz=z+(face==2?-1:face==3?1:0),ny=y+(face==4?-1:face==5?1:0);
                    if(nx<0||nx>=16||nz<0||nz>=16||ny<LOW||ny>HIGH){safe=false;touchesBoundary=true;boundaryFaces++;continue;}
                    int n=((ny-LOW)<<8)|(nz<<4)|nx;BlockState next=snapshot[n];
                    if(ice(next)){if(!seen.get(n)){seen.set(n);queue[tail++]=n;}continue;}
                    if(!aquatic(next)&&!(face==5&&next.is(Blocks.MAGMA_BLOCK))){
                        safe=false;nonAquaticFaces++;
                        if(firstBlocker.isEmpty())firstBlocker=(bx+nx)+","+ny+","+(bz+nz)+":"+next;
                    }
                }
            }
            boolean oversized=tail>MAX_COMPONENT;if(oversized)safe=false;
            if(targetComponent)recordTarget(owner,tail,protectedHits,protectedCells.get(diagIndex),touchesBoundary,boundaryFaces,
                nonAquaticFaces,oversized,minComponentY,maxComponentY,firstBlocker,safe);
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
        record(owner,iceCount,melt.cardinality(),retained,boundary,protectedCells.cardinality(),false);return melt.cardinality();
    }
    private static void recordTarget(ChunkAccess chunk,int size,int protectedHits,boolean targetProtected,boolean touchesBoundary,
        int boundaryFaces,int nonAquaticFaces,boolean oversized,int minY,int maxY,String firstBlocker,boolean safe){
        if(REPORT.isEmpty())return;
        JsonObject r=new JsonObject();r.addProperty("revision",REVISION);r.addProperty("diagnostic","R3924-target-ice-component");
        r.addProperty("target_x",DIAG_X);r.addProperty("target_y",DIAG_Y);r.addProperty("target_z",DIAG_Z);
        r.addProperty("chunk_x",chunk.getPos().x());r.addProperty("chunk_z",chunk.getPos().z());r.addProperty("component_size",size);
        r.addProperty("protected_hits",protectedHits);r.addProperty("target_protected",targetProtected);
        r.addProperty("touches_chunk_boundary",touchesBoundary);r.addProperty("boundary_faces",boundaryFaces);
        r.addProperty("non_aquatic_faces",nonAquaticFaces);r.addProperty("oversized",oversized);
        r.addProperty("min_y",minY);r.addProperty("max_y",maxY);r.addProperty("first_blocker",firstBlocker);
        r.addProperty("safe_to_melt",safe);
        try{Path dir=Path.of(REPORT);Files.createDirectories(dir);Files.writeString(dir.resolve("target_component_"+chunk.getPos().x()+"_"+chunk.getPos().z()+".json"),r+"\n",StandardOpenOption.CREATE_NEW);}
        catch(java.io.IOException e){throw new IllegalStateException("R3913 target diagnostic write failed",e);}
    }
    private static void record(ChunkAccess chunk,int before,int changed,int retained,int boundary,int protectedCount,boolean unknown){
        if(REPORT.isEmpty())return;JsonObject r=new JsonObject();r.addProperty("revision",REVISION);
        r.addProperty("chunk_x",chunk.getPos().x());r.addProperty("chunk_z",chunk.getPos().z());
        r.addProperty("ice_before",before);r.addProperty("ice_to_source_water",changed);r.addProperty("retained_components",retained);
        r.addProperty("unknown_boundary_components",boundary);r.addProperty("protected_cells",protectedCount);r.addProperty("unresolved_structure_geometry",unknown);
        r.addProperty("max_component",MAX_COMPONENT);r.addProperty("surface_buffer",SURFACE_BUFFER);r.addProperty("all_ice_fixed",false);
        try{Path dir=Path.of(REPORT);Files.createDirectories(dir);Files.writeString(dir.resolve(chunk.getPos().x()+"_"+chunk.getPos().z()+"_"+IDS.incrementAndGet()+".json"),r+"\n",StandardOpenOption.CREATE_NEW);}
        catch(java.io.IOException e){throw new IllegalStateException("R3913 evidence write failed",e);}
    }
}
