package net.minecraft.world.level.levelgen.structure.templatesystem;

import com.mojang.serialization.Codec;
import com.mojang.serialization.DataResult;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.level.WorldGenRegion;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.ServerLevelAccessor;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import org.jspecify.annotations.Nullable;

/** Native 26.2 adapters. No direct world writes and no mutable, shared RNG. */
public final class NeverNetherNativeProcessors {
    private NeverNetherNativeProcessors() { }
    private static final Identifier EMPTY = Identifier.fromNamespaceAndPath("minecraft", "empty");
    private static final Codec<Float> SCALE = Codec.FLOAT.validate(v -> Float.isFinite(v) && v > 0.0f
        ? DataResult.success(v) : DataResult.error(() -> "Scale must be finite and positive"));

    public static void register(Registry<MapCodec<? extends StructureProcessor>> registry) {
        Registry.register(registry, Identifier.fromNamespaceAndPath("neverfolia", "structure_void"), VoidFilter.CODEC);
        Registry.register(registry, Identifier.fromNamespaceAndPath("neverfolia", "noise_replace_properties"), NoiseProperties.CODEC);
        Registry.register(registry, Identifier.fromNamespaceAndPath("neverfolia", "random_replace_properties"), RandomProperties.CODEC);
        Registry.register(registry, Identifier.fromNamespaceAndPath("neverfolia", "vertical_pillar"), VerticalPillar.CODEC);
    }

    private static <T extends Comparable<T>> String valueName(BlockState state, Property<T> property) {
        return property.getName(state.getValue(property));
    }
    private static <T extends Comparable<T>> BlockState assign(BlockState state, Property<T> property, String value) {
        return property.getValue(value).map(v -> state.setValue(property, v)).orElse(state);
    }
    public static BlockState copyProperties(BlockState source, BlockState destination) {
        for (Property<?> property : source.getProperties()) {
            Property<?> target = destination.getBlock().getStateDefinition().getProperty(property.getName());
            if (target != null) destination = assign(destination, target, valueName(source, property));
        }
        return destination;
    }
    private static StructureTemplate.StructureBlockInfo replace(StructureTemplate.StructureBlockInfo old, Block block) {
        return new StructureTemplate.StructureBlockInfo(old.pos(), copyProperties(old.state(), block.defaultBlockState()), old.nbt());
    }

    public record NoiseProperties(Block input, Block output, float threshold, float xzScale, float yScale) implements StructureProcessor {
        public static final MapCodec<NoiseProperties> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
            BuiltInRegistries.BLOCK.byNameCodec().fieldOf("input_block").forGetter(NoiseProperties::input),
            BuiltInRegistries.BLOCK.byNameCodec().fieldOf("output_block").forGetter(NoiseProperties::output),
            Codec.floatRange(0, 1).fieldOf("threshold").forGetter(NoiseProperties::threshold),
            SCALE.fieldOf("xz_scale").forGetter(NoiseProperties::xzScale),
            SCALE.fieldOf("y_scale").forGetter(NoiseProperties::yScale)
        ).apply(i, NoiseProperties::new));
        public NoiseProperties {
            if (!Float.isFinite(threshold) || threshold < 0 || threshold > 1 ||
                !Float.isFinite(xzScale) || xzScale <= 0 || !Float.isFinite(yScale) || yScale <= 0)
                throw new IllegalArgumentException("Invalid noise parameters");
        }
        @Override public StructureTemplate.StructureBlockInfo processBlock(LevelReader level, BlockPos position, BlockPos reference,
            BlockPos relative, StructureTemplate.StructureBlockInfo info, StructurePlaceSettings settings) {
            if (!info.state().is(input)) return info;
            long seed = level instanceof WorldGenRegion region ? region.getSeed() : 0L;
            // Preserve float coordinate multiplication of the source processor;
            // changing it to double first would change its block pattern.
            double noise = NeverNetherNoise.sample(seed, info.pos().getX() * xzScale, info.pos().getY() * yScale, info.pos().getZ() * xzScale);
            return noise / 2.0 + 0.5 < threshold ? replace(info, output) : info;
        }
        @Override public MapCodec<NoiseProperties> codec() { return CODEC; }
    }

    public record RandomProperties(Block input, Block output, float probability) implements StructureProcessor {
        // Exact supported source profile has one output_block; no output_blocks
        // list is translated by the source converter.
        public static final MapCodec<RandomProperties> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
            BuiltInRegistries.BLOCK.byNameCodec().fieldOf("input_block").forGetter(RandomProperties::input),
            BuiltInRegistries.BLOCK.byNameCodec().fieldOf("output_block").forGetter(RandomProperties::output),
            Codec.floatRange(0, 1).fieldOf("probability").forGetter(RandomProperties::probability)
        ).apply(i, RandomProperties::new));
        public RandomProperties {
            if (!Float.isFinite(probability) || probability < 0 || probability > 1) throw new IllegalArgumentException("Invalid probability");
        }
        @Override public StructureTemplate.StructureBlockInfo processBlock(LevelReader level, BlockPos position, BlockPos reference,
            BlockPos relative, StructureTemplate.StructureBlockInfo info, StructurePlaceSettings settings) {
            if (!info.state().is(input)) return info;
            int offset = 0;
            List<StructureProcessor> list = settings.getProcessors();
            // Identity, not value equality: equal processor configurations can
            // occupy different slots and therefore have different random salts.
            for (int i = 0; i < list.size(); i++) if (list.get(i) == this) { offset = i + 1; break; }
            long packed = info.pos().asLong();
            RandomSource random = RandomSource.create(packed * packed * offset);
            return random.nextFloat() < probability ? replace(info, output) : info;
        }
        @Override public MapCodec<RandomProperties> codec() { return CODEC; }
    }

    public record Replacement(BlockState trigger, BlockState replacement) {
        public static final Codec<Replacement> CODEC = RecordCodecBuilder.create(i -> i.group(
            BlockState.CODEC.fieldOf("trigger").forGetter(Replacement::trigger),
            BlockState.CODEC.fieldOf("replacement").forGetter(Replacement::replacement)
        ).apply(i, Replacement::new));
    }

    public record VerticalPillar(List<Replacement> replacements, Identifier processorList, Direction direction,
                                 Optional<BlockState> originalReplacement, int length, boolean forced) implements StructureProcessor {
        private static final Codec<Direction> VERTICAL = Direction.CODEC.validate(d -> d == Direction.DOWN || d == Direction.UP
            ? DataResult.success(d) : DataResult.error(() -> "Only vertical chunk-owned pillars are supported"));
        private static final Codec<Boolean> NO_FORCE = Codec.BOOL.validate(v -> !v ? DataResult.success(false)
            : DataResult.error(() -> "Forced pillar placement is not supported"));
        public static final MapCodec<VerticalPillar> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
            Replacement.CODEC.listOf().fieldOf("pillar_trigger_and_replacements").forGetter(VerticalPillar::replacements),
            Identifier.CODEC.optionalFieldOf("pillar_processor_list", EMPTY).forGetter(VerticalPillar::processorList),
            VERTICAL.optionalFieldOf("direction", Direction.DOWN).forGetter(VerticalPillar::direction),
            BlockState.CODEC.optionalFieldOf("original_replaced_block").forGetter(VerticalPillar::originalReplacement),
            Codec.intRange(1, 1000).optionalFieldOf("pillar_length", 1000).forGetter(VerticalPillar::length),
            NO_FORCE.optionalFieldOf("forced_placement", false).forGetter(VerticalPillar::forced)
        ).apply(i, VerticalPillar::new));
        public VerticalPillar {
            replacements = List.copyOf(replacements);
            if (replacements.isEmpty() || forced || length < 1 || length > 1000 || (direction != Direction.DOWN && direction != Direction.UP))
                throw new IllegalArgumentException("Unsupported pillar profile");
            var unique = new HashSet<BlockState>();
            for (Replacement replacement : replacements)
                if (!unique.add(replacement.trigger())) throw new IllegalArgumentException("Duplicate pillar trigger");
        }
        private @Nullable BlockState material(BlockState state) {
            for (Replacement replacement : replacements) if (replacement.trigger() == state) return replacement.replacement();
            return null;
        }
        @Override public StructureTemplate.@Nullable StructureBlockInfo processBlock(LevelReader level, BlockPos position, BlockPos reference,
            BlockPos relative, StructureTemplate.StructureBlockInfo info, StructurePlaceSettings settings) {
            BlockState material = material(info.state());
            if (material == null) return info;
            BlockState replacement = originalReplacement.orElse(material);
            return replacement.is(Blocks.STRUCTURE_VOID) ? null : new StructureTemplate.StructureBlockInfo(info.pos(), replacement, info.nbt());
        }
        private boolean owned(ServerLevelAccessor level, StructurePlaceSettings settings, BlockPos pos) {
            var box = settings.getBoundingBox();
            if (box == null || !box.isInside(pos) || pos.getY() < -123 || pos.getY() > 378) return false;
            if (!(level instanceof WorldGenRegion region)) return false;
            return Math.floorDiv(pos.getX(), 16) == region.getCenter().x && Math.floorDiv(pos.getZ(), 16) == region.getCenter().z;
        }
        @Override public List<StructureTemplate.StructureBlockInfo> finalizeProcessing(ServerLevelAccessor level, BlockPos position,
            BlockPos reference, List<StructureTemplate.StructureBlockInfo> original, List<StructureTemplate.StructureBlockInfo> processed,
            StructurePlaceSettings settings) {
            // Worldgen only. A command operating on a live ServerLevel does not
            // gain a path to synchronous chunk loads through this processor.
            if (!(level instanceof WorldGenRegion) || settings.getBoundingBox() == null) return processed;
            var occupied = new HashMap<BlockPos, StructureTemplate.StructureBlockInfo>();
            for (var info : processed) occupied.put(info.pos(), info);
            var result = new ArrayList<>(processed);
            var markers = new ArrayList<>(original);
            markers.sort(Comparator.comparingInt(info -> info.pos().getY()));
            List<StructureProcessor> chain = List.of();
            if (!processorList.equals(EMPTY)) {
                chain = level.registryAccess().lookupOrThrow(Registries.PROCESSOR_LIST).get(processorList).orElseThrow().value().list();
            }
            var pillarSettings = new StructurePlaceSettings();
            for (var processor : chain) pillarSettings.addProcessor(processor);
            for (var marker : markers) {
                BlockState material = material(marker.state());
                if (material == null) continue;
                BlockPos anchor = StructureTemplate.calculateRelativePosition(settings, marker.pos()).offset(position);
                if (!owned(level, settings, anchor) || !occupied.containsKey(anchor)) continue;
                var plan = NeverNetherPillarPlan.plan(anchor.getY(), direction.getStepY(), -123, 378, length, y -> {
                    BlockPos pos = new BlockPos(anchor.getX(), y, anchor.getZ());
                    if (!owned(level, settings, pos)) return NeverNetherPillarPlan.Cell.UNKNOWN;
                    var templateCell = occupied.get(pos);
                    if (templateCell != null) {
                        return templateCell.state().canOcclude() ? NeverNetherPillarPlan.Cell.ANCHOR : NeverNetherPillarPlan.Cell.PROTECTED;
                    }
                    BlockState current = level.getBlockState(pos); // same, already-owned chunk only
                    if (current.hasBlockEntity()) return NeverNetherPillarPlan.Cell.PROTECTED;
                    if (current.isAir() || !current.getFluidState().isEmpty()) return NeverNetherPillarPlan.Cell.REPLACEABLE;
                    return current.canOcclude() ? NeverNetherPillarPlan.Cell.ANCHOR : NeverNetherPillarPlan.Cell.PROTECTED;
                });
                if (plan.reason() != NeverNetherPillarPlan.Reason.ANCHORED) continue;
                var additions = new ArrayList<StructureTemplate.StructureBlockInfo>();
                boolean solid = true;
                for (int y : plan.y()) {
                    BlockPos pos = new BlockPos(anchor.getX(), y, anchor.getZ());
                    var info = new StructureTemplate.StructureBlockInfo(pos, material, null);
                    for (var processor : chain) {
                        if (processor instanceof VerticalPillar) continue; // no recursive pillar expansion
                        info = processor.processBlock(level, position, reference, pos.subtract(position), info, pillarSettings);
                        if (info == null) break;
                    }
                    if (info == null || !info.state().canOcclude() || info.state().hasBlockEntity()) { solid = false; break; }
                    additions.add(info);
                }
                if (solid) for (var info : additions) {
                    if (occupied.putIfAbsent(info.pos(), info) == null) result.add(info);
                }
            }
            return result;
        }
        @Override public MapCodec<VerticalPillar> codec() { return CODEC; }
    }

    /** Suppress processor-produced structure void without placing or deleting a world block. */
    public record VoidFilter() implements StructureProcessor {
        public static final VoidFilter INSTANCE = new VoidFilter();
        public static final MapCodec<VoidFilter> CODEC = MapCodec.unit(INSTANCE);
        @Override public StructureTemplate.@Nullable StructureBlockInfo processBlock(LevelReader level, BlockPos position, BlockPos reference,
            BlockPos relative, StructureTemplate.StructureBlockInfo info, StructurePlaceSettings settings) {
            return info.state().is(Blocks.STRUCTURE_VOID) ? null : info;
        }
        @Override public MapCodec<VoidFilter> codec() { return CODEC; }
    }
}
