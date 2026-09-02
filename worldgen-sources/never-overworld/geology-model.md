# NeverOverworld Geology Model

## Target

Replace count-based ore features with deterministic geological provinces.

## Model

seed + absolute coordinates + salt

-> geological province

-> host rock

-> mineralization field

-> vein / lens / layer

## Folia constraints

- each chunk calculates only its owned blocks
- no neighbour chunk loading
- no shared mutable state
- deterministic hash validation required

## Initial deposits

- iron formations
- copper zones
- gold regions
- redstone layers
- lapis pockets
- diamond deep zones
