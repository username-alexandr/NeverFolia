# NeverNether R8: frozen-stage diagnosis and optional decoration candidate

**Development experiment. Strict worldgen acceptance remains BLOCKED.**
Code: `d9539b4e3e363d796f344a91c53d9bfaff4409ff`.
Inspected R7: `a745f043edb7cf4760e188e68cb9de29c64bab67`.
API probe: `89ab2c9b2dc9be773e336bf4a741d87405577167`, run 34784664703.
Native baseline: the verified R6 full-chain runtime `f52ea73154155b88ec4aeebdd599eb05f336a918`.

## Controlled reproduction

R7's 976,582 different saved blocks over 1,599 chunk pairs were a failed measurement,
not a controlled diagnosis of one cause. R8 selects 25 forest/Sealing Halls chunks:
seed 7270913, X=-216..-212, Z=-46..-42. Each phase compares 6,553,600 exact block
states over Y=-128..895. This is not a repeat of the full R7 sample or multiple seeds.

Three NEW baseline worlds have identical runtime byte inventories, datapack, Java
executable, plugin and JVM flags. Simulation is frozen before target generation and
checked at every observation. Requests use forward order, its exact reverse and a
repeated forward order. The final CI candidate repeats the same three-run protocol.

| Observation | Baseline reverse | Final CI candidate reverse | Same-order controls |
| --- | ---: | ---: | ---: |
| Exact CARVERS ProtoChunks | 0 | 0 | 0 |
| First post-feature snapshot | 93,626 | 255 | 0 |
| Settled re-observation | 93,626 | 255 | 0 |
| First-to-settled changes inside each run | 0 | 0 | 0 |

Actual first post-feature status is SPAWN after a LIGHT request, still a ProtoChunk.
Settled snapshots are FULL on their owning thread. There are no explicit FULL
requests. Status changes during capture, unfrozen simulation, incomplete coverage,
wrong hashes or forced stops invalidate a probe. Early exploratory failures were
not counted as successful evidence. The selected divergence already exists during
generation, rather than being caused by subsequent gameplay growth or fluid ticks.
This does not explain every original R7 difference.

## Inspected causes and optional implementation

Per-layer placement observes mutable current columns. Earlier fungal stems and
canopies can become additional apparent floors; fungal placement also branches on
replaceability. Neighbor feature order can therefore change origins and random
consumption. A floor-search-only exploratory control reduced, but did not eliminate,
the difference.

The D&T resources `nova_structures:nether_bricks_base` and
`nova_structures:blackstone_bricks_base` inherit parent placement randomness as
feature pool elements. They execute through TransformerLevelAccessor, not directly
through WorldGenRegion. A trace found that an initial experimental guard missed
this wrapper; the scoped guard now unwraps at most eight known delegating accessors.
The vanilla rule processor already uses position-based randomness and is not broadly
replaced or blamed by this experiment.

The optional candidate uses per-origin support random streams, a plant-transparent
support inspection view, and isolated proposals for seven vanilla Nether flora
features. It retains the original feature geometry algorithms and configured counts.
Each proposal receives independent randomness, and intersecting plant proposals use
an explicit commutative winner. No forest is disabled or cut off at chunk borders.
All block states, including air variants, plants, roof space and flowing lava, remain
in the comparator. This intentionally changes random-stream and overlap semantics;
identical forest layout or visual density relative to the original is not asserted.

Final candidate residual: **255 blocks in 14 chunks**, comprising 158 differences
involving plant states and 97 other differences. This is approximately 99.73% fewer
than the baseline on this selected sample, not a rounded-down pass. Plant-state totals
are 72,475 / 71,945 in the baseline and 72,921 / 72,899 in the final candidate; the
candidate has 9,800 stem blocks in both orders. These are sampled block counts,
including template vegetation, not visual-quality acceptance.

The virtual view is NOT an immutable pre-feature terrain snapshot or a provenance
map. Authored structure vegetation can also look like a plant, and non-plant writes
remain visible. Remaining support/terrain/flora interactions, attachments, visual
quality, performance, other seeds and full persisted-world coverage still need work.
The normal production transformer chain does NOT install this candidate.

## Verified checks

- Local Python suites: **234 passed**, comprising the actual remote baseline's
  197 cases plus 37 new R8 contracts. Existing builder self-tests also passed.
- FIELD-R1 Regression #15 / **34786355225**: SUCCESS; 197 existing cases.
- R8 Candidate Compile #1 / **34786355300**: SUCCESS at d9539b4; 37 R8 cases,
  full production-chain compilation followed by the optional candidate, and
  **9,323 actual registry/algebra checks over 68 plant states**.
- Candidate artifact SHA-256:
  `b878361641de6d9f79696d7c14f6892353c76e379cb1e9e432f7778df0bd024e`.
  Outer hash, every inner checksum and every implementation-source hash verified.
- Final world probes use the unmodified R6 runtime plus the unmodified R8 CI class
  overlay. They are not a newly packaged server JAR. Both reverse-order residual
  and same-order equality reproduce the exploratory result. Every final server
  reaches readiness, saves and exits 0; startup content gates pass. Offline Mojang
  key-fetch errors remain separately recorded as environment errors.
- The diagnostic plugin was recompiled from its published source and its classes
  matched the measured plugin. Runtime classpath contents are hashed before and
  after each accepted run, not inferred merely from unchanged path names.

All five source ZIP hashes remain pinned and unchanged. The same full twenty-
structure datapack is used throughout. Normal native source, density/terrain data,
lava level, dimension bounds and production entry point remain unchanged. No new
acceptance is claimed for the R7 1,599-chunk gate, twenty-structure traversal, dormant
R4 gallery, or the user's original suspended-lava/cavity locations. FIELD-R1 remains.

No production release. Never install this review or QA plugin on an existing user
world, and never bypass the fingerprint guard. The unchanged datapack fingerprint
alone does not authorize a native experimental generator upgrade.
