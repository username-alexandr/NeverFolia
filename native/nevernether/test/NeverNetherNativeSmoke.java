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
        System.out.println("NeverNether native 26.2 bootstrap/codec smoke: " + checks + " checks passed; no worldgen performed");
    }
}
