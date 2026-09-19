package net.minecraft.world.level.levelgen.placement;

import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.lighting.LevelLightEngine;

public final class NeverNetherFieldCleanupR15Smoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}

    private static ProtoChunk fixture(){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(2.0f).downfall(0)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var factory=new PalettedContainerFactory(
            Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),Blocks.NETHERRACK.defaultBlockState(),null,
            Strategy.createForBiomes(ids),holder,null,null);
        var c=new ProtoChunk(new ChunkPos(0,0),UpgradeData.EMPTY,LevelHeightAccessor.create(-128,656),factory,null);
        c.setLightEngine(LevelLightEngine.EMPTY);return c;
    }
    private static void set(ProtoChunk c,int x,int y,int z,Block block){
        c.getSection(c.getSectionIndex(y)).setBlockState(x&15,y&15,z&15,block.defaultBlockState(),false);
    }

    public static void main(String[] args){
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var c=fixture();

        set(c,8,100,8,Blocks.AIR);
        set(c,9,100,8,Blocks.CAVE_AIR);
        set(c,8,101,8,Blocks.AIR);

        for(int x=4;x<=8;x++)set(c,x,120,5,Blocks.AIR);
        set(c,0,140,8,Blocks.AIR);

        set(c,8,10,8,Blocks.LAVA);
        set(c,7,10,8,Blocks.LAVA);
        set(c,9,10,8,Blocks.LAVA);
        set(c,8,11,8,Blocks.LAVA);
        set(c,8,9,8,Blocks.CAVE_AIR);

        set(c,12,10,12,Blocks.LAVA);
        set(c,11,10,12,Blocks.LAVA);
        set(c,13,10,12,Blocks.LAVA);

        set(c,11,20,15,Blocks.LAVA);
        set(c,10,20,15,Blocks.LAVA);
        set(c,12,20,15,Blocks.LAVA);
        set(c,11,21,15,Blocks.LAVA);
        set(c,11,19,15,Blocks.CAVE_AIR);

        set(c,8,512,8,Blocks.BEDROCK);

        check(c.getBlockState(new BlockPos(8,100,8)).isAir(),"fixture air 1");
        check(c.getBlockState(new BlockPos(9,100,8)).isAir(),"fixture cave_air");
        check(c.getBlockState(new BlockPos(8,101,8)).isAir(),"fixture air 2");
        check(c.getBlockState(new BlockPos(4,120,5)).isAir(),"fixture 5-block cavity");
        check(c.getBlockState(new BlockPos(11,19,15)).isAir(),"fixture edge shelf support");

        var result=NeverNetherFieldCleanupR15.clean(c);
        check(result.microPocketBlocksFilled()==3,"micro pocket changed="+result.microPocketBlocksFilled());
        check(result.hangingLavaCellsSolidified()==2,"shelf changed="+result.hangingLavaCellsSolidified());
        var pocketA=c.getBlockState(new BlockPos(8,100,8));
        var pocketB=c.getBlockState(new BlockPos(9,100,8));
        var pocketC=c.getBlockState(new BlockPos(8,101,8));
        check(NeverNetherFieldCleanupR15.isNaturalRock(pocketA),"micro pocket fill state="+pocketA);
        check(NeverNetherFieldCleanupR15.isNaturalRock(pocketB),"micro cave_air fill state="+pocketB);
        check(NeverNetherFieldCleanupR15.isNaturalRock(pocketC),"micro vertical fill state="+pocketC);
        check(c.getBlockState(new BlockPos(4,120,5)).isAir(),"5-block cavity preserved");
        check(c.getBlockState(new BlockPos(0,140,8)).isAir(),"edge cavity preserved");
        var shelfA=c.getBlockState(new BlockPos(8,10,8));
        var shelfB=c.getBlockState(new BlockPos(11,20,15));
        check(NeverNetherFieldCleanupR15.isNaturalRock(shelfA),"hanging shelf solidified state="+shelfA);
        check(NeverNetherFieldCleanupR15.isNaturalRock(shelfB),"edge hanging shelf solidified state="+shelfB);
        check(c.getBlockState(new BlockPos(12,10,12)).is(Blocks.LAVA),"supported lava preserved");
        check(c.getBlockState(new BlockPos(8,512,8)).is(Blocks.BEDROCK),"roof untouched");
        check(NeverNetherFieldCleanupR15.sourceLava(Blocks.LAVA.defaultBlockState()),"source lava classifier");
        check(NeverNetherFieldCleanupR15.isNaturalRock(Blocks.BLACKSTONE.defaultBlockState()),"rock classifier");
        out.println("PASS NeverNetherFieldCleanupR15Smoke checks="+checks+" "+result);
    }
}
