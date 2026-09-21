# ORE-LIGHT-R12 — explicit candidate overlay

## Observed control result

Source `8ce4363b2daa1d9a37c6a3e94b54333112953c44`, run `35639733390`,
artifact `10658057533` (SHA-256
`7e2cf33f47dc4e55d1b7bb227caac157aa705fa06946f9acac3d69fb70d27f9e`):

- Both baseline runs use the EXACT delivered `32c6df3` JAR, identical seed,
  datapacks, high-level generation requests and normal-stop boundaries.
- The baseline repeats differ at 853 resource positions, all Y >= -64:
  317 positions on chunk faces, 536 in interiors; no deep-band differences.
- Baseline resource totals: 23,147 and 23,016; FIELD-R12: 11,493.
- Candidate/baseline ratios: 49.6522% and 49.9348%.
- Candidate is an exact resource-position subset of the second baseline,
  but has 199 absent/retyped resource positions against the first.
- Every sampled resource remains unchanged across the three saved phases
  within its own run. This is fresh-generation variability, not reload decay.
- Both sampled mine pieces stay dry after restart; required chunk metadata is
  present. Air counts are 543 and 250, with 16 rails in the collapsed mine.
- Observed wholly submerged wood/leaf groups: 78 -> 0. These are not proven
  individual tree identities or natural fallen-tree-frequency acceptance.
- The strict historical paired gate FAILED. It has not been weakened or relabelled.

## Source-level defect targeted by this overlay

`applyAfterFeatures` pruned upper ores immediately after one owner's FEATURES.
Other neighbouring FEATURES can still place veins into that owner before LIGHT.
An ore written late can bypass that pruning; early replacement also makes host
rock available for later features. The pure local timing model demonstrates
this at (195,-58,166), coal: upper buried-prune hash bucket 62 (keep<55),
while the final FIELD-R12 keep<25 mask admits the coordinate.

That schedule is not a full natural-world replay and is not claimed to explain
all 853 differences. Vanilla feature overlap/random-stream effects remain a
possible source of further differences. The new native test must reproduce the
specific bypass with actual ProtoChunk writes and the installed prune routine.

## What changes when explicitly installed

`defer-upper-pruning.py` checks the exact hashes of two materialized files and
installs the upper-prune call at the existing pre-FULL, neighbour-complete LIGHT
barrier, before upper lapis/diamond suppression and final 25% resource thinning.
The legacy FEATURES entry point becomes intentionally inert. Retaining its
signature/call preserves the exact ChunkStatusTasks contract used by Nether
installers. Deep pruning, all salts/percentages, tree and mine helpers, disabled
village reclamation, datapacks, locks and saved worlds are unchanged.

The overlay is NOT yet in the normal post-patch wrapper. Its dedicated workflow
applies it AFTER the full FIELD-R12 plus R15 source chain and existing preflights,
then runs the new native regression and all retained native tests. This prevents
silently presenting the unchanged historical paired workflow as testing the fix.
No ready server archive or production promotion is part of this commit.

Local validation: 11 source-installer tests; exact transformation/idempotence
on the verified materialized source contract. Native Java 25 execution and a
new repeated-candidate natural-world test remain separate evidence gates.
