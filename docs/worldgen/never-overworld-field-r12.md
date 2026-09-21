# NeverOverworld FIELD-R12 — candidate, not a release

Base gameplay: `32c6df3029fca001fd3602012e446a901f80eb2f`.
Exact materialized upstream: `14b7fee5c866fca9a40ede4a58998fb928140f65`.

## Requested changes

- Reduce the FINAL remaining Overworld resource population by another roughly
  50% compared with the delivered build.
- Keep generated mine corridors dry across owner-chunk boundaries and pre-FULL
  save/reload, without drying whole caves or restoring square village reclamation.
- Stop unsuitable NEW standing trees from appearing underwater; do not cut
  already placed trees or their submerged blocks. Real fallen trees are allowed
  underwater. Standing trees with at most three submerged wood/leaf blocks and
  the rest above water are allowed intact.

The prior TREE-R1 only protected existing logs/leaves from flood replacement;
its preservation test was not a test of standing-tree spawn admission.

## Implementation

The final installer validates SHA-256 of eight materialized input sources before
writing any of them. It runs AFTER TREE-R1/VILLAGE-NOFILL-R1 and before optional
Nether revisions. It does not alter world data, locks or datapacks.

TreeFeature stages roots, trunks and foliage in a bounded read-after-write
WorldGenLevel view. It decides before decorators/leaf-distance updates and before
publishing any staged blocks. Vetoed proposals therefore leave no stump, root or
soil changes. Valid proposals replay vanilla flags and write-zone checks.
Admission uses original per-column OCEAN_FLOOR_WG / actual water, not Y alone:
dry cave trees under high terrain are not rejected just for their altitude.
The true FallenTreeFeature, not horizontal branches in standing trees, receives
an underwater-position exception. Existing tree frequencies are not changed.
This is a conservative forecast of flooding, not proof for every cave topology.

MineshaftStructure and neverfolia:collapsed_mine record each intersecting PIECE
and its one-block envelope in each owner chunk during FEATURES. The geometry is
stored as versioned chunk PDC, which the existing chunk serializer persists.
The LIGHT pass drains interior fluid/waterlogging, seals empty/fluid cells of the
one-block surrounding rock envelope, and excludes the interior from both surface
and R11 boundary flooding. The union of interiors preserves corridor junctions.
One-block extended structure references provide shell-only chunk coverage; no
neighbour terrain is accessed at LIGHT. The whole structure bounding rectangle
is not filled. Other caves remain floodable. FULL/player-time chunks are not
repaired or repeatedly drained. Shell aesthetics require field review.

Final resource retention changes from 50 to 25 using the SAME salt and hash:
new resources are a nested subset of the old mask. This removes another roughly
half of the former survivors without rerolling positions. Eight existing
Overworld kinds (including existing raw iron/copper handling) retain their
scope. Nether ores, chest loot and player changes are not modified.

## Validation boundaries

Local: exact source transformation and idempotence, previous TREE-R1/no-fill
preflights, plus an exhaustive pure policy matrix on Java 21.
CI: Java 25 compiles the complete candidate and runs real tree feature primitives,
map-backed proposal scenarios, native cross-chunk mine/flood/PDC regressions,
ore-mask/write regressions, retained TREE-R1/village/boundary/desert/sandstorm
smokes and Nether R15 smoke. These are native tests, NOT natural-world acceptance.

A new full bundle must still be gated by fresh saved-world mine-fluid checks,
standing-tree evidence and paired ore sampling. The prior 32c6df3 artifacts do
not contain FIELD-R12. No promotion to staging/main or production is authorized
by a successful source/compilation test. Any future bundle must include matching
NeverOverworld AND NeverNether datapacks and report its actual validation scope.
