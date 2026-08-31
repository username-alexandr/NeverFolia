# NeverNether native density architecture

Branch: `feature/never-nether-worldgen`
Status: implementation design baseline
Worldgen version: `NN-DEV-1`

## Purpose

NeverNether terrain generation is implemented as a NeverFolia-owned deterministic density system. It must satisfy the approved geometry and gameplay profile without relying on copied third-party density-function code.

## Vertical contract

- Technical dimension minimum Y: **-128**.
- Technical dimension height: **1024**.
- Generated terrain body: **Y=-128..383** (512 blocks).
- Roof construction zone: **Y=384..895** (512 blocks).
- Primary lava sea reference: **Y=32**.
- Vanilla-style irregular lower and upper bedrock thickness/profile are preserved relative to the generated terrain body's boundaries.

Approved overlapping terrain bands:

- Deep Nether: `Y=-120..-32`
- Lower / Lava: `Y=-32..96`
- Main Nether: `Y=64..260`
- Upper Nether: `Y=220..376`

Bands are weighting functions, not literal stacked layers.

## Density graph

The native NeverNether density graph is composed from independent deterministic fields. Conceptually:

`final_density = boundary_guard(base_mass + terrain_shape + hanging_mass - cavern_void - tunnel_void - chasm_void - magma_void)`

The exact implementation may use Minecraft density-function primitives and/or NeverFolia bootstrap registrations, but each component has a stable logical identity and independent salt/version.

### 1. Base mass field

Responsibilities:

- maintain coherent large netherrack terrain masses;
- provide large-scale ridges, shelves, cliffs and vertical variation;
- support the balanced overall openness target;
- increase rock density near the lower/upper bedrock boundaries;
- avoid repeated chunk-scale blobs.

The base field uses low-frequency 3D components combined with vertical bias curves. It is not created by stretching a 256-block Nether profile by a fixed factor.

### 2. Band openness field

A smooth vertical weighting field controls the void budget:

- Deep: denser than average;
- Lower/Lava: most open;
- Main: balanced;
- Upper: balanced-open, with density increasing again near the roof.

Band transitions must overlap smoothly over tens of blocks.

### 3. Mega-cavern field

Approved geometry:

- width: `180–450` blocks;
- height: `90–220` blocks;
- length: `300–900+` blocks;
- regional target: roughly one major cavern region per `900–1500` blocks before rejection/merging.

Weighting:

- highest in Lower/Lava;
- moderate in Main;
- moderate-low in Upper;
- lowest in Deep.

Mega-cavern regions are selected from low-frequency regional fields so their classification can be sampled without generating neighbor chunks.

### 4. Secondary cave fields

Small tunnels:

- width `4–12`;
- height `4–10`;
- relatively common, especially in Deep/Main.

Medium caves:

- width `15–45`;
- height `10–30`;
- length `50–180`.

Large ordinary caverns:

- width `45–120`;
- height `25–70`;
- length `100–350`.

These fields provide connectivity and local variation but must not generate excessive spaghetti networks.

### 5. Vertical chasm field

Ordinary chasms:

- width `20–60`;
- vertical extent `80–220`.

Large chasms:

- width `60–140`;
- vertical extent `180–400`;
- distinctly rarer.

Chasms use vertically elongated regional fields with irregular wall modulation and may connect Upper→Main, Main→Lower/Lava, and exceptionally toward Deep.

### 6. Hanging mass field

Approved horizontal scale:

- small `30–80`;
- medium `80–180`;
- large `180–350`;
- very large up to `500`, rare.

Weighting:

- strongest in Upper;
- moderate in Main;
- low in Lower/Lava;
- nearly absent in Deep.

The field adds density back into open cavern volumes to form suspended shelves, islands, arches and ceiling-attached masses.

### 7. Deep magma chamber field

Approved geometry:

- ordinary: `60–140` wide, `30–80` high;
- large: `140–300` wide, `60–140` high;
- giant: `300–500+` wide, up to `180` high, rare.

Primary weighting is Deep Nether, with secondary overlap into Lower/Lava. This field carves chamber volume; a separate fluid/material realization stage determines lava filling, shelves, islands and basaltic character.

### 8. Boundary guard

Boundary rules are absolute correctness requirements:

- cave/void fields may not perforate the lower bedrock boundary;
- terrain/features may not leak through the upper bedrock roof into `Y=384..895`;
- upper density rises smoothly toward the generated-body roof before bedrock surface rules are applied;
- bedrock thickness keeps the vanilla-style irregular profile rather than becoming a uniform slab.

## Lava model

The primary lava sea level is fixed at `Y=32`.

NeverNether additionally supports bounded deterministic deep basins, isolated lakes and lava falls. These are not a second global aquifer. The terrain density system exposes basin/chamber classifications that the fluid realization stage may consume.

## Determinism contract

For a fixed Nether seed, worldgen version and configuration fingerprint:

- terrain is independent of chunk generation order;
- terrain is independent of Folia region/thread scheduling;
- no shared mutable random source may affect results;
- every regional feature field derives randomness only from stable salts + coordinates + seed;
- pregeneration and player exploration must produce byte-equivalent terrain decisions for the same chunk.

## Performance contract

- Regional feature classification must be computable from coordinates without neighbor chunk generation.
- No synchronous search for a better nearby cavern/structure location.
- Expensive high-frequency detail is evaluated only after coarse regional masks indicate relevance.
- The system must remain usable with 20–30 concurrent chunk-generating explorers on the target server profile.

## Diagnostics

Worldgen Inspector should eventually expose at a coordinate/chunk:

- active vertical band weights;
- base density/openness class;
- mega-cavern region id and class;
- secondary cave weights;
- vertical chasm class;
- hanging-mass class;
- magma-chamber class;
- lava-body class;
- upper/lower boundary guard contribution;
- final worldgen fingerprint.

## Implementation order

1. Register/author the native 512-block Nether noise settings and dimension vertical contract.
2. Implement boundary guard + base mass + band openness.
3. Add mega-cavern field.
4. Add secondary cave fields.
5. Add chasm field.
6. Add hanging-mass field.
7. Add magma-chamber and fluid classification fields.
8. Apply biome surface/detail layer.
9. Integrate structure terrain predicates and placement registry.
10. Run deterministic multi-order seed tests and visual DEV seed inspection before promotion from `NN-DEV-1`.
