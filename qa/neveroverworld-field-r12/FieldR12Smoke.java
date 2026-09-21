package net.minecraft.world.level.chunk;

import java.lang.reflect.*;
import java.util.*;
import java.util.function.*;
import net.minecraft.SharedConstants;
import net.minecraft.core.*;
import net.minecraft.server.Bootstrap;
import net.minecraft.tags.BlockTags;
import net.minecraft.util.RandomSource;
import net.minecraft.util.valueproviders.ConstantInt;
import net.minecraft.world.level.*;
import net.minecraft.world.level.biome.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.feature.*;
import net.minecraft.world.level.levelgen.feature.configurations.*;
import net.minecraft.world.level.levelgen.feature.featuresize.TwoLayersFeatureSize;
import net.minecraft.world.level.levelgen.feature.foliageplacers.*;
import net.minecraft.world.level.levelgen.feature.stateproviders.BlockStateProvider;
import net.minecraft.world.level.levelgen.feature.trunkplacers.StraightTrunkPlacer;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.lighting.LevelLightEngine;
import net.minecraft.world.level.material.FluidState;

/** Native block/feature/ProtoChunk regressions. Map-backed WorldGenLevel is a
 * deterministic fixture, not a natural-world or multiplayer acceptance. */
public final class FieldR12Smoke {
    private static int checks;
    private static void check(boolean b,String why){if(!b)throw new AssertionError(why);checks++;}
    private static void tag(Block block,net.minecraft.tags.TagKey<Block> key)throws Exception{
        var holder=block.builtInRegistryHolder();
        Method m=Arrays.stream(holder.getClass().getDeclaredMethods()).filter(a->a.getName().equals("bindTags")&&a.getParameterCount()==1&&a.getParameterTypes()[0].isInstance(Set.of(key))).findFirst().orElseThrow();
        m.setAccessible(true);m.invoke(holder,Set.of(key));check(block.defaultBlockState().is(key),"tag fixture");
    }
    private static final class TestWorld implements InvocationHandler {
        final Map<BlockPos,BlockState> blocks=new HashMap<>();
        final Map<Long,ProtoChunk> chunks=new HashMap<>();
        final int terrain; boolean rejectWrites; int writes;
        final WorldGenLevel world=(WorldGenLevel)Proxy.newProxyInstance(WorldGenLevel.class.getClassLoader(),new Class<?>[]{WorldGenLevel.class},this);
        TestWorld(int terrain){this.terrain=terrain;}
        BlockState at(BlockPos p){return blocks.getOrDefault(p,Blocks.AIR.defaultBlockState());}
        @SuppressWarnings("unchecked") public Object invoke(Object p,Method m,Object[] a)throws Throwable{
            switch(m.getName()){
                case "getBlockState":return at((BlockPos)a[0]);
                case "getFluidState":return at((BlockPos)a[0]).getFluidState();
                case "isStateAtPosition":return ((Predicate<BlockState>)a[1]).test(at((BlockPos)a[0]));
                case "isFluidAtPosition":return ((Predicate<FluidState>)a[1]).test(at((BlockPos)a[0]).getFluidState());
                case "getMinY":return -512;
                case "getMaxY":return 512;
                case "getHeight":return a==null||a.length==0?1024:terrain;
                case "getSeed":return -2996952393010080672L;
                case "ensureCanWrite":return !rejectWrites;
                case "setBlock":if(rejectWrites)return false;blocks.put(((BlockPos)a[0]).immutable(),(BlockState)a[1]);writes++;return true;
                case "getChunk":{
                    if(a.length==1&&a[0] instanceof BlockPos pos)return chunks.computeIfAbsent(ChunkPos.pack(pos.getX()>>4,pos.getZ()>>4),k->fixture(new ChunkPos(pos.getX()>>4,pos.getZ()>>4),59));
                    break;
                }
                case "toString":return "FIELD-R12 map fixture";
                case "hashCode":return System.identityHashCode(p);
                case "equals":return p==a[0];
                default:break;
            }
            if(m.isDefault())return InvocationHandler.invokeDefault(p,m,a);
            throw new UnsupportedOperationException("Unimplemented fixture API: "+m);
        }
    }
    private static void treeTransactions()throws Exception{
        for(int submerged=0;submerged<=5;submerged++){
            TestWorld w=new TestWorld(100);
            var tx=new NeverOverworldTreePlacementR12.Proposal(w.world,true);
            BlockPos oldTree=new BlockPos(3,80,3);w.blocks.put(oldTree,Blocks.BIRCH_LOG.defaultBlockState());
            for(int y=129-submerged;y<=136;y++)tx.view().setBlock(new BlockPos(8,y,8),Blocks.OAK_LOG.defaultBlockState(),19);
            check(w.writes==0,"no proposal published before decision");
            check(tx.view().isStateAtPosition(new BlockPos(8,135,8),s->s.is(Blocks.OAK_LOG)),"staged log visible to trunk/foliage queries");
            check(tx.acceptAndCommit()==(submerged<=3),"exact submerged block quota "+submerged);
            check(w.writes==(submerged<=3?8+submerged:0),"rejected proposal did not leave stump/dirt");
            check(w.at(oldTree).is(Blocks.BIRCH_LOG),"unrelated existing underwater tree preserved");
        }
        TestWorld w=new TestWorld(75);var tx=new NeverOverworldTreePlacementR12.Proposal(w.world,true);
        var config=new TreeConfiguration.TreeConfigurationBuilder(BlockStateProvider.simple(Blocks.OAK_LOG),new StraightTrunkPlacer(6,0,0),
            BlockStateProvider.simple(Blocks.OAK_LEAVES),new BlobFoliagePlacer(ConstantInt.of(2),ConstantInt.of(0),3),new TwoLayersFeatureSize(1,0,1),BlockStateProvider.simple(Blocks.DIRT)).build();
        Method core=TreeFeature.class.getDeclaredMethod("doPlace",WorldGenLevel.class,RandomSource.class,BlockPos.class,BiConsumer.class,BiConsumer.class,FoliagePlacer.FoliageSetter.class,TreeConfiguration.class);
        core.setAccessible(true);
        Set<BlockPos> leaves=new HashSet<>();
        BiConsumer<BlockPos,BlockState> setter=(p,s)->tx.view().setBlock(p,s,19);
        FoliagePlacer.FoliageSetter fs=new FoliagePlacer.FoliageSetter(){
            public void set(BlockPos p,BlockState s){leaves.add(p.immutable());setter.accept(p,s);}
            public boolean isSet(BlockPos p){return leaves.contains(p);}
        };
        check((Boolean)core.invoke(new TreeFeature(TreeConfiguration.CODEC),tx.view(),RandomSource.create(7),new BlockPos(8,75,8),setter,setter,fs,config),"actual vanilla trunk/foliage candidate created");
        check(!leaves.isEmpty(),"native foliage created");
        check(!tx.acceptAndCommit(),"native wholly submerged standing proposal vetoed");
        check(w.writes==0&&w.blocks.isEmpty(),"native rejection leaves no roots, soil, logs or leaves");
        TestWorld cave=new TestWorld(180);var caveTx=new NeverOverworldTreePlacementR12.Proposal(cave.world,true);
        caveTx.view().setBlock(new BlockPos(8,70,8),Blocks.OAK_LOG.defaultBlockState(),19);
        check(caveTx.acceptAndCommit(),"dry cave is not classified as ocean solely by Y");
        TestWorld denied=new TestWorld(90);denied.rejectWrites=true;var bad=new NeverOverworldTreePlacementR12.Proposal(denied.world,true);
        check(!bad.view().setBlock(new BlockPos(8,135,8),Blocks.OAK_LOG.defaultBlockState(),19),"write radius respected");
        check(!bad.acceptAndCommit()&&denied.writes==0,"out-of-zone proposal is unpublished");
        TestWorld wet=new TestWorld(90);var ft=new NeverOverworldTreePlacementR12.Proposal(wet.world,true);
        for(int x=-10;x<=10;x++)for(int z=-10;z<=10;z++){
            wet.blocks.put(new BlockPos(x,90,z),Blocks.STONE.defaultBlockState());
            for(int y=91;y<=98;y++)wet.blocks.put(new BlockPos(x,y,z),Blocks.WATER.defaultBlockState());
        }
        check(NeverOverworldTreePlacementR12.fallenPosition(ft.view(),new BlockPos(0,91,0)),"actual water allowed for fallen log");
        var fc=new FallenTreeConfiguration.FallenTreeConfigurationBuilder(BlockStateProvider.simple(Blocks.BIRCH_LOG),ConstantInt.of(8)).build();
        new FallenTreeFeature(FallenTreeConfiguration.CODEC).place(new FeaturePlaceContext<>(Optional.empty(),ft.view(),null,RandomSource.create(19),new BlockPos(0,91,0),fc));
        ft.commit();
        long horizontal=wet.blocks.values().stream().filter(s->s.is(Blocks.BIRCH_LOG)&&s.getValue(BlockStateProperties.AXIS)!=Direction.Axis.Y).count();
        check(horizontal==6,"actual FallenTreeFeature placed complete horizontal log in water: "+horizontal);
    }
    private static ProtoChunk fixture(ChunkPos cp,int ground){
        var biome=new Biome.BiomeBuilder().hasPrecipitation(false).temperature(.5f).downfall(0).generationSettings(BiomeGenerationSettings.EMPTY).mobSpawnSettings(MobSpawnSettings.EMPTY).specialEffects(new BiomeSpecialEffects.Builder().waterColor(0).build()).build();
        var holder=Holder.direct(biome);var ids=new IdMapper<Holder<Biome>>();ids.add(holder);
        var factory=new PalettedContainerFactory(Strategy.createForBlockStates(Block.BLOCK_STATE_REGISTRY),Blocks.AIR.defaultBlockState(),null,Strategy.createForBiomes(ids),holder,null,null);
        var c=new ProtoChunk(cp,UpgradeData.EMPTY,LevelHeightAccessor.create(-512,1024),factory,null);c.setLightEngine(LevelLightEngine.EMPTY);
        for(int x=0;x<16;x++)for(int z=0;z<16;z++)put(c,cp.getMinBlockX()+x,ground,cp.getMinBlockZ()+z,Blocks.STONE.defaultBlockState());
        c.setPersistedStatus(ChunkStatus.INITIALIZE_LIGHT);return c;
    }
    private static void put(ProtoChunk c,int x,int y,int z,BlockState s){var sec=c.getSection(c.getSectionIndex(y));sec.getStates().set(x&15,y&15,z&15,s);sec.recalcBlockCounts();}
    private static void flood(ProtoChunk c)throws Exception{
        Heightmap.primeHeightmaps(c,EnumSet.of(Heightmap.Types.OCEAN_FLOOR_WG,Heightmap.Types.WORLD_SURFACE_WG));
        Method m=NeverOverworldFlood.class.getDeclaredMethod("floodSurfaceConnectedVolume",ChunkAccess.class,int.class,int.class,BlockState.class);m.setAccessible(true);
        m.invoke(null,c,-511,128,Blocks.WATER.defaultBlockState());NeverOverworldFloodBoundaryR11.floodBoundaryComponents(c);
        NeverOverworldSubmergedRemnants.clean(c);
    }
    private static void dryMines()throws Exception{
        for(int y:new int[]{60,-150}){
            var pieces=List.of(new BoundingBox(-4,y,7,19,y+2,9),new BoundingBox(15,y,7,17,y+2,13));
            Map<Integer,ProtoChunk> leftFirst=new HashMap<>(),rightFirst=new HashMap<>();
            for(var series:List.of(leftFirst,rightFirst))for(int cx=-1;cx<=1;cx++){
                ProtoChunk c=fixture(new ChunkPos(cx,0),y-1);
                for(int x=cx*16;x<cx*16+16;x++)for(int z=0;z<16;z++)for(int h=y;h<=y+4;h++)put(c,x,h,z,Blocks.WATER.defaultBlockState());
                NeverOverworldDryMinesR12.recordBoxes(c,pieces);
                // Persist/reload the real Bukkit chunk metadata container.
                var saved=c.persistentDataContainer.toTagCompound();
                ProtoChunk restored=fixture(new ChunkPos(cx,0),y-1);restored.persistentDataContainer.putAll(saved);
                check(NeverOverworldDryMinesR12.mask(c).interior.equals(NeverOverworldDryMinesR12.mask(restored).interior),"pre-FULL metadata round-trip");
                if(cx==0)put(c,14,y,8,Blocks.RAIL.defaultBlockState());
                series.put(cx,c);
            }
            for(int cx:new int[]{-1,0,1}){NeverOverworldDryMinesR12.prepare(leftFirst.get(cx));flood(leftFirst.get(cx));}
            for(int cx:new int[]{1,0,-1}){NeverOverworldDryMinesR12.prepare(rightFirst.get(cx));flood(rightFirst.get(cx));}
            for(int x=-16;x<32;x++)for(int z=0;z<16;z++)for(int h=y-1;h<=y+4;h++){
                ProtoChunk a=leftFirst.get(x>>4),b=rightFirst.get(x>>4);BlockPos pos=new BlockPos(x,h,z);
                check(a.getBlockState(pos).equals(b.getBlockState(pos)),"mine order independence");
                if(pieces.stream().anyMatch(box->box.isInside(pos)))check(a.getBlockState(pos).getFluidState().isEmpty(),"mine dry at "+pos);
            }
            check(leftFirst.get(0).getBlockState(new BlockPos(14,y,8)).is(Blocks.RAIL),"mine rail preserved");
            check(leftFirst.get(0).getBlockState(new BlockPos(3,y,3)).is(Blocks.WATER),"unrelated cavern remains floodable");
            check(leftFirst.get(1).getBlockState(new BlockPos(16,y+1,8)).isAir(),"corridor junction is not sealed at chunk edge");
            check(leftFirst.get(0).getBlockState(new BlockPos(10,y+3,8)).is(y<0?Blocks.DEEPSLATE:Blocks.STONE),"physical roof seal prevents fluid ingress");
            ProtoChunk full=leftFirst.get(0);full.setPersistedStatus(ChunkStatus.FULL);
            put(full,14,y+1,8,Blocks.WATER.defaultBlockState());
            check(NeverOverworldDryMinesR12.prepare(full)==0&&full.getBlockState(new BlockPos(14,y+1,8)).is(Blocks.WATER),"FULL/player-time water is not erased");
        }
    }
    private static void ore() {
        long seed=-2996952393010080672L;
        for(int kind=1;kind<=8;kind++){
            int old=0,now=0;
            for(int n=0;n<100000;n++){
                int x=n-50000,y=-512+(n%1024),z=n*31;
                boolean a=NeverOverworldOreScarcityFieldR10.retain(seed,x,y,z,kind,50);
                boolean b=NeverOverworldOreScarcityFieldR10.retain(seed,x,y,z,kind,25);
                check(!b||a,"new ore mask is a strict subset, not a reroll");if(a)old++;if(b)now++;
            }
            check((double)now/old>.48&&(double)now/old<.52,"another ~50% reduction for resource "+kind);
        }
        check(NeverOverworldOreScarcityFieldR10.KEEP_PERCENT==25,"installed ore profile");
        var c=fixture(new ChunkPos(-2,3),-200);
        for(int y=-160;y<-144;y++)for(int x=-32;x<-16;x++)for(int z=48;z<64;z++)put(c,x,y,z,Blocks.DEEPSLATE_DIAMOND_ORE.defaultBlockState());
        int changed=NeverOverworldOreScarcityFieldR10.thin(seed,c);
        check(changed>2900&&changed<3300,"native ore writer removed about 75% before old 50% gate");
        check(NeverOverworldOreScarcityFieldR10.thin(seed,c)==0,"ore pass idempotence");
    }
    public static void main(String[] args)throws Exception{
        var out=System.out;SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        tag(Blocks.OAK_LOG,BlockTags.LOGS);tag(Blocks.BIRCH_LOG,BlockTags.LOGS);tag(Blocks.OAK_LEAVES,BlockTags.LEAVES);
        treeTransactions();dryMines();ore();
        out.println("PASS FieldR12Smoke checks="+checks+" native-tree-admission/fallen-water/mines-cross-chunk/PDC/ore-subset");out.flush();
        if(out.checkError())throw new IllegalStateException("smoke output failed");
    }
}
