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

## Observation workflow and persistence barriers

`never-overworld-tree-village-natural.yml` builds the exact branch candidate,
repeats native regressions and both source preflight checks, and fingerprints
the matching Overworld datapack. It starts a NEW disposable server, with no
production Java instrumentation or console placement of synthetic trees.

The fixed seed is `-2996952393010080672`. Three 5x5 areas are located near forest,
birch forest and taiga. Plains and desert village starts are also located.

Run `35510250669` on `ecfdb3d` passed compilation/native smoke and pack creation,
but its observer failed before the requested sample generation. The server
positively acknowledged `Gamerule random_tick_speed is now set to: 0`, then
rejected `save-all flush`. A subsequent say marker did NOT establish a save.
The observer incorrectly attributed that later command error to the gamerule.
Artifact `10606005262` contains the separate replies in `tree-village-server.log`.

The corrected harness does not use `save-all`:

1. It requires the positive gamerule response in that command's new log window.
2. It requests the forest areas and initial village chunks in bounded batches.
   Every requested chunk must answer its own `execute if loaded` probe before
   tickets are released. This is a runtime load barrier, NOT persisted evidence.
3. It explicitly sends `stop` and requires process exit code 0. Only after the
   process has exited does it read saved NBT, check FULL status and coordinates,
   and derive actual village piece bounding boxes.
4. It restarts the SAME newly created test world with the SAME JAR and datapack,
   generates each saved village bbox plus a one-block margin, and stops normally
   again. All final requested chunks are verified FULL from the stopped world.

The plan records both stop phases and final verification separately. An abnormal
stop, missing chunk, wrong persisted status, stale/absent command reply, changed
datapack or incomplete phase cannot be accepted. Source SHA is recorded when
the plan is first created, including for failed runs. Input/installed datapack
hashes are checked before each start. No locks, regions or world data are deleted
or bypassed. A pre-existing working-world directory is rejected.

Thirty synthetic tests cover the original 15 observer regressions and 15 new
console/lifecycle regressions. They test the real command-response parsing and
mock the server lifecycle to assert that no NBT read occurs while it is alive.
They do NOT replace executing the corrected harness against the actual server.
Outputs include source SHA, binary hashes, selected chunks, separate phase logs,
component findings and village Y128 column CSVs.

## Deliberately limited claims

The tree observer classifies six-connected wood/leaf components, not individual
tree identities. A wholly submerged observation is at/below Y128 and contacts
water; not every block face is proven wet. Horizontal logs are candidates, not
proof of a fallen-tree feature. Exact fallen-tree and two/three-submerged-block
fixtures remain separately covered by native smoke. Missing examples are not
manufactured to pass; absence of a complete underwater component still fails.

Village CSVs record Y128 block names and membership in piece XZ boxes. These
boxes are NOT exact foundation footprints. Water between pieces is permitted;
no all-dry village-bbox gate is reinstated. A flat natural area or water between
buildings alone cannot establish visual acceptance. Shoreline buildings and
foundations still need visual review. The source gate separately proves removal
of the custom reclamation hook.

This correction changes only the observer, its tests and this documentation.
The TREE-R1 preservation rules, VILLAGE-NOFILL-R1 override and native Nether
implementation are unchanged. The workflow publishes diagnostics only, not a
release or a replacement server distribution. No staging/main promotion,
existing-world repair, multi-seed or player-load acceptance is claimed.
