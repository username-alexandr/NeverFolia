# NeverNether deep magma chambers

Branch: `feature/never-nether-worldgen`
Status: approved baseline
Worldgen version: `NN-DEV-1`

## Approved size classes

Deep magma chambers and lava basins are regional terrain features concentrated in the Deep Nether and lower part of the Lower/Lava band.

### Ordinary magma chamber

- horizontal extent: approximately **60–140 blocks**;
- vertical extent: approximately **30–80 blocks**;
- common enough to contribute to Deep Nether identity, but not present in every local cave system.

### Large magma chamber

- horizontal extent: approximately **140–300 blocks**;
- vertical extent: approximately **60–140 blocks**;
- clearly less common than ordinary chambers;
- may connect to large caverns, chasms or deep lava basins.

### Giant magma chamber

- horizontal extent: approximately **300–500+ blocks**;
- vertical extent: up to approximately **180 blocks**;
- rare landmark-scale feature;
- may form a regional deep lava basin with islands, shelves and basaltic pillars.

## Vertical weighting

- Primary host: **Deep Nether** (`Y=-120..-32`).
- Secondary overlap: lower part of **Lower / Lava** (`Y=-32..96`).
- Main/Upper Nether should not routinely produce deep magma chambers.
- Chambers may cross band boundaries when the regional terrain field naturally supports it.

## Shape and fluid rules

- Chambers are irregular regional volumes, not smooth ellipsoids or per-chunk spheres.
- A chamber may be partially or heavily lava-filled; full filling is not mandatory.
- Lava surfaces do not define a second global sea level. The global reference lava sea remains `Y=32`.
- Chambers may contain basalt/blackstone-heavy walls, columns, shelves, islands and exposed ridges.
- Connections to vertical chasms and mega-caverns are allowed and should look continuous.
- Deep magma generation must respect lower bedrock protection and may not carve through the lower boundary.

## Determinism and performance

- Chamber existence, approximate bounds and class must be derivable from deterministic regional fields.
- No shared mutable RNG.
- No synchronous neighbor-chunk generation.
- Coarse magma-chamber classification must be queryable for diagnostics and structure terrain validation.
- Final block/fluid realization occurs only for the chunk being generated.

## DEV tuning

Exact frequency, lava-fill ratio, basalt/blackstone material weighting and interaction thresholds with chasms/mega-caverns remain engineering tuning values and can be adjusted after seed inspection without changing the approved size identity.
