package net.minecraft.world.level.levelgen;

import java.util.Arrays;
import java.util.BitSet;
import java.util.LinkedHashMap;
import java.util.Map;
import net.minecraft.util.Mth;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;

/**
 * Replays the already-created NoiseChunk for the owner chunk.
 *
 * This does not regenerate a chunk or read neighbours. It uses the exact
 * interpolation/aquifer object that produced the NOISE stage, so WATER/AIR/
 * SOLID provenance can be checked after FEATURES without guessing from the
 * final BlockState.
 */
public final class NeverOverworldNoiseOracleR3927 {
    public static final byte SOLID=1,AIR=2,WATER=3,LAVA=4,OTHER_FLUID=5,UNKNOWN=6;

    public record Sample(boolean available,String reason,int minY,int maxY,byte[] cells,int cellWidth,int cellHeight) {
        public byte get(int localX,int y,int localZ) {
            if(!available||localX<0||localX>15||localZ<0||localZ>15||y<minY||y>maxY)return UNKNOWN;
            return cells[((y-minY)<<8)|(localZ<<4)|localX];
        }
    }

    private static final class MissingNoiseChunk extends RuntimeException {}
    private record CachedWater(int minY,int maxY,BitSet water) {}

    /**
     * Generation-lifetime fallback for chunks whose NoiseChunk has already
     * been discarded before a later LIGHT pass exposes them as an
     * ImposterProtoChunk. Only one bit per sampled block is retained:
     * "native NOISE/aquifer expected WATER".
     *
     * 512 entries cap the BitSet payload at roughly 10 MiB for the
     * NeverOverworld -511..128 range. Eviction is safe: strict mode then
     * refuses unresolved AIR instead of guessing.
     */
    private static final int CACHE_LIMIT=512;
    private static final Map<Long,CachedWater> WATER_CACHE=new LinkedHashMap<>(64,0.75f,true) {
        @Override protected boolean removeEldestEntry(Map.Entry<Long,CachedWater> eldest) {
            return size()>CACHE_LIMIT;
        }
    };

    private NeverOverworldNoiseOracleR3927() {}

    public static void prime(ChunkAccess chunk,int minY,int maxY) {
        if(cached(chunk,minY,maxY)!=null)return;
        Sample sample=compute(chunk,minY,maxY);
        if(!sample.available())
            throw new IllegalStateException("R3927 provenance prime failed: "+sample.reason());
    }

    public static Sample sample(ChunkAccess chunk,int minY,int maxY) {
        Sample cached=cached(chunk,minY,maxY);
        return cached!=null?cached:compute(chunk,minY,maxY);
    }

    private static Sample compute(ChunkAccess chunk,int minY,int maxY) {
        if(minY>maxY||minY<chunk.getMinY()||maxY>=chunk.getMaxY())
            return unavailable("range");
        final NoiseChunk noise;
        try {
            noise=chunk.getOrCreateNoiseChunk(ignored->{throw new MissingNoiseChunk();});
        } catch(MissingNoiseChunk missing) {
            return unavailable("missing_noise_chunk");
        }
        if(noise==null)return unavailable("null_noise_chunk");

        synchronized(noise) {
            boolean started=false;
            try {
                int cellWidth=noise.cellWidth(),cellHeight=noise.cellHeight();
                if(cellWidth<1||cellHeight<1||16%cellWidth!=0)
                    return unavailable("invalid_cell_geometry");
                int cellsXZ=16/cellWidth;
                int baseCellY=Mth.floorDiv(chunk.getMinY(),cellHeight);
                int minCell=Mth.floorDiv(minY,cellHeight)-baseCellY;
                int maxCell=Mth.floorDiv(maxY,cellHeight)-baseCellY;
                int totalCells=Mth.floorDiv(chunk.getHeight(),cellHeight);
                if(minCell<0||maxCell>=totalCells)return unavailable("cell_range");

                byte[] out=new byte[(maxY-minY+1)*256];
                int baseX=chunk.getPos().getMinBlockX(),baseZ=chunk.getPos().getMinBlockZ();
                noise.initializeForFirstCellX();started=true;

                for(int cellX=0;cellX<cellsXZ;cellX++) {
                    noise.advanceCellX(cellX);
                    for(int cellZ=0;cellZ<cellsXZ;cellZ++) {
                        for(int cellY=maxCell;cellY>=minCell;cellY--) {
                            noise.selectCellYZ(cellY,cellZ);
                            for(int inY=cellHeight-1;inY>=0;inY--) {
                                int y=(baseCellY+cellY)*cellHeight+inY;
                                double fy=(double)inY/cellHeight;
                                noise.updateForY(y,fy);
                                for(int inX=0;inX<cellWidth;inX++) {
                                    int worldX=baseX+cellX*cellWidth+inX;
                                    int localX=worldX-baseX;
                                    double fx=(double)inX/cellWidth;
                                    noise.updateForX(worldX,fx);
                                    for(int inZ=0;inZ<cellWidth;inZ++) {
                                        int worldZ=baseZ+cellZ*cellWidth+inZ;
                                        int localZ=worldZ-baseZ;
                                        double fz=(double)inZ/cellWidth;
                                        noise.updateForZ(worldZ,fz);
                                        BlockState state=noise.getInterpolatedState();
                                        if(y>=minY&&y<=maxY)
                                            out[((y-minY)<<8)|(localZ<<4)|localX]=classify(state);
                                    }
                                }
                            }
                        }
                    }
                    noise.swapSlices();
                }
                remember(chunk,minY,maxY,out);
                return new Sample(true,"ok",minY,maxY,out,cellWidth,cellHeight);
            } catch(RuntimeException failure) {
                return unavailable("replay_"+failure.getClass().getSimpleName());
            } finally {
                if(started) {
                    try { noise.stopInterpolation(); }
                    catch(RuntimeException ignored) {}
                }
            }
        }
    }

    private static void remember(ChunkAccess chunk,int minY,int maxY,byte[] cells) {
        BitSet water=new BitSet(cells.length);
        for(int i=0;i<cells.length;i++)if(cells[i]==WATER)water.set(i);
        synchronized(WATER_CACHE) {
            WATER_CACHE.put(chunk.getPos().longKey(),new CachedWater(minY,maxY,water));
        }
    }

    private static Sample cached(ChunkAccess chunk,int minY,int maxY) {
        final CachedWater cached;
        synchronized(WATER_CACHE) {
            cached=WATER_CACHE.get(chunk.getPos().longKey());
        }
        if(cached==null||cached.minY()!=minY||cached.maxY()!=maxY)return null;
        byte[] cells=new byte[(maxY-minY+1)*256];
        Arrays.fill(cells,SOLID);
        for(int i=cached.water().nextSetBit(0);i>=0;i=cached.water().nextSetBit(i+1))cells[i]=WATER;
        return new Sample(true,"cached_water_origin",minY,maxY,cells,0,0);
    }

    private static byte classify(BlockState state) {
        if(state==null)return SOLID; // NoiseBasedChunkGenerator substitutes default_block.
        if(state.isAir())return AIR;
        if(state.is(Blocks.WATER))return WATER;
        if(state.is(Blocks.LAVA))return LAVA;
        if(!state.getFluidState().isEmpty())return OTHER_FLUID;
        return SOLID;
    }

    private static Sample unavailable(String reason) {
        return new Sample(false,reason,0,-1,new byte[0],0,0);
    }
}
