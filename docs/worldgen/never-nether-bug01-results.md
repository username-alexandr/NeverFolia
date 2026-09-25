# BUG01: roof512 out-of-height flora section access

Hotfix binary/source: `56134a4b93d6e277dca6edac49efd674a83622f1`.
Baseline binary: `b4ac445d7495fb4d7189111ae8f8e42428a4a798`.
Native CI run `35010020610`: SUCCESS, full-chain compilation, native regressions,
Paperclip packaging and packaged Core startup.

## Diagnosis and fix

The reported FEATURES task failed in Nether chunk (-195,-393) with
`ArrayIndexOutOfBoundsException: Index 41 out of bounds for length 41`, through
SubstrateR10.section/proposeBlock, NaturalPolicyR13.proposeFlora and FloraCandidateR8.View.commit.
The log does not give the proposed Y or world seed. The API regression reproduces
the exact old exception at Y528 using a real 41-section ProtoChunk and an explicitly
proxied WorldGenLevel. This is a native API reproduction, not the user's saved world.

ensureCanWrite alone was not a sufficient vertical check. The hotfix rejects
proposals below -128 or at/above the protected roof512 before a chunk lookup,
rejects them before flora queueing and before natural-policy substrate reads,
and verifies the private section-array invariant. No catch-and-ignore, clamping,
array expansion, missing-substrate fallback or world repair is introduced.
Both data packs, storage profile, height locks and Overworld behavior are unchanged.

## Measured tests

- 12 patch-transform tests, 23 existing height-pack and 13 height-hook tests pass in CI.
- 2697 BUG01 native assertions and 194 existing height/registry/profile checks pass.
- Three new-JAR processes use actual java -jar and BOTH unchanged full data packs:
  forward, reverse and a new-JVM readback of a copy of the normally stopped forward world.
- Two old-JAR processes generate the same selected square for baseline comparison.
- All five stop normally with exit 0; startup content checks pass; roof/padding checks pass.
- Selected area: seed 7270913, X=-197..-193 and Z=-395..-391 (25 chunks), all block
  states Y=-128..527, frozen simulation, complete FULL and settled observations.
- The natural baseline does NOT reproduce the user's crash on this bounded default-seed
  square. Exact user-world reproduction remains unestablished without its seed/data.
- Forward versus reverse has 1014 block differences in 3 chunks in BOTH binaries.
  Same-order old versus new has ZERO block and metadata differences in either order.
  Therefore these observed order differences are inherited, not a passed equality gate.
- New-JVM readback has ZERO block and metadata differences against the original settled output.

This hotfix addresses the section-index crash, not general worldgen determinism,
fluid simulation, client behavior, memory use or damage from the earlier crash.

## Distribution identity

JAR SHA256: `1badc2f46732157a39ed325cbfcecf03cd64e5583dc384c0094324c51ffa7262`.
CI artifact SHA256: `c3bd2746d8879cf9d5f6bfe5f971ad2d265d7c6ac10ba4a155ada3473788cfe0`.
Outer archive, internal checksums and shipped JAR identity were verified locally.
Overworld pack SHA256: `e00a7cd8df167e4a1a9ead3ef265da20369d754c01cc04529d4094bd05422338`.
Nether pack SHA256: `d7f9757c9358f9229e2900d1864852b221010fb17fbae31eb5771fd136be6654`.

The UPDATE archive contains server.jar plus revised BUILD-INFO.json and
binaries.sha256, with README/report/checksums. Applying it to a copy of the previous
FULL TEST1 kit changed only those three pre-existing files; both packs and default
configuration remained byte-identical. No QA plugin, world, Java or Mojang bootstrap
is shipped. Back up the test server and first check a copy after a crash. Do not
remove locks or region files. This is not an old-profile migration or production release.
