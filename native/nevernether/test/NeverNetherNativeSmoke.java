package net.minecraft.world.level.levelgen.structure.pools;

import com.mojang.datafixers.util.Either;
import com.mojang.serialization.JsonOps;
import java.util.List;
import java.util.Optional;
import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.structure.templatesystem.*;

/** Isolated registry/codec smoke test, copied into CI sources only. No world is created. */
public final class NeverNetherNativeSmoke {
    private static int checks;
    private static void check(boolean condition, String name) {
        if (!condition) throw new AssertionError(name);
        checks++;
    }
    private static NeverNetherLimitedPoolElement element(String name, int count) {
        return new NeverNetherLimitedPoolElement(
            Either.left(Identifier.fromNamespaceAndPath("neverfolia", "qa/template")),
            Holder.direct(new StructureProcessorList(List.of())),
            StructureTemplatePool.Projection.RIGID, Optional.empty(), name, count);
    }
    public static void main(String[] args) {
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();
        var type = BuiltInRegistries.STRUCTURE_POOL_ELEMENT
            .getOptional(Identifier.fromNamespaceAndPath("neverfolia", "limited_single_pool_element")).orElseThrow();
        check(type == StructurePoolElementType.NEVERFOLIA_LIMITED_SINGLE, "native element registry");
        var filter = BuiltInRegistries.STRUCTURE_PROCESSOR
            .getOptional(Identifier.fromNamespaceAndPath("neverfolia", "structure_void")).orElseThrow();
        check(filter == NeverNetherNativeProcessors.VoidFilter.CODEC, "native processor registry");
        var a = element("same-group", 1);
        var b = element("same-group", 1);
        check(NeverNetherLimitedPoolElement.canAppend(a, List.of()), "single fits empty start");
        check(!NeverNetherLimitedPoolElement.canAppend(element("zero", 0), List.of()), "zero root rejected");
        var nested = new ListPoolElement(List.of(a, b), StructureTemplatePool.Projection.RIGID);
        check(!NeverNetherLimitedPoolElement.canAppend(nested, List.of()), "nested duplicate group rejected");
        var different = new ListPoolElement(List.of(a, element("other-group", 1)), StructureTemplatePool.Projection.RIGID);
        check(NeverNetherLimitedPoolElement.canAppend(different, List.of()), "independent nested groups accepted");
        var encoded = NeverNetherLimitedPoolElement.CODEC.codec().encodeStart(JsonOps.INSTANCE, a).getOrThrow();
        var decoded = NeverNetherLimitedPoolElement.CODEC.codec().parse(JsonOps.INSTANCE, encoded).getOrThrow();
        check(decoded.getType() == type, "codec roundtrip type");
        check(encoded.getAsJsonObject().get("max_count").getAsInt() == 1, "codec preserves limit");
        check(encoded.getAsJsonObject().get("name").getAsString().equals("same-group"), "codec preserves group");
        encoded.getAsJsonObject().addProperty("max_count", -1);
        check(NeverNetherLimitedPoolElement.CODEC.codec().parse(JsonOps.INSTANCE, encoded).error().isPresent(), "codec rejects negative limit");
        var voidBlock = new StructureTemplate.StructureBlockInfo(BlockPos.ZERO, Blocks.STRUCTURE_VOID.defaultBlockState(), null);
        var stoneBlock = new StructureTemplate.StructureBlockInfo(BlockPos.ZERO, Blocks.BLACKSTONE.defaultBlockState(), null);
        var settings = new StructurePlaceSettings();
        var processor = NeverNetherNativeProcessors.VoidFilter.INSTANCE;
        check(processor.processBlock(null, BlockPos.ZERO, BlockPos.ZERO, BlockPos.ZERO, voidBlock, settings) == null, "void suppressed");
        check(processor.processBlock(null, BlockPos.ZERO, BlockPos.ZERO, BlockPos.ZERO, stoneBlock, settings) == stoneBlock, "solid untouched");
        r5Checks();
        System.out.println("NeverNether native 26.2 bootstrap/codec smoke: " + checks + " checks passed; no worldgen performed");
    }
    private static void r5Checks() {
        for (String id : List.of("noise_replace_properties", "random_replace_properties", "vertical_pillar")) {
            check(BuiltInRegistries.STRUCTURE_PROCESSOR.getOptional(Identifier.fromNamespaceAndPath("neverfolia", id)).isPresent(), "R5 registered " + id);
        }
        var random = new NeverNetherNativeProcessors.RandomProperties(Blocks.RED_NETHER_BRICK_STAIRS, Blocks.NETHER_BRICK_STAIRS, 1.0f);
        var settings = new StructurePlaceSettings().addProcessor(random);
        for (var state : Blocks.RED_NETHER_BRICK_STAIRS.getStateDefinition().getPossibleStates()) {
            var input = new StructureTemplate.StructureBlockInfo(new BlockPos(-17, 31, 16), state, null);
            var out = random.processBlock(null, BlockPos.ZERO, BlockPos.ZERO, BlockPos.ZERO, input, settings);
            check(out.state().is(Blocks.NETHER_BRICK_STAIRS) && out.state().getValues().equals(state.getValues()), "all stair properties preserved");
        }
        var slab = Blocks.RED_NETHER_BRICK_SLAB.defaultBlockState().setValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.SLAB_TYPE, net.minecraft.world.level.block.state.properties.SlabType.TOP);
        check(NeverNetherNativeProcessors.copyProperties(slab, Blocks.NETHER_BRICK_SLAB.defaultBlockState()).getValues().equals(slab.getValues()), "slab properties retained");
        var zero = new NeverNetherNativeProcessors.RandomProperties(Blocks.RED_NETHER_BRICKS, Blocks.NETHER_BRICKS, 0.0f);
        var info = new StructureTemplate.StructureBlockInfo(BlockPos.ZERO, Blocks.RED_NETHER_BRICKS.defaultBlockState(), null);
        check(zero.processBlock(null, BlockPos.ZERO, BlockPos.ZERO, BlockPos.ZERO, info, new StructurePlaceSettings()) == info, "probability zero");
        var encoded = NeverNetherNativeProcessors.RandomProperties.CODEC.codec().encodeStart(JsonOps.INSTANCE, random).getOrThrow();
        check(NeverNetherNativeProcessors.RandomProperties.CODEC.codec().parse(JsonOps.INSTANCE, encoded).getOrThrow().equals(random), "random codec roundtrip");
        encoded.getAsJsonObject().addProperty("probability", -1);
        check(NeverNetherNativeProcessors.RandomProperties.CODEC.codec().parse(JsonOps.INSTANCE, encoded).error().isPresent(), "reject invalid probability");
        for (int slot = 0; slot < 4; slot++) {
            var r = new NeverNetherNativeProcessors.RandomProperties(Blocks.RED_NETHER_BRICKS, Blocks.NETHER_BRICKS, 0.25f);
            var list = new StructurePlaceSettings();
            for (int j = 0; j < slot; j++) list.addProcessor(NeverNetherNativeProcessors.VoidFilter.INSTANCE);
            list.addProcessor(r);
            for (int i = -100; i < 100; i++) {
                var pos = new BlockPos(i * 13, i % 17, -i * 23);
                var input = new StructureTemplate.StructureBlockInfo(pos, Blocks.RED_NETHER_BRICKS.defaultBlockState(), null);
                long packed = pos.asLong();
                boolean expected = new java.util.Random(packed * packed * (slot + 1)).nextFloat() < 0.25f;
                check(r.processBlock(null, BlockPos.ZERO, BlockPos.ZERO, BlockPos.ZERO, input, list).state().is(Blocks.NETHER_BRICKS) == expected, "source-compatible random salt");
            }
        }
        var noise = new NeverNetherNativeProcessors.NoiseProperties(Blocks.RED_NETHER_BRICKS, Blocks.NETHER_BRICKS, 0.35f, 0.2f, 0.2f);
        var noiseJson = NeverNetherNativeProcessors.NoiseProperties.CODEC.codec().encodeStart(JsonOps.INSTANCE, noise).getOrThrow();
        check(NeverNetherNativeProcessors.NoiseProperties.CODEC.codec().parse(JsonOps.INSTANCE, noiseJson).getOrThrow().equals(noise), "noise codec roundtrip");
        noiseJson.getAsJsonObject().addProperty("xz_scale", 0);
        check(NeverNetherNativeProcessors.NoiseProperties.CODEC.codec().parse(JsonOps.INSTANCE, noiseJson).error().isPresent(), "reject zero scale");
        for (long seed = -20; seed < 20; seed++) {
            var reference = new net.minecraft.world.level.levelgen.structure.templatesystem.noise.OpenSimplex2F(seed);
            for (int i = -40; i < 40; i++) {
                double x = i * 0.2f, y = (i + 10) * 0.21f, z = i * -0.32f;
                check(Double.doubleToLongBits(NeverNetherNoise.sample(seed, x, y, z)) == Double.doubleToLongBits(reference.noise3_Classic(x, y, z)), "CC0 noise wrapper parity");
            }
        }
        var triggers = List.of(new NeverNetherNativeProcessors.Replacement(Blocks.BLUE_STAINED_GLASS.defaultBlockState(), Blocks.POLISHED_BLACKSTONE_BRICKS.defaultBlockState()));
        var pillar = new NeverNetherNativeProcessors.VerticalPillar(triggers, Identifier.fromNamespaceAndPath("minecraft", "empty"), net.minecraft.core.Direction.DOWN, Optional.empty(), 1000, false);
        var pjson = NeverNetherNativeProcessors.VerticalPillar.CODEC.codec().encodeStart(JsonOps.INSTANCE, pillar).getOrThrow();
        check(NeverNetherNativeProcessors.VerticalPillar.CODEC.codec().parse(JsonOps.INSTANCE, pjson).getOrThrow().equals(pillar), "pillar codec roundtrip");
        pjson.getAsJsonObject().addProperty("direction", "north");
        check(NeverNetherNativeProcessors.VerticalPillar.CODEC.codec().parse(JsonOps.INSTANCE, pjson).error().isPresent(), "reject cross-chunk horizontal pillar");
        pjson.getAsJsonObject().addProperty("direction", "down");
        pjson.getAsJsonObject().addProperty("forced_placement", true);
        check(NeverNetherNativeProcessors.VerticalPillar.CODEC.codec().parse(JsonOps.INSTANCE, pjson).error().isPresent(), "reject forced destruction");
        var marker = new StructureTemplate.StructureBlockInfo(BlockPos.ZERO, Blocks.BLUE_STAINED_GLASS.defaultBlockState(), null);
        var changed = pillar.processBlock(null, BlockPos.ZERO, BlockPos.ZERO, BlockPos.ZERO, marker, settings);
        check(changed.state().is(Blocks.POLISHED_BLACKSTONE_BRICKS), "marker replaced without world write");
        check(pillar.finalizeProcessing(null, BlockPos.ZERO, BlockPos.ZERO, List.of(marker), List.of(changed), settings).equals(List.of(changed)), "live/unknown world is not accessed");
    }

}
