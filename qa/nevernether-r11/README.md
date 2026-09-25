# R11 isolated lifecycle QA

**Never run these tools or the QA plugin on an existing user/server world.**
The only supported restart input is a newly created, explicitly marked, loopback-
only disposable R11 test world with identical runtime, Java, plugin and datapack.
The generator does not migrate unversioned chunks or remove fingerprint locks.

Prepare exact generated Folia sources with the normal NeverFolia chain, then apply
optional R8, R9, REMOTE R10 and R11 in that order with
`--acknowledge-experimental-worldgen`. The previous attached LOCAL R10 patch is
not the base for R11. Use the checked remote base identified in the verification.

Compile `NeverNetherLifecycleProbeR11.java` using Java 25 against that complete
runtime, include the adjacent plugin.yml and package a temporary diagnostic JAR.
Use the R8 `run-stage-probe.py` launcher for NEW directories, with explicit EULA
acknowledgement. Plans use seed and chunk pairs as in the R8/R10 examples; the
review includes exact primary, secondary and 81-chunk plans.

For the checkpoint, add `"stop_after_carvers": true` to the plan. The launcher
waits for the report, sends normal stop and records input and runtime identities.
Then launch a NEW process against that disposable checkpoint:

```sh
python3 qa/nevernether-r11/resume-stage-probe.py \
  --resume-directory /disposable/checkpoint --runtime-dir /exact/runtime \
  --java /java25/bin/java --acknowledge-disposable-checkpoint
```

Old observations, startup log and runtime identities are retained under
`checkpoint-evidence`. Compare this completed run with a continuous control using
`compare-never-nether-stages-r8.py --relation same`. Additionally compare exact
block and metadata observation bytes:

```sh
python3 scripts/compare-never-nether-metadata-r11.py \
  --left-observations /disposable/control/plugins/NN-STAGE-R8-QA \
  --right-observations /disposable/checkpoint/plugins/NN-STAGE-R8-QA \
  --output /reports/restart-metadata.json
```

Repeat the resume command with `--mode full-readback` to read saved completed FULL
chunks in another new process. It preserves the previous run under
`before-full-readback`; compare its `observations` directory with the new report
using the metadata comparator's `--phase settled`. This verifier checks snapshots,
not runtime provenance; use it together with launcher identities, the block stage
comparator and the startup gate. Readback cannot be silently used as initial
CARVERS generation evidence.

`test-corrupt-checkpoint.py` is a destructive NEGATIVE TEST only inside a NEW copy
of an already stopped marked disposable world. It changes one section profile in
one copied Anvil chunk, preserves the source and requires a typed loader refusal
with the copied corrupted chunk payload unchanged. The expected result is a fatal
load refusal, not a clean start. Do not point it at a live world or interpret it as
a repair utility. It does not test arbitrary physical MCA corruption.

Final observation protocol: capture coherent detached section copies, verify
status did not change around capture, then serialize the copies. All initial
ProtoChunk, exact CARVERS, owning-FULL and frozen-simulation checks remain. It is
not an atomic all-world snapshot. No state categories are filtered from comparison.

Native `NeverNetherStorageR11Smoke` uses synthetic sections and real NBT I/O;
`NeverNetherGuardR11Smoke` classifies typed errors. They do not replace actual
restart, negative-loader or broad order probes. See the R11 lifecycle document
for measured results, invalid attempts and remaining acceptance limitations.
