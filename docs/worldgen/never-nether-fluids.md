# NeverNether fluid profile

Branch: `feature/never-nether-worldgen`
Status: approved lava-level baseline; secondary lava-body tuning pending
Worldgen version: `NN-DEV-1`

## Approved primary lava level

- Primary Nether lava sea level: **Y=32**.
- This value is intentionally preserved from the supplied Amplified Nether source profile.
- Increasing the generated Nether body to 512 blocks does **not** proportionally raise the primary lava level.
- The primary lava level is part of the NeverNether worldgen contract and therefore contributes to the worldgen fingerprint.

## Vertical context

Generated Nether body: `Y=-128..383`.

Approved overlapping terrain bands:
- Deep Nether: `Y=-120..-32`
- Lower / Lava: `Y=-32..96`
- Main Nether: `Y=64..260`
- Upper Nether: `Y=220..376`

The primary lava sea at `Y=32` sits inside the Lower/Lava band and acts as the main reference surface for large open lava seas.

## Lava-body model

NeverNether should not be represented by one perfectly flat global lava sheet. The approved design uses multiple deterministic lava-body categories:

1. **Primary lava sea**
   - reference surface: `Y=32`
   - large connected open basins and seas
   - major visual/navigation layer of the lower Nether

2. **Deep lava basins**
   - may occur below the primary sea in Deep/Lower terrain
   - generated as bounded large basins/chambers, not as a second global sea

3. **Isolated lava lakes**
   - may occur above or below Y=32 where terrain permits
   - must be distinct placed/generated features rather than uncontrolled aquifer leakage

4. **Lava falls**
   - may descend from walls/ceilings through large caverns across much of the generated Nether body
   - deterministic placement and biome/terrain-aware density

5. **Structure lava**
   - explicitly placed or preserved by approved structures/processors
   - validated independently from natural lava features

## Nether Monument integration

`repurposed_structures:monument_nether` is tied to large lava bodies.

- Target rarity: successful occurrences roughly 3000–4000 blocks apart.
- Preferred vertical band: Lower/Lava.
- Candidate must intersect or border a sufficiently large continuous lava sea/lake basin.
- Lower monument volume may be submerged or embedded into the lava basin floor while a recognizable upper portion remains exposed above lava.
- Small isolated lava lakes are not valid Monument hosts.
- Monument candidate validation must use deterministic coarse terrain/fluid predicates first and must never synchronously generate chunks while locating or validating candidates.

## Implementation rules

- Amplified Nether source `sea_level: 32` is retained as the NeverNether primary lava level.
- NeverFolia owns the final fluid logic; source datapack fluid placement is not authoritative after merge.
- Fluid generation may not leak above the upper bedrock roof into the roof construction zone `Y=384..895`.
- Lava placement is deterministic from Nether seed + worldgen version + stable feature salt + coordinates.
- Fluid behavior used for worldgen is separated from normal player bucket/fluid simulation after chunk generation.
- Fast Locate and Worldgen Inspector should be able to classify major lava bodies without forcing chunk generation.

## Still pending DEV tuning

- Exact frequency and typical dimensions of deep lava basins.
- Exact frequency/size range of isolated high lava lakes.
- Lava-fall density by biome and vertical band.
- Minimum lava-body area/volume required for Nether Monument placement.
- Interaction of Hearths lava/fire features with NeverNether fluid categories after the merged content layer is assembled.
