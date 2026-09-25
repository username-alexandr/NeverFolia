#!/usr/bin/env python3
"""Re-anchor ocean monuments to the NeverOverworld flood surface.

NeverOverworld intentionally keeps the vanilla noise-settings sea_level=63
while flooding surface-connected volume to Y=128. Therefore monument placement
cannot use ChunkGenerator#getSeaLevel as the NeverOverworld flood reference.
For the -512/1024 NeverOverworld height contract the monument base is Y=104
(128-24); ordinary dimensions retain their vanilla seaLevel-24 behavior.
Existing saved starts preserve their stored minY when regenerated.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

JAVA=Path('folia-server/src/minecraft/java')
STRUCT=Path('net/minecraft/world/level/levelgen/structure/structures/OceanMonumentStructure.java')
PIECES=Path('net/minecraft/world/level/levelgen/structure/structures/OceanMonumentPieces.java')
STRUCT_SHA='5a3f7706980899f2c3542bf5ba588d1c1ce56b0c55ed5dd74e802ee1033796da'
PIECES_SHA='9099ed9ce958626fcf9f377e2b0931d1aae1083df25b20e6b95d728a0874cb43'

def sha(s:str)->str:return hashlib.sha256(s.encode()).hexdigest()

def patch_struct(s:str)->str:
    if 'neverOverworldMonumentBaseY' in s:
        return s
    if sha(s)!=STRUCT_SHA: raise ValueError('OceanMonumentStructure source identity changed')
    old='''    private static StructurePiece createTopPiece(final ChunkPos chunkPos, final WorldgenRandom random) {
        int west = chunkPos.getMinBlockX() - 29;
        int north = chunkPos.getMinBlockZ() - 29;
        Direction orientation = Direction.Plane.HORIZONTAL.getRandomDirection(random);
        return new OceanMonumentPieces.MonumentBuilding(random, west, north, orientation);
    }

    private static void generatePieces(final StructurePiecesBuilder builder, final Structure.GenerationContext context) {
        builder.addPiece(createTopPiece(context.chunkPos(), context.random()));
    }
'''
    new='''    private static int neverOverworldMonumentBaseY(final Structure.GenerationContext context) {
        return context.heightAccessor().getMinY() == -512 && context.heightAccessor().getHeight() == 1024
            ? 104
            : context.chunkGenerator().getSeaLevel() - 24;
    }

    private static StructurePiece createTopPiece(final ChunkPos chunkPos, final WorldgenRandom random, final int baseY) {
        int west = chunkPos.getMinBlockX() - 29;
        int north = chunkPos.getMinBlockZ() - 29;
        Direction orientation = Direction.Plane.HORIZONTAL.getRandomDirection(random);
        return new OceanMonumentPieces.MonumentBuilding(random, west, north, orientation, baseY);
    }

    private static void generatePieces(final StructurePiecesBuilder builder, final Structure.GenerationContext context) {
        builder.addPiece(createTopPiece(context.chunkPos(), context.random(), neverOverworldMonumentBaseY(context)));
    }
'''
    if s.count(old)!=1: raise ValueError('OceanMonumentStructure creation block drifted')
    s=s.replace(old,new,1)
    old2='StructurePiece topPiece = new OceanMonumentPieces.MonumentBuilding(random, west, north, orientation);'
    new2='StructurePiece topPiece = new OceanMonumentPieces.MonumentBuilding(random, west, north, orientation, oldBoundingBox.minY());'
    if s.count(old2)!=1: raise ValueError('OceanMonumentStructure reload call drifted')
    return s.replace(old2,new2,1)

def patch_pieces(s:str)->str:
    if 'final int baseY' in s and 'makeBoundingBox(west, baseY, north' in s:
        return s
    if sha(s)!=PIECES_SHA: raise ValueError('OceanMonumentPieces source identity changed')
    old='''        public MonumentBuilding(final RandomSource random, final int west, final int north, final Direction direction) {
            super(StructurePieceType.OCEAN_MONUMENT_BUILDING, direction, 0, makeBoundingBox(west, 39, north, direction, 58, 23, 58));
            this.setOrientation(direction);
'''
    new='''        public MonumentBuilding(final RandomSource random, final int west, final int north, final Direction direction) {
            this(random, west, north, direction, 39);
        }

        public MonumentBuilding(final RandomSource random, final int west, final int north, final Direction direction, final int baseY) {
            super(StructurePieceType.OCEAN_MONUMENT_BUILDING, direction, 0, makeBoundingBox(west, baseY, north, direction, 58, 23, 58));
            this.setOrientation(direction);
'''
    if s.count(old)!=1: raise ValueError('OceanMonumentPieces constructor drifted')
    return s.replace(old,new,1)

def prepare(folia:Path)->dict[Path,str]:
    root=folia/JAVA
    a=root/STRUCT;b=root/PIECES
    if not a.is_file() or not b.is_file(): raise ValueError('monument sources missing')
    return {a:patch_struct(a.read_text()), b:patch_pieces(b.read_text())}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folia',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    staged=prepare(a.folia)
    if a.check_only:
        print('[NeverFolia][NeverOverworld monument R11] preflight OK')
        return
    for path,text in staged.items(): path.write_text(text)
    print('[NeverFolia][NeverOverworld monument R11] NeverOverworld -512/1024 monument base fixed at Y=104; other worlds use seaLevel-24')

if __name__=='__main__':main()
