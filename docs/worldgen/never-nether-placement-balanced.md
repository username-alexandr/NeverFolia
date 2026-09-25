# NeverNether balanced structure placement profile

Branch: `feature/never-nether-worldgen`
Status: approved density + vertical-band baseline; final salts/config implementation pending
Worldgen version: `NN-DEV-1`

## Approved density target

Profile: **BALANCED**

Distances below are design targets for mathematical placement candidates before biome, terrain, bounding-box, collision and exclusion validation. They are not guarantees that a structure will successfully generate at every candidate.

### Tier A — landmark / major

Target successful-candidate spacing: approximately **1000–1600 blocks**.

Members:
- `minecraft:fortress`
- `minecraft:bastion_remnant`
- `nova_structures:nether_keep`
- `nova_structures:piglin_donjon`
- `nova_structures:sealing_halls`
- `repurposed_structures:monument_nether`

Rules:
- Vanilla Fortress and Dungeons & Taverns `nether_keep` **coexist**; neither replaces the other.
- Vanilla Bastion rarity is preserved as the initial NeverNether baseline. Piglin custom structures do not automatically reduce Bastion frequency.
- Major structures use mutual bounding-box collision checks and exclusion margins.
- Nether Monument is intentionally much rarer than normal Tier A structures: target successful occurrences approximately **3000–4000 blocks apart**.

### Tier B — medium destination

Target successful-candidate spacing: approximately **500–900 blocks**.

Members:
- `nova_structures:nether_port`
- `nova_structures:hamlet`
- `nova_structures:piglin_outstation`
- `explorify:black_spiral`
- `hearths:crimson_tower`
- `hearths:warped_tower`
- `structory_towers:nether/fortress_tower`
- `structory_towers:nether/strange_outpost`
- `structory_towers:nether/warped_outpost`

Rules:
- Medium structures may use biome-specific pools and vertical preferences.
- They may be near major structures when terrain allows, but their final bounding boxes must not intersect major structure bounding boxes or protected structure envelopes.

### Tier C — small / ambient

Target successful-candidate spacing: approximately **250–450 blocks**.

Members:
- `minecraft:ruined_portal_nether`
- `minecraft:nether_fossil`
- `hearths:netherrack_spiral`
- `nova_structures:nether_skeleton_tower_fort`
- `nova_structures:nether_skeleton_tower_warped`
- `nova_structures:nether_skeleton_tower_crimson`
- `nova_structures:nether_skeleton_tower_soul`
- `nova_structures:piglin_camp`
- `nova_structures:piglin_camp_collony`

Rules:
- Small structures **may generate close to a major structure** and may visually form camps/outskirts around it.
- They must never generate inside or overlap the bounding box of a major structure.
- A small configurable safety margin will be applied around the major structure's exact bounding box to avoid clipping walls, bridges or jigsaw extensions.

## Approved vertical terrain bands

The generated Nether body is `Y=-128..383`. Bands overlap intentionally so terrain/structure placement does not look like rigid horizontal floors.

- **Deep Nether:** `Y=-120..-32`
- **Lower / Lava:** `Y=-32..96`
- **Main Nether:** `Y=64..260`
- **Upper Nether:** `Y=220..376`

Structures receive preferred bands, not hard universal floors, unless their gameplay/terrain requirements demand one.

### Initial family preferences

- Vanilla Fortress: Lower/Lava + Main; rare Upper candidates allowed when terrain validation succeeds.
- Bastion Remnant: Lower/Lava + Main; vanilla rarity retained.
- Nether Keep: Main + Upper, with occasional Lower/Lava placement.
- Piglin Donjon: Lower/Lava + Main.
- Sealing Halls: Deep + Lower/Lava, favoring enclosed large caverns.
- Nether Port: Lower/Lava, near large lava bodies or lava-accessible terrain.
- Hamlet: Main + Upper, requiring usable terrain volume.
- Piglin Outstation: Main + Upper.
- Hearths Crimson/Warped Towers: Main + Upper in their matching biomes.
- Explorify Black Spiral: Lower/Lava + Main.
- Structory Nether Towers: Main + Upper, with biome-specific eligibility.
- Skeleton towers: Lower/Lava + Main, biome-specific where applicable.
- Piglin camps: Lower/Lava + Main; may occur as outskirts near major Piglin structures.
- Ruined Portal: broad placement across Deep/Lower/Main/Upper when safe.
- Nether Fossil: primarily Soul Sand Valley-compatible terrain across Lower/Main, with limited Deep placement.
- Netherrack Spiral: Lower/Main in Nether Wastes-compatible terrain.

## Nether Monument — approved placement identity

`repurposed_structures:monument_nether` is a rare lava-sea/lava-lake landmark.

- Target successful occurrence distance: **3000–4000 blocks**.
- Preferred band: **Lower / Lava** (`Y=-32..96`).
- It should generate in a sufficiently large lava lake/sea basin, not as an arbitrary dry cave structure.
- The lower monument volume may be submerged in lava / embedded into the lava basin floor while a recognizable upper portion remains exposed above lava.
- Candidate validation must confirm a large enough continuous lava body and sufficient surrounding cavern volume.
- It must not clip bedrock, the upper roof, or other major structures.
- Monument validation is coarse-first and deterministic; rejection must not trigger synchronous chunk generation.

## Collision and exclusion policy

1. Exact bounding-box intersection is always rejected.
2. Jigsaw structures are checked after assembly against bedrock boundaries and the roof construction zone.
3. Small/medium structures may be geographically close to majors, but may not occupy the major structure body or protected envelope.
4. Major-vs-major placement receives a much larger exclusion radius to prevent landmark clustering.
5. Terrain validation may reject a mathematically valid candidate without searching nearby terrain synchronously.
6. Candidate rejection never triggers synchronous chunk generation.
7. Small/medium proximity is allowed only when the complete structure bounding box remains outside the major structure protected envelope.

## Next implementation values

The implementation may now choose deterministic salts and exact chunk-based `spacing`/`separation` values that approximate the approved block-distance targets. These are engineering constants and do not require separate gameplay approval unless testing shows visibly wrong density.

Still to tune through DEV seeds:
- exact protected-envelope margin around Tier A structures;
- exact lava-body size/coverage threshold for Nether Monument;
- final biome predicates for imported structures;
- exact per-structure candidate spacing after empirical generation counts.
