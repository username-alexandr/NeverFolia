# NeverNether R9: support/canopy stabilization and residual localization

**Optional development experiment. Strict generation acceptance remains BLOCKED.**
Baseline: `6d1ddf46b2172ffd74a77e515d8bf7ac38196b01` (R8).
Candidate code: `9d132aa4a3b2abc432e4d21220b51da92bddb76f`.
Candidate CI: **34791271615**, SUCCESS. Existing regression CI: **34791271426**, SUCCESS.
Pinned ore API inspection: **34790551047**; no ore algorithm is changed by R9.

## Measured progress, not a replacement for full-world acceptance

The original seed 7270913 sample was reproduced before changing the candidate:
25 chunks, X=-216..-212, Z=-46..-42, every block state from Y=-128 to 895.
The same complete twenty-structure data pack is used for every run in this intake.
Simulation is frozen before target generation and checked at every observation.

| Candidate within this intake | CARVERS differences | Post-feature differences | Settled differences |
| --- | ---: | ---: | ---: |
| Reproduced R8 | 0 | 255 | 255 |
| R9 blackstone-support extension alone | 0 | 176 | 176 |
| R9 support plus per-cell fungus random | 0 | 59 | 59 |
| Final unmodified R9 CI classes | 0 | 59 | 59 |

The final first-seed remainder is **59 blocks in 10 chunks**: 36 ore/material
conflicts and 23 small-plant differences. Relative to the reproduced R8 candidate,
196 of 255 differences are removed (76.86%). This is not a zero-difference pass.
The final repeated-forward control has zero differences in all three phases.
No first-to-settled changes were found within these accepted runs.

An additional seed **123456789** on the same 25 coordinate pairs has **5 differences
in 3 chunks** after decoration: four basalt/quartz and one red-mushroom/air pair.
Its CARVERS snapshots and repeated-forward control match exactly. Its first and
settled snapshots agree within each run. This additional seed also FAILS strict
order equality; it is not averaged into a passing result.

All six final CI-runtime probes reach readiness, stop normally, save and exit 0.
Their content startup gates pass. Only the separately recorded offline Mojang
public-key request fails in the isolated environment. The final sample is not the
old R7 union of 1,599 chunks, and no broad multi-biome or visual acceptance is implied.

## Narrow optional changes

The extra support path is **nova_structures:blackstone_base**, not one of the two
previously handled brick-base resources. Actual tracing found that in forward
order its column reached lower terrain; in reverse order a previously generated
fungal canopy stopped it early. The R9 extension applies the same scoped
plant-transparent read policy and per-origin random seeding to this exact ID.

Huge-fungus stem-corner and canopy decisions now use a random stream keyed by
world seed, fungus origin, individual proposed cell and purpose salt. A blocked
cell can no longer shift the random choices of subsequent canopy cells. This
applies only through the explicit isolated planning-view marker; ordinary calls
receive the original RandomSource object without additional draws. Player-planted
fungi remain outside the R8 planner. Feature counts and geometry loops are not
removed, but the random layout/overlap semantics intentionally change.

In the first-seed final candidate, huge-fungus-associated states no longer differ
between orders. There are 9,800 stem blocks, 49,196 wart blocks, 1,834 shroomlights,
1,636 weeping-vine tips and 3,562 weeping-vine plant blocks in each order. These are
sampled block counts, not proof of forest aesthetics, connectivity or performance.

The ordinary production entry point still installs neither R8 nor R9. No base
terrain resource, dimension height, sea level, standard native production source,
source ZIP or structure definition is changed by this candidate.

## Residual causes observed, not hidden by normalization

At **(-3410,31,-684)**, the exact ore trace shows quartz accepting netherrack first
in forward order, then magma rejecting the already replaced block. In reverse
order magma is accepted and quartz is rejected. The same first-writer exclusion
is seen for magma/blackstone at **(-3425,27,-671)**. These sampled traces show
actual OreFeature eligibility checks and direct section writes. The 36 residual
ore/material differences remain in the comparator; R9 does not make arbitrary
natural blackstone replaceable or clip veins to get a green result.

For crimson forest vegetation, the candidate-origin list differs at column
**X=-3391, Z=-722**: the selected Y is 66 forward and 115 reverse. Ground-search
tracing confirms the cause in that column. An earlier glowstone block creates
an additional apparent floor at Y=168 in the reverse order, moving the requested
ordinal floor. All traced origins except this one match. The 23 small-plant
state differences are retained; no unsupported-plant cleanup is substituted for
a stable pre-decoration/provenance-aware placement rule.

A broader exploratory before-own-decoration floor snapshot added no benefit:
it still produced 59 differences. It is REJECTED and absent from the final
candidate. Two preliminary probes were invalidated by a chunk-status transition
during observation; they were not counted as successful evidence. The final six
accepted probes all pass the unchanged observer checks on their first attempts
in the recorded final series. Trace-only classes are not on the final classpath.

## Verification and reproducibility

- **255 local Python regressions** pass: previous 234 plus 21 R9 contracts.
- CI reruns **197 existing cases** and **21 new source-transform cases**.
  The 37 unchanged R8 stage-comparison cases also pass locally; they are not
  misrepresented as newly rerun by the R9 compile job.
- **6,151 native guard/random checks** pass in CI and locally using its class export.
- Full normal NeverFolia production-chain compilation followed by opt-in R8/R9
  succeeds. This is not a production server-JAR release.
- Candidate artifact SHA-256:
  `35313403f2f06863ebefcdee2e79923c97cd05ae00bf999f6253d1333f5a7bab`.
  Outer archive, internal checksums and implementation-source hashes are verified.
- Final runtime: unmodified verified full R6 export `f52ea731...`, unmodified R8
  CI overlay `d9539b4...`, then unmodified R9 CI overlay `9d132aa...`.
  Complete classpath payloads are hashed before and after each probe.
- All **24 Core resource payloads** match the prior R8 CI Core. All five original
  source archive hashes still match the pinned manifest.

See `qa/nevernether-r9/README.md` for exact installation order and controlled probe
procedure. The review contains source, reports, trace excerpts and logs; a separate
snapshot bundle preserves the six accepted runs' observation inputs for rechecking
without a server. Neither contains a production server or user-world migration.

Remaining gates: provenance-aware ore/decoration planning, full persisted-world
and multi-seed equality, geometry/attachments/playability, Donjon gallery hookup,
and the user's original suspended-lava/cavity locations. FIELD-R1 remains unchanged.
Do not install an experiment on an existing user world or bypass its fingerprint lock.
