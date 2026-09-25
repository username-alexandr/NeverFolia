# R14: verified exact Y512 roof and bounded saved-world checks

**Height requirement verified on the recorded samples; full release acceptance remains blocked.**
Native code: `d6f90e9908c6ee064706007ee7d8f98754eb4cf9`.
Observer and source contracts: `da2d3ba0941d1d18ec2b21f0fc74c6ba1ad9e3ef`.
This document adds results only, not a generator change or a new native build.

## Exact interpretation

The upper bedrock block is at **Y=512**, not 511. The previous buildable roof zone is removed.
Writes of non-air blocks above Y512 are refused by the checked native mutation paths;
replacing the roof block with another material or air is refused too. Construction below
the roof remains available. The lower bound remains Y=-128 and the lava plane Y=32.

Technical storage is 656 blocks / 41 sections, Y=-128..527. Y=513..527 is empty,
non-buildable padding needed to include the Y512 block in a complete section. It is
not another player building area. Profile: `NN-R14-SUBSTRATE-1-ROOF512`. Existing
R13 worlds are not migrated and no fingerprint/height lock is removed or bypassed.

## Actual completed runs with the full twenty-structure pack

The unmodified full R14 classpath runtime from CI was used, not locally substituted
native classes. The same Java executable, runtime, pack, probe and flags were hashed
before and after each accepted process. Simulation was frozen before selected chunks.

- Boundary world: four chunks, **248 real API checks**, zero failures. Level, Chunk,
  Section and Bukkit writes at/above the roof were tested, as well as the inside/outside
  height complement and placing/restoring a block below the roof. These are actual
  server API operations, not a Minecraft client packet session.
- Seed **7270913**, 81 chunks X=-218..-210 / Z=-48..-40: forward/reverse FULL and
  settled snapshots have **zero different blocks and identical metadata bytes**.
- Seed **123456789**, 25 chunks X=-216..-212 / Z=-46..-42: the same zero-difference
  result. Neither block states nor air, fluids, plants or technical padding are filtered.
- A true additional JVM process reloaded the first seed's 81 saved FULL chunks:
  **zero different blocks, identical metadata bytes, roof and padding valid**.
- All six accepted processes reached readiness, passed content startup checks,
  saved and exited 0 without forced stopping. Offline Mojang key-request errors
  remain recorded separately, not hidden as content fixes.

After Java stopped, an independent audit read real saved Anvil data for 81 + 25
chunks. It validated **4,346 section records**, **27,136 roof cells** and **407,040
padding cells**. Roof512 was bedrock, padding was air, canonical metadata digests,
current-block hashes and provenance invariants passed with no failures. These are
106 selected saved chunks across two seeds, not a whole-world scan.

The full pack retains all twenty approved definitions. **1,032 NBT template
payloads are byte-identical to the R13 input**. Finding templates/clean startup is
not a new twenty-dungeon natural-placement or traversal acceptance result.

## Large test failed and is excluded

The exact original **1,599-chunk** forward plan was attempted with the recorded
`-Xmx2304M` diagnostic heap. After **1,281 observations**, Java reported
`OutOfMemoryError: Java heap space`; errors also occurred while saving. Normal
stop was attempted, then the bounded supervisor forced termination. Exit **-9**,
`forced_stop=true`, elapsed **566.058 seconds**. No broad reverse comparison was
accepted, no partial output was called PASS, and this world was not resumed.

This is Java heap exhaustion, not evidence identifying a retained-memory leak.
The all-object histogram includes potentially collectable objects and cannot by
itself establish the cause. Memory/lifecycle work and a completed large test remain
release gates. Earlier R12/R13 results are not attributed to the new height profile.

## Builds, checks and runnable artifact

Native CI **34925794611** succeeded at d6f90e9: full-chain compilation, **194 native
height/registry/filesystem checks**, Paperclip packaging and packaged-JAR startup
with matching **Core only**, followed by normal save and exit 0. The large/full-pack
local tests use its classpath export; they are not claimed as packaged-JAR tests.

Observation CI **34927896531** succeeded at da2d3ba. **98 Python tests** passed both
locally and in the corresponding CI suites (23 pack, 13 hooks, 24 observer, 17 restart,
21 saved-region contracts). All outer artifact hashes and inner checksums were
verified. The 73 relevant native/build source files match between the CI-native and
observer revisions. Recompiling the published observer produced the exact same
class bytes as the probe used in all recorded runs.

JAR SHA-256: `56ad309f152302497f343274772c6aaa69eb210db97aadaf2b06b611fe6e2f94`.
Full R14 pack SHA-256: `d7f9757c9358f9229e2900d1864852b221010fb17fbae31eb5771fd136be6654`.
Full pack content fingerprint: `b2feb1911583c58b6ded351c767b45aa53b645fed831fab84370a35caebc908f`.
The full pack includes Core; never enable both at once. Third-party NBT is not
committed with this result document.

Only NEW isolated test worlds may use the diagnostic JAR and matching R14 pack.
Still unaccepted: large-area completion/equality, dynamic fluids, falling-block
lifecycle and pistons, actual client placement/portal paths, every dungeon's
geometry/playability, original screenshot defects, Donjon gallery and long-lived
storage/performance. The normal production transformer entry point is unchanged.
