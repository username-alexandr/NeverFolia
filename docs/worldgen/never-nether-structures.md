# NeverNether structure registry

Branch: `feature/never-nether-worldgen`
Status: candidate registry; placement values pending user approval
Worldgen version: `NN-DEV-1`

This registry contains only structures approved for Nether consideration. Source datapack placement values are reference-only.

## Vanilla baseline

- `minecraft:fortress`
- `minecraft:bastion_remnant`
- `minecraft:ruined_portal_nether`
- `minecraft:nether_fossil`

## Hearths

- `hearths:crimson_tower`
  - Source biome: `minecraft:crimson_forest`
  - Source jigsaw size: 6
  - Source start height: absolute 12..24
  - Source terrain adaptation: none
- `hearths:warped_tower`
  - Source biome: `minecraft:warped_forest`
  - Source jigsaw size: 6
  - Source start height: absolute 8..20
  - Source terrain adaptation: none
- `hearths:netherrack_spiral`
  - Source biome: `minecraft:nether_wastes`
  - Source jigsaw size: 6
  - Source start height: absolute 18..22
  - Source terrain adaptation: none

## Dungeons and Taverns

### Major Nether structures

- `nova_structures:nether_port`
- `nova_structures:nether_keep`
- `nova_structures:hamlet`
- `nova_structures:piglin_outstation`
- `nova_structures:piglin_donjon`
- `nova_structures:sealing_halls`

### Nether encampments / towers

- `nova_structures:nether_skeleton_tower_fort`
- `nova_structures:nether_skeleton_tower_warped`
- `nova_structures:nether_skeleton_tower_crimson`
- `nova_structures:nether_skeleton_tower_soul`
- `nova_structures:piglin_camp`
- `nova_structures:piglin_camp_collony`

### Important source notes

- `nether_keep` uses the Dungeons and Taverns `minecraft:nether_fortress/*` Jigsaw content and is not the vanilla `minecraft:fortress` structure.
- `piglin_donjon` and `sealing_halls` are source jigsaw size 20 and should be treated as major structures.
- Source absolute heights (mostly around Y 19..70) must be replaced for the 512-block NeverNether body.

## Explorify

- `explorify:black_spiral`
  - Bastion-compatible Nether biome tag
  - Source jigsaw size: 7
  - Source start height: absolute 32
  - Source spacing/separation: 40/18 (reference only)

## Structory: Towers

- `structory_towers:nether/fortress_tower`
- `structory_towers:nether/strange_outpost`
- `structory_towers:nether/warped_outpost`

Source structure set excludes locations near vanilla `minecraft:nether_complexes`; NeverNether will replace this with its own conflict/exclusion policy.

## Repurposed Structures / Better Monuments

- `repurposed_structures:monument_nether`
  - Start pool: `betteroceanmonuments:nether/starts`
  - Source size: 20
  - Source start height: absolute 31
  - Source spawn overrides: magma cube, wither skeleton, ghast
  - Requires compatibility rewrite from Repurposed Structures custom jigsaw/processor types into NeverFolia/native equivalents.

## Candidate classification

### Tier A — landmark / major

- `minecraft:fortress`
- `minecraft:bastion_remnant`
- `nova_structures:nether_keep`
- `nova_structures:piglin_donjon`
- `nova_structures:sealing_halls`
- `repurposed_structures:monument_nether`

### Tier B — medium destination

- `nova_structures:nether_port`
- `nova_structures:hamlet`
- `nova_structures:piglin_outstation`
- `explorify:black_spiral`
- `hearths:crimson_tower`
- `hearths:warped_tower`
- `structory_towers:nether/fortress_tower`
- `structory_towers:nether/strange_outpost`
- `structory_towers:nether/warped_outpost`

### Tier C — small / ambient

- `minecraft:ruined_portal_nether`
- `minecraft:nether_fossil`
- `hearths:netherrack_spiral`
- `nova_structures:nether_skeleton_tower_fort`
- `nova_structures:nether_skeleton_tower_warped`
- `nova_structures:nether_skeleton_tower_crimson`
- `nova_structures:nether_skeleton_tower_soul`
- `nova_structures:piglin_camp`
- `nova_structures:piglin_camp_collony`

## Placement principles already fixed

- No normal structure may generate in the roof construction zone `Y=384..895`.
- Final placement uses NeverFolia-controlled salts, spacing, separation, biome eligibility, vertical profiles and terrain validation.
- Major structures must have mutual exclusion rules to prevent structure clusters and overlap.
- Jigsaw bounding boxes must be validated against bedrock boundaries and the roof construction zone.
- Fast Locate must use mathematical placement candidates and must never generate chunks.
- Structure placement must be deterministic across pregeneration, exploration and thread ordering.

## Decisions still required

1. Overall structure density target.
2. Whether vanilla Fortress and Dungeons and Taverns Nether Keep coexist.
3. Relative rarity of Nether Monument.
4. Whether structures may span multiple vertical terrain bands or should have preferred bands.
5. Whether small structures are allowed close to major structures or should also respect exclusion radii.
