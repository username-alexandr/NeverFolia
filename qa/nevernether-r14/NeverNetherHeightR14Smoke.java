import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.LevelHeightAccessor;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.levelgen.placement.NeverNetherHeightR14;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;

/** Real block registry and filesystem guard tests. Not world generation evidence. */
public final class NeverNetherHeightR14Smoke {
    private static int count;
    private static void check(boolean value,String name){if(!value)throw new AssertionError(name);count++;}
    private static void rejects(Runnable run,String name){try{run.run();}catch(RuntimeException expected){count++;return;}throw new AssertionError("Accepted "+name);}
    private static JsonObject marker(){return JsonParser.parseString("{\"profile\":\"NN-R14-SUBSTRATE-1-ROOF512\",\"schema\":1,\"bedrock_roof_y\":512,\"technical_height\":656,\"technical_max_y\":527,\"sections\":41,\"min_y\":-128,\"building_max_y\":512,\"bedrock_envelope\":5,\"dimension\":\"minecraft:the_nether\",\"roof_building_allowed\":false,\"new_world_required\":true}").getAsJsonObject();}
    private static JsonObject dimension(){return JsonParser.parseString("{\"min_y\":-128,\"height\":656,\"logical_height\":641}").getAsJsonObject();}
    private static byte[] bytes(JsonObject o){return o.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);}
    private static void validate(JsonObject m,JsonObject d){NeverNetherHeightR14.validateProfile(bytes(m),bytes(d));}
    private static Path pack(Path world,JsonObject m)throws Exception {
        var p=world.resolve("datapacks/profile.zip");Files.createDirectories(p.getParent());
        try(var z=new ZipOutputStream(Files.newOutputStream(p))){
            z.putNextEntry(new ZipEntry("nevernether-worldgen-fingerprint.json"));z.write("{}".getBytes());z.closeEntry();
            if(m!=null){z.putNextEntry(new ZipEntry("data/neverfolia/nevernether/height_profile.json"));z.write(bytes(m));z.closeEntry();
                z.putNextEntry(new ZipEntry("data/minecraft/dimension_type/the_nether.json"));z.write(bytes(dimension()));z.closeEntry();}
        }return p;
    }
    public static void main(String[] args)throws Exception {
        var output=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        validate(marker(),dimension());count++;
        check(NeverNetherHeightR14.ROOF_Y==512,"exact roof not511");
        check(NeverNetherHeightR14.HEIGHT%16==0&&NeverNetherHeightR14.SECTIONS==41,"storage sections");
        check(!NeverNetherHeightR14.active(null),"null scope");
        check(!NeverNetherHeightR14.active(LevelHeightAccessor.create(-128,656)),"numeric bounds alone not scope");
        for(int y=500;y<=530;y++)for(var b:List.of(Blocks.AIR,Blocks.CAVE_AIR,Blocks.BEDROCK,Blocks.STONE,Blocks.LAVA))
            check(NeverNetherHeightR14.permitted(y,b.defaultBlockState())==(y==512?b==Blocks.BEDROCK:y>512?b.defaultBlockState().isAir():true),"write "+y+" "+b);
        for(String field:List.of("schema","bedrock_roof_y","technical_height","technical_max_y","sections","min_y","building_max_y","bedrock_envelope")) {
            var m=marker();m.addProperty(field,1.5);rejects(()->validate(m,dimension()),"fractional "+field);
            m.addProperty(field,"512");rejects(()->validate(m,dimension()),"string "+field);
        }
        for(String field:List.of("roof_building_allowed","new_world_required")) {
            var m=marker();m.addProperty(field,"false");rejects(()->validate(m,dimension()),"string boolean "+field);
        }
        var old=marker();old.addProperty("profile","NN-R13-SUBSTRATE-1-RECONCILED-NATURAL");rejects(()->validate(old,dimension()),"old storage profile");
        var d=dimension();d.addProperty("height",1024);rejects(()->validate(marker(),d),"old height");
        check(BuiltInRegistries.STRUCTURE_PROCESSOR.getOptional(Identifier.fromNamespaceAndPath("neverfolia","height_r14_required")).isPresent(),"runtime marker registered");
        Path root=Files.createTempDirectory("nn-roof512-test-");
        try {
            var world=root.resolve("new");pack(world,marker());NeverNetherHeightR14.verifyDatapacks(world,world.resolve("datapacks"));
            var lock=world.resolve(".neverfolia-nevernether-height.lock");check(Files.readString(lock).equals(NeverNetherHeightR14.PROFILE+"\n"),"new lock");
            NeverNetherHeightR14.verifyDatapacks(world,world.resolve("datapacks"));check(Files.readString(lock).equals(NeverNetherHeightR14.PROFILE+"\n"),"restart same lock");
            Files.delete(world.resolve("datapacks/profile.zip"));rejects(()->NeverNetherHeightR14.verifyDatapacks(world,world.resolve("datapacks")),"locked world no pack");
            var legacy=root.resolve("legacy");pack(legacy,null);rejects(()->NeverNetherHeightR14.verifyDatapacks(legacy,legacy.resolve("datapacks")),"R13 pack");
            check(!Files.exists(legacy.resolve(".neverfolia-nevernether-height.lock")),"rejected old pack writes no lock");
            for(String region:List.of("dimensions/minecraft/the_nether/region","DIM-1/region")) {
                var used=Files.createTempDirectory(root,"existing");pack(used,marker());var file=used.resolve(region+"/r.0.0.mca");Files.createDirectories(file.getParent());Files.writeString(file,"sentinel");
                rejects(()->NeverNetherHeightR14.verifyDatapacks(used,used.resolve("datapacks")),"old Nether "+region);check(Files.readString(file).equals("sentinel"),"existing region not edited");
                check(!Files.exists(used.resolve(".neverfolia-nevernether-height.lock")),"no adoption lock");
            }
            var sibling=root.resolve("sibling");pack(sibling,marker());var file=root.resolve("sibling_nether/DIM-1/region/r.0.0.mca");Files.createDirectories(file.getParent());Files.writeString(file,"sentinel");
            rejects(()->NeverNetherHeightR14.verifyDatapacks(sibling,sibling.resolve("datapacks")),"Bukkit sibling Nether");
            var plain=root.resolve("vanilla");Files.createDirectories(plain);NeverNetherHeightR14.verifyDatapacks(plain,plain.resolve("datapacks"));check(!Files.exists(plain.resolve(".neverfolia-nevernether-height.lock")),"plain other world unchanged");
        }finally{try(var paths=Files.walk(root)){for(Path p:paths.sorted(Comparator.reverseOrder()).toList())Files.delete(p);}}
        output.println("NN-R14 native height/registry/profile/filesystem: "+count+" checks passed; no world generated");
    }
}
