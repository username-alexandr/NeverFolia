# NeverOverworld native migration audit

## Current repository state

The repository currently contains the architecture layer for NeverOverworld:

- worldgen-spec: contracts and validation targets
- worldgen-sources: design documentation
- neverfolia-patches: patch layer
- tools: validation utilities

## Native migration status

The migration target remains:

1. Native dimension contract
2. Native fluid policy
3. Native geology engine
4. Native structure placement
5. Native locate optimizations

## Audit findings

The current branch does not expose a direct Java implementation of NeverFluidPolicy or NeverGeologyEngine in the searchable tree yet. The next implementation stage must locate the actual Folia patch insertion points before adding Java classes.

Required search targets in upstream patches:

- NoiseBasedChunkGenerator
- NoiseGeneratorSettings
- DimensionType bootstrap
- ChunkGenerator.applyBiomeDecoration
- Structure placement hooks

## Next implementation order

1. Add native package skeleton only after locating patch targets.
2. Implement NeverFluidPolicy behind a dimension check.
3. Add runtime fingerprint logging.
4. Add deterministic geology prototype.
5. Add CI compilation gate.
