# NeverNether SOURCE-R6: clean content startup and bounded D&T gameplay bridge

Status: **development candidate, not a production release**.
Base: `9c36fe889e36e2b04f84d9ea276e21ce2564b795`.
Native implementation commit: `f52ea73154155b88ec4aeebdd599eb05f336a918`.
No original source ZIPs, third-party NBT, generated Minecraft code or runtime binaries are committed here.

## Scope and root cause

Fifteen Dungeons and Taverns functions relied on commands disabled in the exact
Folia runtime: data, scoreboard, item, tag, function and loot. Re-enabling generic
commands globally is not this fix. `neverfolia:dnt` exposes 25 fixed, permission-gated
operations with no arbitrary selector, NBT path, loot identifier or function name.
An entity must be on its owning region thread before any mutation is attempted.

The source converter is pinned to the exact D&T ZIP and 17 affected resource hashes.
It preserves the 15 function resources, translates their unsupported actions,
converts one exact boss threshold, and preserves the quest loot branch structure.
Four projectile steps become one spawn/copy/retire operation: only the newly created
fireball is modified; the source is retired only after accepted spawning.
Regeneration remains one tick, amplifier 6, hidden particles (not one second).

The minion counter is persistent, per-entity tags capped at seven. It is not a
cross-region scoreboard. The source's inverted threshold condition is retained.
Five fixed trader loot operations use a hash-validated 45-resource closure with
count/component-only effects and known conditions. Arbitrary loot functions and
shared random sequences are rejected. Weights/distributions are preserved, but
invocation-local RNG is intentional; original random-stream equivalence is not claimed.
Trade changes are limited to three exact offer edits on an AbstractVillager.

Nearest-fireball owner removal is allowed only when the complete 45-block query
box belongs to the current region. Boundary cases are conservatively rejected,
not scanned cross-region or rescheduled using stale entities. Acceptance of this
edge behavior and other high-concurrency gameplay remains outstanding.

## Quest locations and pool references

`tavern_quest` now uses 13 authored tags with optional structure references.
All thirteen source branches, weights and conditions remain. The twelve Overworld
taverns are not imported, synthesized or replaced. Absent optional taverns mean
non-membership, preserving the existing fallback branch. Inventory generation is
tested; full player use of every generated chart is not yet accepted.

The physical `piglin_camp/fake_caves` alias pool already exists in the source ZIP.
The scanner retains a supplied physical alias and its resolved targets, because
runtime expansion-size inspection may read the pool before remapping. Missing
physical aliases are never replaced by empty pools. Native fixed function/loot
dependencies and structure membership tags are traced explicitly.

NBT dependency inspection now walks every palette and block/entity NBT, skipping
scalar coordinates and palette indices that cannot contain resource references.
It does not change original NBT or bypass malformed input checks elsewhere.

## Real verification versus unit tests

- Local Python regression suites: **160 tests pass** (the prior 138 plus 22 R6).
- Native R6 parser/permission/entity-less refusal smoke: **61 checks pass**.
- Actual Folia owning-region QA: **50 checks pass**, covering persisted counter
  tags, independent bosses, saddle/regen, offer cost/result/compass/max uses,
  the five actual loot tables, trade tags, three projectile powers and preserved
  owner/motion, fixed-function execution, and six generic commands still disabled.
- Full real five-archive pack builds with all 20 approved custom structures.
- The latest local startup gate is **PASS**: Done, normal save, exit 0, zero failed
  functions/data, zero missing loot references and zero unresolved pool warnings.
  A blocked Mojang authentication-key request is recorded separately as an
  offline-environment error, not suppressed as a content fix.

The first local gameplay probe used the verified R5 CI runtime plus locally
compiled R6 code and an exact single-callsite registration patch for QA. This is
not by itself a complete native source build. The native workflow compiles the
normal full NeverFolia transformer chain with the R6 source hook and runs both
native smoke classes. Consult the exact CI run and the accompanying verification
report for the final full-runtime rerun rather than inferring success from a
workflow file. The QA plugin source is under `qa/nevernether-r6`; never install
that plugin on a live server. The source archives are not present in synthetic CI.

## Remaining acceptance gates

Natural placement and complete traversal of every structure; chart use, boss and
jockey behavior across region boundaries; connecting the R4 gallery to its frame;
persisted fluid/cavity inspection and strict chunk-order determinism. No density,
sea level or base terrain rule is changed by R6. The earlier FIELD-R1 lava candidate
is preserved; the user's reported cavities have not been diagnosed on supplied
saved regions. Existing user worlds and fingerprint locks are not modified.

This is a source review, not a packaged production JAR. Use only isolated new test
worlds with matching runtime and datapack; do not bypass the fingerprint guard.
