# NeverNether SOURCE-R5: complete import and actual runtime loading

Status: **development candidate; runtime content gate BLOCKED**.
Source recovery baseline: 5897d5214650341c1af1582ccb4076b088667a7c.
Native runtime compiled by CI: 73fd4d879ab2a4421189d840efa7d2a9500507f0,
run 34774518337. The later snapshot changes no native source.

## Completed

The interrupted R5 work was recovered from GitHub. The final native job is
SUCCESS, not the earlier failed attempts. Its complete offline runtime and Java
were retrieved; the artifact SHA-256 and all internal checksums were verified.
Local execution of the same native smoke class passed 4,106 checks. Pure CI quota
and pillar-planner tests passed 359 and 539 assertions respectively.

The real five-source importer now builds all **20 approved custom structures**,
including the Nether Monument. The raw input ZIP hashes remain pinned and unchanged.
This is a successful import, not a claim that all twenty were naturally generated.
Monument conversion includes 25 limited pool-element entries and nine processor
entries (four noise, three random, one pillar and one structure-void filter).
Original upstream monument loot plus its lucky-pool dependency are retrieved by
immutable Git blob IDs, with the source license. No mod assets are committed here.

The native processors preserve compatible block-state properties, avoid mutable
shared RNG/sampler reseeding and restrict pillar planning to bounded owning-chunk
worldgen with confirmed anchors. This is deliberately more conservative than
unbounded/forced support writes; full in-world pillar geometry is not yet accepted.

## Errors found only after starting a real full pack

The first complete pack failed registry loading because two monument decoration
features still used minecraft:random_patch, absent from the inspected 26.2 runtime.
The exact two hashed inputs are now converted to minecraft:sequence and placement
modifiers. Attempt counts and the triangular offset distribution are preserved;
**historic RNG consumption/layout equivalence is not claimed**.

After this conversion a fresh isolated server reached Done(), generated initial
world areas, created the matching NeverNether fingerprint lock, and saved/stopped.
The first successful-start probe still exposed two omitted loot-table resources:
bare discriminator IDs such as type=loot_table were not followed by the source
scanner. The inspection view now normalizes default minecraft discriminator IDs
without changing source bytes. The final rebuild includes these dependencies;
the third probe confirms the missing-loot-reference warnings are gone.

## Actual final runtime status: ready does NOT mean clean

The final probe used the complete rebuilt pack with the unchanged compiled R5
runtime. It reached Done(), exited 0 after stop, and logged all dimensions saved.
It nevertheless remains blocked by:

- **15 failed Dungeons and Taverns functions**, involving entity-data, trading,
  projectiles/jockeys and enchantment behavior. No function is deleted or emptied
  to turn this red gate green. Native command compatibility still needs work.
- **nova_structures:villagers/tavern_quest** loot data refers to twelve Overworld
  tavern structures outside the approved Nether import set. The table fails parsing.
- An unresolved runtime pool warning **nova_structures:piglin_camp/fake_caves**.
  Source alias coverage and runtime assembly context must be reconciled; it is
  not silently declared intentional or replaced with an empty pool.

The isolated network cannot fetch the Mojang authentication public key. This is
recorded separately as an environment error, not a datapack fix. Tests listen only
on loopback and never use, delete, upgrade or regenerate an existing user world.

The new validate-never-nether-startup-r5.py requires readiness AND clean content
loading AND a saved normal stop. It returns exit 2 for this actual run despite
Done() and exit 0 from the server process. Synthetic gate tests are separate from
the real log result. A passing Python CI cannot override the red runtime gate.

## Verification scope

Local Python suites: **138 tests passed** (29 monument R5, 12 startup gate,
23 FIELD-R1, 29 source inputs, 26 SOURCE-R3, 19 reconstruction R4).
CI runs these synthetic suites, contracts and Core only; original source ZIPs are
not installed in CI. Consult the actual commit/run result before claiming CI passes.
Native compilation/4,106-check execution refers to the exact prior native SHA above;
source-import changes do not imply a second native compilation.

No density function, sea level or base terrain resource is changed in this step.
The FIELD-R1 lava-shelf candidate remains; reported user-world cavities have not
been reproduced or repaired. The R4 gallery still needs deliberate frame hookup.
Full structure placement, loot/behavior QA, lava/cavity inspection and strict
chunk-order determinism remain outstanding. No production JAR is released here.

Do not use a diagnostic pack to update a live world or bypass the fingerprint lock.
All five original source archives are available; repeated upload is unnecessary.
