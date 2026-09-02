# NeverOverworld native structures — NR-DEV-1

This document describes the native placement contract reserved for the extended NeverOverworld (`Y=-512..511`).

## Placement model

Structure candidate coordinates are derived from the world seed, placement-group salt and absolute chunk coordinates. Candidate rejection must never search nearby chunks, synchronously load neighboring chunks, or write outside the owning generation chunk/structure start lifecycle.

The upper vanilla Overworld remains compatible with vanilla 26.2 structure placement. Deep extensions are allowed only inside the custom deep domain and are validated independently.

## Deep vanilla extensions

- Mineshafts may receive a deep placement profile in `Y=-448..-112`, with a solid-rock thickness requirement and rejection of surface-connected flood volumes.
- Trial Chambers may receive a deep placement profile in `Y=-320..-96`, requiring stable floor support, sufficient rock cover and no open-chasm/flood intersection.
- Ancient Cities keep their vanilla rules and are not extended into the lowest deep geology in v1.

## NeverFolia structure groups

`deep_major` contains large dungeons/landmarks with strong exclusion spacing. `deep_medium` contains exploration structures such as collapsed mines and vaults. `deep_ambient` contains smaller caches and camps.

The initial reserved IDs are intentionally native `neverfolia:*` registry IDs. They define placement contracts before structure templates are committed; no placeholder structure is considered enabled until its template/structure implementation is present and validated.

## Terrain checks

Native placement may use deterministic absolute-coordinate noise and data already owned by the candidate chunk. Relevant profiles can require rock shell thickness, floor support, cavern headroom, water contact, or rejection of surface-connected flood volume. No check may depend on mutable generation order in a neighboring chunk.

## Fast locate

The native locate path searches the deterministic candidate grid first and does not generate chunks. Terrain prechecks use seed/absolute-noise data. Exact verification may inspect already-generated data; generating new chunks merely to satisfy `/locate` is forbidden by the NR-DEV-1 contract.
