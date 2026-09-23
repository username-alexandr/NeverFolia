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
    static boolean heightPlant(BlockState s){
        return s.is(Blocks.CACTUS)
            || s.is(Blocks.MELON)
            || s.is(Blocks.BAMBOO)
            || s.is(Blocks.BAMBOO_SAPLING)
            || s.is(Blocks.COCOA)
            || s.is(Blocks.DANDELION)
            || s.is(Blocks.POPPY)
            || s.is(Blocks.BLUE_ORCHID)
            || s.is(Blocks.ALLIUM)
            || s.is(Blocks.AZURE_BLUET)
            || s.is(Blocks.RED_TULIP)
            || s.is(Blocks.ORANGE_TULIP)
            || s.is(Blocks.WHITE_TULIP)
            || s.is(Blocks.PINK_TULIP)
            || s.is(Blocks.OXEYE_DAISY)
            || s.is(Blocks.CORNFLOWER)
            || s.is(Blocks.LILY_OF_THE_VALLEY)
            || s.is(Blocks.WITHER_ROSE)
            || s.is(Blocks.TORCHFLOWER)
            || s.is(Blocks.PITCHER_PLANT)
            || s.is(Blocks.PINK_PETALS)
            || s.is(Blocks.WILDFLOWERS)
            || s.is(Blocks.CACTUS_FLOWER)
            || s.is(Blocks.CLOSED_EYEBLOSSOM)
            || s.is(Blocks.OPEN_EYEBLOSSOM)
            || s.is(Blocks.SUNFLOWER)
            || s.is(Blocks.LILAC)
            || s.is(Blocks.ROSE_BUSH)
            || s.is(Blocks.PEONY);
    }

    public static boolean allowSimpleBlock(WorldGenLevel level,BlockPos origin,BlockState state){
        return !scope(level)||!heightPlant(state)||origin.getY()>OCEAN_Y;
    }

    public static boolean allowOceanHeightOrigin(WorldGenLevel level,BlockPos origin){
        return !scope(level)||origin.getY()>OCEAN_Y;
    }

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
                final boolean waterContact=y<=OCEAN_Y&&touchesWater(chunk,pos,probe);
                final boolean seamCandidate=y<=OCEAN_Y&&floodedCavePlant(s)&&horizontalChunkEdge(chunk,pos);
                if(!shouldRemove(s,y,waterContact||seamCandidate))continue;
                chunk.setBlockState(pos,replacementAfterRemoval(waterContact),0);++changed;
            }
        }
        return changed;
    }

    static boolean shouldRemove(BlockState state,int y,boolean waterContact){
        return heightPlant(state)&&y<=OCEAN_Y
            || floodedCavePlant(state)&&y<=OCEAN_Y&&waterContact;
    }

    static BlockState replacementAfterRemoval(boolean waterContact){
        return waterContact ? Blocks.WATER.defaultBlockState() : Blocks.AIR.defaultBlockState();
    }

    static boolean horizontalChunkEdge(ChunkAccess chunk,BlockPos pos){
        final int minX=chunk.getPos().getMinBlockX(),minZ=chunk.getPos().getMinBlockZ();
        return pos.getX()==minX||pos.getX()==minX+15||pos.getZ()==minZ||pos.getZ()==minZ+15;
    }

    private static boolean touchesWater(ChunkAccess chunk,BlockPos pos,BlockPos.MutableBlockPos probe){
        if(chunk.getBlockState(pos).getFluidState().is(FluidTags.WATER))return true;
        int minX=chunk.getPos().getMinBlockX(),minZ=chunk.getPos().getMinBlockZ();
        int[][] d={{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}};
        for(int[] v:d){
            int x=pos.getX()+v[0],y=pos.getY()+v[1],z=pos.getZ()+v[2];
            if(x<minX||x>minX+15||z<minZ||z>minZ+15||y<chunk.getMinY()||y>=chunk.getMaxY())continue;
            probe.set(x,y,z);
            if(chunk.getBlockState(probe).getFluidState().is(FluidTags.WATER))return true;
        }
        return false;
    }
}
}
