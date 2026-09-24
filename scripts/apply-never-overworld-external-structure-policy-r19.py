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
MARKER = "// NeverFolia R19: external surface structures require a dry island footprint."
GENERATED_MARKER = "// NeverFolia R19: generated external-land pieces must stay on dry island terrain."

def fail(message: str) -> None:
    raise SystemExit("[NeverFolia][External Structure Policy R19] " + message)

def load_spec() -> dict:
    data = json.loads(SPEC.read_text(encoding="utf-8"))
    radii = data.get("island_radii", {})
    if data.get("profile") != "NeverOverworld-External-Structures-R19":
        fail("wrong spec profile")
    if len(radii) != 136:
        fail(f"expected 136 island-adapted structures, got {len(radii)}")
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

import net.minecraft.core.Holder;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
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
final class NeverOverworldExternalStructurePolicyR19 {{
    static final int EXPECTED_MIN_Y = -512;
    static final int EXPECTED_HEIGHT = 1024;
    static final int MIN_DRY_SURFACE_Y = 129;
    static final int MAX_PIECE_SPAN = 256;

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
        final int base = generator.getBaseHeight(
            chunkPos.getMiddleBlockX(),
            chunkPos.getMiddleBlockZ(),
            Heightmap.Types.WORLD_SURFACE_WG,
            heightAccessor,
            randomState
        );
        return base >= MIN_DRY_SURFACE_Y;
    }}

    static boolean allowsGenerated(
        final ChunkGenerator generator,
        final Holder<Structure> structure,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final StructureStart start,
        final ResourceKey<Level> dimension
    ) {{
        if (!inScope(dimension, heightAccessor)) return true;
        if (radiusForId(structureId(structure)) <= 0) return true;
        if (start == null || !start.isValid()) return false;

        for (final StructurePiece piece : start.getPieces()) {{
            final BoundingBox box = piece.getBoundingBox();
            final long width = (long)box.maxX() - box.minX() + 1L;
            final long depth = (long)box.maxZ() - box.minZ() + 1L;
            if (width <= 0L || depth <= 0L || width > MAX_PIECE_SPAN || depth > MAX_PIECE_SPAN) {{
                return false;
            }}
            for (int z = box.minZ(); z <= box.maxZ(); ++z) {{
                for (int x = box.minX(); x <= box.maxX(); ++x) {{
                    final int base = generator.getBaseHeight(
                        x,
                        z,
                        Heightmap.Types.WORLD_SURFACE_WG,
                        heightAccessor,
                        randomState
                    );
                    if (base < MIN_DRY_SURFACE_Y) return false;
                }}
            }}
        }}
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

def verify(folia: Path) -> None:
    spec = load_spec()
    chunk = (folia / CHUNK_REL).read_text(encoding="utf-8")
    helper = (folia / HELPER_REL).read_text(encoding="utf-8")
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
        "nova_structures:lone_citadel",
        "nova_structures:toxic_lair",
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
    ):
        if f'case "{untouched}"' in helper:
            fail("untouched structure accidentally island-gated: " + untouched)
    if "WORLD_SURFACE_WG" not in helper or "MIN_DRY_SURFACE_Y = 129" not in helper:
        fail("R19 dry island height policy missing")
    for marker in ("allowsGenerated(", "for (final StructurePiece piece : start.getPieces())", "MAX_PIECE_SPAN = 256"):
        if marker not in helper:
            fail("R19 generated-piece safety marker missing: " + marker)
    if "getChunk(" in helper or "getBlockState(" in helper:
        fail("R19 policy must not read generated neighbour chunk state")
    print("[NeverFolia][External Structure Policy R19] final invariants OK")

def self_test() -> None:
    spec = load_spec()
    helper = java_helper(spec)
    if helper.count('case "') != 136:
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
    helper = folia / HELPER_REL
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(java_helper(load_spec()), encoding="utf-8")
    verify(folia)
    print("[NeverFolia][External Structure Policy R19] installed")

if __name__ == "__main__":
    main()
