package net.minecraft.world.level.levelgen.placement;

import java.lang.reflect.*;
import java.util.*;
import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/** Real native section and proposal code; world access is an explicit proxy fixture.
 * --expect-bug verifies the unmodified TEST1 binary throws the reported exception.
 * These are API regressions, not a natural-world or player-connection test.
 */
public final class NeverNetherBug01Smoke {
    private static int checks, lookups, writes, ownershipChecks, savedFlags, savedLimit;
    private static final ChunkPos CP = new ChunkPos(-195,-393);
    private static ProtoChunk chunk;
    private static boolean writable = true, missing = false;
    private static void check(boolean b,String label) { if(!b)throw new AssertionError(label);checks++; }
    private static BlockPos pos(int y) { return new BlockPos(CP.getMinBlockX(),y,CP.getMinBlockZ()); }
    private static void resetCounters() { lookups=writes=ownershipChecks=0; }
    private static ProtoChunk createChunk() {
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(.5f).downfall(0)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        // Codecs are not used by this section-only fixture. Persisted section
        // assertions below call the actual R11 encoder, not these null factory codecs.
        var factory=new PalettedContainerFactory(Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),
            Blocks.AIR.defaultBlockState(),null,Strategy.createForBiomes(ids),holder,null,null);
        var value=new ProtoChunk(CP,UpgradeData.EMPTY,LevelHeightAccessor.create(-128,656),factory,null);
        for(int i=0;i<value.getSections().length;i++) {
            var section=value.getSection(i);
            section.neverNetherR10Data=new NeverNetherSubstrateR10.SectionData(section.getStates().copy());
            NeverNetherStorageR11.bind(section.neverNetherR10Data,7270913L,CP.x(),-8+i,CP.z());
        }
        return value;
    }
    private static WorldGenLevel fixture() {
        return (WorldGenLevel)Proxy.newProxyInstance(WorldGenLevel.class.getClassLoader(),new Class<?>[]{WorldGenLevel.class},(self,method,args)->{
            return switch(method.getName()) {
                case "ensureCanWrite" -> { ownershipChecks++;yield writable; }
                case "getChunk" -> {
                    lookups++;
                    if(args.length!=4 || (int)args[0]!=CP.x() || (int)args[1]!=CP.z() || args[2]!=ChunkStatus.CARVERS || (boolean)args[3])
                        throw new AssertionError("Unexpected synchronous/outside chunk request");
                    yield missing ? null : chunk;
                }
                case "setBlock" -> {
                    writes++;savedFlags=(int)args[2];savedLimit=(int)args[3];
                    BlockPos p=(BlockPos)args[0];
                    chunk.getSection(chunk.getSectionIndex(p.getY())).setBlockState(p.getX()&15,p.getY()&15,p.getZ()&15,(BlockState)args[1],false);
                    yield true;
                }
                case "getMinY" -> -128;
                case "getHeight" -> 656;
                case "getMaxY" -> 527;
                case "getSeed" -> 7270913L;
                case "toString" -> "BUG01 nonupgrading WorldGenLevel fixture";
                default -> throw new AssertionError("Unreviewed world access: "+method);
            };
        });
    }
    private static void expectFailure(Runnable action,String label) {
        try { action.run(); } catch(IllegalStateException expected) { checks++;return; }
        throw new AssertionError(label+" unexpectedly accepted");
    }
    public static void main(String[] args) throws Exception {
        var output=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        chunk=createChunk();var world=fixture();var plant=Blocks.WARPED_WART_BLOCK.defaultBlockState();
        check(chunk.getSections().length==41,"real 41-section fixture");
        check(chunk.getSectionIndex(528)==41,"exact failing index at Y528");
        if(args.length==1 && args[0].equals("--expect-bug")) {
            try { NeverNetherSubstrateR10.proposeBlock(world,pos(528),plant,2,512); }
            catch(ArrayIndexOutOfBoundsException error) {
                check(error.getMessage().contains("41"),"observed index41 exception");
                check(lookups==1 && writes==0,"fails at section access before write");
                output.println("BUG01 BASELINE REPRODUCED: "+error+"; native ProtoChunk and proposal path, fixture world");return;
            }
            throw new AssertionError("Expected baseline bug was not reproduced");
        }
        int[] invalid={Integer.MIN_VALUE,-1024,-145,-144,-129,512,513,527,528,529,543,544,895,896,4096,Integer.MAX_VALUE};
        for(int y:invalid) {
            resetCounters();
            check(!NeverNetherSubstrateR10.proposeBlock(world,pos(y),plant),"default overload rejects Y"+y);
            check(!NeverNetherSubstrateR10.proposeBlock(world,pos(y),plant,18,27),"flags overload rejects Y"+y);
            check(lookups==0 && writes==0 && ownershipChecks==0,"reject before every world lookup Y"+y);
            var top=chunk.getSection(40);var before=NeverNetherStorageR11.encode(top,CP,32);
            check(!NeverNetherSubstrateR10.proposeSection(top,pos(y),plant),"direct section rejects Y"+y);
            check(before.equals(NeverNetherStorageR11.encode(top,CP,32)),"no phantom metadata or aliased write Y"+y);
        }
        // Every valid Y can reach the unchanged original proposal path.
        for(int y=-128;y<512;y++) {
            resetCounters();
            check(NeverNetherSubstrateR10.proposeBlock(world,pos(y),plant,18,27),"valid proposal "+y);
            check(lookups==1 && writes==1 && ownershipChecks==1,"valid ownership/access/write "+y);
            check(savedFlags==18 && savedLimit==27,"original flags/recursion "+y);
            check(chunk.getBlockState(pos(y))==plant,"actual section write "+y);
        }
        writable=false;resetCounters();
        check(!NeverNetherSubstrateR10.proposeBlock(world,pos(100),plant),"horizontal ownership still enforced");
        check(lookups==0 && writes==0 && ownershipChecks==1,"no lookup after ownership refusal");writable=true;
        missing=true;expectFailure(()->NeverNetherSubstrateR10.proposeBlock(world,pos(100),plant),"missing chunk not suppressed");missing=false;
        var middle=chunk.getSection(chunk.getSectionIndex(100));var saved=middle.neverNetherR10Data;middle.neverNetherR10Data=null;
        expectFailure(()->NeverNetherSubstrateR10.proposeBlock(world,pos(100),plant),"missing substrate not suppressed");middle.neverNetherR10Data=saved;
        // Exercise actual private flora view's setBlock path without constructing
        // a fake WorldGenRegion. Reflection is test-only, not shipped in the runtime.
        Class<?> viewClass=Class.forName("net.minecraft.world.level.levelgen.placement.NeverNetherFloraCandidateR8$View");
        var ctor=viewClass.getDeclaredConstructor(WorldGenLevel.class,RandomSource.class,boolean.class);ctor.setAccessible(true);
        Object view=ctor.newInstance(world,RandomSource.create(1),false);
        var proxyField=viewClass.getDeclaredField("proxy");proxyField.setAccessible(true);
        var planned=(WorldGenLevel)proxyField.get(view);
        var mapField=viewClass.getDeclaredField("writes");mapField.setAccessible(true);
        for(int y:invalid) {
            resetCounters();check(!planned.setBlock(pos(y),plant,18,27),"planner rejects Y"+y);
            check(((Map<?,?>)mapField.get(view)).isEmpty(),"invalid write not queued Y"+y);
            check(lookups==0 && writes==0 && ownershipChecks==0,"planner rejection has no world calls Y"+y);
        }
        resetCounters();check(planned.setBlock(pos(511),plant,18,27),"planner allows below roof");
        check(((Map<?,?>)mapField.get(view)).size()==1 && ownershipChecks==1,"valid planner path retained");
        check(NeverNetherHeightR14.ROOF_Y==512 && NeverNetherHeightR14.HEIGHT==656,"height not expanded");
        output.println("BUG01 FIXED: "+checks+" native proposal, section, metadata, flags and planner checks passed; no natural-world acceptance claimed");
    }
}
