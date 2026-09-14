# Independent R13 FULL-only observation

This is **not a successful replacement result for the CARVERS/LIGHT protocol**.
The old observer/comparator and their rejection checks are unchanged. This probe
is named `NN-FULL-R13`, explicitly requests all 1,599 original R7 chunks at FULL,
then re-observes them at FULL. It accepts only the pinned seed/coordinate set.

Run only in a new loopback-only disposable test world with the exact R13 runtime
and matching complete datapack. Do not install the QA plugin on a live world,
remove a worldgen lock, infer original terrain from decorated chunks, or resume a
failed run as though it were a clean checkpoint.

`NeverNetherFullProbeR13.java` requires the owning region thread, frozen simulation,
FULL status, exact coordinates/bounds and coherent detached section copies. It
records block snapshots and all 64 section metadata records at both `full` and
`settled`. Its plugin name/folder stays `NN-STAGE-R8-QA` solely for compatibility
with the existing bounded supervisor; the JSON protocol name is different.

## Compile and run

With Java 25 and the exact full runtime classpath, compile the published source
into a NEW temporary classes directory. Copy `full-plugin.yml` to `plugin.yml`
inside that directory and package only those probe classes/resources into a JAR:

```sh
javac -cp "$EXACT_R13_CLASSPATH" -d /new/qa-classes \
  qa/nevernether-r13/NeverNetherFullProbeR13.java
cp qa/nevernether-r13/full-plugin.yml /new/qa-classes/plugin.yml
jar --create --file /new/full1599-qa.jar -C /new/qa-classes .
python3 qa/nevernether-r13/broad1599.py plan > /plans/original1599.json
```

Use `broad1599.py run` and its existing `--java`, `--runtime-dir`, `--pack`,
`--qa-plugin`, `--new-directory`, `--plan`, `--accept-eula` arguments. Review the
Minecraft EULA before giving explicit acknowledgement. `--check-only` checks
inputs without launching a world. `--reverse` reverses the same original sequence.
Run ONE server at a time. Do not run memory-heavy region analysis while it is alive.
Use the same runtime, Java, flags, pack and probe JAR for both worlds.

After BOTH processes stop normally, independently run the content-startup
validator using their actual exit codes. Then compare:

```sh
python3 qa/nevernether-r13/compare-full1599.py \
  --left /worlds/forward --right /worlds/reverse --output /reports/full.json
python3 scripts/compare-never-nether-persisted-r7.py \
  --left /worlds/forward/world/dimensions/minecraft/the_nether/region \
  --right /worlds/reverse/world/dimensions/minecraft/the_nether/region \
  --plan /plans/original1599.json --output /reports/persisted.json
python3 scripts/compare-never-nether-metadata-r11.py \
  --left-observations /worlds/forward/plugins/NN-STAGE-R8-QA \
  --right-observations /worlds/reverse/plugins/NN-STAGE-R8-QA \
  --phase settled --profile r13 --output /reports/metadata.json
```

The FULL-only comparator records first-to-settled changes, checks every block
state including fluid levels/air/plants/roof space, and rejects incomplete or
mismatched identities. Metadata contents and actual saved region data are separate
checks, not inferred from matching snapshot hashes. A nonzero mismatch result is
not a pass. `release_ready` stays false. Natural starts can additionally be audited
with `inspect-saved-starts.py`; a saved piece is not necessarily a room, and finding
all starts does not establish traversal, joins, entity behavior or fluid stability.

`test-never-nether-full-r13.py` tests synthetic evidence and source guards. It does
not generate Minecraft worlds. Real comparisons must be reported separately,
including every invalid preliminary attempt. Do not repeatedly rerun a failing
capture until a desired result appears, and do not weaken the old stage checks.
