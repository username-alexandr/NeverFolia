package net.minecraft.world.level.chunk;

import java.util.ArrayList;
import java.util.BitSet;
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.StructureStart;
import net.minecraft.world.level.levelgen.structure.structures.MineshaftStructure;
import org.bukkit.NamespacedKey;
import org.bukkit.persistence.PersistentDataType;

/** Per-PIECE dry mineshaft protection. Recorded in every referenced owner chunk
 * during FEATURES, including the one-block shell references. Chunk PDC persists
 * the geometry if a pre-FULL chunk is saved/reloaded. No LIGHT neighbour access,
 * no rectangular village reclamation, no whole-mineshaft aggregate-box fill.
 */
public final class NeverOverworldDryMinesR12 {
    private static final NamespacedKey KEY = new NamespacedKey("neverfolia", "dry_mines_r12");
    private static final int MAX_BOXES = 4096;
    private static final Comparator<BoundingBox> ORDER = Comparator.comparingInt(BoundingBox::minX)
        .thenComparingInt(BoundingBox::minY).thenComparingInt(BoundingBox::minZ)
        .thenComparingInt(BoundingBox::maxX).thenComparingInt(BoundingBox::maxY).thenComparingInt(BoundingBox::maxZ);
    private NeverOverworldDryMinesR12() {}

    static boolean scope(WorldGenLevel level) {
        return level.getLevel().dimension().equals(Level.OVERWORLD) && level.getMinY() == -512 && level.getHeight() == 1024;
    }

    static boolean mine(WorldGenLevel level, StructureStart start) {
        if (start.getStructure() instanceof MineshaftStructure) return true;
        var id = level.registryAccess().lookupOrThrow(Registries.STRUCTURE).getKey(start.getStructure());
        return id != null && id.toString().equals("neverfolia:collapsed_mine");
    }

    public static BoundingBox referenceBox(WorldGenLevel level, StructureStart start) {
        BoundingBox box = start.getBoundingBox();
        return scope(level) && mine(level, start) ? box.inflatedBy(1) : box;
    }

    public static void record(WorldGenLevel level, StructureStart start, ChunkPos owner) {
        if (!scope(level) || !start.isValid() || !mine(level, start)) return;
        // StructureStart is already placing this owner chunk in WorldGenRegion.
        // This is not a LIGHT-stage lookup of mutable neighbouring terrain.
        ChunkAccess chunk = level.getChunk(owner.x(), owner.z());
        if (chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) return;
        List<BoundingBox> pieces = new ArrayList<>();
        for (var piece : start.getPieces()) pieces.add(piece.getBoundingBox());
        recordBoxes(chunk, pieces);
    }

    static void recordBoxes(ChunkAccess chunk, List<BoundingBox> pieces) {
        if (chunk.getMinY() != -512 || chunk.getHeight() != 1024
            || chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) {
            throw new IllegalStateException("Dry mine geometry requires a new NeverOverworld chunk");
        }
        TreeSet<BoundingBox> all = new TreeSet<>(ORDER);
        all.addAll(readBoxes(chunk));
        int x = chunk.getPos().getMinBlockX(), z = chunk.getPos().getMinBlockZ();
        for (BoundingBox box : pieces) {
            if (box.inflatedBy(1).intersects(x, z, x + 15, z + 15)) all.add(box);
        }
        if (all.size() > MAX_BOXES) throw new IllegalStateException("Unbounded mineshaft piece count");
        if (all.isEmpty()) return;
        int[] values = new int[2 + 6*all.size()]; values[0] = 1; values[1] = all.size();
        int i = 2;
        for (BoundingBox b : all) {
            values[i++] = b.minX(); values[i++] = b.minY(); values[i++] = b.minZ();
            values[i++] = b.maxX(); values[i++] = b.maxY(); values[i++] = b.maxZ();
        }
        chunk.persistentDataContainer.set(KEY, PersistentDataType.INTEGER_ARRAY, values);
        chunk.neverOverworldDryMineMaskR12 = null;
    }

    private static List<BoundingBox> readBoxes(ChunkAccess chunk) {
        int[] values = chunk.persistentDataContainer.get(KEY, PersistentDataType.INTEGER_ARRAY);
        if (values == null) return List.of();
        if (values.length < 2 || values[0] != 1 || values[1] < 1 || values[1] > MAX_BOXES
            || values.length != 2 + 6*values[1]) throw new IllegalStateException("Invalid dry mineshaft metadata");
        List<BoundingBox> boxes = new ArrayList<>();
        for (int i = 2; i < values.length; i += 6) {
            if (values[i] > values[i+3] || values[i+1] > values[i+4] || values[i+2] > values[i+5]
                || (long)values[i+3]-values[i] > 256 || (long)values[i+5]-values[i+2] > 256
                || values[i+1] < -512 || values[i+4] > 511) {
                throw new IllegalStateException("Invalid dry mineshaft piece bounds");
            }
            boxes.add(new BoundingBox(values[i],values[i+1],values[i+2],values[i+3],values[i+4],values[i+5]));
        }
        return boxes;
    }

    public static final class Mask {
        final BitSet interior = new BitSet();
        final BitSet envelope = new BitSet();
    }

    static Mask mask(ChunkAccess chunk) {
        Mask mask = new Mask();
        for (BoundingBox box : readBoxes(chunk)) {
            paint(mask.interior, box, chunk);
            paint(mask.envelope, box.inflatedBy(1), chunk);
        }
        return mask;
    }

    private static void paint(BitSet bits, BoundingBox box, ChunkAccess chunk) {
        int bx = chunk.getPos().getMinBlockX(), bz = chunk.getPos().getMinBlockZ();
        int minX = Math.max(bx, box.minX()), maxX = Math.min(bx+15, box.maxX());
        int minZ = Math.max(bz, box.minZ()), maxZ = Math.min(bz+15, box.maxZ());
        int minY = Math.max(chunk.getMinY()+1, box.minY());
        int maxY = Math.min(128, box.maxY());
        for (int y = minY; y <= maxY; ++y) for (int z = minZ; z <= maxZ; ++z) {
            if (minX <= maxX) bits.set(index(minX-bx,y,z-bz,chunk), index(maxX-bx,y,z-bz,chunk)+1);
        }
    }

    private static int index(int x, int y, int z, ChunkAccess chunk) {
        return ((y-chunk.getMinY())<<8)|(z<<4)|x;
    }

    public static boolean protectedCell(ChunkAccess chunk, BlockPos pos) {
        Mask mask = chunk.neverOverworldDryMineMaskR12;
        if (mask == null) return false;
        int x = pos.getX()-chunk.getPos().getMinBlockX(), z = pos.getZ()-chunk.getPos().getMinBlockZ();
        return x>=0 && x<16 && z>=0 && z<16 && pos.getY()>=chunk.getMinY() && pos.getY()<chunk.getMaxY()
            && mask.interior.get(index(x,pos.getY(),z,chunk));
    }

    /** A one-block natural-rock envelope closes fluid entrances while preserving
     * every union-of-pieces corridor junction, rail, support, loot and spawner.
     * Only shell air/pure fluids become host rock; existing structures are not
     * replaced. This prevents later fluid ticks from immediately refilling the
     * newly drained corridors, rather than repeatedly deleting water on ticks.
     */
    public static int prepare(ChunkAccess chunk) {
        if (chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) return 0;
        if (chunk.getMinY()!=-512 || chunk.getHeight()!=1024) throw new IllegalStateException("Wrong dry mine envelope");
        Mask mask = mask(chunk);
        chunk.neverOverworldDryMineMaskR12 = mask;
        int changed = 0;
        BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        for (int i = mask.envelope.nextSetBit(0); i >= 0; i = mask.envelope.nextSetBit(i+1)) {
            int y=chunk.getMinY()+(i>>>8);
            pos.set(chunk.getPos().getMinBlockX()+(i&15), y, chunk.getPos().getMinBlockZ()+((i>>>4)&15));
            BlockState state = chunk.getBlockState(pos), replacement = state;
            if (mask.interior.get(i)) {
                if (state.is(Blocks.WATER) || state.is(Blocks.LAVA)) replacement=Blocks.AIR.defaultBlockState();
                else if (state.hasProperty(BlockStateProperties.WATERLOGGED) && state.getValue(BlockStateProperties.WATERLOGGED)) {
                    replacement=state.setValue(BlockStateProperties.WATERLOGGED,false);
                }
            } else if (state.isAir() || state.is(Blocks.WATER) || state.is(Blocks.LAVA)) {
                replacement=(y<0 ? Blocks.DEEPSLATE : Blocks.STONE).defaultBlockState();
            }
            if (replacement != state) { chunk.setBlockState(pos,replacement,0); ++changed; }
        }
        return changed;
    }
}
