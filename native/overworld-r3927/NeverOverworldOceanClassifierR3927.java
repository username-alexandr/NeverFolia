package net.minecraft.world.level.chunk;

import com.google.gson.JsonObject;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.BitSet;
import java.util.concurrent.atomic.AtomicLong;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.GenerationChunkHolder;
import net.minecraft.util.StaticCache2D;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.NeverOverworldNoiseOracleR3927;

/**
 * R39.27 classifies AIR by provenance instead of its final block name.
 *
 * - ProtoChunk CarvingMask marks exact world-carver AIR.
 * - the retained NoiseChunk is replayed only for the owner to identify native
 *   WATER/AIR/SOLID output from NOISE + aquifer interpolation.
 * - broad native Y=63 ocean water is an exterior seed, so an island roof at
 *   Y=128 no longer disconnects the water volume below it.
 * - Y>128 is never read.
 */
public final class NeverOverworldOceanClassifierR3927 {
    public static final String REVISION="R3927-native-origin-v1";
    private static final boolean ENABLED=Boolean.getBoolean("neverfolia.r3927OceanClassifier");
    private static final boolean STRICT=Boolean.getBoolean("neverfolia.r3927StrictAir");
    private static final String REPORT=System.getProperty("neverfolia.r3927ReportDirectory","");
    private static final AtomicLong IDS=new AtomicLong();
    private static final int LOW=-511,HIGH=128,NATIVE_SEA=63,HEIGHT=HIGH-LOW+1,WIDTH=48,AREA=WIDTH*WIDTH;

    private NeverOverworldOceanClassifierR3927() {}

    public static int apply(WorldGenLevel world,StaticCache2D<GenerationChunkHolder> cache,ChunkAccess owner) {
        if(!ENABLED||!world.getLevel().dimension().equals(Level.OVERWORLD)
            ||owner.getMinY()!=-512||owner.getHeight()!=1024
            ||owner.getPersistedStatus().isOrAfter(ChunkStatus.FULL))return 0;

        ChunkAccess[] chunks=new ChunkAccess[9];chunks[4]=owner;
        int cx=owner.getPos().x(),cz=owner.getPos().z(),missing=0;
        for(int dz=-1;dz<=1;dz++)for(int dx=-1;dx<=1;dx++) {
            if(dx==0&&dz==0)continue;
            int tile=(dz+1)*3+dx+1;
            if(cache!=null&&cache.contains(cx+dx,cz+dz)) {
                GenerationChunkHolder holder=cache.get(cx+dx,cz+dz);
                if(holder!=null)chunks[tile]=holder.getChunkIfPresent(ChunkStatus.FEATURES);
            }
            if(chunks[tile]==null)missing++;
        }
        return close(chunks,missing);
    }

    static int close(ChunkAccess[] chunks,int missing) {
        if(chunks.length!=9||chunks[4]==null)throw new IllegalArgumentException("R3927 owner missing");
        ChunkAccess owner=chunks[4];
        int cx=owner.getPos().x(),cz=owner.getPos().z();
        NeverOverworldNoiseOracleR3927.Sample oracle=NeverOverworldNoiseOracleR3927.sample(owner,LOW,HIGH);

        byte[] cells=new byte[AREA*HEIGHT];
        BlockState[] originalOwner=new BlockState[256*HEIGHT];
        BlockPos.MutableBlockPos p=new BlockPos.MutableBlockPos();
        int carvingMaskChunks=0,carvedOwner=0;

        for(int tile=0;tile<9;tile++) {
            ChunkAccess chunk=chunks[tile];
            if(chunk==null)continue;
            if(chunk.getMinY()!=-512||chunk.getHeight()!=1024
                ||chunk.getPos().x()!=cx+tile%3-1||chunk.getPos().z()!=cz+tile/3-1)
                throw new IllegalArgumentException("R3927 inconsistent witness chunk");

            BitSet protectedCells=NeverOverworldDryMinesR12.mask(chunk).envelope;
            CarvingMask carving=null;
            if(chunk instanceof ProtoChunk proto) {
                carving=proto.getCarvingMask();
                if(carving!=null)carvingMaskChunks++;
            }
            int bx=chunk.getPos().getMinBlockX(),bz=chunk.getPos().getMinBlockZ();
            int ox=(tile%3)*16,oz=(tile/3)*16;

            for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
                p.set(bx+x,y,bz+z);
                BlockState state=chunk.getBlockState(p);
                int layer=y-LOW,plane=(oz+z)*WIDTH+ox+x,index=layer*AREA+plane;
                int local=(layer<<8)|(z<<4)|x;
                if(tile==4)originalOwner[local]=state;

                int maskIndex=((y-chunk.getMinY())<<8)|(z<<4)|x;
                if(protectedCells.get(maskIndex))cells[index]=OceanConnectivityR3927.PROTECTED;
                else if(state.isAir()) {
                    boolean carved=carving!=null&&carving.get(bx+x,y,bz+z);
                    cells[index]=carved?OceanConnectivityR3927.CARVED_AIR:OceanConnectivityR3927.AIR;
                    if(tile==4&&carved)carvedOwner++;
                }
                else if(aquatic(state))cells[index]=OceanConnectivityR3927.WATER;
                else if(state.is(Blocks.LAVA))cells[index]=OceanConnectivityR3927.LAVA;
                else cells[index]=OceanConnectivityR3927.SOLID;
            }
        }

        OceanConnectivityR3927.Proof proof=OceanConnectivityR3927.solve(
            WIDTH,WIDTH,HEIGHT,cells,NATIVE_SEA-LOW
        );

        int bx=owner.getPos().getMinBlockX(),bz=owner.getPos().getMinBlockZ();
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x;
            p.set(bx+x,y,bz+z);
            if(owner.getBlockState(p)!=originalOwner[local])
                throw new IllegalStateException("R3927 owner changed during capture");
        }

        int changed=0,connectedFill=0,restoredNoiseWater=0,beforeAquatic=0,preservedAquatic=0;
        int remainingCarved=0,remainingNoiseAir=0,remainingSolidOrigin=0,remainingExpectedLava=0,remainingExpectedOtherFluid=0,remainingOracleUnknown=0,oracleUnavailableAir=0,missedExpectedWater=0;

        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int local=((y-LOW)<<8)|(z<<4)|x;
            int index=(y-LOW)*AREA+(z+16)*WIDTH+x+16;
            BlockState before=originalOwner[local];
            p.set(bx+x,y,bz+z);

            boolean target=cells[index]==OceanConnectivityR3927.AIR||cells[index]==OceanConnectivityR3927.CARVED_AIR;
            if(target&&proof.connected().get(index)) {
                owner.setBlockState(p,Blocks.WATER.defaultBlockState(),0);
                changed++;connectedFill++;
            } else if(target&&oracle.available()
                &&oracle.get(x,y,z)==NeverOverworldNoiseOracleR3927.WATER) {
                // The exact NOISE/aquifer replay says this position originally
                // generated as water. Restoring it cannot turn a dry noise cave
                // into ocean; dry structures/mineshafts are already protected.
                owner.setBlockState(p,Blocks.WATER.defaultBlockState(),0);
                changed++;restoredNoiseWater++;
            }

            if(aquatic(before)) {
                beforeAquatic++;
                if(owner.getBlockState(p)==before)preservedAquatic++;
            }
        }
        if(beforeAquatic!=preservedAquatic)
            throw new IllegalStateException("R3927 existing aquatic state changed");

        // Postcondition: every remaining AIR is assigned a provenance class.
        for(int y=LOW;y<=HIGH;y++)for(int z=0;z<16;z++)for(int x=0;x<16;x++) {
            int index=(y-LOW)*AREA+(z+16)*WIDTH+x+16;
            if(cells[index]!=OceanConnectivityR3927.AIR&&cells[index]!=OceanConnectivityR3927.CARVED_AIR)continue;
            p.set(bx+x,y,bz+z);
            if(!owner.getBlockState(p).isAir())continue;
            if(cells[index]==OceanConnectivityR3927.CARVED_AIR) {
                remainingCarved++;
                continue;
            }
            if(!oracle.available()) {
                oracleUnavailableAir++;
                continue;
            }
            byte expected=oracle.get(x,y,z);
            if(expected==NeverOverworldNoiseOracleR3927.WATER)missedExpectedWater++;
            else if(expected==NeverOverworldNoiseOracleR3927.AIR)remainingNoiseAir++;
            else if(expected==NeverOverworldNoiseOracleR3927.SOLID)remainingSolidOrigin++;
            else if(expected==NeverOverworldNoiseOracleR3927.LAVA)remainingExpectedLava++;
            else if(expected==NeverOverworldNoiseOracleR3927.OTHER_FLUID)remainingExpectedOtherFluid++;
            else remainingOracleUnknown++;
        }

        if(STRICT&&(!oracle.available()||missedExpectedWater>0||remainingOracleUnknown>0))
            throw new IllegalStateException("R3927 strict AIR provenance failed: oracle="+oracle.reason()
                +" missedWater="+missedExpectedWater+" oracleUnknown="+remainingOracleUnknown
                +" unavailableAir="+oracleUnavailableAir);

        if(!REPORT.isEmpty()) {
            JsonObject r=new JsonObject();
            r.addProperty("revision",REVISION);
            r.addProperty("chunk_x",cx);r.addProperty("chunk_z",cz);
            r.addProperty("added_air_to_water",changed);
            r.addProperty("connected_air_to_water",connectedFill);
            r.addProperty("restored_noise_water",restoredNoiseWater);
            r.addProperty("native_sea_seed_cells",proof.nativeSeaSeedCells());
            r.addProperty("native_sea_components",proof.nativeSeaComponents());
            r.addProperty("carved_air_witness",proof.carvedAir());
            r.addProperty("connected_carved_air",proof.connectedCarvedAir());
            r.addProperty("owner_carved_air",carvedOwner);
            r.addProperty("carving_mask_chunks",carvingMaskChunks);
            r.addProperty("missing_cache_chunks",missing);
            r.addProperty("noise_oracle_available",oracle.available());
            r.addProperty("noise_oracle_reason",oracle.reason());
            r.addProperty("noise_oracle_cell_width",oracle.cellWidth());
            r.addProperty("noise_oracle_cell_height",oracle.cellHeight());
            r.addProperty("remaining_carved_air",remainingCarved);
            r.addProperty("remaining_noise_air",remainingNoiseAir);
            r.addProperty("remaining_solid_origin_air",remainingSolidOrigin);
            r.addProperty("remaining_expected_lava_air",remainingExpectedLava);
            r.addProperty("remaining_expected_other_fluid_air",remainingExpectedOtherFluid);
            r.addProperty("remaining_oracle_unknown_air",remainingOracleUnknown);
            r.addProperty("oracle_unavailable_air",oracleUnavailableAir);
            r.addProperty("missed_expected_water",missedExpectedWater);
            r.addProperty("read_min_y",LOW);r.addProperty("read_max_y",HIGH);
            r.addProperty("reads_above_sea_level",0);
            r.addProperty("native_aquatic_cells",beforeAquatic);
            r.addProperty("preserved_aquatic_cells",preservedAquatic);
            try {
                Path dir=Path.of(REPORT);Files.createDirectories(dir);
                Files.writeString(dir.resolve(cx+"_"+cz+"_"+IDS.incrementAndGet()+".json"),
                    r.toString()+"\n",StandardOpenOption.CREATE_NEW);
            } catch(java.io.IOException error) {
                throw new IllegalStateException("Cannot retain R3927 diagnostics",error);
            }
        }
        return changed;
    }

    private static boolean aquatic(BlockState s) {
        return s.is(Blocks.WATER)||s.is(Blocks.BUBBLE_COLUMN)||s.is(Blocks.KELP)||s.is(Blocks.KELP_PLANT)
            ||s.is(Blocks.SEAGRASS)||s.is(Blocks.TALL_SEAGRASS);
    }
}
