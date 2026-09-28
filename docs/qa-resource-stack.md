# Ordered resource-stack QA

The R3919 diagnostic branch extends the exact R3917 QA source baseline
`5df53b7ac21b2540e2939efabd7887954459d17d`. It does not replace the independent
R40/R41 branches or publish a game-server kit.

## Why the additional check exists

`qa/field-r3915/check_combined_resources.py` compares one NeverOverworld pack
against bundled vanilla. Keep that regression: it proves the intended cart
resource delta. It is not the effective resource stack of a server that also
loads NeverNether. The new check preserves the isolated result and performs a
separate before/after audit with the complete configured base QA stack.

## Entry points

- `scripts/never_resource_stack.py`: reusable read-only audit using a JSON manifest.
- `scripts/test_never_resource_stack.py`: synthetic precedence and validation tests.
- `qa/field-r3919/check_stack.py`: exact historical input hashes, configured order,
  before/after comparison, root identity and shadowed-content checks.
- `qa/field-r3919/run_stack_smoke.py`: fresh isolated server startup and enabled
  order read back from the saved `level.dat`.
- `.github/workflows/never-r3919-resource-stack.yml`: reproducible CI using the
  existing pinned input artifacts; publishes evidence, not a server kit.

## Manifest contract

`schema` is `1`. `server` contains an explicit `path` and `sha256`. Each member
of `packs` contains `id`, `path` and `sha256`. The list is ordered **low to high
priority**, after the vanilla resources embedded in the pinned server JAR.
Pack IDs and input paths must be unique. Basenames are never resource identities:
namespace and complete resource path are retained. A checksum mismatch, an
unsupported pack directive or an incomplete graph raises an error rather than
silently supplying an empty room or dropping a dependency.

```sh
python3 scripts/test_never_resource_stack.py
python3 scripts/never_resource_stack.py \
  --manifest artifacts/stack-after-manifest.json \
  --report artifacts/standalone-stack-report.json
```

The standalone command exits with `0` only when its scoped reference graph has
no reported gaps. Exit `1` means missing references or graph errors. Input or
manifest failures return `2`. The report path must be new and cannot replace an
input. All paths in a manifest are resolved from the command's working directory.

## Evidence and acceptance

The input hashes include the bundled server and every datapack. A separate hash
identifies the nested Folia engine. Each non-tag resource records its effective
provider; overrides retain the previous and winning provider hashes, including
byte-identical duplicates. Root definitions retain their provider too.

`stack-delta.json` distinguishes a preserved intended delta from a complete
reference closure. Its `pass` does not imply `full_resource_acceptance`.
`stack-smoke.json` separately records startup, shutdown, persisted enabled order,
input hashes and targeted errors. `stack-acceptance.json` is written only when
both the delta and the fresh startup witness satisfy their scoped requirements.
No report grants production acceptance or claims all world-generation bugs fixed.

## Deliberate boundaries

Only flat datapacks are supported. An `overlays` or `filter` directive stops the
audit; it is not ignored. Tag contributions are recorded but not merged or
validated. The jigsaw graph uses the existing root-local correlated alias walker
and checks pool, template and placed-feature-holder references. Palette state,
not the optional NBT block-entity `id`, identifies a jigsaw block.

This does **not** prove registry codec validity, tag semantics, complete feature
contents, loot, command/function behavior, geometry, biome eligibility, generation
frequency, natural-world appearance, mob behavior or compatibility of other
server plugins. The temporary `CartQa` selection pack belongs to the separate
cart fixture; it is not silently included in the base server audit.

All startup worlds are newly created under `.work/r3919/stack-smoke`, bind only to
loopback, accept no QA player clients and have no connection to production world
folders. The configured source order is not represented as runtime evidence until
it has been compared with the saved enabled order from that fresh server run.
