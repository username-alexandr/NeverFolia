# NeverOverworld TREE-R1 — keep submerged trees intact

## Requested rule

Fully underwater trees are not automatically deleted. Existing fallen-tree
features are allowed to survive the flood, including their horizontal logs and
leaves. Trees with only two or three wood/leaf blocks submerged keep the entire
tree. There is no new rule deleting a tree at four submerged blocks and no
per-block truncation at the ocean waterline.

## Implementation

The final production transformer `preserve-never-overworld-trees-r1.py` runs at
the end of `apply-neverfolia-post-patches.sh`, after all historic hash-checked
FIELD-R10/R11 and DESERT-R1 stages. It removes the historic positive LOGS/LEAVES
flood clauses and adds an explicit early exclusion before `canBeReplaced()` in
both `NeverOverworldFlood.isFloodable` and
`NeverOverworldFloodBoundaryR11.isFloodable`.

This protects logs and leaves in the surface-connected pass, the R8 cavern
fallback and the FIELD-R11 boundary pass. Exact block properties, including log
axis and existing leaf waterlogging, are not rewritten. The algorithm never
reads or writes a neighbouring chunk. It does not cancel the whole flood when
a tree is present: connected surrounding air and ordinary removable flora
remain floodable.

This is a flood-preservation change, not a new fallen-tree model/placement
algorithm or a change to configured tree frequencies. Previously erased blocks
cannot be restored by this patch. Existing FULL-chunk relight protection is
unchanged; validation belongs in a fresh disposable NeverOverworld test world.

## Tests and scope

The Python transformer regressions check both targets, idempotence, removal of
the historic pair, ordering ahead of generic replaceability, failure on source
drift/partial installations, and preflight without partial writes.

The native Java 25 ProtoChunk smoke exercises installed surface/R8/R11/remnant
methods with a fully submerged standing tree, a fallen birch log, waterlogged
leaves, exactly two/three submerged log/leaf blocks, and a tree across a negative
chunk boundary in both processing orders. Exact block states are compared after
each pass. Nearby flooding and flower/grass/snow cleanup are also asserted.
Block-tag bindings are test-fixture setup in the standalone smoke JVM; they do
not alter server tags or prove a natural tree-distribution acceptance.

Existing boundary, oasis, village-foundation and sandstorm smoke tasks remain
mandatory. Village square reclamation is NOT fixed or accepted by this change.
Neither Nether rules nor `staging`/`main` are promoted by this change. CI publishes
only logs/scope, not a replacement server archive before natural-world testing.
