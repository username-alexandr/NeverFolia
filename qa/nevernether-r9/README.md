# R9 support and canopy experiment

**Opt-in development candidate, not a production generator or server release.**
Never use an existing user world or remove its worldgen/fingerprint lock.
The unchanged data-pack fingerprint does not authorize native generator changes.

Start with the normal pinned Folia build and the normal NeverFolia transformer
chain. Then apply optional R8 and R9 in order to a fresh generated build tree:

```sh
python3 scripts/apply-never-nether-experiment-r8.py /fresh/Folia \
  --acknowledge-experimental-worldgen
python3 scripts/apply-never-nether-experiment-r9.py /fresh/Folia \
  --acknowledge-experimental-worldgen
```

Every input hash, occurrence count and helper-file conflict is checked before
writes. Reapplication is accepted only when the transformed source inverts to
the exact inspected original. The ordinary production entry point does not call
either experiment. There is no world edit, blanket filling or comparison filter.

R9 adds the actual `nova_structures:blackstone_base` support path to the scoped
R8 inspection policy. It also makes huge-fungus stem-corner and canopy choices
independent per proposed cell. The seed includes world seed, fungus origin,
cell position and purpose salt. No mutable world-wide random source is added.
Outside the isolated R9 planning-view marker, the original random object is
returned unchanged. Player-planted fungi are not handled by the R8 planner.

The support view remains plant-transparent, not an immutable terrain/provenance
snapshot. The random-stream change can change forest shape. Visual quality,
attachments, support geometry and overall performance remain acceptance tasks.
Do not infer those from matching a selected sample's canopy blocks.

## Reproduce controlled probes

Use the R8 `NeverNetherStageProbe.java`, adjacent plugin.yml and
`run-stage-probe.py`. Compile the plugin against the exact compatible runtime.
Use new loopback-only directories and explicitly acknowledge the Minecraft EULA.
Keep Java, complete runtime byte inventory, data pack, plugin and JVM flags
identical within each comparison. Freeze simulation before target generation.

The selected plans contain all 25 pairs from X=-216..-212 and Z=-46..-42, ordered
by ascending X then Z, with seeds 7270913 and 123456789. The review bundle includes
both full plans. Request forward, reverse and repeated forward sequences in
separate new worlds. Use `compare-never-nether-stages-r8.py` with the default
reverse relation or `--relation same` for the repeated forward control.

All states from Y=-128..895 are compared, including fluids, air, plants and roof
space. A nonzero comparison exits 2 and is not a pass. The first post-feature
snapshot is normally a SPAWN ProtoChunk after LIGHT; settled snapshots may be
FULL on their owning thread. Status changes during capture invalidate the run;
do not relax that check or count partial output as passing. Startup loading and
normal stop must also pass `validate-never-nether-startup-r5.py` independently.

The CI artifact is a class overlay for the exact compatible runtime, not a
standalone JAR. Final probes use the verified full R6 runtime plus unmodified
R8 and R9 CI overlays. Trace-only classes and rejected floor-snapshot experiments
are not on that final classpath.

## Tests and remaining diagnosis

`test-never-nether-candidate-r9.py` tests synthetic source-transform contracts.
`NeverNetherCandidateR9Smoke` tests the actual native random/guard behavior without
creating a world. Neither replaces the six controlled world probes described in
the accompanying verification report.

The selected first-seed remainder has 36 ore/material conflicts and 23 small-plant
state differences. At sampled ore coordinates, two decorators both require
netherrack, so the first writer makes the second ineligible. An origin-column
trace also shows an earlier glowstone cluster being counted as an extra floor,
shifting a small-plant proposal from Y=66 to Y=115. Full provenance-aware planning
remains necessary; do not make all natural blackstone replaceable or delete
plants merely to silence a comparator. See `docs/worldgen/never-nether-r9-determinism.md`.
