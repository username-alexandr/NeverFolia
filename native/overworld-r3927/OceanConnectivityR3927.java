package net.minecraft.world.level.chunk;

import java.util.BitSet;

/**
 * R39.27 hybrid ocean/cave classifier.
 *
 * Exact cave evidence comes from vanilla CarvingMask / CAVE_AIR in the adapter.
 * First, every AIR/CAVE cell physically connected to the sea plane is flooded.
 * Then only residual components with NO cave provenance may be inferred as an
 * ocean void. That inference is deliberately restricted to large shallow
 * components; deep or small unknown cavities remain dry.
 */
public final class OceanConnectivityR3927 {
    public static final byte UNKNOWN=0,SOLID=1,PROTECTED=2,AIR=3,WATER=4,LAVA=5,CAVE=6;
    private static final int SHALLOW_BAND=48;
    private static final int MIN_VOID_VOLUME=32;
    private static final int MIN_FOOTPRINT=8;
    private OceanConnectivityR3927(){}

    public record Proof(BitSet flood,int oceanConnected,int inferredOcean,int dryCave,int unresolvedAir){}

    public static Proof solve(int width,int depth,int height,byte[] cells){
        int area=Math.multiplyExact(width,depth),count=Math.multiplyExact(area,height);
        if(width<1||depth<1||height<1||count>2_000_000||cells.length!=count)
            throw new IllegalArgumentException("Invalid bounded ocean volume");

        BitSet blocked=new BitSet(count);
        for(int i=0;i<count;i++){
            if(cells[i]<UNKNOWN||cells[i]>CAVE)throw new IllegalArgumentException("Unknown cell code");
            if(cells[i]!=LAVA)continue;
            blocked.set(i);
            int x=i%width,z=(i/width)%depth;
            if(x>0)blocked.set(i-1);if(x+1<width)blocked.set(i+1);
            if(z>0)blocked.set(i-width);if(z+1<depth)blocked.set(i+width);
            if(i>=area)blocked.set(i-area);if(i+area<count)blocked.set(i+area);
        }

        BitSet flood=new BitSet(count),seen=new BitSet(count);
        int[] queue=new int[count];
        int head=0,tail=0,top=(height-1)*area;
        for(int p=0;p<area;p++){
            int i=top+p;
            if(passable(cells[i]))tail=offer(i,cells,blocked,flood,queue,tail);
        }
        while(head<tail){
            int i=queue[head++],x=i%width,z=(i/width)%depth;
            if(x>0)tail=offer(i-1,cells,blocked,flood,queue,tail);
            if(x+1<width)tail=offer(i+1,cells,blocked,flood,queue,tail);
            if(z>0)tail=offer(i-width,cells,blocked,flood,queue,tail);
            if(z+1<depth)tail=offer(i+width,cells,blocked,flood,queue,tail);
            if(i>=area)tail=offer(i-area,cells,blocked,flood,queue,tail);
            if(i+area<count)tail=offer(i+area,cells,blocked,flood,queue,tail);
        }
        int oceanConnected=0;
        for(int i=flood.nextSetBit(0);i>=0;i=flood.nextSetBit(i+1))
            if(cells[i]==AIR||cells[i]==CAVE)oceanConnected++;

        int inferred=0,dryCave=0,unresolved=0;
        int[] component=new int[count];
        BitSet footprint=new BitSet(area);
        for(int seed=0;seed<count;seed++){
            if(flood.get(seed)||seen.get(seed)||(cells[seed]!=AIR&&cells[seed]!=CAVE))continue;
            int ch=0,ct=0,maxLayer=-1;boolean cave=false;
            footprint.clear();seen.set(seed);component[ct++]=seed;
            while(ch<ct){
                int i=component[ch++],x=i%width,z=(i/width)%depth,layer=i/area;
                cave|=cells[i]==CAVE;maxLayer=Math.max(maxLayer,layer);footprint.set(z*width+x);
                if(x>0)ct=componentOffer(i-1,cells,blocked,flood,seen,component,ct);
                if(x+1<width)ct=componentOffer(i+1,cells,blocked,flood,seen,component,ct);
                if(z>0)ct=componentOffer(i-width,cells,blocked,flood,seen,component,ct);
                if(z+1<depth)ct=componentOffer(i+width,cells,blocked,flood,seen,component,ct);
                if(i>=area)ct=componentOffer(i-area,cells,blocked,flood,seen,component,ct);
                if(i+area<count)ct=componentOffer(i+area,cells,blocked,flood,seen,component,ct);
            }
            boolean shallow=maxLayer>=Math.max(0,height-1-SHALLOW_BAND);
            boolean oceanVoid=!cave&&shallow&&ct>=MIN_VOID_VOLUME&&footprint.cardinality()>=MIN_FOOTPRINT;
            if(oceanVoid){
                for(int n=0;n<ct;n++)if(cells[component[n]]==AIR){flood.set(component[n]);inferred++;}
            }else if(cave){
                for(int n=0;n<ct;n++)if(cells[component[n]]==AIR||cells[component[n]]==CAVE)dryCave++;
            }else{
                for(int n=0;n<ct;n++)if(cells[component[n]]==AIR)unresolved++;
            }
        }
        return new Proof(flood,oceanConnected,inferred,dryCave,unresolved);
    }

    private static boolean passable(byte c){return c==AIR||c==CAVE||c==WATER;}
    private static int offer(int i,byte[] cells,BitSet blocked,BitSet flood,int[] q,int tail){
        if(flood.get(i)||blocked.get(i)||!passable(cells[i]))return tail;
        flood.set(i);q[tail++]=i;return tail;
    }
    private static int componentOffer(int i,byte[] cells,BitSet blocked,BitSet flood,BitSet seen,int[] q,int tail){
        if(seen.get(i)||flood.get(i)||blocked.get(i)||(cells[i]!=AIR&&cells[i]!=CAVE))return tail;
        seen.set(i);q[tail++]=i;return tail;
    }
}
