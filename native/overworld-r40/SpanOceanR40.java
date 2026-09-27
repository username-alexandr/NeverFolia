package net.minecraft.world.level.chunk;

import java.util.Arrays;
import java.util.BitSet;
import java.util.Objects;

/** Pure ocean connectivity on an immutable, column-major snapshot.
 * Each column stores all Y cells contiguously. Vertical spans reduce the queue
 * from one integer per voxel to one per passable vertical interval. Missing
 * space is never an ocean witness. A negative result is not global enclosure.
 */
public final class SpanOceanR40 {
    public static final byte UNKNOWN=0, SOLID=1, PROTECTED=2, AIR=3, WATER=4, LAVA=5, REMOVABLE=6, ICE=7;
    public static final int MAX_CELLS=30_000_000;
    private SpanOceanR40() {}
    public record Proof(BitSet connected, int visitedCells, int spans, int unprovenAir) {}
    private static boolean passable(byte code) { return code==AIR || code==WATER || code==REMOVABLE; }

    public static Proof solve(int width,int depth,int height,byte[] cells,boolean[] sky,BitSet boundaryLava) {
        Objects.requireNonNull(cells);Objects.requireNonNull(sky);Objects.requireNonNull(boundaryLava);
        if(width<1||depth<1||height<1)throw new IllegalArgumentException("Nonpositive dimensions");
        long areaLong=(long)width*depth,countLong=areaLong*height;
        if(areaLong>MAX_CELLS||countLong>MAX_CELLS||countLong<1)throw new IllegalArgumentException("Volume exceeds bounded budget");
        int area=(int)areaLong,count=(int)countLong;
        if(cells.length!=count||sky.length!=area||boundaryLava.length()>count)throw new IllegalArgumentException("Mismatched snapshot arrays");
        BitSet blocked=(BitSet)boundaryLava.clone();
        for(int i=0;i<count;i++) {
            int code=cells[i];if(code<UNKNOWN||code>ICE)throw new IllegalArgumentException("Unknown cell class");
            if(code!=LAVA)continue;
            int y=i%height,c=i/height,x=c%width,z=c/width;
            if(y>0)blocked.set(i-1);if(y+1<height)blocked.set(i+1);
            if(x>0)blocked.set(i-height);if(x+1<width)blocked.set(i+height);
            if(z>0)blocked.set(i-width*height);if(z+1<depth)blocked.set(i+width*height);
        }
        int[] starts=new int[area+1];Spans spans=new Spans(Math.min(1024,count));
        for(int c=0;c<area;c++) {
            starts[c]=spans.size;int y=0,base=c*height;
            while(y<height) {
                while(y<height&&(!passable(cells[base+y])||blocked.get(base+y)))y++;
                if(y==height)break;
                int lo=y++;
                while(y<height&&passable(cells[base+y])&&!blocked.get(base+y))y++;
                spans.add(c,lo,y-1);
            }
        }
        starts[area]=spans.size;
        BitSet reached=new BitSet(spans.size);int[] queue=new int[spans.size];int head=0,tail=0;
        for(int c=0;c<area;c++) {
            int last=starts[c+1]-1;
            if(sky[c]&&last>=starts[c]&&spans.hi[last]==height-1) {reached.set(last);queue[tail++]=last;}
        }
        while(head<tail) {
            int s=queue[head++],c=spans.column[s],x=c%width,z=c/width;
            if(x>0)tail=offer(c-1,spans.lo[s],spans.hi[s],starts,spans,reached,queue,tail);
            if(x+1<width)tail=offer(c+1,spans.lo[s],spans.hi[s],starts,spans,reached,queue,tail);
            if(z>0)tail=offer(c-width,spans.lo[s],spans.hi[s],starts,spans,reached,queue,tail);
            if(z+1<depth)tail=offer(c+width,spans.lo[s],spans.hi[s],starts,spans,reached,queue,tail);
        }
        BitSet connected=new BitSet(count);int visited=0,unproven=0;
        for(int s=reached.nextSetBit(0);s>=0;s=reached.nextSetBit(s+1)) {
            int base=spans.column[s]*height;connected.set(base+spans.lo[s],base+spans.hi[s]+1);
            visited+=spans.hi[s]-spans.lo[s]+1;
        }
        for(int i=0;i<count;i++)if(cells[i]==AIR&&!connected.get(i))unproven++;
        return new Proof(connected,visited,spans.size,unproven);
    }

    private static int offer(int c,int lo,int hi,int[] starts,Spans spans,BitSet seen,int[] queue,int tail) {
        int a=starts[c],b=starts[c+1];
        while(a<b) {int m=(a+b)>>>1;if(spans.hi[m]<lo)a=m+1;else b=m;}
        for(int s=a;s<starts[c+1]&&spans.lo[s]<=hi;s++)if(!seen.get(s)) {seen.set(s);queue[tail++]=s;}
        return tail;
    }
    private static final class Spans {
        int size;int[] column,lo,hi;
        Spans(int capacity) {column=new int[capacity];lo=new int[capacity];hi=new int[capacity];}
        void add(int c,int low,int high) {
            if(size==column.length) {
                int capacity=Math.min(MAX_CELLS,Math.max(size+1,size+size/2));
                column=Arrays.copyOf(column,capacity);lo=Arrays.copyOf(lo,capacity);hi=Arrays.copyOf(hi,capacity);
            }
            column[size]=c;lo[size]=low;hi[size]=high;size++;
        }
    }
}
