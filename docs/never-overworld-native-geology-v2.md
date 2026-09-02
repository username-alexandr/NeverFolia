# NeverOverworld native geology v2

NR-DEV-1 native ore geology derives mineral provinces and vein segments from world seed, absolute coarse-cell coordinates and per-ore salts. Every chunk evaluates geometrically relevant candidates independently and clips reads/writes to its own `ChunkAccess`.

The v2 promotion target contains coal, iron, copper, gold, redstone, lapis, diamond and emerald. Legacy TEST1 `deep_ore_*` count/height placed features are removed from the generated Core pack after native promotion; `deep_tuff` remains temporarily as a material layer until native host-rock geology replaces it.

The transition is intentionally staged: baseline native geology first proves compilation/runtime/determinism, then the Core pack removes legacy ore placements. This avoids conflating a generator regression with a datapack migration regression.
