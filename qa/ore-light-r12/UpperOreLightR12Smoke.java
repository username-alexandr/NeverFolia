package net.minecraft.world.level.chunk;

import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.lighting.LevelLightEngine;

/** Native test of an explicit late-vein schedule, not a replay of all vanilla
 * decoration. No neighbour chunk is fetched or mutated by the pruning pass. */
public final class UpperOreLightR12Smoke {
    private static final long SEED = -2996952393010080672L;
    private static int checks;
    private static void check(boolean value, String why) {
        if (!value) throw new AssertionError(why);
        ++checks;
    }
    private static ProtoChunk chunk() {
        var biome = new Biome.BiomeBuilder().hasPrecipitation(false).temperature(.5f).downfall(0)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder = Holder.direct(biome);
        var ids = new IdMapper<Holder<Biome>>(); ids.add(holder);
        var factory = new PalettedContainerFactory(
            Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY), Blocks.AIR.defaultBlockState(), null,
            Strategy.createForBiomes(ids), holder, null, null);
        var c = new ProtoChunk(new ChunkPos(12,10), UpgradeData.EMPTY, LevelHeightAccessor.create(-512,1024), factory, null);
        c.setLightEngine(LevelLightEngine.EMPTY);
        c.setPersistedStatus(ChunkStatus.INITIALIZE_LIGHT);
        return c;
    }
    private static void set(ProtoChunk c, BlockPos p, BlockState s) {
        var section = c.getSection(c.getSectionIndex(p.getY()));
        section.getStates().set(p.getX() & 15, p.getY() & 15, p.getZ() & 15, s);
        section.recalcBlockCounts();
    }
    private static ProtoChunk buriedHost(BlockPos p) {
        var c = chunk();
        set(c,p,Blocks.DEEPSLATE.defaultBlockState());
        for (var d : Direction.values()) set(c,p.relative(d),Blocks.DEEPSLATE.defaultBlockState());
        return c;
    }
    private static void finish(ProtoChunk c) {
        NeverOverworldOreExposurePruner.pruneUpperAtLight(SEED,c);
        NeverOverworldOreScarcityFieldR10.thin(SEED,c);
    }
    private static void lateVeinRegression() {
        var p = new BlockPos(195,-58,166);
        var ore = Blocks.DEEPSLATE_COAL_ORE.defaultBlockState();
        check(NeverOverworldOreScarcityFieldR10.retain(SEED,p.getX(),p.getY(),p.getZ(),1,25),"witness must survive final25 mask");

        // Model the OLD timing with the actual upper-pruning algorithm:
        // prune a complete local pass, then let a neighbouring vein write late.
        var formerlyEarly = buriedHost(p);
        set(formerlyEarly,p,ore);
        NeverOverworldOreExposurePruner.pruneUpperAtLight(SEED,formerlyEarly);
        NeverOverworldOreScarcityFieldR10.thin(SEED,formerlyEarly);
        var formerlyLate = buriedHost(p);
        NeverOverworldOreExposurePruner.pruneUpperAtLight(SEED,formerlyLate);
        set(formerlyLate,p,ore);
        NeverOverworldOreScarcityFieldR10.thin(SEED,formerlyLate);
        check(formerlyEarly.getBlockState(p).is(Blocks.DEEPSLATE),"upper policy removes witness");
        check(formerlyLate.getBlockState(p).is(Blocks.DEEPSLATE_COAL_ORE),"late deposit bypasses early upper prune");

        // Corrected lifecycle: old entry point is inert, including absence of
        // any ServerLevel access; all deposits precede the one LIGHT pass.
        var early = buriedHost(p);
        set(early,p,ore);
        NeverOverworldOreExposurePruner.applyAfterFeatures(null,early);
        check(early.getBlockState(p).equals(ore),"local FEATURES cannot free the ore host");
        var late = buriedHost(p);
        NeverOverworldOreExposurePruner.applyAfterFeatures(null,late);
        set(late,p,ore);
        finish(early); finish(late);
        check(early.getBlockState(p).equals(late.getBlockState(p)),"pruning result independent of this late-vein schedule");
        check(early.getBlockState(p).is(Blocks.DEEPSLATE),"late deposit must not escape upper policy");
        finish(early);
        check(early.getBlockState(p).is(Blocks.DEEPSLATE),"LIGHT pruning idempotence");
    }
    private static void invalidStagesRemainUnchanged() {
        var p = new BlockPos(195,-58,166);
        for (var status : new ChunkStatus[]{ChunkStatus.FEATURES,ChunkStatus.FULL}) {
            var c=buriedHost(p); set(c,p,Blocks.DEEPSLATE_COAL_ORE.defaultBlockState());
            c.setPersistedStatus(status);
            boolean rejected=false;
            try { NeverOverworldOreExposurePruner.pruneUpperAtLight(SEED,c); }
            catch (IllegalStateException expected) { rejected=true; }
            check(rejected,"prune rejects "+status);
            check(c.getBlockState(p).is(Blocks.DEEPSLATE_COAL_ORE),"rejected stage never edits blocks");
        }
    }
    public static void main(String[] args) {
        var out=System.out;
        SharedConstants.tryDetectVersion(); Bootstrap.bootStrap();
        lateVeinRegression(); invalidStagesRemainUnchanged();
        out.println("PASS UpperOreLightR12Smoke checks="+checks+" early-prune-bypass/late-vein/LIGHT/FULL-guard");
        out.flush();
        if(out.checkError()) throw new IllegalStateException("Native smoke output failed");
    }
}
