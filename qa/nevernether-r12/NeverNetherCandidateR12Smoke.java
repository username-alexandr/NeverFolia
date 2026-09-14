package net.minecraft.world.level.levelgen.placement;

import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.IdMapper;
import net.minecraft.nbt.NbtAccounter;
import net.minecraft.nbt.NbtIo;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.chunk.*;

/** Native section/proposal/serialization contracts. Synthetic sections, not a world acceptance test. */
public final class NeverNetherCandidateR12Smoke {
    private static int checks;
    private static final ChunkPos CP=new ChunkPos(-214,-43);
    private static final BlockPos POS=new BlockPos(-3410,31,-684);
    private static void check(boolean test,String why){if(!test)throw new AssertionError(why);checks++;}
    private static LevelChunkSection section(BlockState initial) {
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(0.5f).downfall(0.0f)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        return new LevelChunkSection(new PalettedContainer<>(initial,Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY)),
            new PalettedContainer<Holder<Biome>>(holder,Strategy.createForBiomes(ids)));
    }
    private static LevelChunkSection capture(BlockState initial) {
        var s=section(initial);s.neverNetherR10Data=new NeverNetherSubstrateR10.SectionData(s.getStates().copy());
        NeverNetherStorageR11.bind(s.neverNetherR10Data,7270913L,CP.x(),1,CP.z());return s;
    }
    private static BlockState at(LevelChunkSection s){return s.getBlockState(POS.getX()&15,POS.getY()&15,POS.getZ()&15);}
    public static void main(String[] args)throws Exception {
        var output=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        check(NeverNetherStorageR11.PROFILE.equals("NN-R12-SUBSTRATE-1-DECORATION-PROPOSALS"),"new policy version");
        check(!NeverNetherProposalR12.handles(null),"unknown context not intercepted");
        check(NeverNetherProposalR12.orePriority(Blocks.GRAVEL.defaultBlockState())>0,"gravel is a controlled inclusion");
        check(NeverNetherProposalR12.orePriority(Blocks.GLOWSTONE.defaultBlockState())==0,"glowstone not accepted as generic ore output");
        check(NeverNetherProposalR12.orePriority(Blocks.LAVA.defaultBlockState())==0,"lava not accepted as generic ore output");
        check(NeverNetherProposalR12.priority(Blocks.LAVA.defaultBlockState().setValue(BlockStateProperties.LEVEL,1))==0,"flowing lava not accepted as source proposal");
        for(var block:List.of(Blocks.CHEST,Blocks.BEDROCK,Blocks.AIR,Blocks.NETHERRACK,Blocks.WATER))
            check(NeverNetherProposalR12.priority(block.defaultBlockState())==0,"unhandled state "+block);
        var values=new ArrayList<BlockState>();
        for(var state:Block.BLOCK_STATE_REGISTRY)if(NeverNetherProposalR12.priority(state)>0)values.add(state);
        for(var a:values){check(NeverNetherSubstrateR10.winner(a,a)==a,"idempotence");for(var b:values){
            check(NeverNetherSubstrateR10.winner(a,b)==NeverNetherSubstrateR10.winner(b,a),"commutativity");
            var c=values.get((Block.getId(a)^Block.getId(b))%values.size());
            check(NeverNetherSubstrateR10.winner(NeverNetherSubstrateR10.winner(a,b),c)==NeverNetherSubstrateR10.winner(a,NeverNetherSubstrateR10.winner(b,c)),"associativity");
        }}
        // Full proposal order is independent before/after serialized intermediate state.
        var proposals=new ArrayList<>(List.of(Blocks.GRAVEL.defaultBlockState(),Blocks.BASALT.defaultBlockState(),Blocks.BLACKSTONE.defaultBlockState(),Blocks.MAGMA_BLOCK.defaultBlockState(),Blocks.NETHER_QUARTZ_ORE.defaultBlockState(),Blocks.NETHER_GOLD_ORE.defaultBlockState()));
        for(int n=0;n<120;n++) {
            Collections.shuffle(proposals,new java.util.Random(n));var s=capture(Blocks.NETHERRACK.defaultBlockState());
            for(int i=0;i<proposals.size();i++) {
                check(NeverNetherSubstrateR10.proposeSection(s,POS,proposals.get(i)),"eligible ore proposal");
                if(i==2){var tag=NeverNetherStorageR11.encode(s,CP,1);var restored=s.copy();restored.neverNetherR10Data=null;NeverNetherStorageR11.restore(restored,tag,CP,1);s=restored;}
            }
            check(at(s).is(Blocks.NETHER_GOLD_ORE),"resources win inclusion conflicts");
            check(NeverNetherSubstrateR10.original(s,POS).is(Blocks.NETHERRACK),"original remains immutable");
        }
        // Every newly supported state survives compressed, disk-backed NBT roundtrip.
        var file=Files.createTempFile("r12-proposals-",".nbt");
        try {
            for(var state:values) {
                var s=capture(Blocks.AIR.defaultBlockState());NeverNetherSubstrateR10.proposeSection(s,POS,state);
                var tag=NeverNetherStorageR11.encode(s,CP,1);NbtIo.writeCompressed(tag,file);
                var loaded=s.copy();loaded.neverNetherR10Data=null;
                NeverNetherStorageR11.restore(loaded,NbtIo.readCompressed(file,NbtAccounter.create(4*1024*1024)),CP,1);
                check(NeverNetherStorageR11.encode(loaded,CP,1).equals(tag),"new state NBT roundtrip");
                loaded.setBlockState(POS.getX()&15,POS.getY()&15,POS.getZ()&15,state,false);
                var external=NeverNetherStorageR11.encode(loaded,CP,1);var restored=loaded.copy();restored.neverNetherR10Data=null;NeverNetherStorageR11.restore(restored,external,CP,1);
                check(!NeverNetherSubstrateR10.proposeSection(restored,POS,Blocks.LAVA.defaultBlockState()),"same-state foreign write protected after storage");
                check(at(restored)==state,"foreign block retained");
            }
        }finally{Files.deleteIfExists(file);}
        for(boolean reverse:new boolean[]{false,true}) {
            var s=capture(Blocks.AIR.defaultBlockState());
            var a=Blocks.CRIMSON_ROOTS.defaultBlockState();var b=Blocks.GLOWSTONE.defaultBlockState();
            NeverNetherSubstrateR10.proposeSection(s,POS,reverse?b:a);NeverNetherSubstrateR10.proposeSection(s,POS,reverse?a:b);
            check(at(s)==b,"glowstone/plant arbitration");
        }
        var old=capture(Blocks.AIR.defaultBlockState());var tag=NeverNetherStorageR11.encode(old,CP,1);tag.putString("Profile","NN-R11-SUBSTRATE-1-REMOTE-R10-PRIORITY");var target=section(Blocks.AIR.defaultBlockState());
        try{NeverNetherStorageR11.restore(target,tag,CP,1);throw new AssertionError("old profile accepted");}catch(NeverNetherLoadGuardR11.InvalidSubstrate expected){checks++;}
        check(target.neverNetherR10Data==null,"old profile rejection cannot publish metadata");
        for(int y=-128;y<896;y++){
            var p=new BlockPos(-3410,y,-684);long seed=NeverNetherProposalR12.seed(7270913L,p,1);
            check(seed==NeverNetherProposalR12.seed(7270913L,p,1),"coordinate random stable");
            check(seed!=NeverNetherProposalR12.seed(7270913L,p.above(4096),1),"no packed-height alias");
        }
        output.println("NN-R12 native proposal/storage: "+checks+" assertions over "+values.size()+" states; no world acceptance claimed");
    }
}
