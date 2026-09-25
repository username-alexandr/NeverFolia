package net.minecraft.world.level.chunk;

import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.IdMapper;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.LevelHeightAccessor;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.biome.BiomeGenerationSettings;
import net.minecraft.world.level.biome.BiomeSpecialEffects;
import net.minecraft.world.level.biome.MobSpawnSettings;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.lighting.LevelLightEngine;

public final class FloodConnectivityR14Smoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}

    private static ProtoChunk fixture(){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(0.8f).downfall(0.4f)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var factory=new PalettedContainerFactory(Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),
            Blocks.STONE.defaultBlockState(),null,Strategy.createForBiomes(ids),holder,null,null);
        var c=new ProtoChunk(new ChunkPos(0,0),UpgradeData.EMPTY,LevelHeightAccessor.create(-512,1024),factory,null);
        c.setLightEngine(LevelLightEngine.EMPTY);return c;
    }
    private static void set(ProtoChunk c,int x,int y,int z,Block b){
        var s=c.getSection(c.getSectionIndex(y));
        s.getStates().set(x&15,y&15,z&15,b.defaultBlockState());s.recalcBlockCounts();
    }
    private static void corridor(ProtoChunk c, boolean wet, boolean lavaBarrier){
        set(c,0,10,8,wet?Blocks.WATER:Blocks.AIR);
        set(c,1,10,8,Blocks.AIR);set(c,2,10,8,Blocks.AIR);
        for(int x=0;x<=2;x++){
            set(c,x,9,8,Blocks.STONE);set(c,x,11,8,Blocks.STONE);
            set(c,x,10,7,Blocks.STONE);set(c,x,10,9,Blocks.STONE);
        }
        set(c,3,10,8,Blocks.STONE);
        if(lavaBarrier)set(c,1,10,9,Blocks.LAVA);
    }

    public static void main(String[] args){
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();

        var dry=fixture();corridor(dry,false,false);
        check(NeverOverworldFloodConnectivityR14.floodVerifiedBoundaryComponents(dry)==0,
            "sealed boundary cave without ocean water must remain dry");
        check(dry.getBlockState(new BlockPos(1,10,8)).isAir(),"sealed cave cell remains air");

        var wet=fixture();corridor(wet,true,false);
        int changed=NeverOverworldFloodConnectivityR14.floodVerifiedBoundaryComponents(wet);
        check(changed==2,"verified water seed floods connected dry cells: "+changed);
        check(wet.getBlockState(new BlockPos(2,10,8)).is(Blocks.WATER),"connected cave becomes water");

        var lava=fixture();corridor(lava,true,true);
        check(NeverOverworldFloodConnectivityR14.hasAdjacentLava(lava,new BlockPos(1,10,8)),
            "lava adjacency detected");
        check(NeverOverworldFloodConnectivityR14.floodVerifiedBoundaryComponents(lava)==0,
            "lava barrier blocks water continuation");
        check(lava.getBlockState(new BlockPos(1,10,8)).isAir(),"cell beside lava remains dry");

        out.println("PASS FloodConnectivityR14Smoke checks="+checks);
    }
}
