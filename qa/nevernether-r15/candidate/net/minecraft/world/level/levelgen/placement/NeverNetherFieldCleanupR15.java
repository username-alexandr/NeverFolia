package net.minecraft.world.level.levelgen.placement;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.serialization.MapCodec;
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.ZipFile;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessor;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate;

/**
 * R15 field cleanup for defects proven to exist in the immutable CARVERS
 * substrate before R10 capture.
 *
 * <p>Only owner-chunk state is inspected. Tiny fully enclosed air components
 * of at most four blocks are filled only when every known boundary block is
 * natural Nether rock and the component never touches a chunk/Y boundary.
 * Unsupported source-lava shelf cells are solidified only when the cell has air
 * below and at least two horizontal source-lava neighbours. Large caves,
 * boundary-connected air and lavafall/edge cells are preserved.</p>
 */
public final class NeverNetherFieldCleanupR15 {
    static final int MIN_Y = -128;
    static final int MAX_Y = 511;
    static final int MAX_MICRO_POCKET = 4;
    static final String NATIVE_PROFILE = "NN-R15-FIELD-CLEANUP-1";
    private static final String HEIGHT_LOCK = ".neverfolia-nevernether-height.lock";
    private static final String NATIVE_LOCK = ".neverfolia-nevernether-native.lock";
    private static final String PACK_FINGERPRINT = "nevernether-worldgen-fingerprint.json";
    private static final String NATIVE_MARKER = "data/neverfolia/nevernether/native_profile.json";
    private static final int[][] DIRECTIONS = {
        {1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}
    };
    private static final int[][] HORIZONTAL = {
        {1,0},{-1,0},{0,1},{0,-1}
    };

    private NeverNetherFieldCleanupR15() {}

    public static Result clean(final ChunkAccess chunk) {
        validateEnvelope(chunk);
        final int pockets = fillMicroPockets(chunk, false);
        final int shelves = solidifyHangingLava(chunk);
        return new Result(pockets, shelves);
    }

    public static Result afterFeatures(final WorldGenLevel level, final ChunkAccess chunk) {
        if (!level.getLevel().dimension().equals(Level.NETHER)
            || level.getMinY() != MIN_Y
            || level.getHeight() != NeverNetherHeightR14.HEIGHT
            || chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)
            || chunk.hasAnyStructureReferences()) {
            return new Result(0, 0);
        }
        validateEnvelope(chunk);
        return new Result(fillMicroPockets(chunk, true), 0);
    }

    public static void verifyNativeRevision(final Path worldRoot, final Path datapackDir) {
        try {
            final Path heightLock = worldRoot.resolve(HEIGHT_LOCK);
            final Path nativeLock = worldRoot.resolve(NATIVE_LOCK);

            if (!Files.exists(heightLock)) {
                if (Files.exists(nativeLock)) {
                    throw new IllegalStateException(
                        "NeverNether R15 native lock exists without the required R14 height lock"
                    );
                }
                return;
            }

            final String expectedHeight = NeverNetherHeightR14.PROFILE + "\n";
            if (!Files.readString(heightLock).equals(expectedHeight)) {
                throw new IllegalStateException(
                    "NeverNether R15 requires the exact active R14 height profile"
                );
            }
            verifyNativeDatapacks(datapackDir);

            if (Files.exists(nativeLock)) {
                final String locked = Files.readString(nativeLock);
                if (!locked.equals(NATIVE_PROFILE + "\n")) {
                    throw new IllegalStateException(
                        "NeverNether native revision mismatch: locked=" + locked.trim()
                            + " active=" + NATIVE_PROFILE
                    );
                }
                return;
            }

            if (hasNetherRegions(worldRoot)) {
                throw new IllegalStateException(
                    "NeverNether R15 cannot adopt existing R14-only Nether regions; use a NEW/reset Nether"
                );
            }

            Files.createDirectories(worldRoot);
            final Path tmp = Files.createTempFile(worldRoot, NATIVE_LOCK + ".", ".tmp");
            try {
                Files.writeString(tmp, NATIVE_PROFILE + "\n");
                try {
                    Files.move(tmp, nativeLock, StandardCopyOption.ATOMIC_MOVE);
                } catch (AtomicMoveNotSupportedException ex) {
                    Files.move(tmp, nativeLock, StandardCopyOption.REPLACE_EXISTING);
                }
            } finally {
                Files.deleteIfExists(tmp);
            }
        } catch (IOException ex) {
            throw new IllegalStateException("NeverNether R15 native revision lock verification failed", ex);
        }
    }

    private static void verifyNativeDatapacks(final Path datapackDir) throws IOException {
        if (!Files.isDirectory(datapackDir)) {
            throw new IllegalStateException("NeverNether R15 matching datapack directory is missing");
        }
        boolean found = false;
        try (var paths = Files.list(datapackDir)) {
            for (Path pack : paths.sorted().toList()) {
                if (Files.isDirectory(pack)) {
                    if (!Files.isRegularFile(pack.resolve(PACK_FINGERPRINT))) continue;
                    final Path marker = pack.resolve(NATIVE_MARKER.replace('/', java.io.File.separatorChar));
                    if (!Files.isRegularFile(marker)) {
                        throw new IllegalStateException("R15 native profile marker missing from " + pack.getFileName());
                    }
                    validateNativeProfile(Files.readAllBytes(marker), pack.toString());
                    found = true;
                } else if (Files.isRegularFile(pack)
                    && pack.getFileName().toString().toLowerCase(java.util.Locale.ROOT).endsWith(".zip")) {
                    try (ZipFile zip = new ZipFile(pack.toFile())) {
                        if (zip.getEntry(PACK_FINGERPRINT) == null) continue;
                        final var marker = zip.getEntry(NATIVE_MARKER);
                        if (marker == null) {
                            throw new IllegalStateException("R15 native profile marker missing from " + pack.getFileName());
                        }
                        validateNativeProfile(zip.getInputStream(marker).readAllBytes(), pack.toString());
                        found = true;
                    }
                }
            }
        }
        if (!found) {
            throw new IllegalStateException("NeverNether R15 matching native-profile datapack is not installed");
        }
    }

    private static void validateNativeProfile(final byte[] payload, final String source) {
        if (payload.length > 65536) {
            throw new IllegalStateException("Oversized R15 native profile in " + source);
        }
        final JsonObject value = JsonParser.parseString(
            new String(payload, java.nio.charset.StandardCharsets.UTF_8)
        ).getAsJsonObject();
        if (!value.has("schema") || value.get("schema").getAsInt() != 1
            || !value.has("profile") || !NATIVE_PROFILE.equals(value.get("profile").getAsString())
            || !value.has("requires_height_profile")
            || !NeverNetherHeightR14.PROFILE.equals(value.get("requires_height_profile").getAsString())
            || !value.has("new_world_required") || !value.get("new_world_required").getAsBoolean()) {
            throw new IllegalStateException("Invalid R15 native profile in " + source);
        }
    }

    private static boolean hasNetherRegions(final Path worldRoot) throws IOException {
        final Path[] regions = {
            worldRoot.resolve("dimensions/minecraft/the_nether/region"),
            worldRoot.resolve("DIM-1/region"),
            worldRoot.resolveSibling(worldRoot.getFileName() + "_nether").resolve("DIM-1/region")
        };
        for (Path region : regions) {
            if (!Files.isDirectory(region)) continue;
            try (var files = Files.list(region)) {
                if (files.anyMatch(path -> path.getFileName().toString().endsWith(".mca"))) {
                    return true;
                }
            }
        }
        return false;
    }

    private static void validateEnvelope(final ChunkAccess chunk) {
        if (chunk.getMinY() != MIN_Y || chunk.getMaxY() < MAX_Y + 1) {
            throw new IllegalStateException("R15 cleanup requires the NeverNether -128..511 generated body");
        }
    }

    static int fillMicroPockets(final ChunkAccess chunk) {
        return fillMicroPockets(chunk, false);
    }

    static int fillMicroPocketsPublished(final ChunkAccess chunk) {
        return fillMicroPockets(chunk, true);
    }

    private static int fillMicroPockets(final ChunkAccess chunk, final boolean published) {
        final int height = MAX_Y - MIN_Y + 1;
        final boolean[] visited = new boolean[height * 256];
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;

        for (int y = MIN_Y; y <= MAX_Y; ++y) {
            for (int lz = 0; lz < 16; ++lz) {
                for (int lx = 0; lx < 16; ++lx) {
                    final int startIndex = index(lx, y, lz);
                    if (visited[startIndex]) continue;
                    pos.set(baseX + lx, y, baseZ + lz);
                    if (!chunk.getBlockState(pos).isAir()) continue;
                    if (published && !originalAir(chunk, lx, y, lz)) {
                        visited[startIndex] = true;
                        continue;
                    }

                    final ArrayDeque<Cell> queue = new ArrayDeque<>();
                    final java.util.ArrayList<Cell> cells = new java.util.ArrayList<>(MAX_MICRO_POCKET + 1);
                    final Map<BlockState,Integer> boundary = new HashMap<>();
                    boolean safe = true;
                    queue.add(new Cell(lx,y,lz));
                    visited[startIndex] = true;

                    while (!queue.isEmpty()) {
                        final Cell cell = queue.removeFirst();
                        if (cells.size() <= MAX_MICRO_POCKET) cells.add(cell);
                        if (cell.x == 0 || cell.x == 15 || cell.z == 0 || cell.z == 15
                            || cell.y == MIN_Y || cell.y == MAX_Y) {
                            safe = false;
                        }
                        for (int[] d : DIRECTIONS) {
                            final int nx = cell.x + d[0];
                            final int ny = cell.y + d[1];
                            final int nz = cell.z + d[2];
                            if (nx < 0 || nx > 15 || nz < 0 || nz > 15 || ny < MIN_Y || ny > MAX_Y) {
                                safe = false;
                                continue;
                            }
                            pos.set(baseX + nx, ny, baseZ + nz);
                            final BlockState adjacent = chunk.getBlockState(pos);
                            if (adjacent.isAir()) {
                                if (published && !originalAir(chunk, nx, ny, nz)) {
                                    safe = false;
                                    continue;
                                }
                                final int nextIndex = index(nx,ny,nz);
                                if (!visited[nextIndex]) {
                                    visited[nextIndex] = true;
                                    queue.addLast(new Cell(nx,ny,nz));
                                }
                            } else if (isNaturalRock(adjacent)) {
                                if (isFillMaterial(adjacent)) boundary.merge(adjacent,1,Integer::sum);
                            } else {
                                safe = false;
                            }
                        }
                    }

                    if (!safe || cells.isEmpty() || cells.size() > MAX_MICRO_POCKET) continue;
                    final BlockState replacement = chooseFill(boundary);
                    if (replacement == null) continue;
                    for (Cell cell : cells) {
                        write(chunk, cell.x, cell.y, cell.z, replacement, published, pos);
                        ++changed;
                    }
                }
            }
        }
        return changed;
    }

    static int solidifyHangingLava(final ChunkAccess chunk) {
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;
        for (int y = MIN_Y + 1; y < MAX_Y; ++y) {
            for (int lz = 0; lz < 16; ++lz) {
                for (int lx = 0; lx < 16; ++lx) {
                    pos.set(baseX + lx, y, baseZ + lz);
                    final BlockState state = chunk.getBlockState(pos);
                    if (!sourceLava(state)) continue;
                    pos.set(baseX + lx, y - 1, baseZ + lz);
                    if (!chunk.getBlockState(pos).isAir()) continue;
                    int horizontalSource = 0;
                    int horizontalRock = 0;
                    int missingHorizontal = 0;
                    for (int[] d : HORIZONTAL) {
                        final int nx = lx + d[0];
                        final int nz = lz + d[1];
                        if (nx < 0 || nx > 15 || nz < 0 || nz > 15) {
                            ++missingHorizontal;
                            continue;
                        }
                        pos.set(baseX + nx, y, baseZ + nz);
                        final BlockState neighbor = chunk.getBlockState(pos);
                        if (sourceLava(neighbor)) ++horizontalSource;
                        else if (isNaturalRock(neighbor)) ++horizontalRock;
                    }
                    final boolean interiorShelf = missingHorizontal == 0 && horizontalSource >= 2;
                    final boolean edgeShelf = missingHorizontal == 1
                        && horizontalSource >= 1
                        && horizontalRock >= 2
                        && sourceLava(stateAt(chunk, lx, y + 1, lz, pos));
                    if (!interiorShelf && !edgeShelf) continue;
                    final BlockState replacement = surroundingRock(chunk, lx, y, lz, pos);
                    if (replacement == null) continue;
                    directSet(chunk, lx, y, lz, replacement);
                    ++changed;
                }
            }
        }
        return changed;
    }

    private static void write(
        final ChunkAccess chunk,
        final int localX,
        final int y,
        final int localZ,
        final BlockState state,
        final boolean published,
        final BlockPos.MutableBlockPos pos
    ) {
        if (!published) {
            directSet(chunk, localX, y, localZ, state);
            return;
        }
        final var section = chunk.getSection(chunk.getSectionIndex(y));
        NeverNetherSubstrateR10.externalWrite(section, localX, y, localZ);
        section.getStates().set(localX & 15, y & 15, localZ & 15, state);
        section.recalcBlockCounts();
    }

    private static void directSet(
        final ChunkAccess chunk,
        final int localX,
        final int y,
        final int localZ,
        final BlockState state
    ) {
        final var section = chunk.getSection(chunk.getSectionIndex(y));
        section.getStates().set(localX & 15, y & 15, localZ & 15, state);
        section.recalcBlockCounts();
    }

    static boolean sourceLava(final BlockState state) {
        return state.is(Blocks.LAVA) && state.getFluidState().isSource();
    }

    static boolean isNaturalRock(final BlockState state) {
        return state.is(Blocks.NETHERRACK)
            || state.is(Blocks.BASALT)
            || state.is(Blocks.SMOOTH_BASALT)
            || state.is(Blocks.BLACKSTONE)
            || state.is(Blocks.MAGMA_BLOCK)
            || state.is(Blocks.SOUL_SAND)
            || state.is(Blocks.SOUL_SOIL)
            || state.is(Blocks.CRIMSON_NYLIUM)
            || state.is(Blocks.WARPED_NYLIUM)
            || state.is(Blocks.NETHER_QUARTZ_ORE)
            || state.is(Blocks.NETHER_GOLD_ORE)
            || state.is(Blocks.ANCIENT_DEBRIS)
            || state.is(Blocks.GRAVEL)
            || state.is(Blocks.BEDROCK);
    }

    private static boolean originalAir(
        final ChunkAccess chunk,
        final int localX,
        final int y,
        final int localZ
    ) {
        final var section = chunk.getSection(chunk.getSectionIndex(y));
        final BlockPos pos = new BlockPos(
            chunk.getPos().getMinBlockX() + localX,
            y,
            chunk.getPos().getMinBlockZ() + localZ
        );
        return NeverNetherSubstrateR10.original(section, pos).isAir();
    }

    private static boolean isFillMaterial(final BlockState state) {
        return !state.is(Blocks.NETHER_QUARTZ_ORE)
            && !state.is(Blocks.NETHER_GOLD_ORE)
            && !state.is(Blocks.ANCIENT_DEBRIS)
            && !state.is(Blocks.BEDROCK);
    }

    private static BlockState chooseFill(final Map<BlockState,Integer> counts) {
        if (counts.isEmpty()) return null;
        BlockState best = null;
        int bestCount = -1;
        int bestId = Integer.MAX_VALUE;
        for (var entry : counts.entrySet()) {
            final int id = Block.getId(entry.getKey());
            final int count = entry.getValue();
            if (count > bestCount || count == bestCount && id < bestId) {
                best = entry.getKey();
                bestCount = count;
                bestId = id;
            }
        }
        return best;
    }

    private static BlockState stateAt(
        final ChunkAccess chunk,
        final int localX,
        final int y,
        final int localZ,
        final BlockPos.MutableBlockPos pos
    ) {
        if (localX < 0 || localX > 15 || localZ < 0 || localZ > 15 || y < MIN_Y || y > MAX_Y) {
            return Blocks.BEDROCK.defaultBlockState();
        }
        pos.set(chunk.getPos().getMinBlockX() + localX, y, chunk.getPos().getMinBlockZ() + localZ);
        return chunk.getBlockState(pos);
    }

    private static BlockState surroundingRock(
        final ChunkAccess chunk,
        final int lx,
        final int y,
        final int lz,
        final BlockPos.MutableBlockPos pos
    ) {
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final Map<BlockState,Integer> counts = new HashMap<>();
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dz = -1; dz <= 1; ++dz) {
                for (int dx = -1; dx <= 1; ++dx) {
                    if (dx == 0 && dy == 0 && dz == 0) continue;
                    final int nx = lx + dx;
                    final int ny = y + dy;
                    final int nz = lz + dz;
                    if (nx < 0 || nx > 15 || nz < 0 || nz > 15 || ny < MIN_Y || ny > MAX_Y) continue;
                    pos.set(baseX + nx, ny, baseZ + nz);
                    final BlockState state = chunk.getBlockState(pos);
                    if (isNaturalRock(state) && isFillMaterial(state)) counts.merge(state,1,Integer::sum);
                }
            }
        }
        return chooseFill(counts);
    }

    private static int index(final int x, final int y, final int z) {
        return (y - MIN_Y) * 256 + z * 16 + x;
    }

    private record Cell(int x,int y,int z) {}
    public record Result(int microPocketBlocksFilled,int hangingLavaCellsSolidified) {}

    /** Datapack/runtime marker: an R15 pack must not decode on an older R14 runtime. */
    public record RequiredProcessor() implements StructureProcessor {
        public static final RequiredProcessor INSTANCE = new RequiredProcessor();
        public static final MapCodec<RequiredProcessor> CODEC = MapCodec.unit(INSTANCE);
        @Override
        public StructureTemplate.StructureBlockInfo processBlock(
            LevelReader level,
            BlockPos pos,
            BlockPos ref,
            BlockPos relative,
            StructureTemplate.StructureBlockInfo info,
            StructurePlaceSettings settings
        ) {
            return info;
        }
        @Override public MapCodec<RequiredProcessor> codec() { return CODEC; }
    }
}
