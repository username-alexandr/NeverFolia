# NeverFolia NN TEST1 — packaged-JAR acceptance at roof Y512

**Ready for bounded player tests in separate NEW worlds; not production acceptance.**

Native binary commit: `b4ac445d7495fb4d7189111ae8f8e42428a4a798`.
Native CI: `34942618496`, successful full-chain compilation, native smoke and packaged Core startup.
The TEST1 distribution does not modify or recompile that binary. It renames the exact CI Paperclip to
`NeverFolia-26.2-NN-TEST1-ROOF512-b4ac445.jar` and combines it with the matching complete datapack,
launch scripts, an unaccepted-by-default EULA file, local-only server properties and verification results.
There are no third-party QA plugins, saved worlds, Java distribution or Mojang bootstrap JAR in the player kit.

## Exact binary and pack identity

- JAR SHA-256: `5c81d41f90b57d1de08dbd909a03cb8ba709c2db81ae198066a5ab5d2e78a06c`.
- Complete datapack SHA-256: `d7f9757c9358f9229e2900d1864852b221010fb17fbae31eb5771fd136be6654`.
- Native CI artifact SHA-256: `26c62a68353b1863e468a831bcb880992a98bb87a25b16911aa576953b176fd4`.
- Profile: `NN-R14-SUBSTRATE-1-ROOF512`.
- Lower bound -128; bedrock roof exactly 512; technical height 656 / 41 sections.
- Y513..527 is empty storage padding, not a buildable region.
- All 20 approved structure definitions are in the complete datapack, which already includes Core.

The b4ac445 binary includes the earlier fix for retiring a falling block whose above-roof placement
was refused with drops disabled. No new native behavior or memory fix is introduced by this acceptance stage.

## Actual runnable-JAR tests, not classpath substitution

Paperclip itself first patched and extracted its runtime using a separately pinned original Mojang
bootstrap. All resulting library/version files were checked against the embedded JAR manifests.
Every game process then used `java -jar`; no replacement Minecraft class directory or class overlay
was added. Runnable JAR, dependencies, datapack, Java executable, flags and observer identities were
recorded, and the relevant immutable files were checked again after each process.

Eight accepted game processes reached readiness, saved normally and exited 0:

1. Four-chunk mutation/boundary probe: **248 checks, zero boundary failures**.
2. Seed 7270913, 81 chunks, forward order.
3. The same 81 chunks in exact reverse order.
4. A real new JVM process reading the saved 81 forward chunks.
5. Seed 123456789, 25 chunks, forward order.
6. The same 25 chunks in exact reverse order.
7. A separate genuinely ticking entity/piston scenario: **15 checks passed**.
8. A fresh no-QA-plugin world launched by the actual distributed Linux start script with the complete datapack.

The two order comparisons have **zero block differences and byte-identical section metadata** in
both FULL and settled observations. The 81-chunk restart also has zero differences. Every block
state from Y=-128 through 527 is included; fluids, air variants and plant states are not normalized.
The frozen observation protocol does not claim post-generation fluid simulation acceptance.

Independent reads of the stopped Anvil files verified **106 FULL chunks, 4,346 section metadata
records, 27,136 roof cells and 407,040 padding cells**. The roof is bedrock and the padding is air.
These are new checks of the b4ac445 packaged-JAR worlds, not results transferred from d6f90e9 or R13.

The separate dynamic scenario verified that sand below the roof actually lands, both above-roof
falling-block drop modes retire, a free piston works below the roof, a roof-blocked piston does not
extend, and all physical roof/padding cells of the selected chunk remain valid. Actual
`ENTITY_TICKING`, owning-region execution and running—not frozen—simulation were checked.
This is not a connected-client test or coverage of every piston/fluid/portal mechanism.

### Preliminary harness failures are preserved

The first dynamic probe failed four falling-block assertions. A targeted diagnostic established
`BLOCK_TICKING`, not `ENTITY_TICKING`; all three falling entities had ticks_lived=0 and had not moved.
Those two preliminary runs remain failed evidence, not game passes. The accepted probe used a
temporary force-loaded ticket changed on the global region thread and checked ENTITY_TICKING before
accepting entity results. No server JAR change, direct manual entity tick or weakened roof assertion
was used to obtain the pass. The temporary ticket and the test entities were cleaned up.

## Launcher and source checks

- **98 current Python regression tests** passed locally.
- Native CI recorded **194 registry/profile/filesystem checks**.
- **Eight Linux launcher contract tests** passed, including refusal of Java21, unaccepted EULA,
  checksum changes, invalid heap settings, and injected Java options before invoking Java.
- The actual shipped Linux launcher then started the real JAR/full datapack with no QA plugin,
  reached Done, saved and exited 0. Its test startup validator passed.
- Windows/PowerShell scripts are provided but were not executed in this Linux environment.
  The explicit `java -jar` command is also documented.
- Startup-content validators distinguish isolated-environment Mojang key-fetch failures from
  content-loading errors. Such environment errors are retained, not silently claimed repaired.

The player kit defaults to localhost port 25596, online authentication, whitelist, Java25 and
2304 MiB heap. EULA is false until the operator explicitly accepts it. This heap setting is a
bounded-test profile, not a proven size for large pregeneration. There is no automatic restart loop.

## Remaining gates — do not promote this kit to production

The full 1599-chunk R14 generation/memory gate remains unaccepted. An earlier R14 build exhausted
heap at 2304 MiB; these bounded tests do not fix or disprove that limitation. The original screenshot
locations, general fluid/portal/client behavior, all dungeon joins/traversal, the dormant R4 Donjon
gallery and third-party plugin compatibility remain separate work. The presence of all 20 definitions
is not a new claim that all 20 natural starts were accepted at the new height.

Use only a separate new test world. Do not import an old Nether, delete fingerprint or height locks,
install the QA observer on a live server, or treat a successful bounded test as an old-world migration.
No production release or existing-world compatibility is asserted.

The delivered evidence includes the actual run logs, exact observer sources, failed-harness reports,
comparisons and checksums. The runnable binary remains the unchanged CI artifact at the SHA above.
