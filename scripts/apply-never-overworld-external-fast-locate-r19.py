#!/usr/bin/env python3
"""FIELD-R19 no-generation fast locate for island-adapted external structures.

Vanilla /locate calls Structure#findValidGenerationPoint while scanning random
spread candidates. For imported surface Jigsaw structures on NeverOverworld
this can synchronously load/generate non-FULL chunks from Folia's global region
and trip the watchdog. R19 already owns the placement policy for these
structures, so locate can reproduce the random-spread candidate grid and the
same cheap biome + dry-island admission without loading chunks.
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

CHUNK_REL=Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java")
HELPER_REL=Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldExternalFastLocateR19.java")

ANCHOR="        // NeverFolia start - flooded vanilla no-generation fast locate\n"
MARKER="        // NeverFolia R19: external island structures use no-generation locate.\n"

HOOK=MARKER+"""        if (!createReference
            && level.dimension().equals(net.minecraft.world.level.Level.OVERWORLD)
            && level.getMinY() == -512
            && level.getHeight() == 1024
            && NeverOverworldExternalFastLocateR19.handles(wantedStructures)) {
            return NeverOverworldExternalFastLocateR19.find(
                this, level, wantedStructures, pos, maxSearchRadius
            );
        }
"""

HELPER=r'''package net.minecraft.world.level.chunk;

import com.mojang.datafixers.util.Pair;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.core.QuartPos;
import net.minecraft.core.SectionPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.levelgen.DensityFunction;
import net.minecraft.world.level.levelgen.LegacyRandomSource;
import net.minecraft.world.level.levelgen.WorldgenRandom;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructureSet;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement;

/**
 * Predictive locate for FIELD-R19 external land structures.
 *
 * <p>Only structure IDs owned by NeverOverworldExternalStructurePolicyR19 are
 * intercepted. Candidate structure-set positions and weighted retry ordering
 * mirror ChunkGenerator#createStructures, while terrain admission uses the
 * preliminary-surface density router and therefore never synchronously loads
 * neighbour chunks.</p>
 */
final class NeverOverworldExternalFastLocateR19 {
    private static final int EXPECTED_MIN_Y=-512;
    private static final int EXPECTED_HEIGHT=1024;
    private static final int MIN_DRY_SURFACE_Y=129;
    private static final int MAX_CANDIDATE_RINGS=64;

    private NeverOverworldExternalFastLocateR19(){}

    static boolean handles(final HolderSet<Structure> wantedStructures){
        boolean any=false;
        for(final Holder<Structure> holder:wantedStructures){
            final String id=structureId(holder);
            if(id==null||NeverOverworldExternalStructurePolicyR19.radiusForId(id)<=0){
                return false;
            }
            any=true;
        }
        return any;
    }

    static Pair<BlockPos,Holder<Structure>> find(
        final ChunkGenerator generator,
        final ServerLevel level,
        final HolderSet<Structure> wantedStructures,
        final BlockPos origin,
        final int requestedRings
    ){
        if(!Level.OVERWORLD.equals(level.dimension())
            ||level.getMinY()!=EXPECTED_MIN_Y||level.getHeight()!=EXPECTED_HEIGHT){
            return null;
        }

        final Set<String> wantedIds=new HashSet<>();
        for(final Holder<Structure> holder:wantedStructures){
            final String id=structureId(holder);
            if(id!=null) wantedIds.add(id);
        }
        if(wantedIds.isEmpty()) return null;

        final ChunkGeneratorStructureState state=level.getChunkSource().getGeneratorState();
        final List<SetRef> sets=collectRelevantSets(state,wantedIds);
        if(sets.isEmpty()) return null;

        final int originChunkX=SectionPos.blockToSectionCoord(origin.getX());
        final int originChunkZ=SectionPos.blockToSectionCoord(origin.getZ());
        final int maxRings=Math.max(0,Math.min(requestedRings,MAX_CANDIDATE_RINGS));

        for(int radius=0;radius<=maxRings;++radius){
            final List<Candidate> candidates=new ArrayList<>();
            for(final SetRef setRef:sets){
                appendRingCandidates(state,setRef,origin,originChunkX,originChunkZ,radius,candidates);
            }
            candidates.sort(CANDIDATE_ORDER);
            for(final Candidate candidate:candidates){
                final Holder<Structure> generated=predictGeneratedStructure(generator,state,candidate);
                final String generatedId=generated==null?null:structureId(generated);
                if(generatedId!=null&&wantedIds.contains(generatedId)){
                    return Pair.of(candidate.placement().getLocatePos(candidate.chunkPos()),generated);
                }
            }
        }
        return null;
    }

    private static List<SetRef> collectRelevantSets(
        final ChunkGeneratorStructureState state,
        final Set<String> wantedIds
    ){
        final List<SetRef> result=new ArrayList<>();
        for(final Holder<StructureSet> holder:state.possibleStructureSets()){
            final StructureSet set=holder.value();
            if(!(set.placement() instanceof RandomSpreadStructurePlacement placement)) continue;
            boolean relevant=false;
            for(final StructureSet.StructureSelectionEntry entry:set.structures()){
                final String id=structureId(entry.structure());
                if(id!=null&&wantedIds.contains(id)){relevant=true;break;}
            }
            if(relevant) result.add(new SetRef(holder,set,placement));
        }
        return result;
    }

    private static void appendRingCandidates(
        final ChunkGeneratorStructureState state,
        final SetRef setRef,
        final BlockPos origin,
        final int originChunkX,
        final int originChunkZ,
        final int radius,
        final List<Candidate> output
    ){
        final RandomSpreadStructurePlacement placement=setRef.placement();
        final int spacing=placement.spacing();
        final ResourceKey<StructureSet> setKey=setRef.holder().unwrapKey().orElse(null);

        for(int x=-radius;x<=radius;++x){
            final boolean xEdge=x==-radius||x==radius;
            final int zStep=xEdge?1:Math.max(1,radius*2);
            for(int z=-radius;z<=radius;z+=zStep){
                final int sectorX=originChunkX+spacing*x;
                final int sectorZ=originChunkZ+spacing*z;
                final ChunkPos chunk=placement.getPotentialStructureChunk(state.getLevelSeed(),sectorX,sectorZ);
                if(!placement.isStructureChunk(state,chunk.x(),chunk.z(),setKey)) continue;
                final BlockPos locatePos=placement.getLocatePos(chunk);
                output.add(new Candidate(setRef,placement,chunk,locatePos.distSqr(origin)));
            }
        }
    }

    /** Mirrors createStructures weighted retry ordering for the structure set. */
    private static Holder<Structure> predictGeneratedStructure(
        final ChunkGenerator generator,
        final ChunkGeneratorStructureState state,
        final Candidate candidate
    ){
        final ArrayList<StructureSet.StructureSelectionEntry> entries=
            new ArrayList<>(candidate.setRef().set().structures());
        final WorldgenRandom random=new WorldgenRandom(new LegacyRandomSource(0L));
        random.setLargeFeatureSeed(state.getLevelSeed(),candidate.chunkPos().x(),candidate.chunkPos().z());

        int totalWeight=0;
        for(final StructureSet.StructureSelectionEntry entry:entries) totalWeight+=entry.weight();

        while(!entries.isEmpty()&&totalWeight>0){
            int draw=random.nextInt(totalWeight);
            int selectedIndex=0;
            for(int i=0;i<entries.size();++i){
                draw-=entries.get(i).weight();
                if(draw<0){selectedIndex=i;break;}
            }
            final StructureSet.StructureSelectionEntry selected=entries.get(selectedIndex);
            if(predictViable(generator,state,candidate.chunkPos(),selected.structure())){
                return selected.structure();
            }
            entries.remove(selectedIndex);
            totalWeight-=selected.weight();
        }
        return null;
    }

    private static boolean predictViable(
        final ChunkGenerator generator,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> holder
    ){
        final String id=structureId(holder);
        if(id==null) return false;

        final int centerX=chunkPos.getMiddleBlockX();
        final int centerZ=chunkPos.getMiddleBlockZ();
        final int centerSurface=preliminarySurfaceY(state,centerX,centerZ);
        if(centerSurface==Integer.MIN_VALUE) return false;
        if(!passesBiomeAtY(generator,state,chunkPos,holder,centerSurface)) return false;

        final int radius=NeverOverworldExternalStructurePolicyR19.radiusForId(id);
        if(radius<=0){
            // A non-island sibling can win a mixed source set and therefore
            // block the requested island structure at this candidate. Preserve
            // weighted ordering with a conservative biome-valid prediction.
            return true;
        }

        final int half=Math.max(1,radius/2);
        final int[] offsets={-radius,-half,0,half,radius};
        for(final int dx:offsets){
            for(final int dz:offsets){
                if(preliminarySurfaceY(state,centerX+dx,centerZ+dz)<MIN_DRY_SURFACE_Y){
                    return false;
                }
            }
        }
        return true;
    }

    private static int preliminarySurfaceY(
        final ChunkGeneratorStructureState state,
        final int blockX,
        final int blockZ
    ){
        final double estimated=state.randomState()
            .router()
            .preliminarySurfaceLevel()
            .compute(new DensityFunction.SinglePointContext(blockX,0,blockZ));
        if(!Double.isFinite(estimated)) return Integer.MIN_VALUE;
        return (int)Math.floor(estimated);
    }

    private static boolean passesBiomeAtY(
        final ChunkGenerator generator,
        final ChunkGeneratorStructureState state,
        final ChunkPos chunkPos,
        final Holder<Structure> holder,
        final int biomeY
    ){
        final int blockX=chunkPos.getMiddleBlockX();
        final int blockZ=chunkPos.getMiddleBlockZ();
        final Holder<Biome> biome=generator.getBiomeSource().getNoiseBiome(
            QuartPos.fromBlock(blockX),
            QuartPos.fromBlock(biomeY),
            QuartPos.fromBlock(blockZ),
            state.randomState().sampler()
        );
        return holder.value().biomes().contains(biome);
    }

    private static String structureId(final Holder<Structure> holder){
        final Optional<ResourceKey<Structure>> key=holder.unwrapKey();
        return key.map(value->value.identifier().toString()).orElse(null);
    }

    private static String setId(final SetRef ref){
        return ref.holder().unwrapKey().map(key->key.identifier().toString()).orElse("");
    }

    private static final Comparator<Candidate> CANDIDATE_ORDER=Comparator
        .comparingDouble(Candidate::distanceSq)
        .thenComparingInt(candidate->candidate.chunkPos().x())
        .thenComparingInt(candidate->candidate.chunkPos().z())
        .thenComparing(candidate->setId(candidate.setRef()));

    private record SetRef(
        Holder<StructureSet> holder,
        StructureSet set,
        RandomSpreadStructurePlacement placement
    ){}

    private record Candidate(
        SetRef setRef,
        RandomSpreadStructurePlacement placement,
        ChunkPos chunkPos,
        double distanceSq
    ){}
}
'''

def fail(message:str)->None:
    raise SystemExit("[NeverFolia][External Fast Locate R19] "+message)

def patch_chunk(text:str)->str:
    if MARKER in text:
        return text
    if ANCHOR not in text:
        fail("flooded vanilla fast-locate anchor missing")
    return text.replace(ANCHOR,HOOK+"\n"+ANCHOR,1)

def verify(root:Path)->None:
    chunk=(root/CHUNK_REL).read_text(encoding="utf-8")
    helper=(root/HELPER_REL).read_text(encoding="utf-8")
    if chunk.count(MARKER.strip())!=1:
        fail("ChunkGenerator R19 fast-locate hook missing/duplicated")
    for marker in (
        "NeverOverworldExternalFastLocateR19.handles(wantedStructures)",
        "NeverOverworldExternalStructurePolicyR19.radiusForId",
        "getPotentialStructureChunk",
        "isStructureChunk",
        "DensityFunction.SinglePointContext",
        ".preliminarySurfaceLevel()",
        "MAX_CANDIDATE_RINGS=64",
    ):
        if marker not in chunk+helper:
            fail("fast-locate marker missing: "+marker)
    for forbidden in ("moonrise$syncLoadNonFull","getChunk(","getBaseHeight("):
        if forbidden in helper:
            fail("chunk-loading/expensive primitive leaked into helper: "+forbidden)
    print("[NeverFolia][External Fast Locate R19] invariants OK")

def self_test()->None:
    with tempfile.TemporaryDirectory(prefix="nr-r19-fast-locate-") as tmp:
        root=Path(tmp);chunk=root/CHUNK_REL;chunk.parent.mkdir(parents=True,exist_ok=True)
        chunk.write_text("""class ChunkGenerator {
    void x(){
        // NeverFolia start - flooded vanilla no-generation fast locate
        if (x) return;
    }
}
""",encoding="utf-8")
        helper=root/HELPER_REL;helper.parent.mkdir(parents=True,exist_ok=True)
        chunk.write_text(patch_chunk(chunk.read_text(encoding="utf-8")),encoding="utf-8")
        helper.write_text(HELPER,encoding="utf-8")
        verify(root)
        if patch_chunk(chunk.read_text(encoding="utf-8"))!=chunk.read_text(encoding="utf-8"):
            fail("transform is not idempotent")
    print("[NeverFolia][External Fast Locate R19] SELF-TEST OK")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",nargs="?",type=Path)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args()
    if a.self_test:self_test();return
    if a.folia is None:p.error("folia worktree is required")
    root=a.folia.resolve()
    if a.check_only:verify(root);return
    self_test()
    chunk=root/CHUNK_REL
    if not chunk.is_file():fail("ChunkGenerator missing")
    chunk.write_text(patch_chunk(chunk.read_text(encoding="utf-8")),encoding="utf-8")
    helper=root/HELPER_REL;helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text(HELPER,encoding="utf-8")
    verify(root)
    print("[NeverFolia][External Fast Locate R19] installed")

if __name__=="__main__":main()
