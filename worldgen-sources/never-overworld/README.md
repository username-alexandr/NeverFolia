# NeverOverworld WorldGen

Native world generation target for NeverFolia.

## Ownership

This package describes systems that should eventually move from datapack/runtime hooks into the NeverFolia core:

- dimension lifecycle
- noise settings
- fluid policy
- geology
- structures

## Design rules

- deterministic from seed and absolute coordinates
- Folia region safe
- no neighbour chunk writes during generation
- no order-dependent RandomSource usage
