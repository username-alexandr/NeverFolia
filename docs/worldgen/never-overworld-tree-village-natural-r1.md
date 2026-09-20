# TREE-R1 / VILLAGE-NOFILL-R1: native result and saved-world observation

## Confirmed preceding result

Source `2e3c011d0bb815ac88a22c983b1c413c5ac68fb9`, run `35508664061`,
completed successfully on 2026-09-20. The downloaded diagnostic artifact
`10604813283` passed its ZIP CRC check and recorded:

- `PASS TreePreservationSmoke checks=21325`;
- `PASS VillageFoundationSmoke checks=7` (historical helper, runtime call disabled);
- `PASS FloodBoundarySmoke checks=6`;
- `PASS DesertR1Smoke checks=591378`;
- `PASS SandstormR1Smoke checks=47809`;
- 13 tree-transformer tests, 12 no-reclamation transformer tests and 6 FIELD-R11 tests.

This proves compilation and the stated native fixtures, not natural village shape.

## New observation workflow

`never-overworld-tree-village-natural.yml` builds the exact branch candidate,
repeats the native regressions and both source preflight checks, builds and
fingerprints the matching Overworld datapack, and then starts a NEW disposable
server. There is no new production Java change in this step, no debug source
instrumentation and no placement of synthetic trees through console commands.

The fixed seed is `-2996952393010080672`. Three 5x5 areas are chosen near located
forest, birch forest and taiga biomes. Plains and desert village starts are
located and first saved; then the actual union of saved piece boxes plus a
one-block margin is generated. Every requested chunk must be saved FULL before
unloading. The observer reads final evidence again only after a normal stop.
Missing chunks/statuses/palette data are errors, not empty terrain.

The new script refuses an existing working-world directory instead of deleting
it. Its offline audit only reads region files. Output contains source SHA,
server/datapack byte hashes, requested chunk sets, structured component findings,
logs and village Y128 column CSVs. Fifteen synthetic observer tests cover packed
state decoding, negative coordinates, unknown-neighbour handling, coverage,
non-destructive setup, and preservation of water-between-pieces diagnostics.

## Deliberately limited claims

The tree observer classifies six-connected wood/leaf components. It does not
claim one component equals one tree. Wholly submerged observations mean every
component block is at/below Y128 and the component contacts water; they do not
prove every face is wet. Horizontal logs are reported as candidates, not proof
of a fallen-tree feature. Natural observations do not replace exact native
fixtures for fallen trees or two/three submerged blocks. An absent example is
reported as absent, never manufactured to pass the observation.

Village CSVs record block names at Y128 and membership in piece XZ bounding
boxes. Those boxes are NOT exact building/foundation footprints. Water outside
them is permitted; no zero-water-over-the-whole-village requirement is used.
Neither a flat natural area nor water between buildings automatically proves or
disproves an artificial platform. Visual review of shoreline buildings and
foundations remains outstanding. The source gate separately proves removal of
the custom reclamation hook.

The workflow publishes diagnostics only. No staging/main promotion, old-world
repair, complete release, multi-seed or player-load acceptance is claimed.
