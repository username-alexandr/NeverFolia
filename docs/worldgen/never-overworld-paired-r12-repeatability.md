# FIELD-R12: controlled replay and ore repeatability

## Observed failure, not a release

Run `35612057461`, source `5ad7aabec505aa8006b33873a44921e8e92c7ed2`,
built and passed all native checks, then rejected the paired saved-world gate.
On seed `-2996952393010080672`, the forest sample contained 23,016 resource
blocks in delivered `32c6df3` and 11,554 in the candidate (50.19986% retained).
However, 260 candidate resource coordinates were absent or another resource
kind in the baseline. The strict nested-position gate therefore failed. No
accepted FIELD-R12 bundle was published.

The sampled vanilla mine had one piece (720 cells, 543 air); the collapsed mine
had one piece (1,976 cells, 250 air, 16 rails). Both sampled interiors were dry
and had the required persisted metadata after restart. This is not acceptance
of every mineshaft geometry. Observed wholly submerged wood/leaf components
were 85 -> 0; these are connected components, not individual tree identities
and not proof of natural fallen-tree frequency.

## Defect in the former experimental protocol

The baseline ran initial locate/5x5 loading and then completion. The candidate
was given the resulting plan, skipped initial locate/5x5 loading, and ran
completion plus restart. Consequently the experiment had different generation
requests and stop boundaries. This is a confirmed methodological difference,
NOT proof that it accounts for all 260 changed resource coordinates. Parallel
feature ordering or a gameplay regression remain possible until controlled
saved-world evidence is available.

## Changes

All roles now execute the same three phases: initial, complete, restart. Every
role independently performs the same locate requests and initial forest/mine
coverage, then derives its own saved structure-piece geometry. A supplied plan
is an equality check, never permission to skip discovery. Different locations,
coverage or geometry reject the comparison. Exact high-level request sequences
are retained and compared; asynchronous completion timing is not asserted equal.

The exact pinned baseline JAR is run twice in independent new directories.
Both runs use the same seed, datapack hashes, request plan and stop boundaries.
The second baseline is a repeatability control, not an alternative baseline
chosen to obtain a pass. Candidate resources must satisfy the existing strict
subset/density check against BOTH baseline runs. A control difference is not a
tolerance: any differing control resource position also rejects acceptance.

Every role saves a complete, hashed resource-coordinate census after each of
its three normal stops. Full per-phase deltas and both candidate/baseline
deltas are retained, not only the first 30 examples. Differences are also
counted below/above Y=-64 and at chunk faces/interiors. Both height bands and
all resource kinds remain in the acceptance population. Changes to already
FULL sampled resources between phases reject acceptance too. No region is read
while its test server is running; nonzero stops never qualify as evidence.

`compare_ore`, mine validation, resource enumeration and the existing density
interval remain unchanged. The final gate and packager require the additional
control fields, not just a top-level success flag. The existing workflow runs
the expanded tests without relaxing native checks or the two-datapack bundle.

## Validation scope

40 local tests: the original 20 plus 16 control/delta/gate checks and four
orchestration tests with mocked server/NBT boundaries. The orchestration tests
exercise real Python control flow and verify 9 starts, 15 locate calls, 9 full
censuses, 6 transitions, identical high-level requests, normal-stop read guards,
and failure on changed replay selection. They do not execute Minecraft.

This commit changes observer/tests/documentation only. Tree admission, final
ore retention 25%, dry-mine code, Nether R15 and disabled village reclamation
are unchanged. New control results must be obtained in CI; existing failed
reports are not relabelled. No world reset, lock edit, deployment or promotion
to staging/main is part of this change.
