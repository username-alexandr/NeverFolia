# BUG01: decoration proposal outside the 41-section roof512 world

Baseline runtime: b4ac445d7495fb4d7189111ae8f8e42428a4a798.
The reported FEATURES failure reaches NeverNetherSubstrateR10.section through
NaturalPolicyR13.proposeFlora and the flora view commit. The exact exception is
ArrayIndexOutOfBoundsException: Index 41 out of bounds for length 41.

WorldGenRegion.ensureCanWrite checks the horizontal dependency/write zone; for
non-retrogen chunks it is not a vertical bounds guard. Original substrate reads
return air above Y527, and the flora planner previously queued writes there.
Commit then looked up section 41 before the later Level/worldgen roof guard ran.

Apply scripts/apply-never-nether-bug01-bounds.py AFTER the exact R14 chain.
It changes three generated Nether sources only: proposal entries reject Y<-128
and Y>=512 before lookups, the flora view rejects these writes before queueing,
and natural-flora commit checks before substrate reads. A private section-array
invariant remains fail-closed for inconsistent inputs. No catch-and-ignore,
index clamping, extra sections, terrain fill or metadata reset is introduced.

The roof stays BEDROCK at Y512. Both datapacks, the storage profile, height lock,
worldgen fingerprint and ordinary Overworld behavior are unchanged. Existing
R14 formats remain compatible, but a world interrupted by a chunk-system crash
must be backed up and tested on a copy; this patch is not repair of prior damage.

Native smoke supports --expect-bug against the unmodified TEST1 runtime and
reproduces the exact exception with an actual 41-section ProtoChunk. World access
is an explicit proxy fixture, not a simulated claim of live generation. Without
that option it checks invalid extremes and padding, all valid Y coordinates,
flags, recursion limits, private planner queueing and unchanged metadata on
refusal. Missing chunks/substrate still raise errors. Separate real-world and
packaged-JAR checks must be stated with their exact scope.
