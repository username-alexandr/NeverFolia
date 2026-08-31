# NeverNether Worldgen

Status: design + implementation branch
Branch: `feature/never-nether-worldgen`
Dimension key: `minecraft:the_nether`
Initial worldgen version: `NN-DEV-1`

## Already fixed by NeverFolia architecture

- Nether keeps the vanilla dimension key `minecraft:the_nether`.
- Nether generation is implemented by NeverFolia core, not an external world generator plugin.
- Nether has its own independent worldgen version and fingerprint.
- Nether can use a seed derived from the master seed, or a dedicated override seed.
- Changing the Nether seed is only valid together with an explicit full reset of the Nether dimension.
- Future Nether resets do not touch Overworld, End, or other NeverLand dimensions.
- DEV/TEST/STAGING/PRODUCTION lifecycle rules apply independently to Nether.
- Generation must be deterministic regardless of chunk order and worldgen thread count.
- Fast Locate, diagnostics, pregen and Dimension Lifecycle Manager must be dimension-aware.

## To define before implementation lock

1. Vertical build range and logical height.
2. Overall terrain identity and vertical layers.
3. Lava sea level and lava-fluid rules.
4. Biomes and biome remapping.
5. Cave/cavern/canyon system.
6. Ores and geological richness maps.
7. Vanilla and custom structures.
8. Fortress and bastion placement rules.
9. Portal safety and spawn validation.
10. Pregeneration/border policy.
11. Reset/resource-renewal policy.
12. Performance budget and regression seeds.

## Design rule

NeverNether should remain recognizably Nether-like where that improves gameplay and plugin compatibility, but exact vanilla generation is not a goal when a custom NeverLand solution is more stable, performant or visually stronger.
