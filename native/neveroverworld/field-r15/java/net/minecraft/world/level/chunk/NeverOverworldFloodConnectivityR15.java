package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.tags.BlockTags;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/**
 * FIELD-R15 final flood audit.
 *
 * Scans every floodable component through Y=128, not only chunk-border
 * components. A dry cell is converted to water only when its own component
 * already contains verified surface-ocean water at Y=128. Underground water pockets
 * do not qualify as ocean seeds, so sealed caves/mineshafts stay dry. Lava-adjacent cells and dry-mine cells are hard
 * barriers.
 */
public final class NeverOverworldFloodConnectivityR15 {
    static final int SCAN_MIN_Y = -64;
    static final int SCAN_MAX_Y = 128;
    static final int DEEP_FLOW_MAX_Y = 96;
    static final int MIN_DEEP_APERTURE = 6;

    private NeverOverworldFloodConnectivityR15() {}

    public static int apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024) return 0;
        return floodVerifiedComponents(chunk);
    }

    public static int reconcileSeams(final WorldGenLevel level, final StaticCache2D<GenerationChunkHolder> cache, final ChunkAccess owner) {
        if (level == null || cache == null || owner == null) return 0;
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024) return 0;
        final int minY = Math.max(SCAN_MIN_Y, owner.getMinY() + 1);
        final int maxY = Math.min(SCAN_MAX_Y, owner.getMaxY() - 1);
        if (minY > maxY) return 0;

        final boolean[] externalSeeds = new boolean[(maxY - minY + 1) * 256];
        final ChunkPos cp = owner.getPos();
        final int west = seedFromNeighbor(cache, owner, cp.x() - 1, cp.z(), 0, 15, true, minY, maxY, externalSeeds);
        final int east = seedFromNeighbor(cache, owner, cp.x() + 1, cp.z(), 15, 0, true, minY, maxY, externalSeeds);
        final int north = seedFromNeighbor(cache, owner, cp.x(), cp.z() - 1, 0, 15, false, minY, maxY, externalSeeds);
        final int south = seedFromNeighbor(cache, owner, cp.x(), cp.z() + 1, 15, 0, false, minY, maxY, externalSeeds);
        final int seeded = west + east + north + south;

        // Always run the seam-capable owner pass. A component can be
        // ocean-connected through the owner's own Y=128 seed even when no
        // immediate neighbour contributes an external seed. Returning early
        // here produced one-sided WATER/AIR chunk walls.
        final int changed = floodVerifiedComponents(owner, externalSeeds, true);
        if (Boolean.getBoolean("neverfolia.debugFloodSeams")) {
            System.out.println(
                "[NeverFolia][R22Seam] chunk=" + cp.x() + "," + cp.z()
                + " seeds=" + west + "," + east + "," + north + "," + south
                + " total=" + seeded + " changed=" + changed
            );
        }
        return changed;
    }

    private static int seedFromNeighbor(
        final StaticCache2D<GenerationChunkHolder> cache,
        final ChunkAccess owner,
        final int neighborChunkX,
        final int neighborChunkZ,
        final int ownerEdge,
        final int neighborEdge,
        final boolean xAxis,
        final int minY,
        final int maxY,
        final boolean[] externalSeeds
    ) {
        if (!cache.contains(neighborChunkX, neighborChunkZ)) return 0;
        final GenerationChunkHolder holder = cache.get(neighborChunkX, neighborChunkZ);
        if (holder == null) return 0;
        final ChunkAccess neighbor = holder.getChunkIfPresent(ChunkStatus.FEATURES);
        if (neighbor == null) return 0;

        final boolean[] neighborOceanWater = oceanConnectedFloodable(neighbor, minY, maxY);
        final int ownerBaseX = owner.getPos().getMinBlockX();
        final int ownerBaseZ = owner.getPos().getMinBlockZ();
        final int neighborBaseX = neighbor.getPos().getMinBlockX();
        final int neighborBaseZ = neighbor.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos ownerPos = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos neighborPos = new BlockPos.MutableBlockPos();
        int seeded = 0;

        for (int y = minY; y < SCAN_MAX_Y; ++y) {
            for (int lateral = 0; lateral < 16; ++lateral) {
                final int ox = xAxis ? ownerEdge : lateral;
                final int oz = xAxis ? lateral : ownerEdge;
                final int nx = xAxis ? neighborEdge : lateral;
                final int nz = xAxis ? lateral : neighborEdge;
                final int ne = encode(nx, y, nz, minY);
                if (!neighborOceanWater[ne]) continue;

                ownerPos.set(ownerBaseX + ox, y, ownerBaseZ + oz);
                neighborPos.set(neighborBaseX + nx, y, neighborBaseZ + nz);
                if (!traversable(neighbor, neighborPos)) continue;
                if (!traversable(owner, ownerPos)) continue;
                if (y <= DEEP_FLOW_MAX_Y
                    && (!hydraulicOpen(neighbor, nx, y, nz) || !hydraulicOpen(owner, ox, y, oz))) continue;

                if (!owner.getBlockState(ownerPos).is(Blocks.WATER)) {
                    owner.setBlockState(ownerPos, Blocks.WATER.defaultBlockState(), 0);
                }
                final int oe = encode(ox, y, oz, minY);
                if (!externalSeeds[oe]) {
                    externalSeeds[oe] = true;
                    ++seeded;
                }
            }
        }
        return seeded;
    }

    static boolean[] oceanConnectedFloodable(final ChunkAccess chunk, final int minY, final int maxY) {
        final int capacity = (maxY - minY + 1) * 256;
        final boolean[] connected = new boolean[capacity];
        final int[] queue = new int[capacity];
        int head = 0, tail = 0;
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        for (int z = 0; z < 16; ++z) for (int x = 0; x < 16; ++x) {
            pos.set(baseX + x, SCAN_MAX_Y, baseZ + z);
            if (!chunk.getBlockState(pos).is(Blocks.WATER)) continue;
            final int e = encode(x, SCAN_MAX_Y, z, minY);
            connected[e] = true;
            queue[tail++] = e;
        }

        while (head < tail) {
            final int e = queue[head++];
            final int x = e & 15, z = (e >>> 4) & 15, y = minY + (e >>> 8);
            tail = enqueueFloodable(chunk, connected, queue, tail, x - 1, y, z, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x + 1, y, z, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x, y, z - 1, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x, y, z + 1, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x, y - 1, z, minY, maxY);
            tail = enqueueFloodable(chunk, connected, queue, tail, x, y + 1, z, minY, maxY);
        }
        return connected;
    }

    private static int enqueueFloodable(
        final ChunkAccess chunk, final boolean[] connected, final int[] queue, final int tailIn,
        final int x, final int y, final int z, final int minY, final int maxY
    ) {
        if (x < 0 || x > 15 || z < 0 || z > 15 || y < minY || y > maxY) return tailIn;
        final int e = encode(x, y, z, minY);
        if (connected[e]) return tailIn;
        final BlockPos pos = new BlockPos(chunk.getPos().getMinBlockX() + x, y, chunk.getPos().getMinBlockZ() + z);
        if (!traversable(chunk, pos)) return tailIn;
        if (y <= DEEP_FLOW_MAX_Y && !hydraulicOpen(chunk, x, y, z)) return tailIn;
        connected[e] = true;
        queue[tailIn] = e;
        return tailIn + 1;
    }

    static int floodVerifiedComponents(final ChunkAccess chunk) {
        return floodVerifiedComponents(chunk, null, false);
    }

    static int floodVerifiedComponents(final ChunkAccess chunk, final boolean[] externalSeeds, final boolean allowSeams) {
        final int minY=Math.max(SCAN_MIN_Y,chunk.getMinY()+1);
        final int maxY=Math.min(SCAN_MAX_Y,chunk.getMaxY()-1);
        final int layers=maxY-minY+1;
        if(layers<=0)return 0;
        final int capacity=layers*256;
        final boolean[] visited=new boolean[capacity];
        final int[] queue=new int[capacity];
        int changed=0;
        final ChunkPos cp=chunk.getPos();
        final int baseX=cp.getMinBlockX(),baseZ=cp.getMinBlockZ();
        final BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();

        for(int y=minY;y<=maxY;++y)for(int z=0;z<16;++z)for(int x=0;x<16;++x){
            final int seed=encode(x,y,z,minY);
            if(visited[seed])continue;
            pos.set(baseX+x,y,baseZ+z);
            if(!traversable(chunk,pos)
                || (y<=DEEP_FLOW_MAX_Y&&!hydraulicOpen(chunk,x,y,z))){visited[seed]=true;continue;}
            changed+=scan(chunk,visited,queue,x,y,z,minY,maxY,externalSeeds,allowSeams);
        }
        return changed;
    }

    private static int scan(ChunkAccess chunk,boolean[] visited,int[] queue,
                            int seedX,int seedY,int seedZ,int minY,int maxY,
                            boolean[] externalSeeds,boolean allowSeams){
        final int baseX=chunk.getPos().getMinBlockX(),baseZ=chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
        int head=0,tail=0;boolean hasOceanSeed=false,touchesHorizontalSeam=false;
        int boundaryCells=0,componentMinY=seedY,componentMaxY=seedY;
        int sampleSeamX=Integer.MIN_VALUE,sampleSeamY=Integer.MIN_VALUE,sampleSeamZ=Integer.MIN_VALUE;
        int seed=encode(seedX,seedY,seedZ,minY);visited[seed]=true;queue[tail++]=seed;
        while(head<tail){
            int e=queue[head++],x=e&15,z=(e>>>4)&15,y=minY+(e>>>8);
            componentMinY=Math.min(componentMinY,y);componentMaxY=Math.max(componentMaxY,y);
            pos.set(baseX+x,y,baseZ+z);
            if(y==SCAN_MAX_Y&&chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;
            if(externalSeeds!=null&&externalSeeds[e]&&chunk.getBlockState(pos).is(Blocks.WATER))hasOceanSeed=true;
            if(horizontalSeamBelowOcean(x,y,z)){
                touchesHorizontalSeam=true;++boundaryCells;
                if(sampleSeamX==Integer.MIN_VALUE){
                    sampleSeamX=baseX+x;sampleSeamY=y;sampleSeamZ=baseZ+z;
                }
            }
            tail=enqueue(chunk,visited,queue,tail,x-1,y,z,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x+1,y,z,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x,y,z-1,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x,y,z+1,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x,y-1,z,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x,y+1,z,minY,maxY);
        }
        if(!hasOceanSeed){
            if(allowSeams&&touchesHorizontalSeam&&tail>=64&&boundaryCells>=8
                &&Boolean.getBoolean("neverfolia.debugFloodSeams")){
                System.out.println(
                    "[NeverFolia][R22DrySeam] chunk="+chunk.getPos().x()+","+chunk.getPos().z()
                    +" size="+tail+" boundary="+boundaryCells
                    +" y="+componentMinY+":"+componentMaxY
                    +" sample="+sampleSeamX+","+sampleSeamY+","+sampleSeamZ
                );
            }
            return 0;
        }
        if(!allowSeams&&touchesHorizontalSeam)return 0;
        int changed=0;BlockState water=Blocks.WATER.defaultBlockState();
        for(int i=0;i<tail;++i){
            int e=queue[i],x=e&15,z=(e>>>4)&15,y=minY+(e>>>8);
            pos.set(baseX+x,y,baseZ+z);
            BlockState state=chunk.getBlockState(pos);
            if(!state.is(Blocks.WATER)&&traversable(chunk,pos)){chunk.setBlockState(pos,water,0);++changed;}
        }
        return changed;
    }

    private static int enqueue(ChunkAccess chunk,boolean[] visited,int[] queue,int tail,
                               int x,int y,int z,int minY,int maxY){
        if(x<0||x>15||z<0||z>15||y<minY||y>maxY)return tail;
        int e=encode(x,y,z,minY);if(visited[e])return tail;visited[e]=true;
        BlockPos pos=new BlockPos(chunk.getPos().getMinBlockX()+x,y,chunk.getPos().getMinBlockZ()+z);
        if(!traversable(chunk,pos))return tail;
        if(y<=DEEP_FLOW_MAX_Y&&!hydraulicOpen(chunk,x,y,z))return tail;
        queue[tail++]=e;return tail;
    }

    static boolean hydraulicOpen(ChunkAccess chunk,int localX,int y,int localZ){
        if(y>DEEP_FLOW_MAX_Y)return true;
        final int baseX=chunk.getPos().getMinBlockX(),baseZ=chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        int open=0;
        for(int dz=-1;dz<=1;++dz)for(int dx=-1;dx<=1;++dx){
            final int x=localX+dx,z=localZ+dz;
            if(x<0||x>15||z<0||z>15)continue;
            p.set(baseX+x,y,baseZ+z);
            if(traversable(chunk,p)&&++open>=MIN_DEEP_APERTURE)return true;
        }
        return false;
    }

    static boolean traversable(ChunkAccess chunk,BlockPos pos){
        if(NeverOverworldDryMinesR12.protectedCell(chunk,pos))return false;
        return isFloodable(chunk.getBlockState(pos))&&!hasAdjacentLava(chunk,pos);
    }

    static boolean hasAdjacentLava(ChunkAccess chunk,BlockPos pos){
        int minX=chunk.getPos().getMinBlockX(),minZ=chunk.getPos().getMinBlockZ();
        int[][] d={{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}};
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int[] v:d){
            int x=pos.getX()+v[0],y=pos.getY()+v[1],z=pos.getZ()+v[2];
            if(x<minX||x>minX+15||z<minZ||z>minZ+15||y<chunk.getMinY()||y>=chunk.getMaxY())continue;
            p.set(x,y,z);if(chunk.getBlockState(p).is(Blocks.LAVA))return true;
        }
        return false;
    }

    static boolean horizontalSeamBelowOcean(int x,int y,int z){
        return y<SCAN_MAX_Y&&(x==0||x==15||z==0||z==15);
    }

    static boolean isFloodable(BlockState state){
        return state.isAir()||state.is(Blocks.WATER)
            ||(state.getFluidState().isEmpty()&&state.canBeReplaced())
            ||state.is(BlockTags.RAILS)||state.is(Blocks.SUGAR_CANE)||state.is(Blocks.LILY_PAD)
            ||state.is(Blocks.MUSHROOM_STEM)||state.is(Blocks.RED_MUSHROOM_BLOCK)||state.is(Blocks.BROWN_MUSHROOM_BLOCK);
    }
    private static int encode(int x,int y,int z,int minY){return((y-minY)<<8)|(z<<4)|x;}
}
