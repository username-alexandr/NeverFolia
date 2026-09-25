# Final saved village snapshot and manual field-test bundle

## Observed failure, not a generation acceptance

Run `35513620614`, source `71e285da16405863b41fbbba753e4347450bc9ba`,
completed both normal-stop phases with exit code 0. Its plan records 170 distinct
saved FULL chunks: three forest areas of 25 chunks and village areas of 80 and
15 chunks. Compilation/native smoke and Overworld pack construction succeeded.
The observer then failed on `village boxes changed after generation`.

Artifact `10606178653` has SHA-256
`25f23394cc827f684e087c1c503a5cd4bee00367791b7c505e21c100a57523ff`.
It contains the initial planned piece boxes, but not the final boxes that caused
the mismatch. Therefore the exact type of change (ordering, Y, XZ, piece count)
is NOT established by that artifact. No successful natural/visual acceptance
is inferred from the 170 FULL chunks alone.

## Final-snapshot observer

`probe-never-overworld-final-villages-r1.py` reuses the existing two-phase
`generate()` and the existing final `audit()`. It does not modify Java, native
flooding, tree placement, village placement, world files or lock files.

The initial stopped snapshot is a generation plan, not immutable final geometry.
After BOTH successful normal stops, the wrapper:

- retains the original plan as `tree-village-initial-plan.json`;
- reads final village starts only in previously verified FULL chunks;
- records initial and final piece boxes, ordering/multiset/XZ differences,
  added/removed box instances and exact coverage in `tree-village-geometry.json`;
- refuses final geometry requiring ANY chunk outside that verified area;
- verifies all originally requested village chunks again for FULL and coordinates;
- builds a separate final observation plan using the final saved boxes, retaining
  `planning_piece_boxes` and `planning_chunks` in each village entry;
- runs the existing audit against that final plan, including exact box reread,
  complete coverage, forest observations and every waterline CSV column.

Changes are documented, not silently discarded. Invalid or unbounded geometry,
missing starts, abnormal stops and incomplete coverage still fail. Diagnostic
geometry is written even when reconciliation fails. This is stopped-world
observation, NOT proof that changing piece geometry or shoreline shapes are safe
for production. Visual acceptance remains explicitly false.

Fourteen synthetic final-snapshot regressions cover ordering, vertical changes,
XZ changes inside verified coverage, added pieces, unsafe coverage growth,
invalid geometry/statuses, non-destructive failures and negative coordinates.

## Optional manual field-test distribution

The workflow packages the exact JAR and matching Overworld datapack ONLY AFTER
native smoke, natural observation and final geometry checks succeed. Sixteen
synthetic bundle tests cover successful checksums plus rejection of stale SHA,
binary mutation, missing smoke, invalid lifecycle evidence, altered/truncated
CSVs, geometry disagreement, false production claims and output overwrite.

The packager cross-checks source SHA and binary SHA-256 in the original plan,
final plan and report. It recomputes chunk coverage and CSV counts rather than
trusting the success flag alone. The bundle retains both geometry snapshots,
CSV evidence and smoke logs with SHA256SUMS, BUILD-INFO and Russian instructions.

The bundle is for a NEW separate test Overworld. `production_ready=false`,
`village_visual_review_required=true`, no old-region repair/migration and no
staging/main promotion. NeverNether and NeverEnd datapacks are not included.
No EULA acceptance is automated for the recipient. The existing-tree rules and
custom village-reclamation removal are unchanged by this QA/packaging step.
