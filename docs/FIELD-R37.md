# FIELD-R37 — continuation of water / dungeon / mob repair

Base source: `8b52c3f30df55452a06d4ceece2ad84add52ee61`.
This is a **candidate**, not a declaration that all reported world defects are fixed.
Use the JSON results and workflow conclusion for the exact source commit.

## Scope

* Close the R35 neighbour-cache traversal AND final-write bypass. The owner LIGHT
  pass creates synthetic ocean water strictly above each natural ocean floor up
  to Y128. It does not use the old arbitrary Y96 cutoff, flood roofed cave AIR,
  remove native WATER, load missing neighbours, or mutate existing FULL chunks.
* Keep R34 synthetic island/foundation generation disabled; surface structures
  must be admitted by natural terrain instead of receiving a square platform.
* Sanitize foreign `porting_lib` attribute entries in **all** imported namespaces,
  not only Dungeons & Taverns. Preserve original bytes for unaffected templates.
* Retain item frames, glow frames, paintings and leash knots. Set their NBT anchor
  to the fully transformed template world coordinate before entity decoding.
  This is an engine change: use the matching R37 JAR with this pack.
* Replace the empty Witch Huts mob pool with real witch/cat jigsaw templates.
  Their initial placement is a NeverFolia compatibility addition, not an asset
  recovered from the source pack. Original source huts and spawn overrides stay.
* The original pinned D&T archive does not contain `pale_residence/decor_inside`.
  Its explicit optional empty element prevents a broken link; it does NOT invent
  missing decorative content or replace the real mob pools.
* Retain 23 selected D&T runtime functions, including the five previously omitted
  ghast/projectile functions. Reuse the finite native DNT bridge and exact pinned
  R6 migrations. Do not enable Folia's generic /function, /data, /tag, /scoreboard,
  /item or /loot commands. Preserve all 240 original trial-spawner configs.

## Evidence and limitations

`r37-java-unit.json`: 300 assertions on actual materialized Java method bodies
with minimal storage stubs. This is not a Minecraft engine/world simulation.
`r37-import-qa.json`: checksummed five-source import, untouched template bytes,
foreign-attribute removal, function graph and unchanged trial-spawner configs.
`r37-live-controller-qa.json`: actual region-thread runtime controller execution.
`field-r36-water-square-seed.json`: persisted chunk-boundary and screenshot camera
samples for seed -4651369264513492755. Camera coordinates are not a vanilla
reference aquifer oracle. Do not weaken a failed sample merely to pass CI.

The focused tests do not establish: every boss works, every witch hut jigsaw
assembles its mobs, natural trial-spawner activation with a survival player,
all mirrored/rotated decorations, or full save/restart and generation-order
invariance across arbitrary worlds. Those require additional field testing.

## Safe field test

Stop the test server and back up the entire existing instance first. Use a NEW,
separate test world and the exact matching server.jar + NeverOverworld.zip +
NeverNether.zip from one candidate. Do not combine the R37 pack with an old JAR.
Do not put the isolated QA plugin on a production server. Do not delete player
worlds or regenerate populated chunks to test this change.

Already-generated faulty walls, drained water, removed decorations and square
foundations are not repaired by changing generation code. There is deliberately
no destructive automatic world migration in this patch. Verify new chunks or
a fresh seed-matched world. Natural trial-spawner checks need a real eligible
player, not just a spectator camera. Main and the deployed server are unchanged.
