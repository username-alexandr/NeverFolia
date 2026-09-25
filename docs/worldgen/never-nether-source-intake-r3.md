# NeverNether SOURCE-R3 — real Dungeons and Taverns intake

Baseline: `d76739fac10790ebcedc8611fa7e31e48ad312de`, branch
`wip/nevernether-field-r1`. Status: **source integration; NOT a server release**.
No third-party source ZIP, NBT or other third-party asset is committed here.

## All required source archives are present

The uploaded `Dungeons and Taverns v5.3.2(1).zip` has SHA-256
`4096cd6372e0f244efa0e85c4d884bd85afe665a84a050280acd483b3222b4f9`
and size 20,724,798 bytes. All 7,928 ZIP entries were CRC-checked. The working
copy uses the manifest's canonical filename `Dungeons and Taverns v5.3.2.zip`;
its bytes are identical to the upload. The new hash is pinned in the manifest.
All five required archives now pass exact-filename/hash validation. There is
no longer a missing-upload blocker for the twenty selected custom structures.

## Results on actual supplied archives

The source audit finds definitions for **20/20** approved structures.
After the explicit repairs below, **17/20** pass the expanded known-dependency
preflight: Hearths 3/3, Explorify 1/1, Structory 3/3, D&T 10/12. The Nether
Monument is still blocked. This is NOT an installed-world or runtime success rate.

D&T passes: Nether Port, Nether Keep, Hamlet, Sealing Halls, the four skeleton
towers, Piglin Camp and Piglin Camp Collony. Piglin Outstation and Piglin Donjon
still contain genuinely absent templates; their build is rejected, not replaced
by placeholder dungeons.

The expanded D&T reachable resource set includes 949 NBT resource paths (nine
are exact aliases), 46 trial-spawner configurations, 22 enchantments, 30 functions,
151 loot tables, 7 predicates, 1 item-modifier file, required tags, processors,
features and pools. These are source inventory counts, not generation counts.
The full local JSON audit includes both raw and repaired missing-reference lists.

## Implemented changes

1. Accept object-array roots for item modifiers and predicates only. D&T's valid
   empty `item_modifier/loot_modifier.json` no longer fails as a non-object.
   Other registry roots remain object-only; malformed array members are rejected.
2. Follow modern/legacy enchantment component references, enchantment tags and
   effects, trial-spawner normal/ominous configurations and ejected loot, entity
   death loot, processor-injected loot and feature block tags. Read referenced
   function files and trace known static function/predicate/loot references.
3. Resolve Jigsaw `pool_aliases` per structure, including direct, weighted random
   and grouped aliases. Preserve source weights and bindings. A virtual ore pool
   is not treated as a missing physical pool. Follow all candidate alias targets
   without fabricating an alias-pool file. Recheck each root independently in the
   importer so another structure's binding cannot hide a missing binding.
4. Cache per-resource dependency observations, not context-specific resolved
   results. Cached observations are re-resolved for each structure's aliases.
5. Apply thirteen explicit, version/hash-locked source-resource aliases. Each
   destination must be absent; each existing target must match its pinned hash.
   All thirteen are validated before any staging mutation. Source ZIPs and
   existing NBT bytes remain unchanged. No fuzzy matching runs in the builder.

### Thirteen resource aliases

The exact mapping and target hashes are in
`worldgen-spec/never-nether-source-compat.json`:

- Eight NBT names: the skeleton tower `pot_` spelling and seven stale Sealing
  Halls bridge-side/T-junction names, mapped to their existing source variants.
- One NBT name for the unarmoured sword piglin. The existing `swordw` and
  `swordwd` templates are byte-identical and contain a piglin with a golden sword.
- Three loot-table names: pluralized piglin pot loot and two stale Nether Port
  ominous-projectile references, mapped to existing corresponding source tables.
- One piglin camp jockey-pool reference, mapped to the existing camp jockey pool.

These are documented integration choices, not proof of the author's original
intent. They retain existing template geometry/loot and pool selection weights.
There is no generic substitute for unknown missing rooms or foundation pieces.

## Remaining blockers, now precisely identified

D&T contains no files for these four referenced NBT resources:

- `nova_structures:donjon/coloseum_part/deco_14`
- `nova_structures:donjon/coloseum_part/deco_15`
- `nova_structures:donjon/room/donjon_room_3x3x3_1`
- `nova_structures:piglin_outstation/main/piglin_outpost_outer_layer_foundation_1`

These require explicit geometry/connector-compatible replacements or a reviewed
source-content correction. This change does not silently remove their pool
entries, change weights, or replace them with empty structures.

The Nether Monument still requires a native solution for YUNG's max-count pool
elements and four Repurposed Structures processor types, plus its missing
`repurposed_structures:chests/monuments/nether` loot table. Those adapters are
not implemented by SOURCE-R3.

## Runtime and lifecycle caveats

The new graph finds actual function-driven boss/enchantment behavior that the
old importer would have omitted. Function files are inspected as source text,
not executed, and are recorded as requiring runtime review. Dynamic function
macros block the source preflight. Known static-call extraction is not the full
Minecraft command/SNBT parser. Builtin references still need validation against
the exact server registry; a passing source audit is never a runtime guarantee.

In particular, referenced boss code uses scoreboards. The report marks required
initialization; it does not claim that a safe NeverFolia load hook/scoreboard
lifecycle is finished. No broad upstream load/tick tag is imported implicitly.
Boss execution, region ownership, loot production and command compatibility
remain required runtime checks before release.

## Validation

Local suites: **29 existing source tests + 26 new SOURCE-R3 tests + 23 FIELD-R1
tests = 78 passing tests**, plus the existing pipeline/spec self-tests.
The dedicated CI workflow reruns those suites with synthetic fixtures only;
it does not contain the supplied third-party source archives.

The actual full pinned-source builder is expected to reject the four absent D&T
templates. It must not produce an incomplete installable pack. Separate raw and
repaired audits retain the Nether Monument blockers too.

All 24 rebuilt finalized Core resources are byte-identical to FIELD-R1 CI
`857f793`, including its fingerprint. No density, fluid, cave, Overworld or End
implementation changed in this intake. The floating-lava candidate is retained;
no new claim is made about the reported cavity screenshots or saved-world repair.

**Do not deploy a source-review ZIP as a datapack, replace a JAR, or remove a
worldgen lock.** No ready server JAR or complete twenty-structure pack is released
with SOURCE-R3. Runtime startup, full structure assembly, boss/lifecycle checks,
fluid ticks and strict chunk-order determinism remain required.
