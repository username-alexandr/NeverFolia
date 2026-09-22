#!/usr/bin/env python3
"""Install NeverNether R16 enclosed lava-ocean cleanup after exact R15."""
from __future__ import annotations
import argparse
from pathlib import Path

JAVA=Path('folia-server/src/minecraft/java')
TARGET=Path('net/minecraft/world/level/levelgen/placement/NeverNetherFieldCleanupR15.java')
PROCESSORS=Path('net/minecraft/world/level/levelgen/structure/templatesystem/NeverNetherNativeProcessors.java')
OLD_PROFILE='NN-R15-FIELD-CLEANUP-1';NEW_PROFILE='NN-R16-LAVA-OCEAN-CLEANUP-1'
MARK='static final int LAVA_OCEAN_MAX_Y = 31;'
R15_REGISTER='Registry.register(registry, Identifier.fromNamespaceAndPath("neverfolia", "field_r15_required"), net.minecraft.world.level.levelgen.placement.NeverNetherFieldCleanupR15.RequiredProcessor.CODEC);'
R16_REGISTER='Registry.register(registry, Identifier.fromNamespaceAndPath("neverfolia", "field_r16_required"), net.minecraft.world.level.levelgen.placement.NeverNetherFieldCleanupR15.RequiredProcessorR16.CODEC);'
METHOD=r'''
    static int fillLavaOceanAirPockets(final ChunkAccess chunk, final boolean published) {
        final int maxCells = MAX_LAVA_OCEAN_AIR_POCKET;
        final int baseX = chunk.getPos().getMinBlockX(), baseZ = chunk.getPos().getMinBlockZ();
        final boolean[] visited = new boolean[(LAVA_OCEAN_MAX_Y - MIN_Y + 1) * 256];
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        int changed = 0;
        for (int y = MIN_Y + 1; y <= LAVA_OCEAN_MAX_Y; ++y) for (int z=0;z<16;++z) for(int x=0;x<16;++x) {
            final int start=oceanIndex(x,y,z);
            if(visited[start])continue;
            pos.set(baseX+x,y,baseZ+z);
            if(!chunk.getBlockState(pos).isAir()){visited[start]=true;continue;}
            final ArrayDeque<Cell> queue=new ArrayDeque<>(), cells=new ArrayDeque<>();
            queue.add(new Cell(x,y,z));visited[start]=true;
            boolean safe=true;int lavaBoundary=0,rockBoundary=0;
            while(!queue.isEmpty()){
                final Cell c=queue.removeFirst();
                if(cells.size()<maxCells+1)cells.addLast(c);
                if(cells.size()>maxCells||c.x==0||c.x==15||c.z==0||c.z==15)safe=false;
                for(int[] d:DIRECTIONS){
                    int nx=c.x+d[0],ny=c.y+d[1],nz=c.z+d[2];
                    if(nx<0||nx>15||nz<0||nz>15||ny<MIN_Y||ny>MAX_Y){safe=false;continue;}
                    pos.set(baseX+nx,ny,baseZ+nz);BlockState s=chunk.getBlockState(pos);
                    if(s.isAir()){
                        if(ny>LAVA_OCEAN_MAX_Y){safe=false;continue;}
                        int ni=oceanIndex(nx,ny,nz);if(!visited[ni]){visited[ni]=true;queue.addLast(new Cell(nx,ny,nz));}
                    } else if(sourceLava(s)) ++lavaBoundary;
                    else if(isNaturalRock(s)) ++rockBoundary;
                    else safe=false;
                }
            }
            if(!safe||cells.isEmpty()||cells.size()>maxCells||lavaBoundary<4||lavaBoundary<rockBoundary)continue;
            for(Cell c:cells){write(chunk,c.x,c.y,c.z,Blocks.LAVA.defaultBlockState(),published,pos);++changed;}
        }
        return changed;
    }
    private static int oceanIndex(final int x,final int y,final int z){return (y-MIN_Y)*256+z*16+x;}

'''
RECORD=r'''
    /** R16 pack/runtime marker: older R15 runtimes cannot decode this processor. */
    public record RequiredProcessorR16() implements StructureProcessor {
        public static final RequiredProcessorR16 INSTANCE = new RequiredProcessorR16();
        public static final MapCodec<RequiredProcessorR16> CODEC = MapCodec.unit(INSTANCE);
        @Override
        public StructureTemplate.StructureBlockInfo processBlock(
            LevelReader level, BlockPos pos, BlockPos ref, BlockPos relative,
            StructureTemplate.StructureBlockInfo info, StructurePlaceSettings settings
        ) { return info; }
        @Override public MapCodec<RequiredProcessorR16> codec() { return CODEC; }
    }

'''

def patch_helper(text):
    if MARK in text:
        if NEW_PROFILE not in text or text.count(MARK)!=1 or text.count('RequiredProcessorR16')<3:raise ValueError('partial R16 helper')
        return text
    if text.count('static final int MAX_MICRO_POCKET = 4;')!=1 or text.count('NATIVE_PROFILE = "'+OLD_PROFILE+'"')!=1:raise ValueError('exact R15 anchors missing')
    text=text.replace('static final int MAX_MICRO_POCKET = 4;','static final int MAX_MICRO_POCKET = 4;\n    '+MARK+'\n    static final int MAX_LAVA_OCEAN_AIR_POCKET = 1024;',1)
    text=text.replace('NATIVE_PROFILE = "'+OLD_PROFILE+'"','NATIVE_PROFILE = "'+NEW_PROFILE+'"',1)
    old='''        final int pockets = fillMicroPockets(chunk, false);
        final int shelves = solidifyHangingLava(chunk);
        return new Result(pockets, shelves);'''
    new='''        final int pockets = fillMicroPockets(chunk, false);
        fillLavaOceanAirPockets(chunk, false);
        final int shelves = solidifyHangingLava(chunk);
        return new Result(pockets, shelves);'''
    if text.count(old)!=1:raise ValueError('R16 pre-capture anchor missing')
    text=text.replace(old,new,1)
    old='''        validateEnvelope(chunk);
        return new Result(fillMicroPockets(chunk, true), 0);
    }'''
    new='''        validateEnvelope(chunk);
        final int pockets = fillMicroPockets(chunk, true);
        fillLavaOceanAirPockets(chunk, true);
        return new Result(pockets, 0);
    }'''
    if text.count(old)!=1:raise ValueError('R16 afterFeatures anchor missing')
    text=text.replace(old,new,1)
    anchor='    private static void write(\n'
    if text.count(anchor)!=1:raise ValueError('R16 method anchor missing')
    text=text.replace(anchor,METHOD+anchor,1)
    marker='    /** Datapack/runtime marker: an R15 pack must not decode on an older R14 runtime. */\n'
    if text.count(marker)!=1:raise ValueError('R15 processor record anchor missing')
    text=text.replace(marker,RECORD+marker,1)
    return text

def patch_processors(text):
    if R16_REGISTER in text:
        if text.count(R16_REGISTER)!=1:raise ValueError('duplicate R16 processor')
        return text
    if text.count(R15_REGISTER)!=1:raise ValueError('R15 processor registration anchor missing')
    return text.replace(R15_REGISTER,R15_REGISTER+'\n        '+R16_REGISTER,1)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folia',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    root=a.folia.resolve()/JAVA;target=root/TARGET;processors=root/PROCESSORS
    values={target:patch_helper(target.read_text()),processors:patch_processors(processors.read_text())}
    if not a.check_only:
        for path,text in values.items():path.write_text(text)
    print('[NeverNether R16] lava-ocean air cleanup + R16 processor lock '+('preflight' if a.check_only else 'installed'))

if __name__=='__main__':main()
