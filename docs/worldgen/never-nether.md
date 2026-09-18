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

## Vertical geometry — current R14 contract

NeverNether keeps the vanilla dimension key `minecraft:the_nether`, but the current
height profile is **NN-R14-SUBSTRATE-1-ROOF512**.

Current coordinate contract:

- dimension `min_y`: **-128**;
- logical upper bedrock roof block: **Y=512**;
- building above the roof: **disabled**;
- technical storage height: **656** blocks;
- technical stored range: **Y=-128..527**;
- technical padding: **Y=513..527**;
- the padding range is required only so the section containing Y=512 can be stored;
- Y=513..527 must remain air and is **not** a second buildable roof zone.

The previous experimental layout with a buildable roof space through Y=895 is
obsolete and must not be used for new NeverNether worlds.

## Bedrock boundaries — current

The lower boundary remains at the translated NeverNether minimum. The upper
boundary uses the R14 roof envelope terminating at **bedrock Y=512**.

- Upper-roof density ramps are moved to the R14 ceiling.
- The upper bedrock envelope is anchored at Y=512.
- Non-air writes above Y=512 are rejected by the checked native mutation paths.
- Replacing the protected roof block with another material or air is rejected.
- Terrain, features and structures must not populate Y=513..527.
- Existing R13 worlds are not implicitly migrated to R14; a matching new-world
  pack/runtime profile is required.

### R14 verification already recorded

The bounded R14 acceptance recorded in
`docs/worldgen/never-nether-r14-bounded-height-results.md` includes:

- **248** real API height/boundary checks with zero failures;
- seed `7270913`: **81 chunks**, forward/reverse FULL + settled equality with
  zero different blocks;
- seed `123456789`: **25 chunks**, the same zero-difference result;
- a true additional JVM restart of the 81-chunk world with zero block or metadata
  differences;
- **106** selected saved FULL chunks independently audited from Anvil;
- **4,346** saved section records validated;
- **27,136** Y=512 roof cells checked as bedrock;
- **407,040** Y=513..527 padding cells checked as air;
- no accepted process required a forced stop.

The attempted 1,599-chunk R14 stress run exhausted its 2304 MiB Java heap and is
not counted as a PASS. Large-area completion, long-lived memory behavior, dynamic
fluids, falling-block/piston behavior, portal/client interaction and full dungeon
playability remain separate release gates.

### Portal behavior

Portal search/creation around the protected roof still requires explicit gameplay
acceptance. The existence of technical padding above Y=512 does not grant a valid
portal or building area there.

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
