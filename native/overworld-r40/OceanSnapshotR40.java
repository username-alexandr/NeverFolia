package net.minecraft.world.level.chunk;

import java.io.*;
import java.util.BitSet;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.InflaterInputStream;

/** Versioned, bounded snapshot codec. No world access and no shared mutable cache. */
public final class OceanSnapshotR40 {
    public static final int LOW=-511,HIGH=128,HEIGHT=640,CELLS=256*HEIGHT;
    private static final int MAGIC=0x4e4f3430,SCHEMA=1,SIZE=24+CELLS+256+512;
    private OceanSnapshotR40() {}
    public record Data(byte[] cells,boolean[] sky,BitSet boundaryLava) {}
    public static byte[] encode(long seed,int cx,int cz,byte[] cells,boolean[] sky,BitSet boundary) {
        validate(cells,sky,boundary);
        try {
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try(DataOutputStream out=new DataOutputStream(new DeflaterOutputStream(bytes))) {
                out.writeInt(MAGIC);out.writeInt(SCHEMA);out.writeLong(seed);out.writeInt(cx);out.writeInt(cz);
                out.write(cells);
                for(boolean b:sky)out.writeByte(b?1:0);
                for(int c=0;c<256;c++) {out.writeByte(boundary.get(c*HEIGHT)?1:0);out.writeByte(boundary.get(c*HEIGHT+HEIGHT-1)?1:0);}
            }
            return bytes.toByteArray();
        }catch(IOException failure){throw new IllegalStateException("Cannot encode ocean snapshot",failure);}
    }
    public static Data decode(byte[] encoded,long seed,int cx,int cz) {
        if(encoded==null||encoded.length<8||encoded.length>SIZE+4096)throw new IllegalStateException("Invalid ocean snapshot size");
        try {
            byte[] bytes;
            try(InflaterInputStream compressed=new InflaterInputStream(new ByteArrayInputStream(encoded))) {bytes=compressed.readNBytes(SIZE+1);}
            if(bytes.length!=SIZE)throw new IOException("Invalid inflated snapshot length");
            try(DataInputStream in=new DataInputStream(new ByteArrayInputStream(bytes))) {
                if(in.readInt()!=MAGIC||in.readInt()!=SCHEMA||in.readLong()!=seed||in.readInt()!=cx||in.readInt()!=cz)throw new IOException("Wrong snapshot identity");
                byte[] cells=in.readNBytes(CELLS);boolean[] sky=new boolean[256];BitSet boundary=new BitSet(CELLS);
                for(int c=0;c<256;c++)sky[c]=bit(in);
                for(int c=0;c<256;c++) {if(bit(in))boundary.set(c*HEIGHT);if(bit(in))boundary.set(c*HEIGHT+HEIGHT-1);}
                validate(cells,sky,boundary);
                return new Data(cells,sky,boundary);
            }
        }catch(IOException|IllegalArgumentException failure){throw new IllegalStateException("Invalid persisted ocean snapshot",failure);}
    }
    private static boolean bit(DataInputStream in)throws IOException {int value=in.readUnsignedByte();if(value>1)throw new IOException("Invalid boolean");return value==1;}
    private static void validate(byte[] cells,boolean[] sky,BitSet boundary) {
        if(cells.length!=CELLS||sky.length!=256||boundary.length()>CELLS)throw new IllegalArgumentException("Wrong snapshot arrays");
        for(byte value:cells)if(value<SpanOceanR40.UNKNOWN||value>SpanOceanR40.ICE)throw new IllegalArgumentException("Invalid snapshot cell");
        for(int i=boundary.nextSetBit(0);i>=0;i=boundary.nextSetBit(i+1))if(i%HEIGHT!=0&&i%HEIGHT!=HEIGHT-1)throw new IllegalArgumentException("Boundary barrier is not on vertical boundary");
    }
}
