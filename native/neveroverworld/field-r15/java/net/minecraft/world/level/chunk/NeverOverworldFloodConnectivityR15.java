package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.tags.BlockTags;
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
 * already contains verified water from the surface-ocean pass. Sealed caves and
 * mineshafts therefore stay dry. Lava-adjacent cells and dry-mine cells are hard
 * barriers.
 */
public final class NeverOverworldFloodConnectivityR15 {
    static final int SCAN_MIN_Y = -64;
    static final int SCAN_MAX_Y = 128;

    private NeverOverworldFloodConnectivityR15() {}

    public static int apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != -512 || level.getHeight() != 1024) return 0;
        return floodVerifiedComponents(chunk);
    }

    static int floodVerifiedComponents(final ChunkAccess chunk) {
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
            if(!traversable(chunk,pos)){visited[seed]=true;continue;}
            changed+=scan(chunk,visited,queue,x,y,z,minY,maxY);
        }
        return changed;
    }

    private static int scan(ChunkAccess chunk,boolean[] visited,int[] queue,
                            int seedX,int seedY,int seedZ,int minY,int maxY){
        final int baseX=chunk.getPos().getMinBlockX(),baseZ=chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos();
        int head=0,tail=0;boolean hasWater=false;
        int seed=encode(seedX,seedY,seedZ,minY);visited[seed]=true;queue[tail++]=seed;
        while(head<tail){
            int e=queue[head++],x=e&15,z=(e>>>4)&15,y=minY+(e>>>8);
            pos.set(baseX+x,y,baseZ+z);
            if(chunk.getBlockState(pos).is(Blocks.WATER))hasWater=true;
            tail=enqueue(chunk,visited,queue,tail,x-1,y,z,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x+1,y,z,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x,y,z-1,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x,y,z+1,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x,y-1,z,minY,maxY);
            tail=enqueue(chunk,visited,queue,tail,x,y+1,z,minY,maxY);
        }
        if(!hasWater)return 0;
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
        queue[tail++]=e;return tail;
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

    static boolean isFloodable(BlockState state){
        return state.isAir()||state.is(Blocks.WATER)
            ||(state.getFluidState().isEmpty()&&state.canBeReplaced())
            ||state.is(BlockTags.RAILS)||state.is(Blocks.SUGAR_CANE)||state.is(Blocks.LILY_PAD)
            ||state.is(Blocks.MUSHROOM_STEM)||state.is(Blocks.RED_MUSHROOM_BLOCK)||state.is(Blocks.BROWN_MUSHROOM_BLOCK);
    }
    private static int encode(int x,int y,int z,int minY){return((y-minY)<<8)|(z<<4)|x;}
}
