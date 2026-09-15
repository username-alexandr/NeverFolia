# Exact roof512 QA, independent from R13 results

Development tools only. Never install the probe plugin on a production world.
Use the matching native R14 runtime and the R14 converted full data pack in a NEW,
loopback-only test directory. Source ZIPs and previous worlds are not modified.
Read and accept the Minecraft EULA explicitly before starting a disposable server.

The native roof block is exactly Y=512. Technical storage has 41 sections at
Y=-128..527; Y=513..527 must remain empty and unbuildable. Metadata profile is
`NN-R14-SUBSTRATE-1-ROOF512`. Old fingerprints/storage profiles are not migrated.
A matching data-pack fingerprint alone does not authorize any native upgrade.

## Observation and comparison

Compile `NeverNetherRoofProbeR14.java` with Java 25 against the exact native R14
classpath, include this directory's `plugin.yml`, and package only the observer
classes and descriptor. Use `run-roof-probe.py` with the existing supervisor
arguments: Java, runtime directory, pack, QA plugin, plan, NEW directory, EULA
acknowledgement, timeout and optional reverse order. `--check-only` is read-only.
Plans explicitly contain the seed and unique integer chunk-coordinate pairs.

The R14 runner reserves off-heap/OS headroom using `-Xmx2304M`, not the old probe's
3200 MiB heap. Exact flags, runtime contents and inputs are recorded before and
after every run and compared across orders. This is a diagnostic environment
choice, not a production RAM recommendation or a generator change. An OOM-killed
or incomplete run is never used as a passing checkpoint or comparison input.

This FULL-only probe does not claim valid pre-FULL CARVERS/LIGHT snapshots. It
requires frozen simulation and owning-region execution, copies all 41 sections,
and captures every state in the storage envelope. The comparer verifies actual
bedrock at Y512 and air above it in the captured arrays, not just summary counts.
Every requested chunk is observed twice unless the explicit readback mode is used.
Neither air, fluids, plants nor metadata differences are filtered to obtain PASS.

`test_mutations: true` is only for a separate throwaway boundary-test world. It
tries Level, Chunk, Section and Bukkit writes at the roof/padding, verifies the
inside/outside-height complement and checks placing/restoring a block below the
roof. Such worlds are explicitly rejected by the order-equality comparator.
Client packet paths, movement, portals and complete fluid simulation are separate
acceptance tasks; these API tests do not pretend a Minecraft client was connected.

After both servers stop normally:

```sh
python3 qa/nevernether-r14/compare-roof-r14.py \
  --left /disposable/forward --right /disposable/reverse --output /reports/order.json
python3 qa/nevernether-r14/audit-saved-roof-r14.py \
  --world /disposable/forward --plan /plans/selected.json --output /reports/saved.json
```

The saved-region audit validates all selected FULL sections' identities,
canonical metadata checksums, actual current-block hashes, external-write/own-
proposal invariants, and roof/padding cells. Do not run heavy offline Anvil
analysis while a large server probe is alive in a memory-constrained environment.
A standalone audit does not establish cross-order equality, natural starts or
playability; use the corresponding separate report.

## True JVM restart

`restart-roof-probe.py` accepts only a completed, normally stopped R14 diagnostic
world with matching snapshots, runtime, Java, pack, plugin and height lock. It
first checks every selected target exists at saved FULL status. It never invents
a checkpoint from partial output, downgrades a guard, or changes a worldgen lock.
Use `--check-only` to validate before moving evidence. Actual restart requires
`--acknowledge-disposable-checkpoint`.

Original observations, log and runtime evidence are archived under
`before-r14-readback`, preserving their normal folder layout. The new Java process
reads the same FULL targets. Compare that archive to the restarted world using
`compare-roof-r14.py --relation same`; only their common settled phase is compared.
The native loader must validate the R14 section profile. Existing user worlds are
not supported by this routine. A second implicit resume is rejected.

## Test scope

The Python suites exercise synthetic malformed/valid observation and storage
fixtures, original Core data conversion and exact native source-hook contracts.
They are not claims of successful generated worlds. Real startup, process exit,
readback and block/metadata comparison reports must be reported separately.
No `release_ready` flag is made true by these tools.
