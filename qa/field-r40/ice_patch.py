#!/usr/bin/env python3
"""Exact-anchor scoped ice producer changes applied to pinned materialized sources."""
from pathlib import Path
import hashlib

ROOT='materialized/folia-server/src/minecraft/java/'
PREFIX='net/minecraft/world/level/'
HELPER='net.minecraft.world.level.chunk.NeverOverworldIceR40'
OCEAN='net.minecraft.world.level.chunk.NeverOverworldOceanR40'

def once(text,before,after):
    if text.count(before)!=1:raise ValueError('Ice source drift: '+before[:120])
    return text.replace(before,after,1)
def bounds(text,signature):
    if text.count(signature)!=1:raise ValueError('Ice method ambiguity: '+signature)
    a=text.index(signature);b=text.index('{',a);depth=1
    for i in range(b+1,len(text)):
        if text[i]=='{':depth+=1
        elif text[i]=='}':
            depth-=1
            if depth==0:return a,i+1
    raise ValueError('Unclosed ice method')

def patch_sources(archive,sources,hashes):
    names={
        'surface':PREFIX+'levelgen/SurfaceSystem',
        'iceberg':PREFIX+'levelgen/feature/IcebergFeature',
        'blue':PREFIX+'levelgen/feature/BlueIceFeature',
        'snow':PREFIX+'levelgen/feature/SnowAndFreezeFeature',
        'flood':PREFIX+'chunk/NeverOverworldFlood',
    }
    for name in names.values():
        raw=archive.read(ROOT+name+'.java');hashes[name]=hashlib.sha256(raw).hexdigest();sources[name]=raw.decode()
    name=names['surface'];text=sources[name]
    call='this.frozenOceanExtension(context.getMinSurfaceLevel(), surfaceBiome.value(), column, blockPos, blockX, blockZ, startingHeight);'
    text=once(text,call,'this.frozenOceanExtension(context.getMinSurfaceLevel(), surfaceBiome.value(), column, blockPos, blockX, blockZ, startingHeight, '+OCEAN+'.envelope(protoChunk) ? 128 : this.seaLevel);')
    a,b=bounds(text,'    private void frozenOceanExtension(');body=text[a:b]
    body=once(body,'        final int height\n','        final int height,\n        final int frozenSeaLevel\n')
    if body.count('this.seaLevel')!=6:raise ValueError('Unexpected frozen sea-level references')
    body=body.replace('this.seaLevel','frozenSeaLevel')
    body=once(body,'column.getBlock(y).isAir() && y < (int)extensionTop && random.nextDouble() > 0.01',
        'column.getBlock(y).isAir() && y < (int)extensionTop\n                    && (frozenSeaLevel == this.seaLevel || y >= frozenSeaLevel || extensionBottom != 0.0 && y > (int)extensionBottom)\n                    && random.nextDouble() > 0.01')
    sources[name]=text[:a]+body+text[b:]
    name=names['iceberg'];text=sources[name]
    text=once(text,'origin = new BlockPos(origin.getX(), context.chunkGenerator().getSeaLevel(), origin.getZ());',
        'origin = new BlockPos(origin.getX(), '+HELPER+'.sea(level, context.chunkGenerator().getSeaLevel()), origin.getZ());')
    text=once(text,'if (snowOnTop && !state.is(Blocks.WATER) && hDiff <=',
        'if (snowOnTop && !state.is(Blocks.WATER)\n                && !(level instanceof WorldGenLevel oceanLevel && '+HELPER+'.belowFutureSea(oceanLevel, pos.getY())) && hDiff <=')
    text=once(text,'return level.getBlockState(pos.below()).isAir();',
        'return level.getBlockState(pos.below()).isAir() && !'+HELPER+'.futureWater(level, pos.below());')
    sources[name]=text
    name=names['blue'];text=sources[name]
    text=once(text,'        RandomSource random = context.random();',
        '        RandomSource random = context.random();\n        if ('+HELPER+'.active(level)) origin = origin.offset(0, 128 - context.chunkGenerator().getSeaLevel(), 0);')
    text=once(text,'origin.getY() > level.getSeaLevel() - 1',
        'origin.getY() > '+HELPER+'.sea(level, level.getSeaLevel()) - 1')
    text=once(text,'if (!level.getBlockState(origin).is(Blocks.WATER) && !level.getBlockState(origin.below()).is(Blocks.WATER)) {',
        'if (!level.getBlockState(origin).is(Blocks.WATER) && !level.getBlockState(origin.below()).is(Blocks.WATER)\n            && !'+HELPER+'.futureWater(level, origin) && !'+HELPER+'.futureWater(level, origin.below())) {')
    sources[name]=text
    name=names['snow'];text=sources[name]
    text=once(text,'                int y = level.getHeight(Heightmap.Types.MOTION_BLOCKING, x, z);',
        '                int y = level.getHeight(Heightmap.Types.MOTION_BLOCKING, x, z);\n                // Old surface below the final ocean must not freeze before inundation.\n                if ('+HELPER+'.active(level) && y <= 128) continue;')
    sources[name]=text
    name=names['flood'];text=sources[name]
    text=once(text,'                    if (isDrownedFrozenOverlay(original)) {',
        '                    if (isDrownedFrozenOverlay(original)\n                        && !('+OCEAN+'.envelope(chunk) && '+HELPER+'.ice(original))) {')
    sources[name]=text
    light='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
    call='                    '+OCEAN+'.close(task.world, task.neverOverworldNeighbours, task.fromChunk);'
    sources[light]=once(sources[light],call,call+'\n                    '+HELPER+'.freezeSurface(task.world, task.fromChunk);')
    return sources
