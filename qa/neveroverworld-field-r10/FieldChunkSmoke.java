package net.minecraft.world.level.chunk;

import java.util.*;
import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.lighting.LevelLightEngine;

public final class FieldChunkSmoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    private static void rejected(Runnable r,String why){try{r.run();}catch(RuntimeException expected){checks++;return;}throw new AssertionError(why);}
    private static ProtoChunk fixture(){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(.5f).downfall(0)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var factory=new PalettedContainerFactory(Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),Blocks.AIR.defaultBlockState(),null,Strategy.createForBiomes(ids),holder,null,null);
        var c=new ProtoChunk(new ChunkPos(0,0),UpgradeData.EMPTY,LevelHeightAccessor.create(-512,1024),factory,null);c.setLightEngine(LevelLightEngine.EMPTY);return c;
    }
    private static void direct(ProtoChunk c,int x,int y,int z,BlockState s){c.getSection(c.getSectionIndex(y)).setBlockState(x&15,y&15,z&15,s,false);}
    public static void main(String[] args){
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var c=fixture();c.setPersistedStatus(ChunkStatus.INITIALIZE_LIGHT);
        for(int[] d:new int[][]{{0,1,0},{0,-1,0},{1,0,0},{-1,0,0},{0,0,1},{0,0,-1}})direct(c,4+d[0],80+d[1],4+d[2], d[1]==1?Blocks.GRAVEL.defaultBlockState():Blocks.STONE.defaultBlockState());
        direct(c,4,80,4,Blocks.SNOW_BLOCK.defaultBlockState());
        direct(c,6,80,6,Blocks.SNOW.defaultBlockState());direct(c,7,80,6,Blocks.WATER.defaultBlockState());
        direct(c,8,80,8,Blocks.POWDER_SNOW.defaultBlockState());
        direct(c,10,80,10,Blocks.POPPY.defaultBlockState());direct(c,11,80,10,Blocks.WATER.defaultBlockState());
        direct(c,12,80,12,Blocks.DANDELION.defaultBlockState());
        direct(c,14,80,14,Blocks.SEAGRASS.defaultBlockState());direct(c,13,80,14,Blocks.WATER.defaultBlockState());
        int cleaned=NeverOverworldSubmergedRemnants.clean(c);
        check(cleaned==4,"cleanup count="+cleaned);
        check(c.getBlockState(new BlockPos(4,80,4)).is(Blocks.GRAVEL),"buried snow host");
        check(c.getBlockState(new BlockPos(6,80,6)).is(Blocks.WATER),"snow to water");
        check(c.getBlockState(new BlockPos(8,80,8)).isAir(),"snow to air");
        check(c.getBlockState(new BlockPos(10,80,10)).is(Blocks.WATER),"flower to water");
        check(c.getBlockState(new BlockPos(12,80,12)).is(Blocks.DANDELION),"dry flower preserved");
        check(c.getBlockState(new BlockPos(14,80,14)).is(Blocks.SEAGRASS),"aquatic flora preserved");
        check(NeverOverworldSubmergedRemnants.clean(c)==0,"cleanup idempotent");

        Block[] ores={Blocks.COAL_ORE,Blocks.DEEPSLATE_COAL_ORE,Blocks.IRON_ORE,Blocks.DEEPSLATE_IRON_ORE,Blocks.COPPER_ORE,Blocks.DEEPSLATE_COPPER_ORE,Blocks.GOLD_ORE,Blocks.DEEPSLATE_GOLD_ORE,Blocks.REDSTONE_ORE,Blocks.DEEPSLATE_REDSTONE_ORE,Blocks.LAPIS_ORE,Blocks.DEEPSLATE_LAPIS_ORE,Blocks.DIAMOND_ORE,Blocks.DEEPSLATE_DIAMOND_ORE,Blocks.EMERALD_ORE,Blocks.DEEPSLATE_EMERALD_ORE};
        for(int i=0;i<ores.length;i++)check(NeverOverworldOreScarcityFieldR10.kind(ores[i].defaultBlockState())==i/2+1,"ore kind "+i);
        for(int kind=1;kind<=8;kind++){
            int total=65536,keep=0;
            for(int i=0;i<total;i++)if(NeverOverworldOreScarcityFieldR10.retain(-2996952393010080672L,-30000+i*3,-512+(i&1023),25000-i*7,kind,50))keep++;
            check(keep>total*.48&&keep<total*.52,"half sample kind="+kind+" keep="+keep);
        }
        var o=fixture();o.setPersistedStatus(ChunkStatus.INITIALIZE_LIGHT);int ox=o.getPos().getMinBlockX(),oz=o.getPos().getMinBlockZ();var original=new HashMap<BlockPos,BlockState>();
        int idx=0;for(int y:new int[]{-400,-200,-96,-64,0,64,127,200})for(Block b:ores){var p=new BlockPos(ox+(idx&15),y,oz+((idx>>4)&15));idx++;direct(o,p.getX(),p.getY(),p.getZ(),b.defaultBlockState());original.put(p,b.defaultBlockState());}
        direct(o,1,100,1,Blocks.RAW_IRON_BLOCK.defaultBlockState());original.put(new BlockPos(1,100,1),Blocks.RAW_IRON_BLOCK.defaultBlockState());
        direct(o,2,100,1,Blocks.RAW_COPPER_BLOCK.defaultBlockState());original.put(new BlockPos(2,100,1),Blocks.RAW_COPPER_BLOCK.defaultBlockState());
        int changed=NeverOverworldOreScarcityFieldR10.thin(-2996952393010080672L,o);int expected=0;
        for(var e:original.entrySet()){
            int kind=NeverOverworldOreScarcityFieldR10.kind(e.getValue());boolean keep=NeverOverworldOreScarcityFieldR10.retain(-2996952393010080672L,e.getKey().getX(),e.getKey().getY(),e.getKey().getZ(),kind,50);if(!keep)expected++;
            check(o.getBlockState(e.getKey()).equals(keep?e.getValue():NeverOverworldOreScarcityFieldR10.host(e.getValue())),"ore actual write "+e.getKey());
        }
        check(changed==expected,"ore changed count");check(NeverOverworldOreScarcityFieldR10.thin(-2996952393010080672L,o)==0,"ore idempotent");
        o.setPersistedStatus(ChunkStatus.FULL);rejected(()->NeverOverworldOreScarcityFieldR10.thin(1L,o),"FULL must reject");
        out.println("PASS FieldChunkSmoke checks="+checks);
    }
}
