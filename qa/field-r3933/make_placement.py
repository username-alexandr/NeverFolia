#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json

ROOT=Path(__file__).resolve().parents[2]
BASE_SCRIPT=ROOT/'scripts/apply-never-overworld-placement-hook.py'
SPEC=ROOT/'worldgen-spec/never-overworld-structures.json'

def need(v,m):
    if not v: raise ValueError(m)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def source():
    base=load('r3932_placement',BASE_SCRIPT)
    spec=json.loads(SPEC.read_text())
    s=base.helper_source(spec)

    old='import net.minecraft.world.level.levelgen.structure.Structure;\n'
    new='import net.minecraft.world.level.levelgen.Heightmap;\n'+old
    need(old in s,'Structure import anchor missing')
    s=s.replace(old,new,1)

    old='    private static final int MAX_SAFE_Y = '
    i=s.find(old)
    need(i>=0,'MAX_SAFE_Y anchor missing')
    line_end=s.find('\n',i)
    constants='''\n    // R39.33: the Trident Trial Monument is a large rigid jigsaw. Keep it off\n    // steep seabeds instead of allowing distant rigid pieces to hang over a\n    // trench or forcing terrain/support columns below them.\n    private static final String TRIDENT_START_POOL = "nova_structures:trident_monument/start";\n    private static final int TRIDENT_SEABED_RADIUS = 48;\n    private static final int TRIDENT_SEABED_STEP = 24;\n    private static final int TRIDENT_MAX_RELIEF = 6;\n'''
    s=s[:line_end+1]+constants+s[line_end+1:]

    old='''        final Profile profile = PROFILES.get(poolId);
        if (profile == null) {
            return previousStartY;
        }
'''
    new='''        if (TRIDENT_START_POOL.equals(poolId)) {
            return hasStableTridentSeabed(context) ? previousStartY : REJECT_Y;
        }

        final Profile profile = PROFILES.get(poolId);
        if (profile == null) {
            return previousStartY;
        }
'''
    need(old in s,'profile lookup anchor missing')
    s=s.replace(old,new,1)

    old='''    private static NoiseColumn column(Structure.GenerationContext context, int x, int z) {
'''
    method='''    private static boolean hasStableTridentSeabed(Structure.GenerationContext context) {
        final ChunkPos chunkPos = context.chunkPos();
        final int centerX = chunkPos.getMinBlockX() + 8;
        final int centerZ = chunkPos.getMinBlockZ() + 8;
        int minY = Integer.MAX_VALUE;
        int maxY = Integer.MIN_VALUE;

        for (int dx = -TRIDENT_SEABED_RADIUS; dx <= TRIDENT_SEABED_RADIUS; dx += TRIDENT_SEABED_STEP) {
            for (int dz = -TRIDENT_SEABED_RADIUS; dz <= TRIDENT_SEABED_RADIUS; dz += TRIDENT_SEABED_STEP) {
                final int y = context.chunkGenerator().getBaseHeight(
                    centerX + dx,
                    centerZ + dz,
                    Heightmap.Types.OCEAN_FLOOR_WG,
                    context.heightAccessor(),
                    context.randomState()
                );
                minY = Math.min(minY, y);
                maxY = Math.max(maxY, y);
                if (maxY - minY > TRIDENT_MAX_RELIEF) {
                    return false;
                }
            }
        }
        return minY != Integer.MAX_VALUE;
    }

'''
    need(old in s,'column method anchor missing')
    s=s.replace(old,method+old,1)

    required=(
      'TRIDENT_START_POOL = "nova_structures:trident_monument/start"',
      'TRIDENT_SEABED_RADIUS = 48',
      'TRIDENT_SEABED_STEP = 24',
      'TRIDENT_MAX_RELIEF = 6',
      'Heightmap.Types.OCEAN_FLOOR_WG',
      'hasStableTridentSeabed(context) ? previousStartY : REJECT_Y',
      'Require a real rock ceiling above the local water.'
    )
    for marker in required: need(marker in s,'missing R39.33 placement marker '+marker)
    return s

def main():
    print(source(),end='')

if __name__=='__main__':main()
