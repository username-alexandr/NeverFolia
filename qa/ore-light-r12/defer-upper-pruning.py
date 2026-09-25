#!/usr/bin/env python3
"""Defer upper-resource pruning to the existing neighbour-complete LIGHT barrier.

The legacy FEATURES entry point is kept but inert so exact Nether installers
retain their inspected ChunkStatusTasks input. Deep pruning, salts, percentages,
world data and datapacks are not changed. Install AFTER FIELD-R12.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

JAVA=Path('folia-server/src/minecraft/java/net/minecraft/world/level/chunk')
CONTRACTS = {'NeverOverworldOreExposurePruner.java': {'before': 'f92b3b6114b5b4d31e5a351fd19ea7600438179f160ea8b4357c48aadffe7f40', 'after': 'a85df34023066b6a9dfc15223e895a878f7ee4e05e706d396244079879544d33'}, 'NeverOverworldFlood.java': {'before': 'ea62519b643b651b00f5ecbfa63fba85b9b184d8b07e979e54454962256d4532', 'after': 'e53f50c7894e8e5f86f5237cdc20da08a83efc002e312313c12da60e3301017e'}}
RULES = {'NeverOverworldOreExposurePruner.java': [['import net.minecraft.world.level.Level;', 'import net.minecraft.world.level.Level;\nimport net.minecraft.world.level.WorldGenLevel;\nimport net.minecraft.world.level.chunk.status.ChunkStatus;', 1], ['        prune(level, chunk, DEEP_MIN_Y, DEEP_MAX_Y, true);', '        prune(level.getSeed(), chunk, DEEP_MIN_Y, DEEP_MAX_Y, true);', 1], ['    public static void applyAfterFeatures(final ServerLevel level, final ChunkAccess chunk) {\n        if (!isNeverOverworld(level)) return;\n        prune(level, chunk, UPPER_MIN_Y, UPPER_MAX_Y, false);\n    }\n', '    /** Compatibility entry point retained for the exact Nether source chain.\n     * Neighbour FEATURES may still write into this chunk here. Do not free ore\n     * host blocks or prune an incomplete input; the LIGHT barrier is authoritative.\n     */\n    public static void applyAfterFeatures(final ServerLevel level, final ChunkAccess chunk) {\n        // ORE-LIGHT-R12: intentionally deferred, including all old callers.\n    }\n\n    public static void applyAtLight(final WorldGenLevel level, final ChunkAccess chunk) {\n        if (!isNeverOverworld(level.getLevel())) return;\n        pruneUpperAtLight(level.getSeed(), chunk);\n    }\n\n    static void pruneUpperAtLight(final long seed, final ChunkAccess chunk) {\n        if (chunk.getMinY() != -512 || chunk.getHeight() != 1024\n            || chunk.getPersistedStatus().isBefore(ChunkStatus.INITIALIZE_LIGHT)\n            || chunk.getPersistedStatus().isOrAfter(ChunkStatus.FULL)) {\n            throw new IllegalStateException("Upper ore pruning requires the new-chunk LIGHT barrier");\n        }\n        prune(seed, chunk, UPPER_MIN_Y, UPPER_MAX_Y, false);\n    }\n', 1], ['    private static void prune(\n        final ServerLevel level,', '    private static void prune(\n        final long seed,', 1], ['retain(level.getSeed(), x, y, z, profile, retainPercent, salt)', 'retain(seed, x, y, z, profile, retainPercent, salt)', 1], [' * FEATURES, so a second pass runs after biome decoration. The latter both', ' * FEATURES, so upper pruning waits for all contributing neighbour FEATURES\n * at the pre-FULL LIGHT barrier. The latter both', 1]], 'NeverOverworldFlood.java': [['        removeUpperLapisDiamondAfterNeighbourFeatures(chunk);', '        // ORE-LIGHT-R12: prune only the complete neighbour-decorated substrate.\n        NeverOverworldOreExposurePruner.applyAtLight(level, chunk);\n        removeUpperLapisDiamondAfterNeighbourFeatures(chunk);', 1]]}

def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def patch(name, text):
    contract=CONTRACTS[name]
    if digest(text)==contract['after']:
        return text
    if digest(text)!=contract['before']:
        raise ValueError('Uninspected ORE-LIGHT-R12 input: '+name)
    for before, after, count in RULES[name]:
        if text.count(before)!=count:
            raise ValueError('ORE-LIGHT-R12 anchor changed: '+name)
        text=text.replace(before,after)
    if digest(text)!=contract['after']:
        raise ValueError('ORE-LIGHT-R12 output contract mismatch: '+name)
    return text


def prepare(folia):
    # Validate all inputs before writing either file.
    return {folia/JAVA/name:patch(name,(folia/JAVA/name).read_text(encoding='utf-8'))
            for name in CONTRACTS}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folia',type=Path)
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    staged=prepare(args.folia.resolve())
    if not args.check_only:
        for path,text in staged.items():path.write_text(text,encoding='utf-8')
    print('[ORE-LIGHT-R12] upper pruning deferred; old percentages/salts preserved; '
          + ('preflight only' if args.check_only else 'two files installed'))


if __name__=='__main__':main()
