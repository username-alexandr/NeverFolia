package net.minecraft.world.level.chunk;

import java.util.BitSet;

/**
 * R39.26 bounded ocean/cave classifier.
 *
 * The solver intentionally knows nothing about blocks above the sea plane.
 * AIR/WATER on the top plane (Y=128 in the adapter) is the only vertical
 * exterior seed. Therefore an island branch, roof or structure at Y>128
 * cannot turn an ocean volume below it into a dry cave.
 *
 * Unknown neighbour space is never a seed. Protected structure cells and
 * lava are barriers. Only AIR cells proven connected to the bounded ocean
 * exterior are returned as flood targets; closed cave components stay dry.
 */
public final class OceanConnectivityR3926 {
    public static final byte UNKNOWN=0, SOLID=1, PROTECTED=2, AIR=3, WATER=4, LAVA=5;
    private OceanConnectivityR3926() {}

    public record Proof(BitSet connected, int visited, int unprovenAir) {}

    public static Proof solve(int width, int depth, int height, byte[] cells) {
        int area=Math.multiplyExact(width,depth), count=Math.multiplyExact(area,height);
        if(width<1 || depth<1 || height<1 || count>2_000_000 || cells.length!=count)
            throw new IllegalArgumentException("Invalid bounded ocean volume");

        BitSet blocked=new BitSet(count);
        for(int i=0;i<count;i++) {
            if(cells[i]<UNKNOWN || cells[i]>LAVA)throw new IllegalArgumentException("Unknown cell code");
            if(cells[i]!=LAVA)continue;
            blocked.set(i);
            int x=i%width,z=(i/width)%depth;
            if(x>0)blocked.set(i-1);
            if(x+1<width)blocked.set(i+1);
            if(z>0)blocked.set(i-width);
            if(z+1<depth)blocked.set(i+width);
            if(i>=area)blocked.set(i-area);
            if(i+area<count)blocked.set(i+area);
        }

        BitSet connected=new BitSet(count);
        int[] queue=new int[count];
        int head=0,tail=0;
        int top=(height-1)*area;

        // Critical R39.26 rule: seed the sea plane itself. No heightmap and no
        // scan of Y>128 is permitted here or in the production adapter.
        for(int p=0;p<area;p++) {
            int i=top+p;
            if(cells[i]==AIR || cells[i]==WATER)
                tail=offer(i,cells,blocked,connected,queue,tail);
        }

        while(head<tail) {
            int i=queue[head++],x=i%width,z=(i/width)%depth;
            if(x>0)tail=offer(i-1,cells,blocked,connected,queue,tail);
            if(x+1<width)tail=offer(i+1,cells,blocked,connected,queue,tail);
            if(z>0)tail=offer(i-width,cells,blocked,connected,queue,tail);
            if(z+1<depth)tail=offer(i+width,cells,blocked,connected,queue,tail);
            if(i>=area)tail=offer(i-area,cells,blocked,connected,queue,tail);
            if(i+area<count)tail=offer(i+area,cells,blocked,connected,queue,tail);
        }

        int unproven=0;
        for(int i=0;i<count;i++)if(cells[i]==AIR&&!connected.get(i))unproven++;
        return new Proof(connected,tail,unproven);
    }

    private static int offer(int i,byte[] cells,BitSet blocked,BitSet connected,int[] queue,int tail) {
        if(connected.get(i)||blocked.get(i)||(cells[i]!=AIR&&cells[i]!=WATER))return tail;
        connected.set(i);
        queue[tail++]=i;
        return tail;
    }
}
