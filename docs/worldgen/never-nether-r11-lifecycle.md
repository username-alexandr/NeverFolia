# NeverNether R11: persisted substrate and safe validation failure propagation

**Optional experiment. Strict broad generation acceptance remains BLOCKED.**
Remote baseline: `589efcde92d911c1e726cea8939890cd4259820f`.
Final native code: `c0860eeb4efa3607d329fac4c1bb9940982f2438`.
Native CI run **34815882118**: SUCCESS. FIELD-R1 #19 **34815881944**: SUCCESS.

## Reconciliation, not replacement of another implementation

The previous attached local R10 used a different provenance implementation from
the remote R10. R11 extends the remote section-owned state and retains its priority
policy and same-value external-write protection. It ports only the local natural
red/brown mushroom support fix. It does not overwrite the remote implementation
with a weak-map approximation or claim previous local measurements for this code.

The normal production entry point still enables none of R8/R9/R10/R11. Every
experiment requires explicit opt-in on a fresh generated build. Existing
unversioned decorated worlds are not migrated, and fingerprints are not bypassed.

## Storage implementation

Each section stores the immutable post-CARVERS/pre-decoration substrate, external
write bitmap and surviving own proposals in `neverfolia:substrate_r11`. The record
contains a schema, exact generator-policy profile, seed, chunk coordinates,
section Y, canonical block-state palette, compact indices and checksums binding
the metadata to the saved current blocks. It uses existing chunk NBT, not sidecars.

`LevelChunkSection.copy()` previously dropped added generator state. R11 copies
that state together with the actual section under the same section-data lock used
by tracked setters. Copy mutations do not share the source bitmap or proposal map.
Load validation rejects unknown profiles, wrong coordinates/seed/dimension,
missing section coverage, malformed palettes/arrays, stale current blocks and
unrecorded mutations. State is published only after successful validation.

This covers the inspected section setter and normal serializer path. It is not a
claim that arbitrary plugins or direct paletted-container mutations are all
tracked. Same-value writes through paths bypassing the inspected setter remain
outside the proven write coverage. Memory, serialization cost and long-running
retention of snapshots in FULL chunks still need production profiling.

## Critical loader correction

The inspected Moonrise loader catches a parse exception and normally returns a
successful empty result, which can create a replacement empty chunk. Merely
throwing from a metadata validator was therefore not sufficient.

R11 introduces a specific `InvalidSubstrate` error and forwards only this typed
error (including bounded cause chains) through the task result. It does not change
handling of unrelated I/O failures or claim a general corrupt-region recovery policy.

A negative test changed one profile in a NEW regular copy of an accepted disposable
world. The actual final CI runtime refused loading, propagated the chunk task error
and stopped rather than loading an empty replacement. The target's decompressed
corrupted NBT remained exactly unchanged after the process stopped; the original
source copy also remained unchanged. This is an expected fatal refusal, NOT a
clean-startup pass. The process exit code alone is not the acceptance criterion.

## Real final-CI lifecycle evidence

Final probes use unmodified full R6 runtime plus unmodified R8, R9, remote R10 and
c0860ee R11 CI overlays. These are not a newly packaged production server JAR.
All classpath file bytes and inputs are hashed before and after every accepted run.

For seed 7270913 and the original 25-chunk plan:

1. One new world generates continuously through CARVERS, post-features and settled.
2. A second new world stops after CARVERS. The process saves normally and exits.
3. A new JVM loads those saved chunks and completes generation. All three block
   stages match the continuous run; all **75 block + metadata observations** match
   byte for byte, covering **4,800 section records across observations**.
4. Another new JVM reads the completed FULL chunks again. All **25 settled block
   and metadata snapshots** match their pre-restart copies (1,600 section records).

Native tests additionally cover a same-value external write surviving NBT storage,
palette widths through 4,096 states, a real compressed NBT file roundtrip, malformed
records, detached copies and concurrent setter/copy consistency. The 86,085 native
assertions include repeated checks that every cell remained unchanged on rejection;
they are not 86,085 independent gameplay scenarios. Four further checks exercise
the typed-error classifier. These synthetic tests are separate from actual JVM
restart and negative-loader tests above.

### Diagnostic observation protocol

One earlier CI-runtime probe was invalidated by status promotion during slow
serialization (`ci-continuous`). It is retained as invalid, not a successful run.
The final observer captures detached section copies and checks chunk status around
that capture. Compression, hashing and NBT writing then read only those copies.
It never relaxes the initial CARVERS/ProtoChunk or owning-FULL checks and still
rejects status changes during capture. This is per-section coherent capture, not
a claim of an atomic snapshot of the entire world. Simulation stays frozen.

## Broad-order gate remains blocked

Nine accepted final R11 processes cover the lifecycle test plus forward/reverse
runs of both 25-chunk seeds and the 81-chunk plan. All nine reach readiness, save
normally and exit zero, with clean content startup gates. The offline Mojang
public-key request remains separately recorded as an environment error.

| Selection | CARVERS | Post-feature / settled block differences |
| --- | ---: | ---: |
| 25 chunks, seed 7270913 | 0 | 0 / 0 |
| 25 chunks, seed 123456789 | 0 | 0 / 0 |
| 81 chunks, seed 7270913 | 0 | **52 / 52** |

The 52 differences comprise 44 gravel/material conflicts and eight remaining
lightstone, small-plant and source-lava interactions. This is worse than the old
local R10 report's eight and must not be concealed. Two additional controlled runs
of the actual REMOTE R10 reproduce exactly the same 52 differences. All selected
block snapshots, in each order separately, match between remote R10 and final R11.
That cross-version observation uses different probe implementations and is not
labelled a same-runtime order gate. It shows no observed new wide-sample block
regression from R11; it does not resolve the inherited conflicts.

Every block name/property from Y=-128..895 remains included. No air, liquid, plant
or problematic material normalization is used. The old R7 1,599-chunk sample has
not been repeated here. Full metadata order independence is also not established
by identical blocks; metadata lifecycle equality is tested at identical order.

## Checks and remaining work

- **303 local Python tests pass** (12 regression suites).
- CI reruns 197 existing field tests and 22 new R11 source-contract tests.
- Full normal production-chain plus optional R8/R9/remote-R10/R11 compiles in CI.
- Native storage smoke: 86,085 assertions; error classifier: four checks.
- Candidate artifact SHA-256:
  `dd6d72dbd5c51dd1aac530377816bffacddb8f6afb5dcc1243fe4e486872a4b3`.
  Outer/internal checksums and implementation-source hashes verified.
- No Core terrain resource or original source ZIP is changed by this stage.

Remaining: gravel/lightstone/spring conflict rules that preserve provenance,
large/multi-seed persisted-world equality, crash/interrupted-save recovery,
standalone unload/reload stress, performance/ore-balance/visual acceptance,
complete dungeon traversal, Donjon gallery hookup and the original user's
suspended-lava/cavity locations. Normal stop/new-JVM lifecycle success does not
prove all these cases. Do not install on an existing user world or bypass its lock.
