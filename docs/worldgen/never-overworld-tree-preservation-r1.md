# NeverOverworld TREE-R1 and VILLAGE-NOFILL-R1

## Tree rule

Fully underwater trees are not automatically deleted. Fallen trees and trees
with only two or three submerged log/leaf blocks must remain intact. There is
no rule deleting a tree at four submerged blocks. This patch is flood
preservation, not a new tree placement algorithm or a change in tree frequency.

## Corrected source-chain diagnosis

Run 35506215292 failed BEFORE Java compilation because the first TREE-R1
installer expected the intermediate R8 positive LOGS/LEAVES clauses. The final
`harden-never-overworld-flood-r9.py` had already removed BOTH clauses and disabled
the R8 cavern fallback call. Therefore the earlier claim that the final R15
bundle still unconditionally removed logs/leaves was not established by reading
R8 alone. The complete final chain, rather than an intermediate helper, is the
source of truth.

The corrected TREE-R1 installer accepts only the inspected complete final
R9/R11 predicates, checks R9 markers and keeps the R8 fallback disabled. It adds
an explicit LOGS/LEAVES exclusion BEFORE generic canBeReplaced evaluation. All
other flood clauses, including traversal of existing water, remain unchanged.

13 Python source-transformer tests cover the real final predicate shape,
source drift, obsolete R8 clauses, ordering, idempotence and read-only preflight.
The existing Java 25 ProtoChunk smoke checks submerged/fallen/partially flooded
trees, waterlogged leaves, negative chunk boundaries and nearby ordinary flora.
Its direct invocation of the retained R8 helper is a defensive isolated test;
it does NOT mean the R8 fallback is enabled in runtime generation.

## Village square reclamation

The final production override
`remove-never-overworld-village-reclamation-r1.py` removes exactly the custom
`NeverOverworldVillageReclamation.apply(level, this, chunkPos)` call immediately
after vanilla `structure.afterPlace`. That custom pass could infer foundations
from unrelated solid blocks inside piece bounding boxes and raise selected
columns to the fixed Y=128 sea plane.

Vanilla piece placement, Jigsaw/template placement, vanilla afterPlace,
structure definitions and the existing village-location policy are retained.
No alternative bbox fill or new foundation heuristic is introduced. This means
natural water between buildings is permitted; it is not a promise that every
village footprint will be dry or every shoreline building well-supported.

12 source-transformer tests ensure only that exact custom call is removed,
vanilla placement is preserved, source drift/duplicates are rejected and
preflight does not modify files. The historical VillageFoundationSmoke still
unit-tests the retained but no-longer-called helper; it is NOT village-shape
acceptance and cannot justify re-enabling reclamation.

## Scope and remaining gates

Both overrides run at the END of the existing post-patch wrapper. Historical
hash-checked stages remain intact. No saved world, lock or region file is edited.
The Nether implementation and staging/main branches are not modified.

Compilation/native smoke and natural saved-world checks remain separate gates.
Natural checks must establish tree survival and the shape around actual village
buildings, including shoreline/foundation safety. The old requirement of zero
water across the entire village bbox is not evidence of natural shape: it can
reward the very artificial square fill the user wants removed.

Previously generated rectangular terrain and erased trees are NOT repaired by
this source change. Test new chunks in a new disposable Overworld. Until the
natural gates are complete this workflow publishes diagnostics only, not a
replacement server distribution.
