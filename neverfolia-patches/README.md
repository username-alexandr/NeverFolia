# NeverFolia patch stages

NeverFolia source patches are split by application phase:

- `pre-apply/*.patch` — applied to the cloned Folia patch repository before `./gradlew applyAllPatches`.
- `post-apply/*.patch` — applied to the fully materialized Folia/Paper source tree after `./gradlew applyAllPatches` and before compilation.

Worldgen/server source modifications belong in `post-apply` unless they intentionally modify Folia's patch sources themselves.

The legacy flat `neverfolia-patches/*.patch` layout is rejected by `scripts/prepare-upstream.sh` to prevent patches from silently applying at the wrong phase.
