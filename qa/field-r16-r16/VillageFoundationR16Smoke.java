package net.minecraft.world.level.levelgen.structure;

import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.chunk.*;

public final class VillageFoundationR16Smoke {
    private static int checks;private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    private static ProtoChunk fixture(){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(true).temperature(0f).downfall(.5f)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var factory=new PalettedContainerFactory(PalettedContainer.Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),
            Blocks.AIR.defaultBlockState(),null,PalettedContainer.Strategy.createForBiomes(ids),holder,null,null);
        return new ProtoChunk(new ChunkPos(0,0),UpgradeData.EMPTY,LevelHeightAccessor.create(-512,1024),factory,null);
    }
    private static void set(ProtoChunk c,int x,int y,int z,Block b){
        c.getSection(c.getSectionIndex(y)).setBlockState(x&15,y&15,z&15,b.defaultBlockState(),false);
    }
    public static void main(String[] args){
        final var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var c=fixture();var p=new BlockPos.MutableBlockPos();
        var box=new BoundingBox(2,140,2,4,150,4);

        set(c,2,140,2,Blocks.SNOW_BLOCK);
        set(c,2,142,2,Blocks.SPRUCE_PLANKS);
        set(c,2,135,2,Blocks.STONE);
        check(NeverOverworldVillageFoundationR16.placedFloorY(c,box,2,2,p)==140,
            "snow floor with village material above is accepted");
        check(NeverOverworldVillageFoundationR16.supportBelow(c,2,140,2,p)==135,
            "short unsupported gap finds natural support");

        var deep=fixture();set(deep,3,140,3,Blocks.SPRUCE_PLANKS);set(deep,3,120,3,Blocks.STONE);
        check(NeverOverworldVillageFoundationR16.supportBelow(deep,3,140,3,p)==Integer.MIN_VALUE,
            "deep ravine is not bridged");

        check(NeverOverworldVillageFoundationR16.isStructureEvidence(Blocks.SPRUCE_PLANKS.defaultBlockState()),
            "planks are structure evidence");
        check(!NeverOverworldVillageFoundationR16.isStructureEvidence(Blocks.SNOW_BLOCK.defaultBlockState()),
            "natural snow alone is not structure evidence");
        check(NeverOverworldVillageFoundationR16.gap(Blocks.SNOW.defaultBlockState()),
            "snow layer is a replaceable foundation gap");

        out.println("PASS VillageFoundationR16Smoke checks="+checks);
    }
}
