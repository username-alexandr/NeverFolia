# NeverNether SOURCE-R4: missing template designs and first native adapters

Status: **candidate development, NOT a server release**. Source baseline is the
actual remote SOURCE-R3 commit d44d869463c102ce5d4cec40a93056f0c5257bca, exported
with verified tree/checksums by snapshot ea5e4656620a9c9db72c8f515ab1ef65c076840e.
No third-party ZIP, template NBT or decompiled Minecraft sources are committed.

## Actual uploaded source result

All 20 approved structure definitions are present. The local dependency audit now
passes **19/20**, including **12/12 Dungeons and Taverns**. The Nether Monument is
still blocked. These are source-dependency counts, not successful generated starts.
The metadata-only audit is `never-nether-source-intake-r4.json`.

Four absent D&T templates are now generated from independently authored geometry:

| Missing path under `nova_structures` | New design | Size |
| --- | --- | --- |
| `donjon/coloseum_part/deco_14` | basalt/blackstone light pedestal | 4 x 4 x 4 |
| `donjon/coloseum_part/deco_15` | gilded/basalt light feature | 4 x 4 x 4 |
| `donjon/room/donjon_room_3x3x3_1` | three-level gallery with ladders and loot/mob connections | 46 x 21 x 46 |
| `piglin_outstation/main/piglin_outpost_outer_layer_foundation_1` | solid buttress/platform with continuation anchors | 22 x 42 x 48 |

These are **replacement designs, not the missing author's original templates**.
No existing source NBT is modified or relabelled as an original. The source ZIP,
six input contract files and all four absent destinations are verified before
staging any generated resource. Repeated generation has deterministic gzip bytes.
Unknown hashes or an already supplied destination stop the reconstruction.

Decorative anchor positions/orientations match observed sibling contracts. The
foundation uses the observed outer-layer attachment envelope and the two land-layer
continuation targets, without copying its vault/loot. The room envelope follows
adjacent modular rooms. Geometry, connectors and block bounds are unit-tested,
but actual world-space placement, walkability and overlap still require runtime QA.

**Important dormant-room finding:** supplied Donjon frames contain no consumer
of `nova_structures:donjon_room_3x3x3`. This room resolves a referenced pool resource;
it does not become naturally reachable merely because its NBT exists. No frame
was enlarged or replaced. Frame hookup is a separate deliberate design task.

## Native API was inspected, not guessed from older mod code

The exact generated Folia 26.2 API from upstream commit
`14b7fee5c866fca9a40ede4a58998fb928140f65` was exported by Native API Probe run
34770168727. Unlike the inspected 26.1 mod sources, 26.2 StructureProcessor is an
interface and returns its MapCodec directly. The adapter uses that actual API.
The original mod classes are research references, not vendored implementations.

R4 adds two native types under the `neverfolia` namespace:

- `limited_single_pool_element`: single template with `name` and `max_count`.
  Quota is shared by group name across variants, per assembled structure. Only
  accepted pieces count. Failed geometry probes do not consume quota; root,
  fallback and nested-list candidates are checked. No global/thread-local mutable
  counter is used. For inconsistent group limits the stricter limit wins.
- `structure_void`: suppresses processor-produced structure void while returning
  non-void block information unchanged. It does not edit the world directly.

The Jigsaw hook is validated against exact source anchors before any file is
written; reapplication is idempotent. Normal vanilla candidates with no quota
remain allowed and the hook consumes no RNG. The normal post-patch entry point
installs these native adapters after the preserved R9 village chain.

**This does not yet translate the monument source codecs.** The importer still
rejects its YUNG/Repurposed Structures resources until the whole port is completed.
Remaining work: noise/property replacement, random/property replacement,
chunk-owned pillar support, the missing monument loot table, and integration of
all adapters with explicit source rewrites. No unsupported behavior is dropped.

## Validation scope

- `test-never-nether-recovery-r4.py`: 19 synthetic reconstruction regressions.
- `NeverNetherPieceBudgetTest`: 359 assertions using immutable inputs, including
  failed attempts, group collisions, nested quotas, cap boundaries and concurrent
  independent starts. This test runs with a real Java compiler, without Minecraft.
- `apply-never-nether-native-adapters-r4.py --self-test`: anchor/idempotence/failure
  atomicity checks, plus local application to the downloaded exact 26.2 sources.
- `NeverNether R4 Native Compile and Codec` CI: intended to compile the native
  additions against the inspected upstream Folia SHA and run real registry and
  codec bootstrap smoke checks. Consult the actual run result; a workflow file
  is not proof of a passing build. No world is created by this job, and it does not
  run the full existing NeverFolia production transformer chain.
- The normal fast regression CI retains R1/R2/R3 tests and adds R4 recovery tests.
  Third-party source ZIPs are absent from CI; real-source audit is local evidence.

No density function, lava level or fluid simulation is changed by SOURCE-R4.
FIELD-R1's lava-shelf candidate is retained, not newly runtime-validated. Reported
cavities still need saved affected Nether chunks to establish their origin.

Do not install this source-review bundle as a datapack, replace a live server JAR,
or bypass the existing worldgen fingerprint lock. Required release gates remain:
full native production-chain build, complete 20-structure import, registry startup,
world-space structure QA, persisted fluid/cavity inspection and strict chunk-order
determinism on freshly generated test worlds.
