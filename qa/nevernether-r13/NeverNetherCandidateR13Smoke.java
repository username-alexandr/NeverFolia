package net.minecraft.world.level.levelgen.placement;

import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;
import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.*;

/** Reconciliation contracts on real registry/sections. No generated-world claim. */
public final class NeverNetherCandidateR13Smoke {
    private static int checks;
    private static final BlockPos POS = new BlockPos(-3410,31,-684);
    private static final ChunkPos CP = new ChunkPos(POS.getX()>>4,POS.getZ()>>4);
    private static void check(boolean result,String label) { if(!result)throw new AssertionError(label);checks++; }
    private static LevelChunkSection captured(BlockState initial) {
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(0.5f).downfall(0.0f)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var section=new LevelChunkSection(new PalettedContainer<>(initial,Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY)),
            new PalettedContainer<Holder<Biome>>(holder,Strategy.createForBiomes(ids)));
        section.neverNetherR10Data=new NeverNetherSubstrateR10.SectionData(section.getStates().copy());
        NeverNetherStorageR11.bind(section.neverNetherR10Data,7270913L,CP.x(),1,CP.z());return section;
    }
    public static void main(String[] args) throws Exception {
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        check(NeverNetherStorageR11.PROFILE.equals("NN-R13-SUBSTRATE-1-RECONCILED-NATURAL"),"explicit reconciled policy");
        check(!NeverNetherNaturalPolicyR13.handles(null),"no live/null context");
        WorldGenLevel fake=(WorldGenLevel)Proxy.newProxyInstance(WorldGenLevel.class.getClassLoader(),new Class<?>[]{WorldGenLevel.class},
            (self,method,argv)->{throw new AssertionError("guard must not consult wrapped world: "+method);});
        check(!NeverNetherNaturalPolicyR13.handles(fake),"untrusted delegate rejected before reads");
        var wrapped=new org.bukkit.craftbukkit.util.DelegatedLevelAccessor() {};wrapped.setDelegate(fake);
        check(!NeverNetherNaturalPolicyR13.handles(wrapped),"structure wrapper not natural");
        check(!NeverNetherProposalR12.handles(wrapped),"actual glow/spring entry uses reconciled guard");
        wrapped.setDelegate(wrapped);
        check(!NeverNetherProposalR12.handles(wrapped),"cyclic wrapper does not hang");
        for(var b:List.of(Blocks.NETHERRACK,Blocks.BEDROCK,Blocks.GLOWSTONE,Blocks.LAVA,Blocks.WATER,Blocks.CHEST,Blocks.BLACKSTONE))
            check(!NeverNetherNaturalPolicyR13.allowsPlantAt(b.defaultBlockState()),"solid/fluid substrate rejected: "+b);
        for(var b:List.of(Blocks.AIR,Blocks.CAVE_AIR,Blocks.VOID_AIR))
            check(NeverNetherNaturalPolicyR13.allowsPlantAt(b.defaultBlockState()),"original air variant accepted");
        for(var state:Block.BLOCK_STATE_REGISTRY) {
            boolean expected=!state.hasBlockEntity()&&(state.isAir()||(state.canBeReplaced()&&state.getFluidState().isEmpty()));
            check(NeverNetherNaturalPolicyR13.allowsPlantAt(state)==expected,"substrate predicate: "+state);
        }
        for(var block:List.of(Blocks.CHEST,Blocks.AIR,Blocks.NETHERRACK,Blocks.CRIMSON_STEM)) {
            try {NeverNetherNaturalPolicyR13.proposeFlora(fake,POS,block.defaultBlockState(),2,512);throw new AssertionError("bad proposal/context accepted");}
            catch(IllegalArgumentException expected){checks++;}
        }
        Method propose=NeverNetherSubstrateR10.class.getDeclaredMethod("propose",WorldGenLevel.class,LevelChunkSection.class,BlockPos.class,BlockState.class,int.class,int.class);
        propose.setAccessible(true);
        for(int flags:new int[]{2,3,18}) for(int depth:new int[]{1,7,512}) {
            var section=captured(Blocks.AIR.defaultBlockState());int[] observed={-1,-1};
            WorldGenLevel level=(WorldGenLevel)Proxy.newProxyInstance(WorldGenLevel.class.getClassLoader(),new Class<?>[]{WorldGenLevel.class},(self,called,argv)->{
                if(!called.getName().equals("setBlock")||argv.length!=4)throw new AssertionError(called.toString());
                observed[0]=(Integer)argv[2];observed[1]=(Integer)argv[3];
                section.setBlockState(POS.getX()&15,POS.getY()&15,POS.getZ()&15,(BlockState)argv[1],false);return true;
            });
            check((Boolean)propose.invoke(null,level,section,POS,Blocks.CRIMSON_STEM.defaultBlockState(),flags,depth),"proposal accepted");
            check(observed[0]==flags&&observed[1]==depth,"flags and recursion preserved");
            var tag=NeverNetherStorageR11.encode(section,CP,1);var copy=section.copy();copy.neverNetherR10Data=null;
            NeverNetherStorageR11.restore(copy,tag,CP,1);check(NeverNetherStorageR11.encode(copy,CP,1).equals(tag),"flags path storage roundtrip");
        }
        for(String old:List.of("NN-R11-SUBSTRATE-1-REMOTE-R10-PRIORITY","NN-R12-SUBSTRATE-1-NATURAL-PROPOSALS","NN-R12-SUBSTRATE-1-DECORATION-PROPOSALS")) {
            var s=captured(Blocks.AIR.defaultBlockState());var tag=NeverNetherStorageR11.encode(s,CP,1);tag.putString("Profile",old);s.neverNetherR10Data=null;
            try {NeverNetherStorageR11.restore(s,tag,CP,1);throw new AssertionError("old profile accepted: "+old);}
            catch(NeverNetherLoadGuardR11.InvalidSubstrate expected){checks++;}
            check(s.neverNetherR10Data==null,"failed restore publishes nothing");
        }
        out.println("NN-R13 native reconciliation: "+checks+" assertions; not world generation or balance acceptance");
    }
}
