# FIELD-R12 paired saved-world observation

Native candidate `3b32c3f282fde4171a5b5ce0b25d2b42576dfc33` passed run
`35604670400`, including FieldR12Smoke (809795 assertions), TREE-R1 (21325),
and Nether R15 (87). These are native fixtures, not natural acceptance.

This change adds only the paired observer, its tests and CI; no gameplay code
or existing worlds/lock files are modified. Baseline is the exact delivered
32c6df3 Paperclip (artifact, bundle and JAR SHA-256 pinned). Expired or wrong
baseline artifacts fail the run; another revision is never substituted.

Both baseline and candidate use separate NEW folders, the same user seed
-2996952393010080672 and the same freshly built NeverOverworld/NeverNether R15
packs. Three forest areas of 5x5 chunks and two mine variants (vanilla mineshaft
and collapsed_mine) are planned. Mine coverage includes individual piece
shells. The candidate is restarted and reloaded with ordinary fluid ticks.
Every region read requires a normal stop; missing sections/chunks are errors.

Hard checks: retained ore position subset and 40–60% of the baseline population
on the paired sample (at least 200 baseline resource blocks); no fluid or
waterlogged states inside sampled mine pieces; saved owner-chunk PDC covers all
intersecting piece shells; nonempty mine air space; joint startup with both
packs; nine FULL Nether chunks with roof512 and empty padding. Tree connected
components must decrease in this sample; they are not complete tree identities
or proof of every placement decision. Precise standing/fallen/2–3-block cases
remain covered separately by native tests. No natural fallen-tree-frequency
claim is made. This gate is manual-test eligibility, not production acceptance.

Only success can package the current JAR AND both packs under world/datapacks.
The package binds binary hashes and source SHA, includes reports/logs, checksums,
and Russian new-world instructions; production_ready=false. It never includes
a prepared level.dat or lock from the probe. Failed runs preserve diagnostics
but do not publish an accepted candidate. No village-shape acceptance is implied.
