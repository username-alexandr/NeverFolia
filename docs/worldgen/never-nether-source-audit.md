# NeverNether source datapack audit

Branch: `feature/never-nether-worldgen`
Status: source archive audit

This document records the exact source archives supplied for NeverNether. These archives are source inputs only; NeverFolia owns final placement, vertical ranges, salts, validation and compatibility.

## Supplied archives

### Hearths
- Archive: `Hearths v1.0.5.dp.zip`
- Internal version: `1.0.5`
- Pack declares support across a broad format range and includes format overlays.
- Approved roles: Nether biome/detail features plus selected Nether structures.
- Nether structures found:
  - `hearths:crimson_tower`
  - `hearths:warped_tower`
  - `hearths:netherrack_spiral`
- Important feature families found include Nether Wastes pillars/lakes/fire, Crimson/Warped vegetation, rocks, stems and tall fungi.

### Amplified Nether
- Archive: `Amplified_Nether_v1.2.15.zip`
- Internal pack id: `amplified_nether`
- Supplied target: Minecraft 26.2
- Pack contains a 26.x overlay and current data-format support.
- Approved role: primary terrain/noise reference for NeverNether.
- Source `minecraft:nether` noise settings use:
  - `sea_level: 32`
  - noise `min_y: 0`
  - noise `height: 256`
  - custom Amplified Nether density functions/noises
  - aquifers disabled
- NeverFolia must adapt this to the approved NeverNether geometry rather than copying the 256-block source height directly.

### Dungeons and Taverns
- Archive: `Dungeons and Taverns v5.3.2.zip`
- Supplied target: Minecraft 26.2
- Pack metadata uses current 26.2 data format.
- Approved role: Nether structure source only.
- Nether-oriented structures referenced by its Nether structure sets include:
  - `nova_structures:nether_port`
  - `nova_structures:nether_keep`
  - `nova_structures:hamlet`
  - `nova_structures:piglin_outstation`
  - `nova_structures:piglin_donjon`
  - `nova_structures:sealing_halls`
  - `nova_structures:piglin_camp`
  - `nova_structures:piglin_camp_collony`
  - `nova_structures:nether_skeleton_tower_fort`
  - `nova_structures:nether_skeleton_tower_warped`
  - `nova_structures:nether_skeleton_tower_crimson`
  - `nova_structures:nether_skeleton_tower_soul`
- The archive also contains a substantial `minecraft:nether_fortress/*` Jigsaw/template-pool content layer. This must be reviewed separately before deciding whether it replaces/extends NeverNether Fortress generation.
- Original source absolute start heights are based on a much smaller Nether and must not be accepted unchanged.

### Explorify
- Archive: `Explorify v1.6.5.dp.zip`
- Internal version: `1.6.5`
- Supplied target: Minecraft 26.2
- Approved role: Nether structures only.
- Nether structure found:
  - `explorify:black_spiral`
- It uses the `explorify:bastion_spiral/*` Jigsaw pools and targets Bastion-compatible Nether biomes.
- Source placement: spacing 40, separation 18, frequency 1.0, salt 30184232. This is reference data only; NeverNether will define final placement.

### Structory: Towers
- Archive: `Structory_Towers_v1.0.17.zip`
- Internal pack id: `structory_towers`
- Supplied target: Minecraft 26.2
- Approved role: Nether tower structures only.
- Nether structures found:
  - `structory_towers:nether/fortress_tower`
  - `structory_towers:nether/strange_outpost`
  - `structory_towers:nether/warped_outpost`
- Source structure set groups these under `structory_towers:nether_towers`; final NeverNether placement will be replaced/rebalanced.

### Repurposed Structures - Better Ocean Monuments compatibility
- Archive: `Repurposed_Structures-Better_Monuments_v7.zip`
- Internal description: `Repurposed Structures - Yung's Better Ocean Monument v7`
- Source pack format: `26`, with broad supported format range.
- SHA-256 of supplied archive: `c76cd5ab549974b051a352a633abd2f78a916acc40392bc53ba0581c3116a8c9`.
- Status: **ACCEPTED as the correct Nether Monument source input**.
- Approved import scope: only the Nether Monument and its required dependencies.
- Nether Monument structure definition found:
  - `repurposed_structures:monument_nether`
- Source structure characteristics:
  - custom type: `repurposed_structures:generic_jigsaw_structure`
  - start pool: `betteroceanmonuments:nether/starts`
  - Jigsaw size: `20`
  - terrain adaptation: `none`
  - source absolute start height: `31`
  - custom monster spawn overrides: magma cubes, wither skeletons and ghasts
- Nether Monument content inventory found in the compatibility archive:
  - 46 Nether `.nbt` structure templates
  - 10 Nether Jigsaw template pools
  - 1 Nether processor list: `betteroceanmonuments:nether/main`
  - dedicated Nether mob templates including magma cube, strider and custom super-wither template content
- The source processor list depends on Repurposed Structures custom processor types, including noise/random property replacement, pillar processing and structure-void processing.
- The archive also references the biome tag `#repurposed_structures:has_structure/monuments/nether`, but that Nether tag is not provided by this compatibility ZIP, indicating dependency on the base Repurposed Structures content/runtime.
- NeverNether will therefore **not** depend on the original custom structure type or missing external biome tag at runtime. NeverFolia will provide its own native placement/validation and explicit Nether biome eligibility.
- Required visual processor behavior will be ported/reimplemented in a deterministic NeverFolia-compatible form rather than requiring the full Repurposed Structures runtime solely for this monument.
- The source absolute Y=31 is reference-only and will be replaced by a NeverNether placement profile suitable for the 512-block generated Nether body.

## Merge rules confirmed by audit

- Source datapack placement values are not production authority.
- All source absolute Y values must be remapped/validated for the 512-block generated Nether body.
- No imported structure or feature may generate in the 512-block roof construction zone unless explicitly approved later.
- Source namespaces may be retained as compatibility aliases internally, but production NeverNether placement and fingerprinting are controlled by NeverFolia.
- Dependencies are imported transitively only when required by approved Nether content: NBT templates, Jigsaw pools, processor lists, loot tables, biome tags and required configured/placed features.
- Custom structure/processor types from source packs are not accepted as mandatory runtime dependencies when the approved content can be represented natively or by a small deterministic NeverFolia implementation.
- Every imported source archive is immutable for a given content fingerprint.
