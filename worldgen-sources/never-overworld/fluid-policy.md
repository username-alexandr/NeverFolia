# NeverOverworld Fluid Policy

## Goals

The final target is native fluid ownership inside NeverFolia.

## Rules

- lava aquifers disabled
- lava generation must be impossible in normal terrain generation
- water placement follows explicit flood policy
- hard lava cleanup is diagnostics only, not generation logic

## Migration order

1. native FluidPicker
2. native aquifer policy
3. remove biome JSON liquid workarounds
4. runtime assertion if forbidden fluids appear
