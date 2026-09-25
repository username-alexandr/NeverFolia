package net.minecraft.world.level.levelgen.structure;

import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.chunk.*;

public final class VillageFoundationSmoke {
    private static int checks;private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    private static ProtoChunk fixture(){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(.5f).downfall(0).generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY).specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);var factory=new PalettedContainerFactory(Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),Blocks.AIR.defaultBlockState(),null,Strategy.createForBiomes(ids),holder,null,null);return new ProtoChunk(new ChunkPos(0,0),UpgradeData.EMPTY,LevelHeightAccessor.create(-512,1024),factory,null);
    }
    private static void direct(ProtoChunk c,int x,int y,int z,net.minecraft.world.level.block.state.BlockState s){c.getSection(c.getSectionIndex(y)).setBlockState(x&15,y&15,z&15,s,false);}
    public static void main(String[] args){
        // Bootstrap redirects System.out; keep the original CI stream for the final result.
        final java.io.PrintStream out = System.out;
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();var c=fixture();var p=new BlockPos.MutableBlockPos();
        var near=new BoundingBox(0,126,0,4,142,4);direct(c,2,130,2,Blocks.OAK_PLANKS.defaultBlockState());direct(c,2,120,2,Blocks.STONE.defaultBlockState());
        check(NeverOverworldVillageReclamation.pieceOccupiesColumn(c,near,2,2,p),"actual piece column");
        check(!NeverOverworldVillageReclamation.pieceOccupiesColumn(c,near,3,3,p),"empty bbox column must not become slab");
        check(NeverOverworldVillageReclamation.findNaturalSupport(c,2,2,p)==120,"support y120");
        var noSupport=new BoundingBox(5,126,5,6,142,6);direct(c,5,130,5,Blocks.OAK_PLANKS.defaultBlockState());
        check(NeverOverworldVillageReclamation.findNaturalSupport(c,5,5,p)==Integer.MIN_VALUE,"no unconditional y80 fallback");
        var high=new BoundingBox(7,170,7,8,190,8);direct(c,7,175,7,Blocks.OAK_PLANKS.defaultBlockState());
        check(!NeverOverworldVillageReclamation.pieceOccupiesColumn(c,high,7,7,p),"high dry piece gets no y128 platform");
        check(NeverOverworldVillageReclamation.clippedMaxZ(14,15)==14,"piece maxZ inside chunk");
        check(NeverOverworldVillageReclamation.clippedMaxZ(40,15)==15,"piece maxZ clips to chunkMaxZ, not chunkMinZ");
        out.println("PASS VillageFoundationSmoke checks="+checks);
        out.flush();
        if (out.checkError()) throw new IllegalStateException("Failed to write village smoke result");
    }
}
