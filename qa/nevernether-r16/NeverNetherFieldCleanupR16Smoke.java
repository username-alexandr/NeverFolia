package net.minecraft.world.level.levelgen.placement;

import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.lighting.LevelLightEngine;

public final class NeverNetherFieldCleanupR16Smoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    private static ProtoChunk fixture(){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(2f).downfall(0)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var factory=new PalettedContainerFactory(Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),
            Blocks.NETHERRACK.defaultBlockState(),null,Strategy.createForBiomes(ids),holder,null,null);
        var c=new ProtoChunk(new ChunkPos(0,0),UpgradeData.EMPTY,LevelHeightAccessor.create(-128,656),factory,null);
        c.setLightEngine(LevelLightEngine.EMPTY);return c;
    }
    private static void set(ProtoChunk c,int x,int y,int z,Block b){
        var s=c.getSection(c.getSectionIndex(y));s.getStates().set(x&15,y&15,z&15,b.defaultBlockState());s.recalcBlockCounts();
    }
    public static void main(String[] args)throws Exception{
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var c=fixture();
        // A genuine enclosed bubble inside source lava must become lava.
        for(int x=6;x<=12;x++)for(int y=8;y<=12;y++)for(int z=6;z<=10;z++)set(c,x,y,z,Blocks.LAVA);
        set(c,8,10,8,Blocks.AIR);set(c,9,10,8,Blocks.CAVE_AIR);set(c,10,10,8,Blocks.AIR);
        int changed=NeverNetherFieldCleanupR15.fillLavaOceanAirPockets(c,false);
        check(changed==3,"three-cell lava-ocean bubble filled: "+changed);
        check(c.getBlockState(new BlockPos(8,10,8)).is(Blocks.LAVA),"bubble cell became lava");

        // Rock cave with only a small lava contact remains a cave.
        var rock=fixture();
        for(int x=6;x<=10;x++)set(rock,x,5,8,Blocks.AIR);
        set(rock,5,5,8,Blocks.LAVA);
        check(NeverNetherFieldCleanupR15.fillLavaOceanAirPockets(rock,false)==0,"rock cave not mistaken for ocean bubble");
        check(rock.getBlockState(new BlockPos(8,5,8)).isAir(),"rock cave preserved");

        // Cross-chunk uncertainty is never guessed.
        var edge=fixture();set(edge,0,10,8,Blocks.AIR);
        set(edge,1,10,8,Blocks.LAVA);set(edge,0,9,8,Blocks.LAVA);set(edge,0,11,8,Blocks.LAVA);
        set(edge,0,10,7,Blocks.LAVA);set(edge,0,10,9,Blocks.LAVA);
        check(NeverNetherFieldCleanupR15.fillLavaOceanAirPockets(edge,false)==0,"chunk-edge bubble preserved");
        check(edge.getBlockState(new BlockPos(0,10,8)).isAir(),"edge air unchanged");

        // Above the lava-ocean contract is outside this repair.
        var high=fixture();set(high,8,40,8,Blocks.AIR);
        check(NeverNetherFieldCleanupR15.fillLavaOceanAirPockets(high,false)==0,"air above lava ocean untouched");
        check(NeverNetherFieldCleanupR15.NATIVE_PROFILE.equals("NN-R16-LAVA-OCEAN-CLEANUP-1"),"R16 native profile");
        out.println("PASS NeverNetherFieldCleanupR16Smoke checks="+checks);
    }
}
