# R15 native revision lock: validation hardening

The active native revision remains `NN-R15-FIELD-CLEANUP-1`. This change does not alter terrain, lava, cavity-cleanup rules, R14 height, or the datapack's generation fingerprint.

## Startup contract

- A new matching R15 world receives `.neverfolia-nevernether-native.lock`.
- An existing matching lock is verified, not rewritten.
- Mismatched, empty, truncated, oversized, non-regular or symbolic-link locks are rejected. A broken symbolic link is not treated as a missing lock.
- Publication uses `CREATE_NEW`, never `REPLACE_EXISTING`. When a competing creator has already created the path, the existing contents must match; otherwise startup fails. Partial writes remain invalid and are not silently repaired or deleted.
- Existing Nether region files without the native lock are rejected in the modern dimension directory, legacy `DIM-1/region`, and Bukkit sibling Nether layout. This is not an existing-world migration.

## Profile validation

Both directory and ZIP datapacks are supported. The native profile is read with a 65,536-byte limit enforced while reading, not after an unbounded allocation. Lock reads are limited to 256 bytes.

The profile must be a JSON object. `schema` must be a numeric exact integer equal to 1; fractional values, overflowing integers and numeric strings are rejected. Profile identifiers must be strings with the expected values. `new_world_required` must be the JSON boolean `true`, not the string `"true"`.

A missing or invalid marker also rejects a previously locked world's restart without modifying its native lock. This change retains the required `neverfolia:field_r15_required` processor so the matching R15 datapack cannot decode on an R14-only runtime.

## Verification scope

The existing native smoke test now additionally checks invalid JSON types and values, bounded directory/ZIP payload rejection, create-only lock conflicts, missing markers on restart, orphan locks and legacy DIM-1 preservation. These tests execute within the existing native integrity workflow; no required checks are disabled or reclassified.

Local Java 21 filesystem-only verification passed 19 checks for the same create-only and bounded-read logic, including regular, empty, mismatched, oversized, directory and symlink paths. This is not a substitute for the Java 25 full-runtime smoke and natural-world audit.

The preceding native-lock baseline is commit `3bf4199688a76d23678c0cc068a663d1bd4f8c04`, workflow run `35467126678`. Its successful audit does not establish acceptance of this new validation change. No production/staging branch promotion is part of this commit.
