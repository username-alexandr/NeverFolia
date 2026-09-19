# NeverNether R15 — original-substrate field cleanup

Status: **candidate under natural acceptance**.

R15 is a narrow native cleanup layered after the exact R14 + BUG01 source chain.
It changes only NEW chunk generation before R10 captures the immutable CARVERS
substrate. It does not migrate or rewrite existing regions, change the R14
datapack/storage profile, loosen the roof512 guard, or remove worldgen locks.

## Evidence that motivated R15

Current-branch natural-integrity baseline:

- source SHA: `57aa2bc6400b02d062397d83fbb1834cfc308c8e`;
- workflow run: `35396582409`;
- seed: `-2996952393010080672`;
- sample: 50 saved `minecraft:full` chunks from two bounded areas;
- Roof512: 12,800/12,800 sampled roof cells were bedrock;
- technical padding Y=513..527: 0 non-air blocks;
- source lava blocks: 1,429,816;
- flowing lava blocks: 48;
- source-lava blocks with air below: 1;
- hanging source-lava shelf candidates: 1;
- enclosed small natural-rock air components up to 64 blocks: 68 / 335 blocks.

The hanging shelf candidate was persisted at:

`X=-3109, Y=10, Z=-6289`

Its saved signature was:

- source lava at the candidate cell;
- source lava directly above;
- cave air directly below;
- 2 horizontal source-lava neighbours;
- not inside a saved structure bbox;
- candidate provenance: `original`;
- below-cell provenance: `original`.

This proves that the observed cell existed in the immutable original substrate.
It was not produced by an R10/R12 proposal or by an externally recorded
post-capture writer.

For tiny cavities, the baseline buckets were:

- size 1: 41 components;
- size 2–4: 16 components;
- size 5–16: 6 components;
- size 17–64: 5 components.

Of the size<=4 set, 50 components / 69 blocks were fully inside an owning chunk.
Seven components / 10 blocks touched a chunk edge and are intentionally outside
the initial R15 cleanup contract.

## R15 cleanup contract

R15 runs after the R10 persisted-status rejection guard and before R10 creates
its immutable CARVERS snapshot.

### Tiny enclosed cavities

R15 may fill an air/cave-air component only when all of the following are true:

1. component size is 1–4 blocks;
2. it is fully contained inside the owning chunk;
3. it does not touch Y=-128 or Y=511;
4. every non-air boundary cell is recognized natural Nether rock;
5. no cross-chunk read is required.

The replacement is chosen deterministically from surrounding non-resource
natural materials. Quartz/gold ore, ancient debris and bedrock are not copied
as generic fill material.

Components of size 5 or more are preserved. Any component touching a chunk
boundary is preserved. This deliberately favors false negatives over sealing a
valid cave or introducing chunk-order dependence.

### Hanging source-lava shelves

R15 may solidify a source-lava cell only when:

1. the block below is air/cave-air;
2. at least two available horizontal cells in the owning chunk are also source lava;
3. the replacement is derived from nearby recognized natural rock;
4. no neighbouring chunk is loaded or read.

The rule targets a horizontal unsupported shelf, not a single source at a
lavafall/edge. The known baseline candidate is on local Z=15, so edge ownership
is explicitly covered without reading the adjacent chunk.

## Ordering and persistence

The required order is:

`R8 → R9 → R10 → R11 → R12 → R13 → R14 → BUG01 → R15`

Inside `NeverNetherSubstrateR10.capture()`:

1. reject a chunk already persisted at/after FEATURES;
2. run R15 cleanup;
3. capture section states as the immutable original substrate;
4. bind/persist R11+ metadata.

Therefore R15 changes become part of the recorded original substrate. They are
not marked as external/proposal writes and cannot run on a previously decorated
saved chunk.

## First natural R15 result — partial, not accepted

Run `35453824789`, source `13644025bd063ee75d98c688d2610055c1f9c772`,
used the same seed and 50-chunk two-area plan as the pre-R15 baseline.

Confirmed:

- native R15 smoke: **PASS**, 19 checks;
- generated/saved chunks: **50/50 FULL**;
- Roof512 cells: **12,800 checked**, no failures;
- technical padding Y=513..527: **0 non-air**;
- natural-integrity runtime gate: **PASS**.

Cavity comparison against baseline `57aa2bc`:

- all enclosed components <=64: **68 -> 45**;
- enclosed blocks: **335 -> 303**;
- tiny size<=4 components: **57 -> 34**;
- tiny blocks: **79 -> 47**;
- owner-chunk-contained original tiny components: **50 -> 27**;
- owner-chunk-contained original tiny blocks: **69 -> 37**;
- chunk-edge tiny components remained **7 / 10 blocks**, which is expected because
  pre-capture R15 deliberately performs no neighbour-chunk reads.

Exactly 23 tiny components disappeared and the audit found **0 newly-added tiny
components** at new sample coordinates. This proves the pre-capture cleanup is
effective but insufficient: some small residual cavities become isolated only
after later FEATURES writes surround portions of a larger CARVERS cavity.

Lava comparison:

- source lava blocks: **1,429,816 -> 1,429,816**;
- source lava with air below: **1 -> 1**;
- hanging shelf candidates: **1 -> 1**;
- the same original-provenance candidate remains at
  `[-3109, 10, -6289]`.

Therefore R15 is still a candidate. The next correction needs a conservative
post-FEATURES owner-chunk cleanup and an evidence-based chunk-edge shelf rule.

## Second natural R15 result — post-FEATURES candidate

Run `35466716075`, source `030234167eb501daf2d37def572a329fd81dfe88`,
adds the conservative LIGHT-barrier post-FEATURES micro-cavity pass and the
evidence-based chunk-edge hanging-lava rule.

Confirmed on the same seed and 50-chunk sample:

- native R15 smoke: **PASS**, 28 checks;
- 50/50 selected chunks saved as `minecraft:full`;
- Roof512: **PASS**, 12,800 roof cells checked;
- technical padding Y=513..527: **0 non-air**;
- source lava with air below: **1 -> 0**;
- hanging source-lava shelf candidates: **1 -> 0**;
- all hanging-shelf provenance buckets: **0**;
- owner-chunk-contained original micro components: **27 -> 7**;
- owner-chunk-contained original micro blocks: **37 -> 8**;
- chunk-edge micro components remain **7 / 10 blocks** by design.

Every one of the seven residual owner-contained original components lies at
**Y=510** (six single-block components and one two-block component). There are
no residual owner-contained original micro-cavities below Y=510 in this sample.

R14 defines a randomized five-block bedrock envelope from Y=507 through Y=511
below the mandatory solid bedrock roof at Y=512. R15 deliberately refuses to
copy bedrock as generic cavity fill material. Therefore residual Y=510 pinholes
belong to the roof-envelope diagnostic class and are not treated as body-rock
field defects. The hard R15 body gate is Y=-128..506; the R14 roof audit remains
the authority for Y=507..512.

## Acceptance gates

Before R15 may be treated as accepted:

- installer self-test must pass;
- native R15 ProtoChunk smoke must pass;
- current Paperclip must compile;
- the same two-area 50-chunk natural-integrity sample must reach FULL and stop normally;
- Roof512/padding must remain exact;
- the baseline hanging shelf must no longer appear;
- owner-chunk-contained size<=4 enclosed cavity findings whose persisted provenance is entirely `original` must fall to zero;
- tiny components created later by `external`/`proposal` writers remain diagnostic rather than being misattributed to CARVERS substrate;
- boundary-touching and size>=5 cavity findings remain diagnostic, not failure conditions;
- all existing NeverOverworld FIELD-R11 / DESERT-R1 / village gates must remain green;
- before production promotion, the native R15 generator revision must participate in a persisted NeverNether worldgen/native lock or matching fingerprint marker. The unchanged R14 datapack content fingerprint alone must not be used to imply that pre-R15 and R15 native generation are the same profile.

R15 is not an existing-world repair. Existing generated Nether chunks require a
separate migration/reset decision. Until the native-revision lock is added, use
R15 only with a NEW disposable/test Nether and do not mix R14-only and R15-generated
chunks under the same production world identity.
