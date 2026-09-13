package net.minecraft.world.level.levelgen.structure.templatesystem;

import com.mojang.serialization.MapCodec;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Registry;
import net.minecraft.resources.Identifier;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.block.Blocks;
import org.jspecify.annotations.Nullable;

/** First native adapter only. Other monument processors deliberately remain blocked. */
public final class NeverNetherNativeProcessors {
    private NeverNetherNativeProcessors() { }

    public static void register(Registry<MapCodec<? extends StructureProcessor>> registry) {
        Registry.register(registry, Identifier.fromNamespaceAndPath("neverfolia", "structure_void"), VoidFilter.CODEC);
    }

    /** Suppress processor-produced structure void without placing or deleting a world block. */
    public record VoidFilter() implements StructureProcessor {
        public static final VoidFilter INSTANCE = new VoidFilter();
        public static final MapCodec<VoidFilter> CODEC = MapCodec.unit(INSTANCE);

        @Override
        public StructureTemplate.@Nullable StructureBlockInfo processBlock(
            LevelReader level, BlockPos targetPosition, BlockPos referencePos,
            BlockPos templateRelativePos, StructureTemplate.StructureBlockInfo processed,
            StructurePlaceSettings settings
        ) {
            return processed.state().is(Blocks.STRUCTURE_VOID) ? null : processed;
        }

        @Override
        public MapCodec<VoidFilter> codec() { return CODEC; }
    }
}
