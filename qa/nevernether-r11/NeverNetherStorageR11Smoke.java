package net.minecraft.world.level.levelgen.placement;

import java.io.*;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.util.*;
import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.nbt.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.*;

/** Real native section/NBT lifecycle tests. Synthetic block content is explicit;
 * these checks do not claim a server restart or natural-world acceptance. */
public final class NeverNetherStorageR11Smoke {
    private static int checks;
    private static final ChunkPos CP=new ChunkPos(-214,-43);
    private static final BlockPos P=new BlockPos(-3410,31,-684);
    private static Method digest;
    private static void check(boolean test,String why){if(!test)throw new AssertionError(why);checks++;}
    private static LevelChunkSection section(BlockState initial) {
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(0.5f).downfall(0.0f)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        return new LevelChunkSection(new PalettedContainer<>(initial,Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY)),
            new PalettedContainer<Holder<Biome>>(holder,Strategy.createForBiomes(ids)));
    }
    private static LevelChunkSection captured(BlockState initial) {
        var s=section(initial);s.neverNetherR10Data=new NeverNetherSubstrateR10.SectionData(s.getStates().copy());
        NeverNetherStorageR11.bind(s.neverNetherR10Data,7270913L,CP.x(),1,CP.z());return s;
    }
    private static LevelChunkSection detached(LevelChunkSection s) {
        var copy=s.copy();copy.neverNetherR10Data=null;return copy;
    }
    private static void resign(CompoundTag tag)throws Exception{tag.putByteArray("Digest",(byte[])digest.invoke(null,tag));}
    private static void reject(LevelChunkSection target,CompoundTag tag,ChunkPos cp,int sy,String why) {
        var before=target.getStates().copy();
        try{NeverNetherStorageR11.restore(target,tag,cp,sy);throw new AssertionError("accepted: "+why);}catch(IllegalStateException expected){checks++;}
        check(target.neverNetherR10Data==null,"failed decode did not publish "+why);
        for(int i=0;i<4096;i++)check(before.get(i&15,i>>8,(i>>4)&15)==target.getBlockState(i&15,i>>8,(i>>4)&15),"decode does not edit blocks");
    }
    private static BlockState at(LevelChunkSection s){return s.getBlockState(P.getX()&15,P.getY()&15,P.getZ()&15);}
    public static void main(String[] args)throws Exception {
        var output=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        digest=NeverNetherStorageR11.class.getDeclaredMethod("digest",CompoundTag.class);digest.setAccessible(true);
        var s=captured(Blocks.NETHERRACK.defaultBlockState());
        check(NeverNetherSubstrateR10.proposeSection(s,P,Blocks.MAGMA_BLOCK.defaultBlockState()),"first proposal");
        CompoundTag saved=NeverNetherStorageR11.encode(s,CP,1);
        var target=detached(s);NeverNetherStorageR11.restore(target,saved,CP,1);
        check(NeverNetherSubstrateR10.original(target,P).is(Blocks.NETHERRACK),"original not inferred from magma");
        check(NeverNetherSubstrateR10.proposeSection(target,P,Blocks.NETHER_QUARTZ_ORE.defaultBlockState()),"proposal after restore");
        check(at(target).is(Blocks.NETHER_QUARTZ_ORE),"original policy after restore");
        check(NeverNetherStorageR11.encode(s,CP,1).equals(saved),"encoding is deterministic and read-only");
        check(NeverNetherStorageR11.encode(target,CP,1).getIntArray("ProposalIndices").orElseThrow().length==1,"proposal survives storage");
        var same=captured(Blocks.NETHERRACK.defaultBlockState());
        NeverNetherSubstrateR10.proposeSection(same,P,Blocks.MAGMA_BLOCK.defaultBlockState());
        same.setBlockState(P.getX()&15,P.getY()&15,P.getZ()&15,Blocks.MAGMA_BLOCK.defaultBlockState(),false);
        var sameOut=detached(same);NeverNetherStorageR11.restore(sameOut,NeverNetherStorageR11.encode(same,CP,1),CP,1);
        check(!NeverNetherSubstrateR10.proposeSection(sameOut,P,Blocks.NETHER_GOLD_ORE.defaultBlockState()),"same-value external protection persists");
        check(at(sameOut).is(Blocks.MAGMA_BLOCK),"external value retained");
        // Actual compressed NBT file roundtrip, not object aliasing.
        Path file=Files.createTempFile("nn-r11-roundtrip-",".nbt");
        try{
            NbtIo.writeCompressed(saved,file);CompoundTag disk=NbtIo.readCompressed(file,NbtAccounter.create(4*1024*1024));
            var fromDisk=detached(s);NeverNetherStorageR11.restore(fromDisk,disk,CP,1);
            check(NeverNetherStorageR11.encode(fromDisk,CP,1).equals(saved),"compressed NBT file exact roundtrip");
            output.println("Uniform rock + one proposal compressed section bytes="+Files.size(file));
        }finally{Files.deleteIfExists(file);}
        var tampered=saved.copy();tampered.putInt("Schema",9);reject(detached(s),tampered,CP,1,"version");
        tampered=saved.copy();tampered.putString("Profile","other");reject(detached(s),tampered,CP,1,"profile");
        reject(detached(s),saved,new ChunkPos(CP.x()+1,CP.z()),1,"chunk position");
        reject(detached(s),saved,CP,2,"section Y");
        tampered=saved.copy();tampered.putLong("Seed",1);reject(detached(s),tampered,CP,1,"checksum");
        var stale=detached(s);stale.setBlockState(0,0,0,Blocks.AIR.defaultBlockState(),false);reject(stale,saved,CP,1,"incoherent current blocks");
        for(String field:List.of("Palette","Original","External","ProposalIndices","ProposalStates","CurrentHash","Digest")){
            tampered=saved.copy();tampered.remove(field);reject(detached(s),tampered,CP,1,"missing "+field);
        }
        tampered=saved.copy();tampered.putLongArray("External",new long[65]);resign(tampered);reject(detached(s),tampered,CP,1,"oversized external bitset");
        tampered=saved.copy();tampered.putIntArray("ProposalIndices",new int[]{4096});resign(tampered);reject(detached(s),tampered,CP,1,"out of bounds proposal");
        tampered=saved.copy();tampered.putIntArray("ProposalIndices",new int[]{0,0});tampered.putIntArray("ProposalStates",new int[]{1,1});resign(tampered);reject(detached(s),tampered,CP,1,"duplicate proposal");
        tampered=saved.copy();tampered.putIntArray("ProposalStates",new int[]{999});resign(tampered);reject(detached(s),tampered,CP,1,"invalid proposal state");
        tampered=saved.copy();tampered.putInt("Bits",12);resign(tampered);reject(detached(s),tampered,CP,1,"palette width");
        tampered=saved.copy();tampered.putLongArray("Original",new long[0]);resign(tampered);reject(detached(s),tampered,CP,1,"truncated packed data");
        tampered=saved.copy();var palette=(ListTag)tampered.get("Palette");palette.set(0,StringTag.valueOf("minecraft:not_a_real_block"));resign(tampered);reject(detached(s),tampered,CP,1,"unknown original block");
        tampered=saved.copy();palette=(ListTag)tampered.get("Palette");palette.set(0,palette.get(1).copy());resign(tampered);reject(detached(s),tampered,CP,1,"duplicate palette");
        // Exercise palette bit packing at every width with real distinct registered states.
        var states=new ArrayList<BlockState>();for(BlockState st:Block.BLOCK_STATE_REGISTRY)if(!st.hasBlockEntity())states.add(st);
        for(int count:new int[]{1,2,3,7,17,33,65,129,257,513,1025,2049,4096}){
            var mixed=section(Blocks.AIR.defaultBlockState());
            for(int i=0;i<4096;i++)mixed.setBlockState(i&15,i>>8,(i>>4)&15,states.get(i%count),false);
            mixed.neverNetherR10Data=new NeverNetherSubstrateR10.SectionData(mixed.getStates().copy());
            NeverNetherStorageR11.bind(mixed.neverNetherR10Data,7270913L,CP.x(),1,CP.z());
            var mixedSaved=NeverNetherStorageR11.encode(mixed,CP,1);var restored=detached(mixed);NeverNetherStorageR11.restore(restored,mixedSaved,CP,1);
            check(NeverNetherStorageR11.encode(restored,CP,1).equals(mixedSaved),"all packing widths roundtrip "+count);
        }
        var copy=s.copy();check(copy.neverNetherR10Data!=null,"engine section.copy retains metadata");
        check(copy.neverNetherR10Data!=s.neverNetherR10Data,"copy metadata isolated");
        copy.setBlockState(P.getX()&15,P.getY()&15,P.getZ()&15,Blocks.AIR.defaultBlockState(),false);
        check(!s.neverNetherR10Data.external.get(((P.getY()&15)<<8)|((P.getZ()&15)<<4)|(P.getX()&15)),"copy mutation does not reach original provenance");
        check(at(s).is(Blocks.MAGMA_BLOCK),"copy mutation does not reach original blocks");
        // Coherent copy while section-level writes occur; the original bitmap
        // and actual blocks must be from one critical section, not different times.
        var concurrent=captured(Blocks.NETHERRACK.defaultBlockState());
        try(var pool=java.util.concurrent.Executors.newFixedThreadPool(2)) {
            var writer=pool.submit(()->{for(int i=0;i<1000;i++)concurrent.setBlockState(0,0,0,
                (i&1)==0?Blocks.AIR.defaultBlockState():Blocks.BLACKSTONE.defaultBlockState(),false);});
            var reader=pool.submit(()->{for(int i=0;i<40;i++) {
                var snapshot=concurrent.copy();var encoded=NeverNetherStorageR11.encode(snapshot,CP,1);
                var restored=detached(snapshot);NeverNetherStorageR11.restore(restored,encoded,CP,1);
                if(!NeverNetherStorageR11.encode(restored,CP,1).equals(encoded))throw new AssertionError("incoherent concurrent section copy");
            }});
            writer.get();reader.get();check(true,"concurrent writes/copies/roundtrip coherent");
        }
        output.println("NN-R11 storage native: "+checks+" checks passed; section/NBT tests, not world restart acceptance");
    }
}
