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
| `donjon/coloseum_part/deco_14` | blackstone light pedestal | 4 x 4 x 4 |
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

## Verified checks and their exact scope

- Local Python suites: **97 tests passed** (23 FIELD-R1, 29 source-input,
  26 remote SOURCE-R3, 19 recovery-R4). FIELD-R1 Regression #5 / 34771424409
  reran these at 5ad127f99553d1494e94e9017ad0ac39610b74b2 and succeeded.
- Pure Java quota tests: **359 assertions passed**, including cap boundaries,
  failed geometry probes, group collisions, nested quotas and concurrent
  independent starts. These assertions do not create a Minecraft world.
- Native isolated compile/codec CI #1 / 34771052539 succeeded at
  3b63dbf238cb7f4fde0b9f0dbc8d35b7a3774c52.
- Native full production-chain compile/codec CI #2 / **34771486487 succeeded**
  at **3e66a80e7e2daa1ac70e4f744daf3c0cd5980359**. The normal NeverFolia post-patch
  script, including the R9 village chain, ran before Java 25 compilation.
  Actual Minecraft bootstrap, registrations, codec round-trip and void behavior
  passed **12 checks**. No world was generated and no server JAR was packaged.
- The downloaded full-chain artifact SHA-256 is
  `85d835316f60370228248a0f72e3f3ed48b4924e6bf9b7c73795d3b75ae4fc20`.
  Its inner checksums and recorded native source hashes were verified locally.
- Validate NeverOverworld #522 / 34771486478 succeeded at the same 3e66a80 SHA.
  This is the fast check, not a fresh Overworld runtime determinism gate.
- The real five-source full importer now stops at **Better Monuments**, not D&T.
  Previously existing output bytes and all five input ZIP hashes stayed unchanged.
  Third-party ZIPs are absent from CI; this is local real-source evidence.

The adapter patcher was also applied twice to the exact inspected 26.2 sources:
reapplication is idempotent; changed anchors are rejected before writing files.
Documentation-only commits after 3e66a80 do not imply another native CI run.

No density function, lava level or fluid simulation is changed by SOURCE-R4.
All **24** resources in the rebuilt Core match the prior FIELD-R1 CI resource
bytes. FIELD-R1's lava-shelf candidate is retained, not newly runtime-validated.
Reported cavities still need saved affected Nether chunks to establish their origin.

Do not install this source-review bundle as a datapack, replace a live server JAR,
or bypass the existing worldgen fingerprint lock. Remaining release gates:
complete monument adapters and 20-structure import, candidate JAR packaging,
startup with the full actual datapack, world-space structure QA, persisted
fluid/cavity inspection and strict chunk-order determinism on fresh test worlds.
