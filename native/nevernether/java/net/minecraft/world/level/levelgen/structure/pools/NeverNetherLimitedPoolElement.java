package net.minecraft.world.level.levelgen.structure.pools;

import com.mojang.datafixers.util.Either;
import com.mojang.serialization.Codec;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import net.minecraft.core.Holder;
import net.minecraft.resources.Identifier;
import net.minecraft.world.level.levelgen.structure.PoolElementStructurePiece;
import net.minecraft.world.level.levelgen.structure.templatesystem.LiquidSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessorList;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate;

/** Native 26.2 single element with a per-structure, group-name quota.
 * No YUNG API dependency and no mutable processor/global/thread-local counters.
 * Source conversion is NOT enabled until the whole monument port is validated.
 */
public final class NeverNetherLimitedPoolElement extends SinglePoolElement {
    public static final MapCodec<NeverNetherLimitedPoolElement> CODEC = RecordCodecBuilder.mapCodec(
        builder -> builder.group(
            NeverNetherLimitedPoolElement.<NeverNetherLimitedPoolElement>templateCodec(),
            NeverNetherLimitedPoolElement.<NeverNetherLimitedPoolElement>processorsCodec(),
            NeverNetherLimitedPoolElement.<NeverNetherLimitedPoolElement>projectionCodec(),
            NeverNetherLimitedPoolElement.<NeverNetherLimitedPoolElement>overrideLiquidSettingsCodec(),
            Codec.STRING.fieldOf("name").forGetter(element -> element.group),
            Codec.intRange(0, 1024).fieldOf("max_count").forGetter(element -> element.limit)
        ).apply(builder, NeverNetherLimitedPoolElement::new)
    );
    private final String group;
    private final int limit;

    public NeverNetherLimitedPoolElement(
        Either<Identifier, StructureTemplate> template,
        Holder<StructureProcessorList> processors,
        StructureTemplatePool.Projection projection,
        Optional<LiquidSettings> liquids,
        String group, int limit
    ) {
        super(template, processors, projection, liquids);
        NeverNetherPieceBudget.Entry validated = new NeverNetherPieceBudget.Entry(group, limit);
        this.group = validated.group();
        this.limit = validated.limit();
    }

    @Override
    public StructurePoolElementType<?> getType() {
        return StructurePoolElementType.NEVERFOLIA_LIMITED_SINGLE;
    }

    public static boolean canAppend(StructurePoolElement candidate, List<?> acceptedPieces) {
        List<NeverNetherPieceBudget.Entry> requested = new ArrayList<>();
        collect(candidate, requested, 0);
        if (requested.isEmpty()) return true;
        List<NeverNetherPieceBudget.Entry> accepted = new ArrayList<>();
        for (Object existing : acceptedPieces) {
            if (existing instanceof PoolElementStructurePiece piece) {
                collect(piece.getElement(), accepted, 0);
            } else {
                throw new IllegalArgumentException("Unexpected non-pool piece in jigsaw quota input");
            }
        }
        return NeverNetherPieceBudget.allows(accepted, requested);
    }

    private static void collect(StructurePoolElement element, List<NeverNetherPieceBudget.Entry> into, int depth) {
        if (depth > 64) throw new IllegalArgumentException("Nested pool elements exceed quota traversal limit");
        if (element instanceof NeverNetherLimitedPoolElement limited) {
            into.add(new NeverNetherPieceBudget.Entry(limited.group, limited.limit));
        } else if (element instanceof ListPoolElement list) {
            // Traverse all children, not only the first (which owns the jigsaws).
            for (StructurePoolElement child : list.neverfoliaQuotaChildren()) collect(child, into, depth + 1);
        }
    }
}
