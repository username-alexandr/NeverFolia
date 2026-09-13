# NeverNether source intake R2

Baseline: `857f793f1752f78ac96e0f3b2d04f7526ab5daca` on
`wip/nevernether-field-r1`. Status: **source-integration work, not a release**.
Exact observed hashes and results: `never-nether-source-intake-r2.json`.

## Real supplied archives

Four of five required source ZIPs were supplied and their CRCs/hashes verified.
The uploaded Better Monuments archive matches its existing pinned SHA-256.
Hearths 1.0.5, Explorify 1.6.5 and Structory Towers 1.0.17 are now pinned too.
Dungeons and Taverns 5.3.2 is absent from this intake; no replacement version or
synthetic structures are substituted for its twelve approved structures.

Source dependency preflight results, **not installed-world counts**:

| Source | Approved definitions supplied | Preflight pass | Selected NBT templates |
| --- | ---: | ---: | ---: |
| Hearths | 3 | 3 | 12 |
| Explorify | 1 | 1 | 15 |
| Structory Towers | 3 | 3 after explicit optional-mod pool overrides | 4 |
| Better Monuments | 1 | 0; adapter and loot dependency work remains | 45 |
| Dungeons and Taverns | 0 of 12 | Not tested; missing archive | Not inspected |

The real source-copy path for the first three packs was exercised locally:
**7 definitions, 31 NBT templates, 72 selected resources**. This was in-memory
staging, not an installable partial datapack or a live server test.

## Importer changes

- Resolve source overlays for data pack format **107.1**, in declared order.
- Traverse dependencies from approved structure roots, rather than copying every
  file in a custom namespace. Follow Jigsaw pools and fallback pools, NBT Jigsaw
  references, chest loot tables, processor lists, biome tags and referenced
  features. Unrelated dimensions, terrain, structures, functions and mod assets
  no longer enter the output merely because they share a namespace.
- Use modern singular resource directories. Legacy-only dependencies are reported
  as missing, not silently renamed or claimed converted.
- Reject duplicate/unsafe ZIP paths, ambiguous pack roots, incompatible declared
  format ranges, corrupt NBT and missing required dependencies.
- Unsupported processor/element types fail the build instead of being removed.
  The old `runtime_external_mod_dependency=false` assertion is gone: vanilla
  references still need verification against the exact server runtime.
- The full builder still requires all five sources and all twenty approved IDs.
  There is no incomplete-pack release mode or placeholder dungeon substitution.

### Structory optional integrations

The three selected towers reference small Waystones/Fabric Waystones sub-pools.
An explicit NeverFolia-authored compatibility profile replaces only these two
optional pools with empty elements on native Folia:

- `structory_towers:waystones/waystone`
- `structory_towers:waystones/fwaystone`

Tower NBT, the main tower pools and loot are retained. The mod-specific mini-piece
NBT is not imported. This is a documented behavior change, not an implicit claim
that mod blocks work on Folia. The policy is in
`worldgen-spec/never-nether-source-compat.json`.

### Nether Monument blockers found in actual content

The previous synthetic tests did not cover these dependencies:

1. `yungsapi:max_count_single_element` in three reachable template pools. Removing
   this type or blindly rewriting it would lose `max_count` semantics.
2. Repurposed Structures noise/property replacement, random/property replacement,
   pillar and structure-void processors. Some are structural behavior, not just
   cosmetic randomization; deleting them is not a valid complete port.
3. Missing loot table `repurposed_structures:chests/monuments/nether`, referenced
   inside the start NBT and absent from the supplied compatibility archive.

The source-level refusal was tested using the real monument archive. It did not
modify previously accepted resources. Native adapters and an explicit loot
resolution are still required; these changes do not implement them.

## Other supplied ZIPs

The two Better Witch Huts v5 files are byte-identical (see hashes in the JSON
report). They are Overworld inputs, not additions to the approved Nether set.
Amplified Nether 1.2.15 is not installed over NeverNether and its implementation
is not imported. The independently authored NeverNether terrain remains intact.
No third-party NBT/assets are committed with this intake or in its source-only
review bundle. The existing source/license policy remains in effect.

## Validation / use

Synthetic tests:

```sh
python3 scripts/test-never-nether-source-inputs.py
python3 scripts/test-never-nether-field-integrity.py
python3 scripts/build-never-nether-test1-pack.py --self-test
```

Inspect locally supplied exact archives (exit 2 is the expected blocked status
for this intake; the JSON still contains the complete observed report):

```sh
python3 scripts/audit-never-nether-source-inputs.py \
  --source-dir /absolute/path/to/archives \
  --output /absolute/path/to/source-preflight.json
```

Local synthetic suites: **29 source regressions + 23 field regressions passed**.
CI reruns synthetic tests only; it does not contain the third-party input ZIPs.
Source evidence JSON is an audit record, not a runtime test.

Every rebuilt finalized Core resource was compared with the prior FIELD-R1 CI
artifact: identical, including fingerprint
`23f6b966541a33e00237d956a5d6c33eb3da305ba9a227789a26678bfd3dd25a`.
No density, lava level, fluid simulation, dimensions or Overworld logic changed.
The earlier lava-shelf candidate is preserved, not newly runtime-validated.
The reported cavities are still not diagnosed against saved affected chunks;
that requires a stopped-world `.mca` copy and positions.

**Do not install this source-only review as a datapack, replace a server JAR or
remove an existing world's worldgen lock.** Registry startup, runtime placement,
fluid ticks, strict chunk-order determinism and full twenty-structure integration
remain release gates.
