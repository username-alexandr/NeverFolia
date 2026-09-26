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

public final class FieldR15FloodEcologySmoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}

    private static ProtoChunk fixture(){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(1f).downfall(0)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var factory=new PalettedContainerFactory(Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),
            Blocks.STONE.defaultBlockState(),null,Strategy.createForBiomes(ids),holder,null,null);
        var c=new ProtoChunk(new ChunkPos(0,0),UpgradeData.EMPTY,LevelHeightAccessor.create(-512,1024),factory,null);
        c.setLightEngine(LevelLightEngine.EMPTY);
        // ProtoChunk test fixtures otherwise leave working sections as air.
        // Materialize the exact R15 flood-audit band as solid rock first so
        // each scenario exposes only the explicitly carved cavity.
        for(int y=-64;y<=128;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++){
            var s=c.getSection(c.getSectionIndex(y));
            s.getStates().set(x,y&15,z,Blocks.STONE.defaultBlockState());
        }
        for(int sy=c.getSectionIndex(-64);sy<=c.getSectionIndex(128);sy++)c.getSections()[sy].recalcBlockCounts();
        return c;
    }
    private static void set(ProtoChunk c,int x,int y,int z,Block b){
        var s=c.getSection(c.getSectionIndex(y));
        s.getStates().set(x&15,y&15,z&15,b.defaultBlockState());s.recalcBlockCounts();
    }

    public static void main(String[] args){
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();

        // Mesa/overhang-like cavity at the exact Y=128 ocean plane.
        var wet=fixture();
        set(wet,2,128,8,Blocks.WATER);
        for(int x=3;x<=7;x++)set(wet,x,128,8,Blocks.AIR);
        int flooded=NeverOverworldFloodConnectivityR15.floodVerifiedComponents(wet);
        check(flooded==5,"Y128 overhang cavity connected to verified water must flood: "+flooded);
        check(wet.getBlockState(new BlockPos(7,128,8)).is(Blocks.WATER),"far cavity cell flooded");

        // Same cavity without a verified water seed remains dry.
        var dry=fixture();
        for(int x=2;x<=7;x++)set(dry,x,128,8,Blocks.AIR);
        check(NeverOverworldFloodConnectivityR15.floodVerifiedComponents(dry)==0,
            "sealed Y128 cavity must stay dry");
        check(dry.getBlockState(new BlockPos(7,128,8)).isAir(),"sealed cavity unchanged");

        // Underground water alone is not an ocean seed and must never flood a whole cave/chunk.
        var underground=fixture();
        set(underground,2,80,8,Blocks.WATER);
        for(int x=3;x<=12;x++)set(underground,x,80,8,Blocks.AIR);
        check(NeverOverworldFloodConnectivityR15.floodVerifiedComponents(underground)==0,
            "underground water pocket must not seed ocean flood");
        check(underground.getBlockState(new BlockPos(12,80,8)).isAir(),
            "underground connected cavity remains dry without Y128 ocean seed");

        // R35: custom NeverFolia ocean water is column-bounded. A genuinely
        // open ocean shaft above its natural OCEAN_FLOOR_WG may receive the
        // raised-ocean overlay, while cells below that floor remain vanilla
        // aquifer territory.
        var column=fixture();
        set(column,2,128,8,Blocks.WATER);
        for(int y=127;y>=80;y--)set(column,2,y,8,Blocks.AIR);
        check(NeverOverworldFloodConnectivityR15.customOceanColumnOpen(
                column,new BlockPos(2,100,8),100),
            "R35 open ocean column above OCEAN_FLOOR_WG must accept custom water");
        check(!NeverOverworldFloodConnectivityR15.customOceanColumnOpen(
                column,new BlockPos(2,70,8),70),
            "R35 cell below natural OCEAN_FLOOR_WG must remain native-aquifer territory");

        // R22: even with zero external neighbour seeds, the LIGHT reconciliation
        // pass must flood a seam-touching component that has its own verified
        // Y128 ocean seed. The pre-reconcile pass intentionally defers it.
        var localOceanSeam=fixture();
        set(localOceanSeam,2,128,8,Blocks.WATER);
        for(int y=127;y>=80;y--)set(localOceanSeam,2,y,8,Blocks.AIR);
        for(int x=3;x<=15;x++)set(localOceanSeam,x,80,8,Blocks.AIR);
        check(NeverOverworldFloodConnectivityR15.floodVerifiedComponents(localOceanSeam)==0,
            "pre-reconcile owner pass must defer seam-touching ocean component");
        boolean[] noExternalSeeds=new boolean[
            (NeverOverworldFloodConnectivityR15.SCAN_MAX_Y
             - NeverOverworldFloodConnectivityR15.SCAN_MIN_Y + 1) * 256
        ];
        int localFlood=NeverOverworldFloodConnectivityR15.floodVerifiedComponents(
            localOceanSeam,noExternalSeeds,true);
        check(localFlood==0,
            "R35 seam reconciliation must not flood an enclosed cave below natural ocean floor");
        check(localOceanSeam.getBlockState(new BlockPos(15,80,8)).isAir(),
            "R35 enclosed deep seam cell must remain dry");

        // Lava contact blocks continuation.
        var lava=fixture();
        set(lava,2,127,8,Blocks.WATER);
        set(lava,3,127,8,Blocks.AIR);
        set(lava,3,127,9,Blocks.LAVA);
        set(lava,4,127,8,Blocks.AIR);
        check(NeverOverworldFloodConnectivityR15.floodVerifiedComponents(lava)==0,
            "lava-adjacent barrier must stop flood");
        check(lava.getBlockState(new BlockPos(3,127,8)).isAir(),"cell beside lava remains dry");

        // Glow-berry vines are now hard height-gated: the user-reported
        // flooded-cave screenshot requires them strictly above the Y128 ocean.
        for(var b:new Block[]{Blocks.CAVE_VINES,Blocks.CAVE_VINES_PLANT}){
            check(NeverOverworldEcologyR15.floodedCavePlant(b.defaultBlockState()),b+" classified as cave flora");
            check(NeverOverworldEcologyR15.heightPlant(b.defaultBlockState()),b+" classified for ocean-height gating");
            check(NeverOverworldEcologyR15.shouldRemove(b.defaultBlockState(),80,true),b+" removed in flooded cave");
            check(NeverOverworldEcologyR15.shouldRemove(b.defaultBlockState(),80,false),b+" removed below ocean even in dry cave");
            check(!NeverOverworldEcologyR15.shouldRemove(b.defaultBlockState(),129,false),b+" allowed above raised ocean");
        }

        // Other flooded cave plants remain allowed in genuinely dry caves.
        for(var b:new Block[]{Blocks.AZALEA,Blocks.FLOWERING_AZALEA,Blocks.SMALL_DRIPLEAF,Blocks.BIG_DRIPLEAF}){
            check(NeverOverworldEcologyR15.floodedCavePlant(b.defaultBlockState()),b+" classified");
            check(NeverOverworldEcologyR15.shouldRemove(b.defaultBlockState(),80,true),b+" removed in flooded cave");
            check(!NeverOverworldEcologyR15.shouldRemove(b.defaultBlockState(),80,false),b+" preserved in dry cave");
        }

        check(NeverOverworldEcologyR15.shouldRemove(Blocks.CACTUS.defaultBlockState(),128,false),
            "cactus blocked at/below ocean plane");
        check(!NeverOverworldEcologyR15.shouldRemove(Blocks.CACTUS.defaultBlockState(),129,false),
            "cactus allowed above ocean plane");
        check(NeverOverworldEcologyR15.shouldRemove(Blocks.MELON.defaultBlockState(),100,false),
            "melon blocked below ocean plane");
        check(!NeverOverworldEcologyR15.shouldRemove(Blocks.MELON.defaultBlockState(),129,false),
            "melon allowed above ocean plane");
        check(NeverOverworldEcologyR15.heightPlant(Blocks.OXEYE_DAISY.defaultBlockState()),
            "oxeye daisy classified for ocean-height gating");
        check(NeverOverworldEcologyR15.shouldRemove(Blocks.OXEYE_DAISY.defaultBlockState(),128,false),
            "oxeye daisy blocked at/below ocean plane");
        check(!NeverOverworldEcologyR15.shouldRemove(Blocks.OXEYE_DAISY.defaultBlockState(),129,false),
            "oxeye daisy allowed above ocean plane");

        for(var flower:new Block[]{Blocks.DANDELION,Blocks.POPPY,Blocks.CORNFLOWER,Blocks.WILDFLOWERS,
                                     Blocks.AZURE_BLUET,Blocks.PINK_PETALS}){
            check(NeverOverworldEcologyR15.heightPlant(flower.defaultBlockState()),flower+" classified for ocean-height gating");
            check(NeverOverworldEcologyR15.shouldRemove(flower.defaultBlockState(),128,false),flower+" blocked at/below ocean plane");
            check(!NeverOverworldEcologyR15.shouldRemove(flower.defaultBlockState(),129,false),flower+" allowed above ocean plane");
        }

        for(var plant:new Block[]{Blocks.BAMBOO,Blocks.BAMBOO_SAPLING,Blocks.COCOA}){
            check(NeverOverworldEcologyR15.heightPlant(plant.defaultBlockState()),plant+" classified for ocean-height gating");
            check(NeverOverworldEcologyR15.shouldRemove(plant.defaultBlockState(),128,false),plant+" blocked at/below ocean plane");
            check(!NeverOverworldEcologyR15.shouldRemove(plant.defaultBlockState(),129,false),plant+" allowed above ocean plane");
        }

        check(NeverOverworldEcologyR15.replacementAfterRemoval(true).is(Blocks.WATER),
            "flooded forbidden flora is replaced by water");
        check(NeverOverworldEcologyR15.replacementAfterRemoval(false).isAir(),
            "dry forbidden flora is replaced by air");

        var seam=fixture();
        check(NeverOverworldEcologyR15.horizontalChunkEdge(seam,new BlockPos(0,80,8)),
            "x-min cave flora is a horizontal seam candidate");
        check(NeverOverworldEcologyR15.horizontalChunkEdge(seam,new BlockPos(15,80,8)),
            "x-max cave flora is a horizontal seam candidate");
        check(!NeverOverworldEcologyR15.horizontalChunkEdge(seam,new BlockPos(8,80,8)),
            "interior cave flora is not a seam candidate");
        check(NeverOverworldEcologyR15.shouldRemove(Blocks.CAVE_VINES.defaultBlockState(),80,true),
            "seam candidate routes through flooded-cave removal contract");

        out.println("PASS FieldR15FloodEcologySmoke checks="+checks);
    }
}
