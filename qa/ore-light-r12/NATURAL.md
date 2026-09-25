# HEIGHT2 + ORE-LIGHT: separate fixed-candidate experiment

The height change is already in the normal FIELD-R12 installer: a standing
TreeFeature origin must be Y >= 126 for ocean Y128. Fallen-tree exception,
existing-tree preservation, 25% final ore retention and dry-mine logic remain.
This change does not modify those rules or any saved world.

## Verified input evidence

HEIGHT2 `58ff05b53ae74061eaf7bd9fd389c07dca640a13` native run `35647930056`
passed: FieldPolicyR12Test 4104; FieldR12Smoke 809851; preservation 21325;
Nether R15 87; all retained village/boundary/desert/sandstorm tests.

Its historical paired run `35647930055` still failed the existing strict gate.
The two copies of delivered 32c6df3 differed at 612 resource positions, all
Y >= -64, despite matching request protocol and stable post-save phases.
Counts: baseline 23016, repeated baseline 23099, candidate 11521. The candidate
retained 50.0565% / 49.8766%. Candidate absent/retyped coordinates were 172 / 97.
Both sampled mine pieces were dry after restart (543 and 250 air cells, 16 rails
in collapsed_mine); wholly submerged wood/leaf groups were 85 -> 0. These are
limited observations, not all-tree identities or multi-piece mine acceptance.
Artifact 10662060397 SHA256:
57fb2add5f6ca94540c1048524e0cd2f96f305ddbc354bf30f0de969594e21cf

## Why a new protocol

The former paired workflow DOES NOT install the ORE-LIGHT overlay. Re-running it
cannot test the timing fix; insisting its old binary become repeatable cannot
be satisfied by changing a new candidate. That workflow, gate and failed
reports are retained unchanged. No historical result is relabelled.

The new workflow explicitly installs defer-upper-pruning.py AFTER canonical
FIELD-R12 and Nether R15, verifies exact materialized output hashes, and builds
that precise candidate. All nine native tests remain mandatory, including
height boundary, late ore writes, exact final-mask subset, dry mines and Nether.

Three independent fresh worlds are generated: the exact pinned delivered JAR
once for historical density, then the FIXED candidate twice. Both candidate
invocations use the shared observer's candidate role, so persisted mine metadata
is mandatory in BOTH. All roles independently run initial/complete/restart,
identical locate requests, chunk selections, seed and both datapacks. Regions
are read only after normal stops. The candidate repeat must have zero differing
resource coordinates or types; no percentage tolerance applies to repeatability.
All resource coordinates must also remain stable through saved phases.

Historical density must remain in the original 40-60% band; at least 200 old
resource blocks are required. Historical exact-position comparisons and FULL
deltas remain in diagnostics, including their original true/false pass fields.
They are not confused with the new candidate-repeatability criterion. Native
mask tests still require exact 25%-mask inclusion in the 50%-mask for identical
inputs. Failure of the NEW candidate repeat, any saved-fluid mine check, phase,
protocol, tree observation or Nether roof check blocks publication.

## Bundle and limits

Only this independent gate can publish a clearly labelled manual test bundle.
It binds source SHA, workflow, explicit profile, post-overlay source hashes,
JAR hash and both datapack hashes. Both packs are under world/datapacks.
No level.dat/regions/locks from probes are included. production_ready=false;
village/mine visual review and wider world testing remain necessary. NeverEnd
is not included. No staging/main promotion or deployment is performed.

25 local unit tests cover verdicts, failure paths, binary/profile binding,
both-pack packaging and independent orchestration with simulated collaborators.
These do not execute Minecraft. The workflow executes the unchanged shared
world/NBT observer against the actual binary three times. Natural confirmation
of the combined HEIGHT2+ORE-LIGHT candidate remains pending until that run.
