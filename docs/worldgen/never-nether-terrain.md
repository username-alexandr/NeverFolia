# NeverNether terrain profile

Branch: `feature/never-nether-worldgen`
Status: approved openness + mega-cavern baseline; secondary cave families pending
Worldgen version: `NN-DEV-1`

## Approved overall openness

Profile: **BALANCED**, with the **Lower / Lava band intentionally more open** than the rest of the Nether.

Generated Nether body: `Y=-128..383`.

Approved overlapping vertical bands:
- Deep Nether: `Y=-120..-32`
- Lower / Lava: `Y=-32..96`
- Main Nether: `Y=64..260`
- Upper Nether: `Y=220..376`

These are probabilistic terrain tendencies, not hard horizontal floors. Caverns, pillars, bridges and terrain masses may cross band boundaries.

## Band character

### Deep Nether — `Y=-120..-32`

- Denser rock than the rest of the dimension.
- Long tunnels and medium caverns are common enough for traversal.
- Very large caverns exist but are comparatively rare.
- Large enclosed magma chambers/deep lava basins may occur.
- Basalt/blackstone-heavy geological character is preferred for later material tuning.
- Terrain should never become an almost-solid unplayable slab; navigable connectivity remains required.

### Lower / Lava — `Y=-32..96`

- **Most open vertical band in NeverNether.**
- Primary lava sea reference level remains `Y=32`.
- Large open lava basins, cliffs, shelves, bridges, pillars and island-like masses are common.
- Long sight lines and large cavern volumes are intentionally more frequent here.
- The band is the main host for lava-sea landmarks such as the Nether Monument.
- Open space must still be interrupted by substantial terrain masses so the dimension does not collapse into one continuous empty lava ocean.

### Main Nether — `Y=64..260`

- Balanced mixture of solid terrain and open caverns.
- Main gameplay layer for forests, Nether Wastes, Soul Sand Valley and Basalt Deltas.
- Supports tunnels, medium/large caverns, vertical shafts, bridges and terrain shelves.
- Should preserve the recognizable spatial language of Amplified Nether while scaling it for the 512-block generated body.

### Upper Nether — `Y=220..376`

- Balanced-open character, but not as open as Lower/Lava.
- More large ceiling caverns, hanging terrain masses, suspended shelves and natural bridges.
- Vertical voids may connect downward into Main Nether.
- Terrain density increases toward the upper bedrock roof so caves/features do not leak into the roof construction zone.

## Mega-cavern profile — approved

Mega-caverns are rare regional terrain volumes, not ordinary per-chunk caves.

Target geometric range:
- width: approximately **180–450 blocks**;
- vertical height: approximately **90–220 blocks**;
- longitudinal extent: approximately **300–900+ blocks**;
- regional occurrence target: approximately **one major mega-cavern region per 900–1500 blocks**, before terrain-field rejection/merging.

Placement character by vertical band:
- **Lower / Lava:** highest mega-cavern probability; many successful regions may host major lava seas, large islands, cliffs and long sight lines.
- **Main Nether:** moderate probability; large caverns should connect biome regions without making the entire band hollow.
- **Upper Nether:** moderate-low probability; favor tall ceiling chambers, hanging masses and vertical connections.
- **Deep Nether:** lowest probability; when present, caverns should feel exceptional and may contain magma chambers or deep lava basins.

Mega-cavern generation rules:
- Caverns are driven by low-frequency deterministic regional fields, never by shared mutable RNG.
- A cavern may cross multiple vertical bands when its regional field supports it.
- Adjacent mega-cavern candidates may blend into one coherent larger system, but must not create near-global continuous voids.
- Cavern edges should transition through shelves, ridges, pillars and secondary chambers instead of abrupt spherical cutouts.
- Bedrock protection gradients take priority near both lower and upper boundaries.
- Mega-cavern classification must be sampleable mathematically for diagnostics and coarse structure validation without loading/generating neighboring chunks.

## Global terrain rules

- NeverNether must not be generated as four literal stacked terrain layers.
- Large terrain features may span multiple vertical bands.
- No global/shared mutable RNG is allowed; terrain sampling must be deterministic from seed, stable salts and coordinates.
- Amplified Nether density/noise is the primary terrain reference, but its original 256-block vertical assumptions must be adapted rather than simply stretched by a factor of two.
- The resulting terrain should preserve large-scale visual coherence: connected ridges, caverns, cliffs and terrain masses rather than independent noisy chunk-scale blobs.
- Terrain generation must remain order-independent across Folia region/thread execution.
- Upper terrain density and bedrock termination must prevent natural blocks/features from entering `Y=384..895`.

## Performance requirements

- Large-cavern decisions must be obtainable from deterministic low-frequency fields and not require neighbor chunk generation.
- Terrain candidate evaluation must avoid synchronous chunk generation.
- Worldgen Inspector should eventually expose local openness/density classification, active terrain band and mega-cavern region id/classification.
- Generation behavior must degrade gracefully with 20–30 concurrent exploring/chunk-generating players.

## Still pending

- Medium cave/tunnel frequency and width profile.
- Vertical chasm dimensions/frequency.
- Hanging-island/mass frequency in Main/Upper Nether.
- Deep magma chamber dimensions/frequency.
- Exact density-function adaptation from Amplified Nether 256-block source to NeverNether 512-block generated body.
