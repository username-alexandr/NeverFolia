# R7 natural-start and persisted-world probes

Development tools only. Never install the QA plugin on a user/live world. It
requests normal generated chunks and thus can consume substantial CPU/memory.
Use a fresh isolated server directory, exact matching runtime/pack, loopback-only
network binding and a bounded external process timeout. Stop normally before
reading region files. A partial report or a killed process is not a passing run.

Compile `NeverNetherWorldgenQa.java` against the exact full NeverFolia runtime
classpath with Java 25, include the adjacent plugin.yml in its JAR, and place it
only in the disposable server's plugins directory. Source dependencies use the
existing five pinned input ZIPs plus verified monument supplemental loot.

Set `-Dneverfolia.qa.isolated=true`. The plugin's modes are:

- `-Dneverfolia.qa.mode=discover`: registered placement candidate chunks, at most
  `-Dneverfolia.qa.rings=10` rings per approved structure group. No /place,
  forced biome, structure-set replacement or runtime start injection is used.
- `-Dneverfolia.qa.mode=full -Dneverfolia.qa.plan=/absolute/plan.json`: request
  FULL chunks in exactly the supplied order. Plan schema:
  `{"seed":8675309,"chunks":[[-1,0],[0,0]]}`. Actual seed must match.

Report: `plugins/NN-WORLDGEN-R7-QA/result.json`. `completed` means the selected
requests finished, not complete gameplay/worldgen acceptance. Discovery records
actual start NBT; FULL coverage is independently checked after normal save/stop.
Waiting occurs on a private QA worker, never a Folia region tick thread. Reports
are streamed rather than constructing extra huge copies of the structure graph.

Read a stopped world's exact Nether region directory:

```sh
python3 scripts/audit-never-nether-worldgen-r7.py \
  --discovery /saved/discovery.json \
  --region-dir /stopped/world/dimensions/minecraft/the_nether/region \
  --plan /saved/plan.json --output /reports/geometry.json
```

Use `--allow-partial-footprints` only to observe deliberately smaller samples.
The report explicitly marks incomplete footprints and cannot label them fully
verified. Bbox policy overlaps remain failures, even without proof of colliding
solid walls. None of these checks asserts walkability.

For two new worlds generated from the same pack/seed with reversed request order:

```sh
python3 scripts/compare-never-nether-persisted-r7.py \
  --left /stopped/a/region --right /stopped/b/region \
  --plan /saved/plan.json --output /reports/exact-comparison.json
```

This compares actual decoded block states, biomes, saved starts, heightmaps and
block entities. Palette-storage order is ignored. Flowing lava, air, vegetation
and all other block states are **not** filtered or normalized. Dynamic entity
simulation and elapsed-tick equality are not established by a saved snapshot.
A failed sample must not be rebranded a successful strict determinism gate.

`NeverNetherFinalStateQa.java` uses the real runtime BlockStateParser on an exact
list of Jigsaw final_state values. Compile separately and run with arguments
`values.txt report.json`; an empty input or an invalid state cannot pass.

Run synthetic contracts separately:
`python3 scripts/test-never-nether-worldgen-r7.py`.
No third-party NBT, generated Minecraft sources or runtime/JDK binaries are
committed in this QA directory.
