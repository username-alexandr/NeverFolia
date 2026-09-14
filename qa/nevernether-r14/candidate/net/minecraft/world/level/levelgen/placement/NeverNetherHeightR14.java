package net.minecraft.world.level.levelgen.placement;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.serialization.MapCodec;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipFile;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LevelHeightAccessor;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessor;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate;

/** Exact logical roof at 512. 41 physical sections include the roof block; the
 * final fifteen cells of the top section are empty, non-buildable padding.
 * No global coordinates/blocks cache, no neighboring chunk loads, no migration.
 */
public final class NeverNetherHeightR14 {
    public static final int MIN_Y = -128, ROOF_Y = 512, HEIGHT = 656, MAX_Y = 527, SECTIONS = 41;
    public static final String PROFILE = "NN-R14-SUBSTRATE-1-ROOF512";
    private static final String MARKER = "data/neverfolia/nevernether/height_profile.json";
    private static final String DIM = "data/minecraft/dimension_type/the_nether.json";
    private static final String LOCK = ".neverfolia-nevernether-height.lock";
    private NeverNetherHeightR14() { }

    public static boolean active(LevelHeightAccessor accessor) {
        // ChunkAccess holds the actual level height accessor; arbitrary dimensions
        // with the same numeric envelope are not selected by numbers alone.
        return accessor instanceof Level level && level.dimension().equals(Level.NETHER)
            && level.getMinY() == MIN_Y && level.getHeight() == HEIGHT;
    }
    public static boolean permitted(int y, BlockState requested) {
        if (y > ROOF_Y) return requested.isAir();
        return y != ROOF_Y || requested.is(Blocks.BEDROCK);
    }
    public static boolean canSet(LevelHeightAccessor level, BlockPos pos, BlockState state) {
        return !active(level) || permitted(pos.getY(), state);
    }
    public static boolean canSetSection(NeverNetherSubstrateR10.SectionData data, int localY, BlockState state) {
        // Section metadata is published ONLY by the matching Nether CARVERS
        // capture; no other world receives these records. Direct section writers
        // therefore cannot bypass the ceiling after worldgen publication.
        return data == null || !data.r11Bound || permitted((data.r11Y << 4) + (localY & 15), state);
    }
    public static int buildMaxY(Level level) { return active(level) ? ROOF_Y : level.getMaxY(); }
    private static IllegalStateException invalid(String why) {
        return new IllegalStateException("NeverNether R14 roof512 profile rejected: " + why);
    }
    private static JsonObject object(byte[] bytes) {
        if (bytes.length > 65536) throw invalid("oversized profile");
        return JsonParser.parseString(new String(bytes,java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject();
    }
    private static int integer(JsonObject o,String key) {
        var v=o.get(key);
        if(v==null || !v.isJsonPrimitive() || !v.getAsJsonPrimitive().isNumber())throw invalid("not an integer: "+key);
        try{return v.getAsBigDecimal().intValueExact();}catch(ArithmeticException e){throw invalid("not an exact int: "+key);}
    }
    private static boolean bool(JsonObject o,String key) {
        var v=o.get(key);
        if(v==null || !v.isJsonPrimitive() || !v.getAsJsonPrimitive().isBoolean())throw invalid("not a boolean: "+key);
        return v.getAsBoolean();
    }
    public static void validateProfile(byte[] marker, byte[] dimension) {
        JsonObject m=object(marker), d=object(dimension);
        if (!m.get("profile").isJsonPrimitive() || !m.getAsJsonPrimitive("profile").isString()
            || !m.get("profile").getAsString().equals(PROFILE) || integer(m,"schema")!=1
            || integer(m,"bedrock_roof_y")!=ROOF_Y || integer(m,"technical_height")!=HEIGHT
            || integer(m,"technical_max_y")!=MAX_Y || integer(m,"sections")!=SECTIONS
            || integer(m,"min_y")!=MIN_Y || integer(m,"building_max_y")!=ROOF_Y
            || integer(m,"bedrock_envelope")!=5 || !m.get("dimension").getAsString().equals("minecraft:the_nether")
            || bool(m,"roof_building_allowed") || !bool(m,"new_world_required")
            || integer(d,"min_y")!=MIN_Y || integer(d,"height")!=HEIGHT
            || integer(d,"logical_height")!=ROOF_Y-MIN_Y+1) throw invalid("inconsistent dimension/profile");
    }
    private static byte[] read(java.io.InputStream in) throws IOException {
        try(in) { byte[] data=in.readNBytes(65537);if(data.length>65536)throw invalid("oversized profile resource");return data; }
    }
    public static void verifyDatapacks(Path worldRoot, Path datapacks) {
        try {
            boolean found=false;
            if (Files.isDirectory(datapacks)) try(var paths=Files.list(datapacks)) {
                for(Path path:paths.sorted().toList()) {
                    if(Files.isDirectory(path)) {
                        boolean fingerprint=Files.isRegularFile(path.resolve("nevernether-worldgen-fingerprint.json"));
                        if(!fingerprint)continue;
                        if(!Files.isRegularFile(path.resolve(MARKER)))throw invalid("old fingerprinted pack: "+path.getFileName());
                        validateProfile(read(Files.newInputStream(path.resolve(MARKER))),read(Files.newInputStream(path.resolve(DIM))));found=true;
                    } else if(Files.isRegularFile(path)&&path.getFileName().toString().endsWith(".zip")) {
                        try(ZipFile z=new ZipFile(path.toFile())) {
                            if(z.getEntry("nevernether-worldgen-fingerprint.json")==null)continue;
                            if(z.getEntry(MARKER)==null||z.getEntry(DIM)==null)throw invalid("old or missing-profile pack: "+path.getFileName());
                            validateProfile(read(z.getInputStream(z.getEntry(MARKER))),read(z.getInputStream(z.getEntry(DIM))));found=true;
                        }
                    }
                }
            }
            Path lock=worldRoot.resolve(LOCK);
            if(!found) { if(Files.exists(lock))throw invalid("height lock exists but R14 pack missing");return; }
            if(Files.exists(lock)) {
                if(!Files.readString(lock).equals(PROFILE+"\n"))throw invalid("different saved height profile");
                return;
            }
            // A native height change must never silently adopt existing Nether
            // regions without the height lock. No region is deleted or rewritten.
            List<Path> regions=new ArrayList<>();
            regions.add(worldRoot.resolve("dimensions/minecraft/the_nether/region"));
            regions.add(worldRoot.resolve("DIM-1/region"));
            regions.add(worldRoot.resolveSibling(worldRoot.getFileName()+"_nether").resolve("DIM-1/region"));
            for(Path region:regions)if(Files.isDirectory(region))try(var files=Files.list(region)) {
                if(files.anyMatch(p->p.getFileName().toString().endsWith(".mca")))throw invalid("existing unversioned Nether regions require a NEW world");
            }
            Files.createDirectories(worldRoot);
            Path temp=Files.createTempFile(worldRoot,".roof512-",".tmp");
            try {Files.writeString(temp,PROFILE+"\n");Files.move(temp,lock,StandardCopyOption.ATOMIC_MOVE);}
            finally {Files.deleteIfExists(temp);}
        } catch(IOException|com.google.gson.JsonParseException|NullPointerException ex) {
            throw invalid("cannot verify height inputs: "+ex.getMessage());
        }
    }
    /** Registry marker deliberately makes a new datapack fail on an old runtime,
     * instead of silently loading with old numeric guards disabled. */
    public record RequiredProcessor() implements StructureProcessor {
        public static final RequiredProcessor INSTANCE=new RequiredProcessor();
        public static final MapCodec<RequiredProcessor> CODEC=MapCodec.unit(INSTANCE);
        @Override public StructureTemplate.StructureBlockInfo processBlock(LevelReader level,BlockPos pos,BlockPos ref,
            BlockPos relative,StructureTemplate.StructureBlockInfo info,StructurePlaceSettings settings){return info;}
        @Override public MapCodec<RequiredProcessor> codec(){return CODEC;}
    }
}
