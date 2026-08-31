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

## Vertical geometry — approved

NeverNether uses two vertically distinct spaces inside one `minecraft:the_nether` dimension:

1. **Generated Nether body:** 512 blocks from the lower bedrock boundary to the upper bedrock roof.
2. **Roof construction zone:** another 512 buildable blocks above the upper bedrock roof.

Initial coordinate layout:

- Dimension `min_y`: `-128`
- Total dimension height: `1024`
- Highest buildable Y: `895`
- Generated Nether body: `Y=-128..383` (512 blocks total)
- Upper bedrock roof top boundary: approximately `Y=383` (exact irregular bedrock thickness/profile will be defined separately)
- Roof construction zone: `Y=384..895` (512 blocks total)

The roof construction zone is part of the same Nether dimension; NeverFolia must not create a second dimension for it.

### Generation rules above the roof

- Normal Nether terrain generation stops at the upper bedrock roof.
- `Y=384..895` is intentionally empty/buildable space by default.
- Players may place blocks throughout the roof construction zone up to the dimension build limit.
- Normal terrain features, ores, caves, lava seas and standard Nether structures must not generate in the roof construction zone unless a future NeverLand feature explicitly opts into roof placement.
- The roof area must survive normal JAR updates and Nether worldgen revisions exactly like any other already-generated player-built area.
- A Nether reset deletes both the generated body and roof player construction area because both belong to the same dimension; reset therefore requires explicit destructive confirmation and backup policy.

### Pending portal decision

Portal search/creation behavior above the upper bedrock roof must be specified separately. Build permission above the roof does not automatically imply that Nether portals should naturally target or spawn in the roof construction zone.

## To define before implementation lock

1. Exact lower/upper bedrock thickness and irregularity.
2. Overall terrain identity and vertical layers inside `Y=-128..383`.
3. Lava sea level and lava-fluid rules.
4. Biomes and biome remapping.
5. Cave/cavern/canyon system.
6. Ores and geological richness maps.
7. Vanilla and custom structures.
8. Fortress and bastion placement rules.
9. Portal safety and spawn validation, including roof-zone behavior.
10. Pregeneration/border policy.
11. Reset/resource-renewal policy.
12. Performance budget and regression seeds.

## Design rule

NeverNether should remain recognizably Nether-like where that improves gameplay and plugin compatibility, but exact vanilla generation is not a goal when a custom NeverLand solution is more stable, performant or visually stronger.
