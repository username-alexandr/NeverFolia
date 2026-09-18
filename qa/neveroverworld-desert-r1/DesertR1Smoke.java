package net.minecraft.world.level.chunk;

import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.lighting.LevelLightEngine;

public final class DesertR1Smoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    private static ProtoChunk fixture(){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(2.0f).downfall(0)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var factory=new PalettedContainerFactory(
            Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),Blocks.AIR.defaultBlockState(),null,
            Strategy.createForBiomes(ids),holder,null,null);
        var chunk=new ProtoChunk(new ChunkPos(0,0),UpgradeData.EMPTY,LevelHeightAccessor.create(-512,1024),factory,null);
        chunk.setLightEngine(LevelLightEngine.EMPTY);
        for(int z=0;z<16;z++)for(int x=0;x<16;x++)
            chunk.setBlockState(new BlockPos(x,NeverOverworldDesertR1.FLOOD_LEVEL,z),Blocks.WATER.defaultBlockState(),0);
        return chunk;
    }
    public static void main(String[] args){
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        long seed=-2996952393010080672L;
        check(NeverOverworldDesertR1.surfaceGroundY(129)==128,"WORLD_SURFACE_WG first-available Y must map to ground Y");
        check(NeverOverworldDesertR1.surfaceGroundY(130)==129,"surface-ground conversion regressed");
        check(!NeverOverworldDesertR1.isEligibleOasisGroundY(127,512),"sub-flood ground must stay ineligible");
        check(NeverOverworldDesertR1.isEligibleOasisGroundY(128,512),"flood-level dry shore must stay eligible");
        check(NeverOverworldDesertR1.isEligibleOasisGroundY(129,512),"dry terrain above flood level must be eligible");
        check(NeverOverworldDesertR1.isFloodedDesertCenter(128,Blocks.WATER.defaultBlockState()),"flood-level water must select sandbar oasis mode");
        check(!NeverOverworldDesertR1.isFloodedDesertCenter(128,Blocks.SAND.defaultBlockState()),"dry flood-level sand must not select flooded mode");
        var flooded=fixture();
        long oasisKey=NeverOverworldDesertR1.mix(seed ^ 0x4E4F574F41534953L);
        int floodedChanged=NeverOverworldDesertR1.buildFloodedOasis(flooded,8,8,oasisKey);
        check(floodedChanged>0,"flooded oasis builder made no changes");
        check(flooded.getBlockState(new BlockPos(8,128,8)).is(Blocks.SANDSTONE),"flooded oasis center foundation");
        check(flooded.getBlockState(new BlockPos(8,129,8)).is(Blocks.SAND),"flooded oasis center sand");
        check(flooded.getBlockState(new BlockPos(8,130,8)).is(Blocks.WATER),"flooded oasis center pool");
        check(flooded.getBlockState(new BlockPos(0,128,0)).is(Blocks.WATER),"flooded oasis must stay local and compact");
        int logs=0,leaves=0;
        for(int y=129;y<=140;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            var state=flooded.getBlockState(new BlockPos(x,y,z));
            if(state.is(Blocks.JUNGLE_LOG))logs++;
            if(state.is(Blocks.JUNGLE_LEAVES))leaves++;
        }
        check(logs>=5,"flooded oasis palm trunk missing logs="+logs);
        check(leaves>=5,"flooded oasis palm canopy missing leaves="+leaves);
        int selected=0;
        int total=0;
        for(int x=-384;x<=384;x++){
            for(int z=-384;z<=384;z++){
                boolean a=NeverOverworldDesertR1.selectedChunk(seed,x,z);
                boolean b=NeverOverworldDesertR1.selectedChunk(seed,x,z);
                check(a==b,"selection non-deterministic");
                if(a)selected++;
                total++;
            }
        }
        double rate=(double)selected/(double)total;
        double expected=1.0D/NeverOverworldDesertR1.OASIS_CHANCE_DENOMINATOR;
        check(rate>expected*0.75D&&rate<expected*1.25D,
            "oasis candidate rate out of bounds selected="+selected+" total="+total+" rate="+rate);
        check(!NeverOverworldDesertR1.selectedChunk(seed,0,0)
              || NeverOverworldDesertR1.selectedChunk(seed,0,0),"repeat determinism");
        out.println("PASS DesertR1Smoke checks="+checks+" selected="+selected+" rate="+rate);
    }
}
