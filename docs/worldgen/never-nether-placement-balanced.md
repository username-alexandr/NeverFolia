# NeverNether balanced structure placement profile

Branch: `feature/never-nether-worldgen`
Status: approved density baseline; per-structure vertical/range tuning pending
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
- Nether Monument gets an independent rarity decision; it is not automatically assigned the normal Tier A frequency.

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

## Collision and exclusion policy

1. Exact bounding-box intersection is always rejected.
2. Jigsaw structures are checked after assembly against bedrock boundaries and the roof construction zone.
3. Small/medium structures may be geographically close to majors, but may not occupy the major structure body or protected envelope.
4. Major-vs-major placement receives a much larger exclusion radius to prevent landmark clustering.
5. Terrain validation may reject a mathematically valid candidate without searching nearby terrain synchronously.
6. Candidate rejection never triggers synchronous chunk generation.

## Still pending

- Exact rarity multiplier for `repurposed_structures:monument_nether`.
- Vertical placement bands/preferences for each structure family inside generated Nether body `Y=-128..383`.
- Exact safety margins for Tier B/C around major bounding boxes.
- Final per-structure `spacing`, `separation`, `salt`, biome eligibility and terrain predicates.
