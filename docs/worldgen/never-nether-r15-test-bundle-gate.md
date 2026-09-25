# R15 field acceptance and Nether-only test bundle

The existing Java smoke, normal server stop, FULL-chunk and roof512 checks remain mandatory. The new gate additionally controls whether the current run can publish a test candidate. Runtime generation and native-lock validation code are not changed by this patch.

## Fixed evidence scope

`check-never-nether-r15-acceptance.py` requires the same seed `-2996952393010080672` and exactly 50 distinct saved chunks: two 5x5 areas centered on chunk `[-4,0]` and `[-195,-393]`. A changed area, missing data, truncated finding list, inconsistent counters, duplicate JSON keys or unknown body-cavity provenance cannot produce passing acceptance.

Mandatory results are 50 FULL chunks, 12,800 checked bedrock cells at Y=512, empty padding Y=513..527, normal stop, matching persisted R14 height and R15 native locks, zero hanging-source-lava shelf candidates, and zero original owner-contained micro-cavities intersecting Y=-128..506. A component crossing Y=506/507 is included in the body gate, not hidden in the roof category.

Owner-contained components wholly within Y=507..511 and components touching a chunk edge remain explicit diagnostics. This follows the existing R15 cleanup scope and does not assert that every reported cavity is a generator defect. Larger cavities and air created by known later writers are not reclassified as CARVERS-substrate defects.

## Publication

Only after every preceding build, smoke, pack verification, generation and acceptance step succeeds does CI upload `NeverFolia-R15-TEST-<source SHA>`.

The ZIP contains `server.jar`, its matching `datapacks/NeverNether.zip`, `ACCEPTANCE.json`, `BUILD-INFO.json`, a Russian setup note and `SHA256SUMS.txt`. It is created exclusively, not overwritten. The manifest records the exact source SHA, run ID, JAR and pack hashes and `production_ready=false`.

This is a **Nether-only disposable test-server bundle**, not an upgrade for an existing world and not a complete NeverFolia distribution. NeverOverworld/NeverEnd datapacks, multi-seed acceptance, multiplayer load testing and migration are outside this bundle's claim. No workflow removes or overwrites existing locks/regions. No staging/main promotion is included.

Failures still upload their diagnostics through the original `always()` artifact step, but never publish the accepted test bundle.

## Local verification

18 synthetic tests cover body/roof/chunk-edge classification, mixed-height cavities, lava regressions despite a green runtime summary, incomplete/truncated evidence, duplicate keys/chunks, malformed types, invalid saved locks, checksum verification and create-only ZIP publication.

The evaluator was also executed against the saved reports from `3bf4199` and `f80212e`. It accepts the former's reported field state and rejects the latter's remaining lava shelf and original body cavities. That replay verifies evaluator behavior only; it does not establish acceptance of a newly compiled JAR or replace its complete CI run.
