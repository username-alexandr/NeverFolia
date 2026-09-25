package net.minecraft.world.level.levelgen.placement;

import java.nio.file.*;
import java.util.Comparator;
import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.lighting.LevelLightEngine;

public final class NeverNetherFieldCleanupR15Smoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}

    private static ProtoChunk fixture(){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(2.0f).downfall(0)
            .generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY)
            .specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var factory=new PalettedContainerFactory(
            Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),Blocks.NETHERRACK.defaultBlockState(),null,
            Strategy.createForBiomes(ids),holder,null,null);
        var c=new ProtoChunk(new ChunkPos(0,0),UpgradeData.EMPTY,LevelHeightAccessor.create(-128,656),factory,null);
        c.setLightEngine(LevelLightEngine.EMPTY);return c;
    }
    private static void set(ProtoChunk c,int x,int y,int z,Block block){
        var section=c.getSection(c.getSectionIndex(y));
        section.getStates().set(x&15,y&15,z&15,block.defaultBlockState());
        section.recalcBlockCounts();
    }

    @FunctionalInterface
    private interface CheckedAction { void run() throws Exception; }

    private static void rejects(CheckedAction action,String why) throws Exception {
        try { action.run(); }
        catch (IllegalStateException | java.io.IOException expected) { checks++;return; }
        throw new AssertionError("accepted invalid native-lock case: "+why);
    }

    private static void nativeLockHardening(Path root,Path datapacks,Path marker) throws Exception {
        final String good=Files.readString(marker);
        final Path world=Files.createDirectory(root.resolve("strict"));
        final Path height=world.resolve(".neverfolia-nevernether-height.lock");
        final Path lock=world.resolve(".neverfolia-nevernether-native.lock");
        Files.writeString(height,NeverNetherHeightR14.PROFILE+"\n");
        final String[] badProfiles={
            good.replace("\"schema\":1","\"schema\":1.5"),
            good.replace("\"schema\":1","\"schema\":4294967297"),
            good.replace("\"schema\":1","\"schema\":\"1\""),
            good.replace("\"schema\":1","\"schema\":null"),
            good.replace("\"schema\":1","\"schema\":true"),
            good.replace("\"schema\":1","\"schema\":[]"),
            good.replace("\"new_world_required\":true","\"new_world_required\":\"true\""),
            good.replace("\"new_world_required\":true","\"new_world_required\":false"),
            good.replace(NeverNetherFieldCleanupR15.NATIVE_PROFILE,"NN-R14-OLD"),
            good.replace(NeverNetherHeightR14.PROFILE,"NN-OTHER-HEIGHT"),
            "[]", "null", "{", "{}", good+" ".repeat(65537)
        };
        for (int i=0;i<badProfiles.length;i++) {
            Files.writeString(marker,badProfiles[i]);
            rejects(()->NeverNetherFieldCleanupR15.verifyNativeRevision(world,datapacks),"profile "+i);
            check(!Files.exists(lock),"rejected profile must not create native lock "+i);
        }
        Files.writeString(marker,good);
        NeverNetherFieldCleanupR15.verifyNativeRevision(world,datapacks);
        check(Files.readString(lock).equals(NeverNetherFieldCleanupR15.NATIVE_PROFILE+"\n"),"strict valid profile accepted");
        var stamp=Files.getLastModifiedTime(lock);
        NeverNetherFieldCleanupR15.createNativeLock(lock);
        check(Files.getLastModifiedTime(lock).equals(stamp),"create-only publication leaves matching lock untouched");

        for (String invalid : new String[]{"", "NN-R14-OLD\n", "NN-R15-FIELD-CLEANUP", "X".repeat(257)}) {
            Files.writeString(lock,invalid);
            rejects(()->NeverNetherFieldCleanupR15.createNativeLock(lock),"competing invalid lock");
            check(Files.readString(lock).equals(invalid),"competing lock must not be overwritten");
        }
        Files.writeString(lock,NeverNetherFieldCleanupR15.NATIVE_PROFILE+"\n");
        Files.delete(marker);
        rejects(()->NeverNetherFieldCleanupR15.verifyNativeRevision(world,datapacks),"missing marker on restart");
        check(Files.readString(lock).equals(NeverNetherFieldCleanupR15.NATIVE_PROFILE+"\n"),"restart failure preserves native lock");
        Files.writeString(marker,good);
        Files.delete(height);
        rejects(()->NeverNetherFieldCleanupR15.verifyNativeRevision(world,datapacks),"orphan native lock");
        check(!Files.exists(height),"orphan rejection must not recreate height lock");
        Files.writeString(height,NeverNetherHeightR14.PROFILE+"\n");

        final Path legacy=Files.createDirectory(root.resolve("legacy-dim1"));
        Files.writeString(legacy.resolve(".neverfolia-nevernether-height.lock"),NeverNetherHeightR14.PROFILE+"\n");
        final Path region=legacy.resolve("DIM-1/region/r.0.0.mca");
        Files.createDirectories(region.getParent());Files.writeString(region,"sentinel");
        rejects(()->NeverNetherFieldCleanupR15.verifyNativeRevision(legacy,datapacks),"legacy DIM-1");
        check(Files.readString(region).equals("sentinel"),"legacy region untouched");
        check(!Files.exists(legacy.resolve(".neverfolia-nevernether-native.lock")),"legacy DIM-1 writes no native lock");

        final Path zipWorld=Files.createDirectory(root.resolve("zip-world"));
        Files.writeString(zipWorld.resolve(".neverfolia-nevernether-height.lock"),NeverNetherHeightR14.PROFILE+"\n");
        final Path zipPacks=Files.createDirectories(zipWorld.resolve("datapacks"));
        final Path zip=zipPacks.resolve("profile.zip");
        for (String payload : new String[]{good,good+" ".repeat(65537)}) {
            try (var output=new java.util.zip.ZipOutputStream(Files.newOutputStream(zip))) {
                output.putNextEntry(new java.util.zip.ZipEntry("nevernether-worldgen-fingerprint.json"));
                output.write("{}".getBytes(java.nio.charset.StandardCharsets.UTF_8));output.closeEntry();
                output.putNextEntry(new java.util.zip.ZipEntry("data/neverfolia/nevernether/native_profile.json"));
                output.write(payload.getBytes(java.nio.charset.StandardCharsets.UTF_8));output.closeEntry();
            }
            if (payload.equals(good)) {
                NeverNetherFieldCleanupR15.verifyNativeRevision(zipWorld,zipPacks);
                check(Files.readString(zipWorld.resolve(".neverfolia-nevernether-native.lock")).equals(
                    NeverNetherFieldCleanupR15.NATIVE_PROFILE+"\n"),"valid zipped profile accepted");
            } else {
                rejects(()->NeverNetherFieldCleanupR15.verifyNativeRevision(zipWorld,zipPacks),"oversized zipped profile");
                check(Files.readString(zipWorld.resolve(".neverfolia-nevernether-native.lock")).equals(
                    NeverNetherFieldCleanupR15.NATIVE_PROFILE+"\n"),"oversized zip failure preserves lock");
            }
        }
    }

    public static void main(String[] args) throws Exception{
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        var c=fixture();

        set(c,8,100,8,Blocks.AIR);
        set(c,9,100,8,Blocks.CAVE_AIR);
        set(c,8,101,8,Blocks.AIR);

        for(int x=4;x<=8;x++)set(c,x,120,5,Blocks.AIR);
        set(c,0,140,8,Blocks.AIR);

        set(c,8,10,8,Blocks.LAVA);
        set(c,7,10,8,Blocks.LAVA);
        set(c,9,10,8,Blocks.LAVA);
        set(c,8,11,8,Blocks.LAVA);
        set(c,8,9,8,Blocks.CAVE_AIR);

        set(c,12,10,12,Blocks.LAVA);
        set(c,11,10,12,Blocks.LAVA);
        set(c,13,10,12,Blocks.LAVA);

        // Exact owning-chunk shape from persisted shelf [-3109,10,-6289]:
        // one same-chunk source-lava neighbour, one missing cross-chunk side,
        // two same-chunk natural-rock sides, source lava above and air below.
        set(c,11,20,15,Blocks.LAVA);
        set(c,10,20,15,Blocks.LAVA);
        set(c,11,21,15,Blocks.LAVA);
        set(c,11,19,15,Blocks.CAVE_AIR);

        set(c,8,512,8,Blocks.BEDROCK);

        check(c.getBlockState(new BlockPos(8,100,8)).isAir(),"fixture air 1");
        check(c.getBlockState(new BlockPos(9,100,8)).isAir(),"fixture cave_air");
        check(c.getBlockState(new BlockPos(8,101,8)).isAir(),"fixture air 2");
        check(c.getBlockState(new BlockPos(4,120,5)).isAir(),"fixture 5-block cavity");
        check(c.getBlockState(new BlockPos(11,19,15)).isAir(),"fixture edge shelf support");
        var roofBefore=c.getBlockState(new BlockPos(8,512,8));
        check(roofBefore.is(Blocks.BEDROCK),"fixture roof before cleanup state="+roofBefore);

        var result=NeverNetherFieldCleanupR15.clean(c);
        check(result.microPocketBlocksFilled()==3,"micro pocket changed="+result.microPocketBlocksFilled());
        check(result.hangingLavaCellsSolidified()==2,"shelf changed="+result.hangingLavaCellsSolidified());

        // Publish the immutable post-prepass substrate exactly where R10 would.
        for (var section : c.getSections()) {
            section.neverNetherR10Data=new NeverNetherSubstrateR10.SectionData(section.getStates().copy());
        }

        check(c.getBlockState(new BlockPos(4,120,5)).isAir(),"5-block cavity pre-pass start preserved");
        check(c.getBlockState(new BlockPos(8,120,5)).isAir(),"5-block cavity pre-pass end preserved");
        set(c,6,120,5,Blocks.NETHERRACK);
        int postChanged=NeverNetherFieldCleanupR15.fillMicroPocketsPublished(c);
        check(postChanged==5,"post-FEATURES fragmented cavity/support changed="+postChanged);
        check(NeverNetherFieldCleanupR15.isNaturalRock(c.getBlockState(new BlockPos(4,120,5))),"post fragment left fill");
        var postSection=c.getSection(c.getSectionIndex(120));
        int postIndex=((120&15)<<8)|((5&15)<<4)|(4&15);
        check(postSection.neverNetherR10Data.external.get(postIndex),"post fill must be recorded as external provenance");
        check(NeverNetherFieldCleanupR15.isNaturalRock(c.getBlockState(new BlockPos(5,120,5))),"post fragment left fill 2");
        check(NeverNetherFieldCleanupR15.isNaturalRock(c.getBlockState(new BlockPos(7,120,5))),"post fragment right fill");
        check(NeverNetherFieldCleanupR15.isNaturalRock(c.getBlockState(new BlockPos(8,120,5))),"post fragment right fill 2");
        check(NeverNetherFieldCleanupR15.isNaturalRock(c.getBlockState(new BlockPos(8,9,8))),"post fill under repaired interior shelf");
        check(c.getBlockState(new BlockPos(11,19,15)).isAir(),"edge shelf support remains because it touches chunk boundary");
        var pocketA=c.getBlockState(new BlockPos(8,100,8));
        var pocketB=c.getBlockState(new BlockPos(9,100,8));
        var pocketC=c.getBlockState(new BlockPos(8,101,8));
        check(NeverNetherFieldCleanupR15.isNaturalRock(pocketA),"micro pocket fill state="+pocketA);
        check(NeverNetherFieldCleanupR15.isNaturalRock(pocketB),"micro cave_air fill state="+pocketB);
        check(NeverNetherFieldCleanupR15.isNaturalRock(pocketC),"micro vertical fill state="+pocketC);
        check(c.getBlockState(new BlockPos(0,140,8)).isAir(),"edge cavity preserved");
        var shelfA=c.getBlockState(new BlockPos(8,10,8));
        var shelfB=c.getBlockState(new BlockPos(11,20,15));
        check(NeverNetherFieldCleanupR15.isNaturalRock(shelfA),"hanging shelf solidified state="+shelfA);
        check(NeverNetherFieldCleanupR15.isNaturalRock(shelfB),"edge hanging shelf solidified state="+shelfB);
        check(c.getBlockState(new BlockPos(12,10,12)).is(Blocks.LAVA),"supported lava preserved");
        check(c.getBlockState(new BlockPos(8,512,8)).is(Blocks.BEDROCK),"roof untouched");
        check(NeverNetherFieldCleanupR15.sourceLava(Blocks.LAVA.defaultBlockState()),"source lava classifier");
        check(NeverNetherFieldCleanupR15.isNaturalRock(Blocks.BLACKSTONE.defaultBlockState()),"rock classifier");

        check(BuiltInRegistries.STRUCTURE_PROCESSOR
            .getOptional(Identifier.fromNamespaceAndPath("neverfolia","field_r15_required")).isPresent(),
            "R15 required processor registered");

        Path lockRoot=Files.createTempDirectory("nn-r15-lock-");
        try {
            Path datapacks=lockRoot.resolve("datapacks");
            Path profile=datapacks.resolve("profile");
            Files.createDirectories(profile);
            Files.writeString(profile.resolve("nevernether-worldgen-fingerprint.json"),"{}\n");

            NeverNetherFieldCleanupR15.verifyNativeRevision(lockRoot,datapacks);
            check(!Files.exists(lockRoot.resolve(".neverfolia-nevernether-native.lock")),"plain world must not receive R15 lock");

            Files.writeString(lockRoot.resolve(".neverfolia-nevernether-height.lock"),NeverNetherHeightR14.PROFILE+"\n");
            try {
                NeverNetherFieldCleanupR15.verifyNativeRevision(lockRoot,datapacks);
                throw new AssertionError("R15 runtime accepted R14-only datapack");
            } catch (IllegalStateException expected) {
                checks++;
            }

            Path nativeMarker=profile.resolve("data/neverfolia/nevernether/native_profile.json");
            Files.createDirectories(nativeMarker.getParent());
            Files.writeString(nativeMarker,
                "{\"schema\":1,\"profile\":\""+NeverNetherFieldCleanupR15.NATIVE_PROFILE+
                "\",\"requires_height_profile\":\""+NeverNetherHeightR14.PROFILE+
                "\",\"new_world_required\":true}\n");

            NeverNetherFieldCleanupR15.verifyNativeRevision(lockRoot,datapacks);
            Path nativeLock=lockRoot.resolve(".neverfolia-nevernether-native.lock");
            check(Files.readString(nativeLock).equals(NeverNetherFieldCleanupR15.NATIVE_PROFILE+"\n"),"new R15 native lock");
            NeverNetherFieldCleanupR15.verifyNativeRevision(lockRoot,datapacks);
            check(Files.readString(nativeLock).equals(NeverNetherFieldCleanupR15.NATIVE_PROFILE+"\n"),"R15 restart lock");

            Files.writeString(nativeLock,"NN-R14-OLD\n");
            try {
                NeverNetherFieldCleanupR15.verifyNativeRevision(lockRoot,datapacks);
                throw new AssertionError("native revision mismatch accepted");
            } catch (IllegalStateException expected) {
                checks++;
            }

            Path legacy=Files.createDirectory(lockRoot.resolve("legacy"));
            Files.writeString(legacy.resolve(".neverfolia-nevernether-height.lock"),NeverNetherHeightR14.PROFILE+"\n");
            Path region=legacy.resolve("dimensions/minecraft/the_nether/region");
            Files.createDirectories(region);
            Files.writeString(region.resolve("r.0.0.mca"),"sentinel");
            try {
                NeverNetherFieldCleanupR15.verifyNativeRevision(legacy,datapacks);
                throw new AssertionError("existing R14-only Nether adopted by R15");
            } catch (IllegalStateException expected) {
                checks++;
            }
            check(!Files.exists(legacy.resolve(".neverfolia-nevernether-native.lock")),"rejected legacy world writes no R15 lock");

            Path sibling=Files.createDirectory(lockRoot.resolve("sibling"));
            Files.writeString(sibling.resolve(".neverfolia-nevernether-height.lock"),NeverNetherHeightR14.PROFILE+"\n");
            Path siblingRegion=lockRoot.resolve("sibling_nether/DIM-1/region");
            Files.createDirectories(siblingRegion);
            Files.writeString(siblingRegion.resolve("r.0.0.mca"),"sentinel");
            try {
                NeverNetherFieldCleanupR15.verifyNativeRevision(sibling,datapacks);
                throw new AssertionError("Bukkit sibling R14-only Nether adopted by R15");
            } catch (IllegalStateException expected) {
                checks++;
            }
            nativeLockHardening(lockRoot,datapacks,nativeMarker);
        } finally {
            try (var paths=Files.walk(lockRoot)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }

        out.println("PASS NeverNetherFieldCleanupR15Smoke checks="+checks+" "+result);
    }
}
