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
        var section=c.getSection(c.getSectionIndex(y));
        section.getStates().set(x&15,y&15,z&15,block.defaultBlockState());
        section.recalcBlockCounts();
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

        // Exact owning-chunk shape from persisted shelf [-3109,10,-6289]:
        // one same-chunk source-lava neighbour, one missing cross-chunk side,
        // two same-chunk natural-rock sides, source lava above and air below.
        set(c,11,20,15,Blocks.LAVA);
        set(c,10,20,15,Blocks.LAVA);
        set(c,11,21,15,Blocks.LAVA);
        set(c,11,19,15,Blocks.CAVE_AIR);

        set(c,8,512,8,Blocks.BEDROCK);

        check(c.getBlockState(new BlockPos(8,100,8)).isAir(),"fixture air 1");
        check(c.getBlockState(new BlockPos(9,100,8)).isAir(),"fixture cave_air");
        check(c.getBlockState(new BlockPos(8,101,8)).isAir(),"fixture air 2");
        check(c.getBlockState(new BlockPos(4,120,5)).isAir(),"fixture 5-block cavity");
        check(c.getBlockState(new BlockPos(11,19,15)).isAir(),"fixture edge shelf support");
        var roofBefore=c.getBlockState(new BlockPos(8,512,8));
        check(roofBefore.is(Blocks.BEDROCK),"fixture roof before cleanup state="+roofBefore);

        var result=NeverNetherFieldCleanupR15.clean(c);
        check(result.microPocketBlocksFilled()==3,"micro pocket changed="+result.microPocketBlocksFilled());
        check(result.hangingLavaCellsSolidified()==2,"shelf changed="+result.hangingLavaCellsSolidified());

        // Publish the immutable post-prepass substrate exactly where R10 would.
        for (var section : c.getSections()) {
            section.neverNetherR10Data=new NeverNetherSubstrateR10.SectionData(section.getStates().copy());
        }

        check(c.getBlockState(new BlockPos(4,120,5)).isAir(),"5-block cavity pre-pass start preserved");
        check(c.getBlockState(new BlockPos(8,120,5)).isAir(),"5-block cavity pre-pass end preserved");
        set(c,6,120,5,Blocks.NETHERRACK);
        int postChanged=NeverNetherFieldCleanupR15.fillMicroPocketsPublished(c);
        check(postChanged==4,"post-FEATURES fragmented cavity changed="+postChanged);
        check(NeverNetherFieldCleanupR15.isNaturalRock(c.getBlockState(new BlockPos(4,120,5))),"post fragment left fill");
        var postSection=c.getSection(c.getSectionIndex(120));
        int postIndex=((120&15)<<8)|((5&15)<<4)|(4&15);
        check(postSection.neverNetherR10Data.external.get(postIndex),"post fill must be recorded as external provenance");
        check(NeverNetherFieldCleanupR15.isNaturalRock(c.getBlockState(new BlockPos(5,120,5))),"post fragment left fill 2");
        check(NeverNetherFieldCleanupR15.isNaturalRock(c.getBlockState(new BlockPos(7,120,5))),"post fragment right fill");
        check(NeverNetherFieldCleanupR15.isNaturalRock(c.getBlockState(new BlockPos(8,120,5))),"post fragment right fill 2");
        var pocketA=c.getBlockState(new BlockPos(8,100,8));
        var pocketB=c.getBlockState(new BlockPos(9,100,8));
        var pocketC=c.getBlockState(new BlockPos(8,101,8));
        check(NeverNetherFieldCleanupR15.isNaturalRock(pocketA),"micro pocket fill state="+pocketA);
        check(NeverNetherFieldCleanupR15.isNaturalRock(pocketB),"micro cave_air fill state="+pocketB);
        check(NeverNetherFieldCleanupR15.isNaturalRock(pocketC),"micro vertical fill state="+pocketC);
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
