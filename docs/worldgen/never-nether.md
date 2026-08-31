# NeverNether Worldgen

Status: design + implementation branch
Branch: `feature/never-nether-worldgen`
Dimension key: `minecraft:the_nether`
Initial worldgen version: `NN-DEV-1`

## Already fixed by NeverFolia architecture

- Nether keeps the vanilla dimension key `minecraft:the_nether`.
- Nether generation is implemented by NeverFolia core, not an external world generator plugin.
- Nether has its own independent worldgen version and fingerprint.
- Nether can use a seed derived from the master seed, or a dedicated override seed.
- Changing the Nether seed is only valid together with an explicit full reset of the Nether dimension.
- Future Nether resets do not touch Overworld, End, or other NeverLand dimensions.
- DEV/TEST/STAGING/PRODUCTION lifecycle rules apply independently to Nether.
- Generation must be deterministic regardless of chunk order and worldgen thread count.
- Fast Locate, diagnostics, pregen and Dimension Lifecycle Manager must be dimension-aware.

## Vertical geometry — approved

NeverNether uses two vertically distinct spaces inside one `minecraft:the_nether` dimension:

1. **Generated Nether body:** 512 blocks from the lower bedrock boundary to the upper bedrock roof.
2. **Roof construction zone:** another 512 buildable blocks above the upper bedrock roof.

Initial coordinate layout:

- Dimension `min_y`: `-128`
- Total dimension height: `1024`
- Highest buildable Y: `895`
- Generated Nether body: `Y=-128..383` (512 blocks total)
- Roof construction zone: `Y=384..895` (512 blocks total)

The roof construction zone is part of the same Nether dimension; NeverFolia must not create a second dimension for it.

## Bedrock boundaries — approved

Both lower and upper bedrock boundaries keep the **vanilla Nether bedrock profile** rather than using a custom uniform slab.

- Lower boundary uses the same irregular vanilla-style bedrock thickness/distribution pattern, translated to the NeverNether lower world boundary.
- Upper roof uses the same irregular vanilla-style bedrock thickness/distribution pattern, translated to the NeverNether roof boundary.
- The roof must remain recognizably vanilla-like: an irregular bedrock layer rather than a perfectly flat solid plate.
- NeverFolia must not increase the bedrock layer solely because the generated Nether body is taller.
- Bedrock placement is deterministic from the dimension seed/worldgen version.
- Normal Nether terrain must terminate against the lower/upper bedrock boundaries without leaking terrain/features into the roof construction zone.

### Generation rules above the roof

- Normal Nether terrain generation stops at the upper bedrock roof.
- `Y=384..895` is intentionally empty/buildable space by default.
- Players may place blocks throughout the roof construction zone up to the dimension build limit.
- Normal terrain features, ores, caves, lava seas and standard Nether structures must not generate in the roof construction zone unless a future NeverLand feature explicitly opts into roof placement.
- The roof area must survive normal JAR updates and Nether worldgen revisions exactly like any other already-generated player-built area.
- A Nether reset deletes both the generated body and roof player construction area because both belong to the same dimension; reset therefore requires explicit destructive confirmation and backup policy.

### Pending portal decision

Portal search/creation behavior above the upper bedrock roof must be specified separately. Build permission above the roof does not automatically imply that Nether portals should naturally target or spawn in the roof construction zone.

## External worldgen/content sources — approved direction

NeverNether will merge selected content from multiple datapacks into one controlled NeverLand worldgen/content layer. The source packs are references/content sources, not independently authoritative runtime generators once merged.

### Terrain / biome feature sources

- **Amplified Nether** — primary reference/source for amplified Nether terrain and large-scale vertical terrain character. It must be adapted to the NeverNether 512-block generated body; its original vertical assumptions must not be copied blindly.
- **Hearths** — biome/detail feature layer for richer vanilla Nether biome decoration and environmental features.

### Structure sources

- **Dungeons and Taverns** — import only structures intended for Nether gameplay.
- **Explorify** — import only structures that are explicitly Nether structures or are deliberately approved for Nether placement.
- **Structory: Towers** — import only Nether-themed tower structures/pools and their required processors/loot dependencies.
- **Repurposed Structures - Better Ocean Monuments Compat** — import only the **Nether Monument** content required for the NeverNether monument. No desert, icy, jungle or normal ocean monument variants are to be imported into NeverNether.

### Structure merge rules

- NeverFolia/NeverNether owns final placement rules, spacing, separation, salts, height ranges and terrain validation.
- Source datapack `structure_set` placement is not accepted automatically; it is reviewed and replaced by NeverNether placement where needed.
- Every imported structure receives a stable NeverLand logical ID or compatibility alias so future source-pack updates do not silently move or remove production structures.
- Imported Jigsaw pools, processors, loot tables, tags and template dependencies must be copied only when actually required by an approved Nether structure.
- Structures from Overworld/End portions of source datapacks are excluded unless separately approved later.
- No imported structure may generate in the roof construction zone `Y=384..895` unless explicitly marked as a future roof structure.
- All approved structures participate in NeverFolia Fast Locate, diagnostics, content validation and worldgen fingerprinting.
- Missing optional pieces may be skipped according to NeverFolia content-severity rules; missing main templates/pools are fatal for that specific structure and cause it to be skipped rather than partially corrupted.
- Production placement must be deterministic from Nether seed + structure salt + worldgen/content versions.

### Source-version rule

Before implementation/final merge, exact source archives/links and versions must be recorded. NeverNether must not depend on an unspecified "latest" archive in production. The selected archives are treated as immutable source inputs for a given content fingerprint.

## To define before implementation lock

1. Overall terrain identity and vertical layers inside `Y=-128..383`.
2. Lava sea level and lava-fluid rules.
3. Exact biome distribution/remapping and merged Hearths/Amplified Nether feature behavior.
4. Cave/cavern/canyon system.
5. Ores and geological richness maps.
6. Exact approved Nether structure list from all source datapacks and each structure's placement profile.
7. Fortress and bastion placement rules.
8. Portal safety and spawn validation, including roof-zone behavior.
9. Pregeneration/border policy.
10. Reset/resource-renewal policy.
11. Performance budget and regression seeds.
12. Exact source datapack versions/archives and license/distribution handling.

## Design rule

NeverNether should remain recognizably Nether-like where that improves gameplay and plugin compatibility, but exact vanilla generation is not a goal when a custom NeverLand solution is more stable, performant or visually stronger.
