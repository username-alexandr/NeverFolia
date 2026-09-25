#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "worldgen-spec/never-overworld-external-structures-r19.json"
CHUNK_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldExternalStructurePolicyR19.java")
GENERIC_REL = Path("folia-server/src/minecraft/java/ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkUpgradeGenericStatusTask.java")
MARKER = "// NeverFolia R19: external surface structures require a dry island footprint."
ISLAND_HOOK = "// NeverFolia R24: materialize synthetic island slices after FEATURES."
GENERATED_MARKER = "// NeverFolia R19: generated external-land pieces must stay on dry island terrain."

def fail(message: str) -> None:
    raise SystemExit("[NeverFolia][External Structure Policy R19] " + message)

def load_spec() -> dict:
    data = json.loads(SPEC.read_text(encoding="utf-8"))
    radii = data.get("island_radii", {})
    if data.get("profile") != "NeverOverworld-External-Structures-R19":
        fail("wrong spec profile")
    if len(radii) != 134:
        fail(f"expected 134 island-adapted structures, got {len(radii)}")
    if any(not isinstance(k, str) or not isinstance(v, int) or v < 1 for k, v in radii.items()):
        fail("invalid island radius entry")
    return data

def java_helper(spec: dict) -> str:
    radii = spec["island_radii"]
    cases = "\n".join(
        f'            case "{sid}" -> {radius};'
        for sid, radius in sorted(radii.items())
    )
    return f'''package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.RandomState;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructurePiece;
import net.minecraft.world.level.levelgen.structure.StructureStart;

/**
 * FIELD-R19 island admission for imported land structures.
 *
 * <p>The pre-generation gate is intentionally cheap: the candidate centre must
 * be above the Y=128 ocean. The authoritative gate runs after the deterministic
 * StructureStart exists and verifies every X/Z column covered by every actual
 * generated piece. Ocean/underground structures are not listed and therefore
 * preserve source placement.</p>
 */
public final class NeverOverworldExternalStructurePolicyR19 {{
    static final int EXPECTED_MIN_Y = -512;
    static final int EXPECTED_HEIGHT = 1024;
    static final int MIN_DRY_SURFACE_Y = 129;
    static final int MAX_PIECE_SPAN = 256;
    static final int BETTER_MONUMENT_TERRAIN_RADIUS = 29;

    private static final java.util.concurrent.ConcurrentHashMap<
        ResourceKey<Level>,
        java.util.concurrent.ConcurrentHashMap<Long, java.util.List<IslandSlice>>
    > SYNTHETIC_ISLANDS = new java.util.concurrent.ConcurrentHashMap<>();

    private record IslandSlice(int[] baseY, int[] fillTopY) {{}}

    private static long chunkKey(final int chunkX, final int chunkZ) {{
        return ((long)chunkX << 32) ^ (chunkZ & 0xffffffffL);
    }}

    private static boolean islandReplaceable(final BlockState state) {{
        return state.isAir() || !state.getFluidState().isEmpty();
    }}

    private static void registerSyntheticIsland(
        final ChunkGenerator generator,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final ChunkPos origin,
        final ResourceKey<Level> dimension,
        final int radius,
        final int topY,
        final StructureStart start
    ) {{
        final int centerX = origin.getMiddleBlockX();
        final int centerZ = origin.getMiddleBlockZ();
        final int minChunkX = (centerX - radius) >> 4;
        final int maxChunkX = (centerX + radius) >> 4;
        final int minChunkZ = (centerZ - radius) >> 4;
        final int maxChunkZ = (centerZ + radius) >> 4;
        final java.util.concurrent.ConcurrentHashMap<Long, java.util.List<IslandSlice>> byChunk =
            SYNTHETIC_ISLANDS.computeIfAbsent(dimension, ignored -> new java.util.concurrent.ConcurrentHashMap<>());

        for (int cz = minChunkZ; cz <= maxChunkZ; ++cz) {{
            for (int cx = minChunkX; cx <= maxChunkX; ++cx) {{
                final int[] baseY = new int[256];
                final int[] fillTopY = new int[256];
                java.util.Arrays.fill(fillTopY, Integer.MIN_VALUE);
                boolean any = false;
                for (int lz = 0; lz < 16; ++lz) {{
                    for (int lx = 0; lx < 16; ++lx) {{
                        final int x = (cx << 4) + lx;
                        final int z = (cz << 4) + lz;
                        final long dx = (long)x - centerX;
                        final long dz = (long)z - centerZ;
                        if (dx * dx + dz * dz > (long)radius * radius) continue;
                        final int index = (lz << 4) | lx;
                        baseY[index] = generator.getBaseHeight(
                            x, z, Heightmap.Types.WORLD_SURFACE_WG, heightAccessor, randomState
                        );
                        int fillTop = topY;
                        for (final StructurePiece piece : start.getPieces()) {{
                            final BoundingBox box = piece.getBoundingBox();
                            if (x >= box.minX() && x <= box.maxX() && z >= box.minZ() && z <= box.maxZ()) {{
                                fillTop = Math.min(fillTop, box.minY() - 1);
                            }}
                        }}
                        fillTopY[index] = fillTop;
                        any = true;
                    }}
                }}
                if (!any) continue;
                final long key = chunkKey(cx, cz);
                byChunk.compute(key, (ignored, list) -> {{
                    final java.util.List<IslandSlice> out =
                        list == null ? new java.util.ArrayList<>() : new java.util.ArrayList<>(list);
                    out.add(new IslandSlice(baseY, fillTopY));
                    return java.util.List.copyOf(out);
                }});
            }}
        }}
    }}

    public static int applySyntheticIslands(final ServerLevel level, final ChunkAccess chunk) {{
        if (level == null || chunk == null || !inScope(level.dimension(), chunk)) return 0;
        final var byChunk = SYNTHETIC_ISLANDS.get(level.dimension());
        if (byChunk == null) return 0;
        final java.util.List<IslandSlice> slices =
            byChunk.remove(chunkKey(chunk.getPos().x(), chunk.getPos().z()));
        if (slices == null || slices.isEmpty()) return 0;

        int changed = 0;
        final int baseX = chunk.getPos().getMinBlockX();
        final int baseZ = chunk.getPos().getMinBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        for (final IslandSlice slice : slices) {{
            for (int lz = 0; lz < 16; ++lz) {{
                for (int lx = 0; lx < 16; ++lx) {{
                    final int index = (lz << 4) | lx;
                    final int fillTop = slice.fillTopY()[index];
                    if (fillTop == Integer.MIN_VALUE) continue;
                    final int fromY = Math.max(slice.baseY()[index] + 1, chunk.getMinY() + 1);
                    if (fromY > fillTop) continue;
                    for (int y = fromY; y <= fillTop; ++y) {{
                        pos.set(baseX + lx, y, baseZ + lz);
                        final BlockState current = chunk.getBlockState(pos);
                        if (!islandReplaceable(current)) continue;
                        final BlockState replacement =
                            y == fillTop && fillTop >= MIN_DRY_SURFACE_Y
                                ? Blocks.GRASS_BLOCK.defaultBlockState()
                                : y >= fillTop - 3
                                    ? Blocks.DIRT.defaultBlockState()
                                    : Blocks.STONE.defaultBlockState();
                        chunk.setBlockState(pos, replacement, 0);
                        ++changed;
                    }}
                }}
            }}
        }}
        return changed;
    }}

    private NeverOverworldExternalStructurePolicyR19() {{}}

    static int radiusForId(final String id) {{
        return switch (id) {{
{cases}
            default -> 0;
        }};
    }}

    static boolean isIslandSurfaceId(final String id) {{
        return radiusForId(id) > 0;
    }}

    static boolean isBetterMonumentId(final String id) {{
        return id.equals("repurposed_structures:monument_desert")
            || id.equals("repurposed_structures:monument_jungle")
            || id.equals("repurposed_structures:monument_icy");
    }}

    private static boolean dryAt(
        final ChunkGenerator generator,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final int x,
        final int z
    ) {{
        return generator.getBaseHeight(
            x,
            z,
            Heightmap.Types.WORLD_SURFACE_WG,
            heightAccessor,
            randomState
        ) >= MIN_DRY_SURFACE_Y;
    }}

    private static boolean monumentTerrainAllowed(
        final ChunkGenerator generator,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final ChunkPos chunkPos
    ) {{
        final int x = chunkPos.getMiddleBlockX();
        final int z = chunkPos.getMiddleBlockZ();
        final int r = BETTER_MONUMENT_TERRAIN_RADIUS;
        return dryAt(generator, randomState, heightAccessor, x, z)
            && dryAt(generator, randomState, heightAccessor, x - r, z - r)
            && dryAt(generator, randomState, heightAccessor, x - r, z + r)
            && dryAt(generator, randomState, heightAccessor, x + r, z - r)
            && dryAt(generator, randomState, heightAccessor, x + r, z + r);
    }}

    private static boolean inScope(
        final ResourceKey<Level> dimension,
        final ChunkAccess heightAccessor
    ) {{
        return Level.OVERWORLD.equals(dimension)
            && heightAccessor.getMinY() == EXPECTED_MIN_Y
            && heightAccessor.getHeight() == EXPECTED_HEIGHT;
    }}

    private static String structureId(final Holder<Structure> structure) {{
        return structure.unwrapKey()
            .map(key -> key.identifier().toString())
            .orElse("");
    }}

    static boolean allows(
        final ChunkGenerator generator,
        final Holder<Structure> structure,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final ChunkPos chunkPos,
        final ResourceKey<Level> dimension
    ) {{
        if (!inScope(dimension, heightAccessor)) return true;
        final int radius = radiusForId(structureId(structure));
        if (radius <= 0) return true;
        final String id = structureId(structure);
        // R24: never reject an imported land structure solely because the
        // candidate is ocean. The generated-piece pass below will either keep
        // natural dry terrain or lift the start and schedule a synthetic island.
        return true;
    }}

    static boolean allowsGenerated(
        final ChunkGenerator generator,
        final Holder<Structure> structure,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final ChunkPos chunkPos,
        final StructureStart start,
        final ResourceKey<Level> dimension
    ) {{
        if (!inScope(dimension, heightAccessor)) return true;
        final String id = structureId(structure);
        final int radius = radiusForId(id);
        if (radius <= 0) return true;
        if (start == null || !start.isValid()) return false;

        boolean needsIsland = false;
        for (final StructurePiece piece : start.getPieces()) {{
            final BoundingBox box = piece.getBoundingBox();
            final long width = (long)box.maxX() - box.minX() + 1L;
            final long depth = (long)box.maxZ() - box.minZ() + 1L;
            if (width <= 0L || depth <= 0L || width > MAX_PIECE_SPAN || depth > MAX_PIECE_SPAN) {{
                return false;
            }}
            if (!needsIsland) {{
                for (int z = box.minZ(); z <= box.maxZ() && !needsIsland; ++z) {{
                    for (int x = box.minX(); x <= box.maxX(); ++x) {{
                        if (!dryAt(generator, randomState, heightAccessor, x, z)) {{
                            needsIsland = true;
                            break;
                        }}
                    }}
                }}
            }}
        }}
        if (!needsIsland) return true;

        final int centerX = chunkPos.getMiddleBlockX();
        final int centerZ = chunkPos.getMiddleBlockZ();
        final int base = generator.getBaseHeight(
            centerX, centerZ, Heightmap.Types.WORLD_SURFACE_WG, heightAccessor, randomState
        );
        final int targetTop = Math.max(MIN_DRY_SURFACE_Y, base);
        final int deltaY = Math.max(0, MIN_DRY_SURFACE_Y - base);
        if (deltaY > 0) {{
            for (final StructurePiece piece : start.getPieces()) {{
                piece.move(0, deltaY, 0);
            }}
        }}
        registerSyntheticIsland(
            generator, randomState, heightAccessor, chunkPos, dimension,
            Math.max(radius, 24), targetTop, start
        );
        return true;
    }}
}}
'''

def matching_brace(source: str, opening: int) -> int:
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    fail("unterminated tryGenerateStructure method")

def param_name(params: str, pattern: str) -> str:
    m = re.search(pattern + r"\s+([A-Za-z_$][A-Za-z0-9_$]*)", params)
    if m is None:
        fail("could not infer parameter for " + pattern)
    return m.group(1)

def patch_source(source: str) -> str:
    method = source.find("private boolean tryGenerateStructure(")
    if method < 0:
        fail("tryGenerateStructure method not found")
    po = source.find("(", method)
    pc = source.find(")", po)
    if pc < 0:
        fail("parameter list not found")
    params = source[po + 1:pc]
    entry = param_name(params, r"(?:StructureSet\.)?StructureSelectionEntry")
    random_state = param_name(params, r"RandomState")
    chunk = param_name(params, r"ChunkAccess")
    chunk_pos = param_name(params, r"ChunkPos")
    dimension = param_name(params, r"ResourceKey\s*<\s*Level\s*>")

    bo = source.find("{", pc)
    bc = matching_brace(source, bo)
    body = source[bo + 1:bc]

    if MARKER not in source:
        m = re.search(
            rf"(?P<indent>^[ \t]*)Structure\s+(?P<var>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*{re.escape(entry)}\.structure\(\)\.value\(\);",
            body,
            re.MULTILINE,
        )
        if m is None:
            fail("structure declaration not found")
        indent = m.group("indent")
        insert = bo + 1 + m.end()
        guard = (
            "\n" + indent + MARKER + "\n"
            + indent + f"if (!NeverOverworldExternalStructurePolicyR19.allows(this, {entry}.structure(), {random_state}, {chunk}, {chunk_pos}, {dimension})) {{\n"
            + indent + "    return false;\n"
            + indent + "}"
        )
        source = source[:insert] + guard + source[insert:]

    if GENERATED_MARKER not in source:
        method = source.find("private boolean tryGenerateStructure(")
        _, method_end = method, matching_brace(source, source.find("{", source.find(")", method))) + 1
        method_text = source[method:method_end]
        start_match = re.search(
            r"(?P<indent>^[ \t]*)StructureStart\s+(?P<start>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*[A-Za-z_$][A-Za-z0-9_$]*\.generate\s*\(",
            method_text,
            re.MULTILINE,
        )
        if start_match is None:
            fail("StructureStart generation assignment not found")
        start_var = start_match.group("start")
        valid_match = re.compile(
            rf"(?P<indent>^[ \t]*)if\s*\(\s*{re.escape(start_var)}\.isValid\(\)\s*\)\s*\{{",
            re.MULTILINE,
        ).search(method_text, start_match.end())
        if valid_match is None:
            fail("StructureStart valid block not found")
        insert = method + valid_match.end()
        indent = valid_match.group("indent") + "    "
        guard = (
            "\n" + indent + GENERATED_MARKER + "\n"
            + indent + f"if (!NeverOverworldExternalStructurePolicyR19.allowsGenerated(\n"
            + indent + "    this,\n"
            + indent + f"    {entry}.structure(),\n"
            + indent + f"    {random_state},\n"
            + indent + f"    {chunk},\n"
            + indent + f"    {chunk_pos},\n"
            + indent + f"    {start_var},\n"
            + indent + f"    {dimension}\n"
            + indent + ")) {\n"
            + indent + "    return false;\n"
            + indent + "}"
        )
        source = source[:insert] + guard + source[insert:]

    if source.count(MARKER) != 1 or source.count(GENERATED_MARKER) != 1:
        fail("R19 generation guards were not injected exactly once")
    return source

def patch_generic(source: str) -> str:
    if ISLAND_HOOK in source:
        return source
    anchor = "        this.complete(newChunk, null);\n"
    if source.count(anchor) != 1:
        fail("Moonrise generic FEATURES completion anchor missing/duplicated")
    injected = (
        "        if (this.toStatus == ChunkStatus.FEATURES) {\n"
        "            " + ISLAND_HOOK + "\n"
        "            net.minecraft.world.level.chunk.NeverOverworldExternalStructurePolicyR19.applySyntheticIslands(this.world, newChunk);\n"
        "        }\n\n"
        + anchor
    )
    return source.replace(anchor, injected, 1)

def verify(folia: Path) -> None:
    spec = load_spec()
    chunk = (folia / CHUNK_REL).read_text(encoding="utf-8")
    helper = (folia / HELPER_REL).read_text(encoding="utf-8")
    generic = (folia / GENERIC_REL).read_text(encoding="utf-8")
    if MARKER not in chunk:
        fail("R19 ChunkGenerator guard missing")
    if "NeverOverworldExternalStructurePolicyR19.allows" not in chunk:
        fail("R19 policy call missing")
    if GENERATED_MARKER not in chunk or "NeverOverworldExternalStructurePolicyR19.allowsGenerated" not in chunk:
        fail("R19 generated-piece dry-island gate missing")
    for sid in (
        "nova_structures:tavern_oak",
        "explorify:tavern",
        "explorify:ruins",
        "nova_structures:stray_outlook",
        "nova_structures:witch_villa",
        "structory_towers:wizard_tower",
        "repurposed_structures:witch_hut_oak",
        "repurposed_structures:monument_jungle",
    ):
        if sid not in helper:
            fail("representative surface ID missing: " + sid)
    if helper.count('case "') != len(spec["island_radii"]):
        fail("generated helper island ID count mismatch")
    for untouched in (
        "minecraft:village_plains",
        "structory_towers:ocean_pillar",
        "nova_structures:catacomb",
        "nova_structures:conduit_ruin",
        "nova_structures:trident_trial_monument",
        "nova_structures:lone_citadel",
        "nova_structures:toxic_lair",
    ):
        if f'case "{untouched}"' in helper:
            fail("untouched structure accidentally island-gated: " + untouched)
    if "WORLD_SURFACE_WG" not in helper or "MIN_DRY_SURFACE_Y = 129" not in helper:
        fail("R19 dry island height policy missing")
    for marker in (
        "SYNTHETIC_ISLANDS",
        "registerSyntheticIsland(",
        "applySyntheticIslands(",
        "piece.move(0, deltaY, 0)",
        "Blocks.GRASS_BLOCK.defaultBlockState()",
    ):
        if marker not in helper:
            fail("R24 synthetic-island marker missing: " + marker)
    if ISLAND_HOOK not in generic or "applySyntheticIslands(this.world, newChunk)" not in generic:
        fail("R24 FEATURES synthetic-island hook missing")
    for marker in (
        "allowsGenerated(",
        "for (final StructurePiece piece : start.getPieces())",
        "MAX_PIECE_SPAN = 256",
        "BETTER_MONUMENT_TERRAIN_RADIUS = 29",
        "monumentTerrainAllowed(",
        "isBetterMonumentId(",
    ):
        if marker not in helper:
            fail("R19 generated-piece safety marker missing: " + marker)
    if "getChunk(" in helper or "level.getBlockState(" in helper:
        fail("R19 policy must not synchronously load/read neighbour chunk state through level")
    if "chunk.getBlockState(pos)" not in helper:
        fail("R24 island materializer must inspect only its owning chunk before replacement")
    print("[NeverFolia][External Structure Policy R19] final invariants OK")

def self_test() -> None:
    spec = load_spec()
    helper = java_helper(spec)
    if helper.count('case "') != 134:
        fail("SELF-TEST helper ID count mismatch")
    fixture = """class ChunkGenerator {
    private boolean tryGenerateStructure(
        StructureSet.StructureSelectionEntry entry,
        StructureManager manager,
        RegistryAccess access,
        RandomState randomState,
        StructureTemplateManager templates,
        long seed,
        ChunkAccess chunk,
        ChunkPos chunkPos,
        SectionPos sectionPos,
        ResourceKey<Level> dimension
    ) {
        Structure structure = entry.structure().value();
        StructureStart start = structure.generate(entry.structure(), dimension, access, this, null, randomState, templates, seed, chunkPos, 0, chunk, x -> true);
        if (start.isValid()) {
            return true;
        }
        return false;
    }
}
"""
    patched = patch_source(fixture)
    if (
        MARKER not in patched
        or GENERATED_MARKER not in patched
        or "NeverOverworldExternalStructurePolicyR19.allows" not in patched
        or "NeverOverworldExternalStructurePolicyR19.allowsGenerated" not in patched
    ):
        fail("SELF-TEST guard injection failed")
    print("[NeverFolia][External Structure Policy R19] SELF-TEST OK")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("folia", nargs="?", type=Path)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test()
        return
    if a.folia is None:
        p.error("folia worktree is required")
    folia = a.folia.resolve()
    if a.check_only:
        verify(folia)
        return
    self_test()
    chunk = folia / CHUNK_REL
    if not chunk.is_file():
        fail("ChunkGenerator source missing")
    chunk.write_text(patch_source(chunk.read_text(encoding="utf-8")), encoding="utf-8")
    generic = folia / GENERIC_REL
    if not generic.is_file():
        fail("Moonrise generic status task missing")
    generic.write_text(patch_generic(generic.read_text(encoding="utf-8")), encoding="utf-8")
    helper = folia / HELPER_REL
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(java_helper(load_spec()), encoding="utf-8")
    verify(folia)
    print("[NeverFolia][External Structure Policy R19] installed")

if __name__ == "__main__":
    main()
