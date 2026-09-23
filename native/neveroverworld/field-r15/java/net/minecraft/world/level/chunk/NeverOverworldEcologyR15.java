package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/** FIELD-R15 final ecology cleanup for the Y=128 flooded Overworld. */
public final class NeverOverworldEcologyR15 {
    static final int OCEAN_Y=128;
    private NeverOverworldEcologyR15(){}

    private static boolean scope(WorldGenLevel level){
        return level.getLevel().dimension().equals(Level.OVERWORLD)&&level.getMinY()==-512&&level.getHeight()==1024;
    }

    static boolean floodedCavePlant(BlockState s){
        return s.is(Blocks.CAVE_VINES)||s.is(Blocks.CAVE_VINES_PLANT)
            ||s.is(Blocks.AZALEA)||s.is(Blocks.FLOWERING_AZALEA)
            ||s.is(Blocks.SMALL_DRIPLEAF)||s.is(Blocks.BIG_DRIPLEAF);
    }
    static boolean heightPlant(BlockState s){return s.is(Blocks.CACTUS)||s.is(Blocks.MELON);}

    public static int cleanup(WorldGenLevel level,ChunkAccess chunk){
        if(!scope(level)||chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return 0;
        int changed=0;int baseX=chunk.getPos().getMinBlockX(),baseZ=chunk.getPos().getMinBlockZ();
        BlockPos.MutableBlockPos pos=new BlockPos.MutableBlockPos(),probe=new BlockPos.MutableBlockPos();
        for(int sy=chunk.getMinSectionY();sy<=chunk.getMaxSectionY();++sy){
            int idx=chunk.getSectionIndexFromSectionY(sy);
            if(idx<0||idx>=chunk.getSections().length)continue;
            LevelChunkSection section=chunk.getSections()[idx];
            if(!section.maybeHas(s->floodedCavePlant(s)||heightPlant(s)))continue;
            int by=sy<<4;
            for(int ly=0;ly<16;++ly)for(int z=0;z<16;++z)for(int x=0;x<16;++x){
                BlockState s=section.getBlockState(x,ly,z);
                if(!floodedCavePlant(s)&&!heightPlant(s))continue;
                int y=by+ly;pos.set(baseX+x,y,baseZ+z);
                final boolean waterContact=floodedCavePlant(s)&&touchesWater(chunk,pos,probe);
                if(!shouldRemove(s,y,waterContact))continue;
                chunk.setBlockState(pos,Blocks.AIR.defaultBlockState(),0);++changed;
            }
        }
        return changed;
    }

    static boolean shouldRemove(BlockState state,int y,boolean waterContact){
        return heightPlant(state)&&y<=OCEAN_Y
            || floodedCavePlant(state)&&y<=OCEAN_Y&&waterContact;
    }

    private static boolean touchesWater(ChunkAccess chunk,BlockPos pos,BlockPos.MutableBlockPos probe){
        if(chunk.getBlockState(pos).getFluidState().is(FluidTags.WATER))return true;
        int minX=chunk.getPos().getMinBlockX(),minZ=chunk.getPos().getMinBlockZ();
        int[][] d={{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}};
        for(int[] v:d){
            int x=pos.getX()+v[0],y=pos.getY()+v[1],z=pos.getZ()+v[2];
            if(x<minX||x>minX+15||z<minZ||z>minZ+15||y<chunk.getMinY()||y>=chunk.getMaxY())continue;
            probe.set(x,y,z);if(chunk.getBlockState(probe).getFluidState().is(FluidTags.WATER))return true;
        }
        return false;
    }
}
