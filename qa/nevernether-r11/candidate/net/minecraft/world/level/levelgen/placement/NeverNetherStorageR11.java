package net.minecraft.world.level.levelgen.placement;

import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.*;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import net.minecraft.world.level.chunk.*;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/** Optional R11 storage. Snapshot + provenance travel with their section, never
 * through a sidecar file or a world-global map. Decode validates before publishing.
 * Unversioned/unknown snapshots cannot be inferred from decorated terrain.
 */
public final class NeverNetherStorageR11 {
    private NeverNetherStorageR11() { }
    public static final String KEY = "neverfolia:substrate_r11";
    public static final String PROFILE = "NN-R11-SUBSTRATE-1-REMOTE-R10-PRIORITY";
    private static final int SIZE = 4096;
    private static IllegalStateException bad(String why) { return new IllegalStateException("NN-R11 substrate: " + why); }
    private static <T extends Comparable<T>> String value(BlockState s, Property<T> p) { return p.getName(s.getValue(p)); }
    private static String name(BlockState s) {
        var p = new TreeMap<String,String>();
        for (var prop : s.getProperties()) p.put(prop.getName(),value(s,prop));
        String id = BuiltInRegistries.BLOCK.getKey(s.getBlock()).toString();
        return p.isEmpty() ? id : id+"["+String.join(",",p.entrySet().stream().map(e->e.getKey()+"="+e.getValue()).toList())+"]";
    }
    private static BlockState state(String text) {
        if (text.length()>512) throw bad("oversized state");
        try {
            BlockState s = BlockStateParser.parseForBlock(BuiltInRegistries.BLOCK,text,false).blockState();
            if (!name(s).equals(text)) throw bad("noncanonical or unknown state: "+text);
            return s;
        } catch (com.mojang.brigadier.exceptions.CommandSyntaxException e) { throw bad("invalid state: "+text); }
    }
    private static int integer(CompoundTag t,String key) { if (!(t.get(key) instanceof IntTag n)) throw bad("missing integer "+key);return n.intValue(); }
    private static long number(CompoundTag t,String key) { if (!(t.get(key) instanceof LongTag n)) throw bad("missing long "+key);return n.longValue(); }
    private static String string(CompoundTag t,String key) { if (!(t.get(key) instanceof StringTag)) throw bad("missing string "+key);return t.getString(key).orElseThrow(); }
    private static int[] ints(CompoundTag t,String key) { if (!(t.get(key) instanceof IntArrayTag a)) throw bad("missing int array "+key);return a.getAsIntArray(); }
    private static long[] longs(CompoundTag t,String key) { if (!(t.get(key) instanceof LongArrayTag a)) throw bad("missing long array "+key);return a.getAsLongArray(); }
    private static byte[] bytes(CompoundTag t,String key) { if (!(t.get(key) instanceof ByteArrayTag a)) throw bad("missing bytes "+key);return a.getAsByteArray(); }
    private static byte[] hash(byte[] data) {
        try { return MessageDigest.getInstance("SHA-256").digest(data); }
        catch(java.security.NoSuchAlgorithmException e){throw new AssertionError(e);}
    }
    private static byte[] currentHash(LevelChunkSection section) {
        try {
            var bytes = new ByteArrayOutputStream();var out = new DataOutputStream(bytes);
            var cached = new IdentityHashMap<BlockState,byte[]>();
            for (int i=0;i<SIZE;i++) {
                BlockState s=section.getBlockState(i&15,i>>8,(i>>4)&15);
                byte[] b=cached.computeIfAbsent(s,st->name(st).getBytes(java.nio.charset.StandardCharsets.UTF_8));
                out.writeInt(b.length);out.write(b);
            }
            return hash(bytes.toByteArray());
        }catch(IOException e){throw new AssertionError(e);}
    }
    /** Canonical digest excludes itself and never depends on CompoundTag iteration order. */
    private static byte[] digest(CompoundTag tag) {
        try {
            var buf=new ByteArrayOutputStream();var out=new DataOutputStream(buf);
            for(String key:List.of("Schema","ChunkX","ChunkZ","SectionY","Bits"))out.writeInt(integer(tag,key));
            out.writeLong(number(tag,"Seed"));out.writeUTF(string(tag,"Profile"));
            if (!(tag.get("Palette") instanceof ListTag palette) || palette.isEmpty() || palette.size()>SIZE)throw bad("palette bounds");
            out.writeInt(palette.size());
            for(Tag t:palette){if(!(t instanceof StringTag))throw bad("palette type");out.writeUTF(t.asString().orElseThrow());}
            for(String key:List.of("Original","External")){long[] a=longs(tag,key);if(a.length>4096)throw bad("array too large");out.writeInt(a.length);for(long n:a)out.writeLong(n);}
            for(String key:List.of("ProposalIndices","ProposalStates")){int[] a=ints(tag,key);if(a.length>SIZE)throw bad("proposal bounds");out.writeInt(a.length);for(int n:a)out.writeInt(n);}
            byte[] current=bytes(tag,"CurrentHash");if(current.length!=32)throw bad("current hash length");out.write(current);
            return hash(buf.toByteArray());
        }catch(IOException e){throw new AssertionError(e);}
    }
    public static void bind(NeverNetherSubstrateR10.SectionData d, long seed, int cx,int sy,int cz) {
        if(d.r11Bound)throw bad("double binding");
        d.r11Seed=seed;d.r11X=cx;d.r11Y=sy;d.r11Z=cz;d.r11Bound=true;
    }
    public static NeverNetherSubstrateR10.SectionData copy(NeverNetherSubstrateR10.SectionData source) {
        synchronized(source) {
            var d = new NeverNetherSubstrateR10.SectionData(source.original.copy());
            d.external.or(source.external);d.proposals.putAll(source.proposals);
            d.r11Seed=source.r11Seed;d.r11X=source.r11X;d.r11Y=source.r11Y;d.r11Z=source.r11Z;d.r11Bound=source.r11Bound;
            return d;
        }
    }
    public static CompoundTag encode(LevelChunkSection section, ChunkPos cp,int sy) {
        var d=section.neverNetherR10Data;if(d==null)return null;
        synchronized(d) {
            if(!d.r11Bound || d.r11X!=cp.x() || d.r11Z!=cp.z() || d.r11Y!=sy || sy < -8 || sy>55)throw bad("unbound/mislocated section on save");
            var ids=new LinkedHashMap<BlockState,Integer>();int[] indices=new int[SIZE];
            for(int i=0;i<SIZE;i++){
                BlockState s=d.original.get(i&15,i>>8,(i>>4)&15);
                indices[i]=ids.computeIfAbsent(s,ignored->ids.size());
            }
            int[] pi=d.proposals.keySet().stream().mapToInt(Integer::intValue).sorted().toArray();
            int[] ps=new int[pi.length];
            for(int n=0;n<pi.length;n++){
                int i=pi[n];BlockState s=d.proposals.get(i);
                if(i<0||i>=SIZE||d.external.get(i)||NeverNetherSubstrateR10.priority(s)==0||section.getBlockState(i&15,i>>8,(i>>4)&15)!=s)throw bad("invalid in-memory proposal");
                ps[n]=ids.computeIfAbsent(s,ignored->ids.size());
            }
            for(int i=0;i<SIZE;i++)if(!d.external.get(i)) {
                BlockState expected=d.proposals.getOrDefault(i,d.original.get(i&15,i>>8,(i>>4)&15));
                if(section.getBlockState(i&15,i>>8,(i>>4)&15)!=expected)throw bad("unrecorded in-memory mutation on save");
            }
            var palette=new ListTag();for(BlockState s:ids.keySet())palette.add(StringTag.valueOf(name(s)));
            int bits=ids.size()==1?0:32-Integer.numberOfLeadingZeros(ids.size()-1);
            int per=bits==0?SIZE:64/bits;long[] packed=bits==0?new long[0]:new long[(SIZE+per-1)/per];
            if(bits!=0)for(int i=0;i<SIZE;i++)packed[i/per]|=(long)indices[i] << ((i%per)*bits);
            var tag=new CompoundTag();tag.putInt("Schema",1);tag.putString("Profile",PROFILE);
            tag.putLong("Seed",d.r11Seed);tag.putInt("ChunkX",d.r11X);tag.putInt("ChunkZ",d.r11Z);tag.putInt("SectionY",d.r11Y);
            tag.put("Palette",palette);tag.putInt("Bits",bits);tag.putLongArray("Original",packed);
            tag.putLongArray("External",d.external.toLongArray());tag.putIntArray("ProposalIndices",pi);tag.putIntArray("ProposalStates",ps);
            tag.putByteArray("CurrentHash",currentHash(section));tag.putByteArray("Digest",digest(tag));return tag;
        }
    }
    public static void restore(LevelChunkSection section, CompoundTag tag, ChunkPos cp,int sy) {
        if(section.neverNetherR10Data!=null)throw bad("restore would overwrite attached metadata");
        if(integer(tag,"Schema")!=1||!string(tag,"Profile").equals(PROFILE))throw bad("unsupported storage schema/profile");
        if(integer(tag,"ChunkX")!=cp.x()||integer(tag,"ChunkZ")!=cp.z()||integer(tag,"SectionY")!=sy||sy < -8||sy>55)throw bad("section coordinate mismatch");
        byte[] check=bytes(tag,"Digest");if(check.length!=32||!MessageDigest.isEqual(check,digest(tag)))throw bad("metadata checksum mismatch");
        if(!MessageDigest.isEqual(bytes(tag,"CurrentHash"),currentHash(section)))throw bad("saved blocks and metadata do not belong to one snapshot");
        var raw=(ListTag)tag.get("Palette");var palette=new ArrayList<BlockState>();var unique=new HashSet<BlockState>();
        for(Tag t:raw){BlockState s=state(t.asString().orElseThrow());if(!unique.add(s))throw bad("duplicate palette state");palette.add(s);}
        int bits=integer(tag,"Bits"),expectedBits=palette.size()==1?0:32-Integer.numberOfLeadingZeros(palette.size()-1);
        if(bits!=expectedBits)throw bad("invalid palette width");
        int per=bits==0?SIZE:64/bits;long[] packed=longs(tag,"Original");
        if(packed.length!=(bits==0?0:(SIZE+per-1)/per))throw bad("invalid packed length");
        long[] external=longs(tag,"External");if(external.length>64)throw bad("external bitmap exceeds section");
        var d=new NeverNetherSubstrateR10.SectionData(section.getStates().copy());
        d.external.or(BitSet.valueOf(external));long mask=(1L<<bits)-1;
        for(int i=0;i<SIZE;i++){
            int id=bits==0?0:(int)(packed[i/per]>>>((i%per)*bits)&mask);
            if(id>=palette.size())throw bad("invalid palette index");
            d.original.set(i&15,i>>8,(i>>4)&15,palette.get(id));
        }
        // Reject non-zero unused bits, preventing alternate/corrupt encodings.
        if(bits!=0)for(int n=0;n<packed.length;n++){
            int used=Math.min(per,SIZE-n*per)*bits;
            if(used<64 && (packed[n]>>>used)!=0)throw bad("non-zero palette padding");
        }
        int[] pi=ints(tag,"ProposalIndices"),ps=ints(tag,"ProposalStates");
        if(pi.length!=ps.length)throw bad("proposal array mismatch");int last=-1;
        for(int n=0;n<pi.length;n++){
            int i=pi[n],s=ps[n];if(i<=last||i>=SIZE||s<0||s>=palette.size()||d.external.get(i))throw bad("invalid proposal index/provenance");
            BlockState proposed=palette.get(s);
            if(NeverNetherSubstrateR10.priority(proposed)==0||section.getBlockState(i&15,i>>8,(i>>4)&15)!=proposed)throw bad("proposal is not the saved current block");
            d.proposals.put(i,proposed);last=i;
        }
        // Every unprotected cell must still be original or a recorded own output.
        for(int i=0;i<SIZE;i++)if(!d.external.get(i)){
            BlockState expected=d.proposals.getOrDefault(i,d.original.get(i&15,i>>8,(i>>4)&15));
            if(section.getBlockState(i&15,i>>8,(i>>4)&15)!=expected)throw bad("unrecorded saved mutation");
        }
        bind(d,number(tag,"Seed"),cp.x(),sy,cp.z());
        section.neverNetherR10Data=d; // publish only fully validated state
    }
    public static void readSection(LevelChunkSection section,CompoundTag sectionTag,ChunkPos cp,int sy) {
        if(!sectionTag.contains(KEY))return;
        if(!(sectionTag.get(KEY) instanceof CompoundTag tag))throw bad("invalid metadata tag type");
        restore(section,tag,cp,sy);
    }
    public static void writeSection(LevelChunkSection section,CompoundTag sectionTag,ChunkPos cp,int sy) {
        CompoundTag tag=encode(section,cp,sy);if(tag!=null)sectionTag.put(KEY,tag);
    }
    public static void validateSectionTags(ServerLevel level,CompoundTag chunkData,ChunkStatus status) {
        boolean expected=NeverNetherSubstrateR10.scope(level)&&status.isOrAfter(ChunkStatus.CARVERS);
        if (!(chunkData.get("sections") instanceof ListTag sections)) {
            if(expected)throw bad("missing section list");
            return;
        }
        var seen=new BitSet(64);
        for(Tag raw:sections) {
            if (!(raw instanceof CompoundTag section)) {if(expected)throw bad("invalid section entry");continue;}
            boolean metadata=section.contains(KEY);
            if(!expected&&!metadata)continue;
            if(!(section.get("Y") instanceof ByteTag yTag))throw bad("missing section coordinate");
            int y=yTag.byteValue();
            if(y < -8 || y > 55) {if(metadata)throw bad("metadata outside dimension");continue;}
            if(seen.get(y+8))throw bad("duplicate saved section");seen.set(y+8);
            if(expected&&!metadata)throw bad("unversioned saved CARVERS section");
            if(metadata&&(!(section.get("block_states") instanceof CompoundTag)||!(section.get(KEY) instanceof CompoundTag)))
                throw bad("invalid section storage container");
        }
        if(expected&&seen.cardinality()!=64)throw bad("incomplete saved substrate coverage");
    }
    public static void validateWorld(ServerLevel level,LevelChunkSection[] sections,ChunkStatus status,ChunkPos cp) {
        boolean expected=NeverNetherSubstrateR10.scope(level)&&status.isOrAfter(ChunkStatus.CARVERS);
        for(int index=0;index<sections.length;index++){var s=sections[index];var d=s==null?null:s.neverNetherR10Data;
            if(d==null){if(expected)throw bad("missing persisted CARVERS substrate; existing unversioned worlds are unsupported");continue;}
            if(!NeverNetherSubstrateR10.scope(level)||!d.r11Bound||d.r11Seed!=level.getSeed()||d.r11X!=cp.x()||d.r11Z!=cp.z()||d.r11Y!=level.getMinSectionY()+index)throw bad("wrong world seed/dimension/chunk location");
        }
    }
}
