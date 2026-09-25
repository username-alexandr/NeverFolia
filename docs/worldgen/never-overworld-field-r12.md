# NeverOverworld FIELD-R12 — candidate, not a release

Base gameplay: `32c6df3029fca001fd3602012e446a901f80eb2f`.
Exact materialized upstream: `14b7fee5c866fca9a40ede4a58998fb928140f65`.

## Current tree rule — height, not submerged block count

The September 21 clarification supersedes FIELD-R12's former one-to-three
submerged-log/leaf census. New ordinary standing trees may start at most TWO
blocks below the ocean: `originY >= OCEAN_Y - 2`. With the existing flood plane
Y=128 this accepts origin Y=126,127,128 and above, and rejects Y=125 and below.

Origin means the `TreeFeature` placement origin (`context.origin()`), not the
supporting ground block and not the lowest root or leaf. For normal trunks it
is the first trunk block. Root placers may shift the trunk upward; the original
planting point still controls admission. Large trunks, low hanging foliage and
root depth do not count against a quota. Even a dry low cave is subject to the
height rule in this NeverOverworld generation scope. Ordinary sapling/player
contexts and other dimensions are outside it. Existing trees are never cut.

The existing FallenTreeFeature exception remains: real fallen trees may generate
underwater below Y126. Incidental horizontal branches on standing trees do not
change their classification. Existing tree frequencies are not altered here.

## Implementation

The exact-source installer still verifies eight materialized inputs and all
expected outputs. Only its TreeFeature transformation changes in this revision;
the other seven outputs are byte-identical to the earlier FIELD-R12 outputs.
The production wrapper already invokes this installer after TREE-R1 and village
no-fill. No separate optional tree-height overlay is required.

`begin(level, origin)` captures the planting height. `canStart()` rejects a low
origin before random/trunk/root/foliage work; `acceptAndCommit()` repeats that
decision before staged blocks are published. The previous OCEAN_FLOOR_WG scans,
water-column forecast and total/atRisk/aboveOcean census are removed. Existing
write-radius checks, staging, vanilla placement flags and decorators remain.

## Retained resource and mine changes

Final resource retention stays at 25 instead of the delivered 50 with the SAME
salt/hash: roughly another half of the old survivors, no rerolled final mask.
The eight Overworld kinds and raw iron/copper scope are unchanged. Nether ores,
chest loot and player changes are not modified.

MineshaftStructure and neverfolia:collapsed_mine still persist PIECE geometry
and its one-block envelope in owner-chunk PDC. The pre-FULL LIGHT pass drains
interior fluids, seals shell air/fluids with rock, and excludes interiors from
both flood passes. Corridor unions remain open and FULL/player-time chunks are
not repeatedly repaired. This tree change does not modify mine logic or restore
village sea-level reclamation.

ORE-LIGHT-R12 remains an explicitly installed, separately tested overlay; its
native workflow 35642347317 on 368a10b succeeded. That previous result is not a
claim that the new tree-height source has already passed native or natural CI.
Historical paired-world failures remain failures, not relabelled acceptance.

## Tests and validation scope

The pure height test covers every integer Y from -2048 through 2048 plus the
125/126 boundary and integer extremes (4104 assertions). Ten installer tests
include origin wiring before vanilla random work and the fallen-tree exception.
Exact transformation and idempotence are checked on the saved source contract.

The updated native smoke covers origins Y125/Y126/Y127/Y128, full real vanilla
trunk/foliage proposals, a 2x2 trunk crossing negative chunk boundaries with more
than three submerged wood blocks, lower waterlogged leaves, supporting soil,
existing underwater logs, non-WorldGenRegion contexts and a real fallen log in
water at Y91. Mine/PDC/ore scenarios and the existing preservation tests remain.
Native tests still use deterministic fixtures, not natural-world acceptance.

No world data, lock file, deployment, staging/main promotion or ready JAR is
produced by this source change. The previous 32c6df3 download does not contain
FIELD-R12. Any accepted future bundle must include matching NeverOverworld AND
NeverNether packs and its actual evidence. Natural repeatability and visual
acceptance remain separate checks.
