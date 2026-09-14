# R13 original-1599 FULL observation and diagnostic Paperclip

**Development result: equality BLOCKED; not a release.**
Base `9bbd5d3cfcca180669a77de47f42112de187d086`.
Generator implementation remains R13 (`5c00ef2...`); this stage changes only QA,
packaging and documentation. The normal production entry point is unchanged.

## The actual end state

Two NEW independent FULL-only test worlds completed, stopped normally and passed
content loading checks. Each requests the exact original R7 1,599 coordinate
pairs at seed 7270913 and then repeats a final read. Every snapshot requires
FULL status, owning-region execution, frozen simulation and coherent section
copies. Identity is checked before and after each process. No fluid/air/plant
normalization is used over Y=-128..895: 419,168,256 block states per phase.

- Both `full` and `settled`: **3,813 differing blocks in 56 chunks**.
- Within either run, `full` to `settled`: **zero changes**.
- Independent saved Anvil comparison: the same 56 chunks have block differences;
  no differences in sampled biomes, layout-normalized structure starts,
  heightmaps or block-entity NBT. This is not equality of the whole .mca file.
- 1,599 final metadata observations (102,336 section records) are checked;
  the same 56 chunks have differing blocks and substrate metadata.
- All 20 approved structure starts exist in saved FULL chunks. Their piece-layout
  hashes match in both worlds, selected bounding boxes meet the body-height
  rules, quota checks pass and footprints lie in the pinned plan. This does NOT
  establish traversal or all joins/supports. The R4 Donjon gallery is absent.

Main state pairs, combining directions where noted: blackstone/air 1,730;
basalt/source lava 897; netherrack/source lava 228 in one observed direction.
In all 3,813 residual cells the saved original substrate is the same. At least
one side marks each residual as an external write (2,274 reverse-only, 1,500
forward-only, 39 both). External means outside the tracked proposal system,
not necessarily a plugin. It does not identify the writer or prove a root cause.
The CSV keeps every differing coordinate and both exact states and metadata.
No proposal filtering or protection weakening has been made to obtain a pass.

## Failed earlier stage probes are not reclassified as successful

One forward CARVERS/LIGHT/settled run completed. Its first reverse attempt
failed `Status changed during immutable capture`, then exited -9 during saving;
the environment recorded one OOM kill. Heavy offline region analysis was running
at that time. A repeat in a NEW world with the same inputs and checks also failed
the capture guard, but stopped normally with exit 0. Neither is accepted evidence.
No more repeats of that protocol were attempted.

The FULL-only protocol is explicitly different: `NN-FULL-R13`, with 3,198 FULL
requests and no claim of pre-FULL observation. The untouched original comparator
rejects it. Thus the old three-stage equality gate has NO valid paired result;
FULL-only equality has an actual failing result. These are not interchangeable.

## Real diagnostic server JAR

Paperclip CI run **34871586469**, commit **905363c**, completed successfully.
It compiles the full normal transformer chain plus optional R8-R13, packages the
actual Paperclip JAR and starts that JAR on a fresh loopback-only Core test world.
Readiness, normal save and exit 0 were observed. CI does NOT include the external
structure pack or this 1,599-chunk run. The packaged JAR is separate from the
classpath runtime used in the large world probes.

The first packaging attempt rejected a moving Folia branch before compilation.
The diagnostic bootstrap now pins inspected upstream
`14b7fee5c866fca9a40ede4a58998fb928140f65` before branding and pre-apply changes.
The next build compiled successfully, but its exporter mistakenly matched both
the actual Paperclip and intermediate bundler. The final exporter selects the
`folia-paperclip-*.jar` task output and verifies the runnable manifest and archive.
Normal upstream preparation policy is not changed by this diagnostic wrapper.

JAR SHA-256:
`67de8a381187f05d1748711b52f9bffbe45195027a93ccfcf0dc790eebf0d6da`.
CI artifact outer SHA-256:
`70859d8609354cb99c23389f1695799f5d254b153bb511dac408bf1d391b808c`.
All inner checksums were verified. A full 20-structure data pack is separately
built from the user's pinned archives; it includes Core, so never enable both
Core and full integration packs at once. Third-party NBT is not committed here.

## Reproducibility and remaining work

The independent protocol has **22 local synthetic regression tests**. The Java
observer was compiled again from the source being published and its class bytes
matched the measured plugin. These tests are not Minecraft gameplay acceptance.
Detailed run, input, runtime and evidence hashes are in the adjacent JSON report.
See `qa/nevernether-r13/FULL-ONLY.md` for commands; process supervision is bounded.

Remaining: identify the actual external writers responsible for residual block
placement, repair coherent pre-FULL capture rather than waive its checks, test
multiple seeds, fluid simulation, natural support geometry, dungeon traversal,
original user screenshot locations and long-lived storage/resource use.
Only separate NEW disposable worlds may use the diagnostic binary. Do not
upgrade an existing user world, remove fingerprint locks or promote to release.
