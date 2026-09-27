package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/** Scoped producer correction, not a scan that deletes arbitrary underwater ice.
 * Vanilla icebergs are anchored to the final ocean. Dry surface frost is skipped
 * where this world will be flooded; surface freezing is performed after closure.
 */
public final class NeverOverworldIceR40 {
    private NeverOverworldIceR40() {}
    public static boolean active(WorldGenLevel level) {
        return NeverOverworldOceanR40.ENABLED && level.getLevel().dimension().equals(Level.OVERWORLD)
            && level.getMinY()==-512 && level.getHeight()==1024;
    }
    public static int sea(WorldGenLevel level,int original) {return active(level)?128:original;}
    public static boolean belowFutureSea(WorldGenLevel level,int y) {return active(level)&&y<128;}
    public static boolean ice(BlockState state) {
        return state.is(Blocks.ICE)||state.is(Blocks.PACKED_ICE)||state.is(Blocks.BLUE_ICE)||state.is(Blocks.FROSTED_ICE);
    }
    /** Virtual source water only for the known raised, open-sky ocean interval.
     * Does not modify aquifers, vanilla getSeaLevel(), or a closed cave.
     */
    public static boolean futureWater(BlockGetter view,BlockPos position) {
        if(!(view instanceof WorldGenLevel level)||!active(level)||position.getY()<64||position.getY()>128)return false;
        BlockState current=view.getBlockState(position);
        if(current.is(Blocks.WATER))return true;
        if(!current.isAir())return false;
        BlockPos.MutableBlockPos probe=new BlockPos.MutableBlockPos();
        for(int y=position.getY()+1;y<level.getMaxY();y++) {
            probe.set(position.getX(),y,position.getZ());BlockState above=view.getBlockState(probe);
            // An already placed natural iceberg may cover its submerged body.
            if(!above.isAir()&&!above.is(Blocks.WATER)&&!ice(above)&&!above.is(Blocks.SNOW_BLOCK)&&!above.is(Blocks.SNOW))return false;
        }
        return true;
    }
    public static int freezeSurface(WorldGenLevel world,ChunkAccess owner) {
        if(!NeverOverworldOceanR40.scope(world,owner)||owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return 0;
        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ(),changed=0;
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            p.set(bx+x,128,bz+z);BlockState state=owner.getBlockState(p);
            if(!state.is(Blocks.WATER)||!state.getFluidState().isSource()||NeverOverworldDryMinesR12.protectedCell(owner,p))continue;
            boolean sky=true;
            for(int y=129;y<owner.getMaxY();y++) {p.set(bx+x,y,bz+z);if(!owner.getBlockState(p).isAir()){sky=false;break;}}
            if(!sky)continue;
            p.set(bx+x,128,bz+z);
            if(owner.getNoiseBiome((bx+x)>>2,128>>2,(bz+z)>>2).value().coldEnoughToSnow(p,128)) {
                owner.setBlockState(p,Blocks.ICE.defaultBlockState(),0);changed++;
            }
        }
        return changed;
    }
}
