# NeverNether R13 probe supervision and preflight

Base: `7ed905f32ea88f7fa03d60eae0fca505a4220408`.
This change concerns Python probe runners only. No generator, source ZIP, world
profile, Java observer or comparison rule is modified. It does not claim a new
full-world generation result or diagnose an internal ChatGPT interruption.

## Why waiting looked like no work

The existing start and resume loops printed their result only after completion.
They polled a report until the overall timeout (defaults: 900/600 seconds) and had
no separate deadline for a report that stopped advancing. This made startup,
progress, a stuck observation and a stopped process difficult to distinguish.

Both runners now share `qa/nevernether-r8/probe_supervisor.py`:

- A stderr heartbeat every 15 seconds reports phase, observation count, last
  completed chunk, elapsed time and seconds without progress. Hash/preflight
  checks announce their own phase before starting. JSON stdout remains usable.
- `probe-progress.json` is replaced atomically and includes PID and terminal
  status. This is liveness evidence, not a worldgen PASS. PID is informational;
  the supervisor controls only the Popen child that it actually created.
- A 180-second no-progress limit distinguishes `startup_stalled` from `stalled`.
  Only a newly advanced observation count resets that limit. Log spam, file
  timestamps and repeatedly rewriting the same report do not. The original
  overall timeout is still enforced independently.
- Stop is requested normally first, with the existing 90-second grace. Failure
  to stop escalates to terminate/kill with bounded waits, is recorded as forced,
  and cannot pass the runner. No automatic retry loop is introduced.
- Malformed/disappearing/regressing reports, spawn failure, early exit and
  interruption have explicit outcomes. A previous report or log is never reused
  as this process's result. A bounded log tail is retained with diagnostics.
- Post-run verification failures still produce failing run evidence when the
  destination remains writable, rather than losing results through an exception.

The exposed options are `--heartbeat-seconds` (default 15), `--stall-timeout`
(default 180), and `--check-only`. The public CLI bounds remain finite. A slow
startup can use an explicitly longer stall limit without changing the worldgen
checks. A stall outcome is NOT a successful run even after a clean process exit.

## Preflight without starting a world

Append `--check-only` to the existing start or resume command. All required input
and checkpoint checks run, but Java is not started, no new world is created, and
old evidence is not moved. The R13 exact-1599 coverage adapter inherits this option
through the common runner. Ordinary plans remain limited to 512 chunks; the
pinned broad adapter is still required for the original 1599 coordinates.

Resume additionally verifies the saved block snapshot bytes, state dictionary,
plan/seed correspondence, exact classpath manifest and fixed JVM flags before
moving any evidence. Previous supervisor diagnostics are archived along with the
existing checkpoint reports. Existing metadata, normal-stop and session-lock
checks remain. Runtime changes or a different generator profile are not migrated.

A partial stalled or forcibly stopped run is not silently resumable. The existing
resume modes still require a clean CARVERS checkpoint or a completed FULL readback
checkpoint. Snapshot-only review archives are not complete saved Minecraft worlds.
Do not manufacture a checkpoint from them or remove a fingerprint/worldgen lock.

## Validation scope

The new regression suite has 34 tests. Child-process scenarios use actual short-
lived Python processes, not mocked Minecraft success. Checkpoint preflight tests
use synthetic fixtures and assert no mutation or process launch for check-only.
The suite includes no-report startup, stalled progress, log spam, total timeout,
malformed/failed reports, child exit, refused normal stop, stale evidence, missing
executable, altered checkpoint inputs and post-run verification failure.

The unchanged 37 stage-comparison tests and 25 R13 reconciliation tests also pass
locally. The dedicated CI reruns these plus the exact original-coverage contracts.
Consult its logs for the final result; a workflow definition is not a passed run.
No Minecraft world, large-area equality result, fluid simulation or JAR is produced
by these tests. The previously compiled R13 generator remains a separate artifact.
